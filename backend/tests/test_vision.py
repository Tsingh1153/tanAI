"""Vision (image input) smoke test.

Sends an image over the chat WebSocket to a fake provider that reports whether
it received image data, and verifies the image is persisted and re-served.
"""

from __future__ import annotations

import os
import tempfile

_IMG_DIR = tempfile.mkdtemp(prefix="localmind_img_")
os.environ.setdefault("LOCALMIND_IMAGES_DIR", _IMG_DIR)
os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_vision_test.db",
)

from collections.abc import AsyncIterator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import ChatMessage, LLMProvider, ProviderModel  # noqa: E402
from app.rag.embeddings import EmbeddingProvider  # noqa: E402

# 1x1 transparent PNG.
_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA"
    "60e6kgAAAABJRU5ErkJggg=="
)


class VisionProbe(LLMProvider):
    name = "ollama"

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="vision")]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        saw = any(m.images for m in messages)
        yield "SAW-IMAGE" if saw else "NO-IMAGE"

    async def health(self) -> bool:
        return True


class FakeEmbeddings(EmbeddingProvider):
    name = "fake"
    model = "hash"

    async def embed(self, texts):
        return [[0.0] * 4 for _ in texts]

    async def health(self):
        return True


def test_vision_flow() -> None:
    with TestClient(app) as client:
        registry = build_default_registry(get_settings())
        registry._providers["ollama"] = VisionProbe()
        app.state.registry = registry
        app.state.embeddings = FakeEmbeddings()

        conv = client.post("/api/conversations", json={}).json()
        tokens: list[str] = []
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            # Use a vision-named model so images are sent directly (not routed
            # through the vision-assist describe path, which fusion tests cover).
            ws.send_json(
                {
                    "content": "what is this?",
                    "images": [_PNG],
                    "model": "vision",
                    "use_memory": False,
                }
            )
            while True:
                ev = ws.receive_json()
                if ev["type"] == "token":
                    tokens.append(ev["data"])
                elif ev["type"] == "done":
                    break
                elif ev["type"] == "error":
                    raise AssertionError(ev["detail"])
        assert "".join(tokens) == "SAW-IMAGE", "image was not passed to the model"

        # Persisted + exposed as a served URL.
        full = client.get(f"/api/conversations/{conv['id']}").json()
        user_msg = full["messages"][0]
        assert len(user_msg["images"]) == 1
        url = user_msg["images"][0]
        assert url.startswith("/images/")
        # The file is served back.
        assert client.get(url).status_code == 200

    print("VISION OK")


if __name__ == "__main__":
    test_vision_flow()
