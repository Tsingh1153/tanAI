"""Tests for vision+text fusion (vision-assist) and the model pull endpoint."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("LOCALMIND_IMAGES_DIR", tempfile.mkdtemp(prefix="lm_fus_"))
os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_fusion_test.db",
)

from collections.abc import AsyncIterator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import LLMProvider, ProviderModel  # noqa: E402
from app.rag.embeddings import EmbeddingProvider  # noqa: E402

_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA"
    "60e6kgAAAABJRU5ErkJggg=="
)


class FusionProvider(LLMProvider):
    name = "ollama"

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="qwen2.5:7b"), ProviderModel(name="llava")]

    async def complete(self, model, messages) -> str:
        # The vision model returns a description; anything else falls through.
        if model == "llava":
            return "A red apple on a table."
        return await super().complete(model, messages)

    async def stream_chat(self, model, messages) -> AsyncIterator[str]:
        has_img = any(m.images for m in messages)
        has_desc = any(
            m.role == "system" and "red apple" in m.content for m in messages
        )
        yield f"img={has_img},desc={has_desc}"

    async def pull(self, name: str) -> AsyncIterator[str]:
        yield '{"status": "pulling manifest"}'
        yield '{"status": "success"}'

    async def health(self) -> bool:
        return True


class FakeEmbeddings(EmbeddingProvider):
    name = "fake"
    model = "hash"

    async def embed(self, texts):
        return [[0.0] * 4 for _ in texts]

    async def health(self):
        return True


def _install() -> None:
    registry = build_default_registry(get_settings())
    registry._providers["ollama"] = FusionProvider()
    app.state.registry = registry
    app.state.embeddings = FakeEmbeddings()


def _chat(client, conv_id: str, model: str) -> str:
    tokens: list[str] = []
    with client.websocket_connect(f"/ws/chat/{conv_id}") as ws:
        ws.send_json(
            {
                "content": "what is this?",
                "images": [_PNG],
                "model": model,
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
    return "".join(tokens)


def test_vision_assist_and_direct() -> None:
    with TestClient(app) as client:
        _install()
        conv = client.post("/api/conversations", json={}).json()["id"]

        # Text-only model + image -> routed through vision model to a description.
        out = _chat(client, conv, "qwen2.5:7b")
        assert out == "img=False,desc=True", out

        # Vision model + image -> image sent directly, no description injected.
        conv2 = client.post("/api/conversations", json={}).json()["id"]
        out2 = _chat(client, conv2, "llava")
        assert out2 == "img=True,desc=False", out2

    print("VISION FUSION OK")


def test_model_pull_stream() -> None:
    with TestClient(app) as client:
        _install()
        resp = client.get("/api/models/pull?name=llava")
        assert resp.status_code == 200
        body = resp.text
        assert "pulling manifest" in body
        assert "success" in body
        assert "done" in body

    print("MODEL PULL OK")


if __name__ == "__main__":
    test_vision_assist_and_direct()
    test_model_pull_stream()
