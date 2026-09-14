"""OpenAI-compatible provider.

A single implementation of the OpenAI Chat Completions protocol unlocks a wide
range of backends that all speak it: LM Studio, vLLM, llama.cpp's server, and
hosted APIs (OpenAI, Groq, OpenRouter, Together, ...). The only differences are
the base URL and whether an API key is required, so both are constructor args.

``base_url`` should include the version path, e.g. ``http://localhost:1234/v1``
for LM Studio or ``https://api.openai.com/v1`` for OpenAI.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import httpx

from .base import ChatMessage, ChatResult, LLMProvider, ProviderModel, ToolCall


class OpenAICompatibleProvider(LLMProvider):
    kind = "openai"

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str | None = None,
        label: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.name = name
        self.label = label or name
        self._base_url = base_url.rstrip("/")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=headers,
            trust_env=False,
        )

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[ProviderModel]:
        resp = await self._client.get("/models")
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [
            ProviderModel(name=item["id"])
            for item in data
            if item.get("id")
        ]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        body = {
            "model": model,
            "messages": [self._serialize(m) for m in messages],
            "stream": True,
        }
        async with self._client.stream(
            "POST", "/chat/completions", json=body
        ) as resp:
            resp.raise_for_status()
            # Server-Sent Events: each token arrives as ``data: {json}`` lines,
            # terminated by ``data: [DONE]``.
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                token = (choices[0].get("delta") or {}).get("content")
                if token:
                    yield token

    @staticmethod
    def _serialize(message: ChatMessage) -> dict:
        if message.tool_name:  # a tool result
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id or "",
                "content": message.content,
            }
        payload: dict = {"role": message.role, "content": message.content}
        if message.images:
            # OpenAI multimodal: content becomes an array of text + image parts.
            payload["content"] = [
                {"type": "text", "text": message.content},
                *[
                    {"type": "image_url", "image_url": {"url": img}}
                    for img in message.images
                ],
            ]
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in message.tool_calls
            ]
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
        }
        if tools:
            body["tools"] = tools
        resp = await self._client.post("/chat/completions", json=body)
        resp.raise_for_status()
        choice = (resp.json().get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls: list[ToolCall] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(
                ToolCall(
                    id=tc.get("id") or str(uuid.uuid4()),
                    name=fn.get("name", ""),
                    arguments=args,
                )
            )
        return ChatResult(content=message.get("content") or "", tool_calls=calls)

    async def aclose(self) -> None:
        await self._client.aclose()
