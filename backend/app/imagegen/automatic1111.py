"""AUTOMATIC1111-compatible Stable Diffusion backend.

Talks to the ``/sdapi/v1/txt2img`` endpoint exposed by AUTOMATIC1111's WebUI
(run with ``--api``) and API-compatible forks (SD.Next, Forge). Returns base64
PNGs which we decode to bytes.
"""

from __future__ import annotations

import base64

import httpx

from .base import ImageGenerator, ImageGenError


class Automatic1111Generator(ImageGenerator):
    name = "automatic1111"

    def __init__(self, server_url: str, timeout: float = 300.0) -> None:
        self._base = server_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base, timeout=timeout, trust_env=False
        )

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/sdapi/v1/sd-models")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def generate(
        self, prompt: str, size: int, steps: int, n: int
    ) -> list[bytes]:
        body = {
            "prompt": prompt,
            "steps": steps,
            "width": size,
            "height": size,
            "batch_size": n,
        }
        try:
            resp = await self._client.post("/sdapi/v1/txt2img", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ImageGenError(
                f"Stable Diffusion server not reachable at {self._base} "
                f"(run AUTOMATIC1111 with --api). Details: {exc}"
            ) from exc

        images = resp.json().get("images", [])
        if not images:
            raise ImageGenError("The image server returned no images.")
        out: list[bytes] = []
        for img in images:
            # A1111 may prefix with a data URL header; strip it if present.
            payload = img.split(",", 1)[1] if img.startswith("data:") else img
            out.append(base64.b64decode(payload))
        return out

    async def aclose(self) -> None:
        await self._client.aclose()
