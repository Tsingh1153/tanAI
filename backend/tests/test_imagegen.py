"""Image generation tests (no real Stable Diffusion server needed)."""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile

_IMG_DIR = tempfile.mkdtemp(prefix="localmind_gen_")
os.environ.setdefault("LOCALMIND_IMAGES_DIR", _IMG_DIR)
os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_imggen_test.db",
)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.imagegen.automatic1111 import Automatic1111Generator  # noqa: E402
from app.imagegen.base import ImageGenerator  # noqa: E402
from app.main import app  # noqa: E402

# 1x1 PNG.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA"
    "60e6kgAAAABJRU5ErkJggg=="
)
_PNG_BYTES = base64.b64decode(_PNG_B64)


def test_automatic1111_decode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sd-models"):
            return httpx.Response(200, json=[{"model_name": "x"}])
        return httpx.Response(200, json={"images": [_PNG_B64]})

    async def run() -> None:
        gen = Automatic1111Generator("http://sd")
        await gen._client.aclose()
        gen._client = httpx.AsyncClient(
            base_url="http://sd", transport=httpx.MockTransport(handler)
        )
        assert await gen.health() is True
        images = await gen.generate("a cat", 64, 5, 1)
        assert images == [_PNG_BYTES]
        await gen.aclose()

    asyncio.run(run())
    print("A1111 OK")


class FakeGenerator(ImageGenerator):
    name = "fake"

    async def generate(self, prompt, size, steps, n):
        return [_PNG_BYTES for _ in range(n)]

    async def health(self):
        return True


def test_generate_endpoint() -> None:
    with TestClient(app) as client:
        app.state.imagegen = FakeGenerator()

        resp = client.post("/api/images/generate", json={"prompt": "a robot"})
        assert resp.status_code == 200, resp.text
        urls = resp.json()["images"]
        assert len(urls) == 1 and urls[0].startswith("/images/")
        # The saved image is served back.
        assert client.get(urls[0]).status_code == 200

        # Empty prompt is rejected.
        assert client.post("/api/images/generate", json={"prompt": ""}).status_code == 400

    print("IMAGE ENDPOINT OK")


if __name__ == "__main__":
    test_automatic1111_decode()
    test_generate_endpoint()
