"""Ollama provider — local Ollama over its REST API (newline-delimited JSON stream)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import httpx

from .base import ChatMessage, ChatResult, LLMProvider, ProviderModel, ToolCall


def _strip_data_url(image: str) -> str:
    """Return bare base64 from a data URL, or the string unchanged."""

    if image.startswith("data:") and "," in image:
        return image.split(",", 1)[1]
    return image


class OllamaProvider(LLMProvider):
    name = "ollama"
    label = "Ollama (local)"
    kind = "ollama"

    def __init__(
        self,
        base_url: str,
        timeout: float = 300.0,
        num_ctx: int = 8192,
        keep_alive: str = "30m",
        num_predict: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._num_ctx = num_ctx
        self._keep_alive = keep_alive
        self._num_predict = num_predict
        # trust_env=False: don't route localhost through system HTTP/SOCKS proxies.
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, trust_env=False
        )

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[ProviderModel]:
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        payload = resp.json()
        return [
            ProviderModel(
                name=item.get("name", ""),
                size=item.get("size"),
                modified_at=item.get("modified_at"),
            )
            for item in payload.get("models", [])
            if item.get("name")
        ]

    def _options(self) -> dict:
        opts: dict = {"num_ctx": self._num_ctx}
        if self._num_predict:
            opts["num_predict"] = self._num_predict
        return opts

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        body = {
            "model": model,
            "messages": [self._serialize(m) for m in messages],
            "stream": True,
            # num_ctx: Ollama silently caps context at 2048 tokens without it.
            "options": self._options(),
            "keep_alive": self._keep_alive,
        }
        async with self._client.stream("POST", "/api/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise RuntimeError(str(chunk["error"]))
                token = (chunk.get("message") or {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break

    @staticmethod
    def _serialize(message: ChatMessage) -> dict:
        if message.tool_name:  # a tool result
            return {
                "role": "tool",
                "name": message.tool_name,
                "content": message.content,
            }
        payload: dict = {"role": message.role, "content": message.content}
        if message.tool_calls:
            payload["tool_calls"] = [
                {"function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in message.tool_calls
            ]
        if message.images:
            # Ollama expects bare base64 (no data-URL prefix).
            payload["images"] = [_strip_data_url(img) for img in message.images]
        return payload

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
    ) -> ChatResult:
        body: dict = {
            "model": model,
            "messages": [self._serialize(m) for m in messages],
            "stream": False,
            "options": self._options(),
            "keep_alive": self._keep_alive,
        }
        if tools:
            body["tools"] = tools
        resp = await self._client.post("/api/chat", json=body)
        resp.raise_for_status()
        message = resp.json().get("message") or {}
        calls: list[ToolCall] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(
                ToolCall(id=str(uuid.uuid4()), name=fn.get("name", ""), arguments=args)
            )
        return ChatResult(content=message.get("content", "") or "", tool_calls=calls)

    async def pull(self, name: str) -> AsyncIterator[str]:
        """Stream Ollama's newline-delimited JSON pull progress for a model."""

        async with self._client.stream(
            "POST",
            "/api/pull",
            json={"model": name},
            timeout=httpx.Timeout(None),  # model pulls can take a long time
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    yield line

    async def delete_model(self, name: str) -> bool:
        resp = await self._client.request("DELETE", "/api/delete", json={"model": name})
        return resp.status_code == 200

    async def aclose(self) -> None:
        await self._client.aclose()
