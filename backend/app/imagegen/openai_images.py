"""OpenAI-compatible images backend (/v1/images/generations), base64 output."""

from __future__ import annotations

import base64

import httpx

from .base import ImageGenerator, ImageGenError


class OpenAIImagesGenerator(ImageGenerator):
    name = "openai"

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str | None,
        timeout: float = 300.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._model = model or "dall-e-3"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self._base, timeout=timeout, headers=headers, trust_env=False
        )

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def generate(self, prompt: str, size: int, steps: int, n: int) -> list[bytes]:
        body = {
            "model": self._model,
            "prompt": prompt,
            "n": n,
            "size": f"{size}x{size}",
            "response_format": "b64_json",
        }
        try:
            resp = await self._client.post("/images/generations", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ImageGenError(f"Image generation failed: {exc}") from exc

        data = resp.json().get("data", [])
        if not data:
            raise ImageGenError("The image API returned no images.")
        return [
            base64.b64decode(item["b64_json"]) for item in data if item.get("b64_json")
        ]

    async def aclose(self) -> None:
        await self._client.aclose()
