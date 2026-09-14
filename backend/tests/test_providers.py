"""Provider subsystem tests.

1. SSE parsing of the OpenAI-compatible provider (via a mock transport).
2. Provider CRUD + aggregated models + chat routed to a chosen provider,
   using a fake provider factory so no real network endpoint is required.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_prov_test.db",
)

from collections.abc import AsyncIterator  # noqa: E402

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import ChatMessage, LLMProvider, ProviderModel  # noqa: E402
from app.providers.openai_provider import OpenAICompatibleProvider  # noqa: E402
from app.rag.embeddings import EmbeddingProvider  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. SSE parsing unit test
# --------------------------------------------------------------------------- #
def test_openai_sse_parsing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-test"}]})
        # Chat completions: emit two token chunks then [DONE].
        body = (
            'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body.encode())

    async def run() -> None:
        provider = OpenAICompatibleProvider("t", "http://mock/v1", label="T")
        # Swap the internal client for one backed by the mock transport.
        await provider._client.aclose()
        provider._client = httpx.AsyncClient(
            base_url="http://mock/v1", transport=httpx.MockTransport(handler)
        )
        models = await provider.list_models()
        assert models[0].name == "gpt-test"
        tokens = [
            t
            async for t in provider.stream_chat("gpt-test", [ChatMessage("user", "hi")])
        ]
        assert "".join(tokens) == "Hello world"
        await provider.aclose()

    asyncio.run(run())
    print("OPENAI SSE OK")


# --------------------------------------------------------------------------- #
# 2. Provider CRUD + routing
# --------------------------------------------------------------------------- #
_DIM = 8


class FakeEmbeddings(EmbeddingProvider):
    name = "fake"
    model = "hash-test"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] * _DIM for _ in texts]

    async def health(self) -> bool:
        return True


class OllamaFake(LLMProvider):
    name = "ollama"
    label = "Ollama (local)"
    kind = "ollama"

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="llama3.2")]

    async def stream_chat(self, model, messages) -> AsyncIterator[str]:
        yield "FROM-OLLAMA"

    async def health(self) -> bool:
        return True


class OpenAIFake(LLMProvider):
    kind = "openai"

    def __init__(self, name: str, label: str) -> None:
        self.name = name
        self.label = label

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="gpt-fake")]

    async def stream_chat(self, model, messages) -> AsyncIterator[str]:
        yield "FROM-OPENAI"

    async def health(self) -> bool:
        return True


def test_provider_crud_and_routing(monkeypatch) -> None:
    with TestClient(app) as client:
        registry = build_default_registry(get_settings())
        registry._providers["ollama"] = OllamaFake()
        app.state.registry = registry
        app.state.embeddings = FakeEmbeddings()

        # Patch the factory so adding a provider needs no real endpoint.
        monkeypatch.setattr(
            main,
            "make_openai_provider",
            lambda name, base_url, api_key, label, timeout: OpenAIFake(name, label),
        )

        # Health reports hardware.
        assert client.get("/api/health").json()["hardware"]

        # Add an OpenAI-compatible provider.
        created = client.post(
            "/api/providers",
            json={"label": "My Cloud", "base_url": "http://cloud/v1", "api_key": "k"},
        ).json()
        assert created["name"] == "my-cloud"
        assert created["online"] is True

        # It is listed and removable; ollama is not removable.
        providers = {p["name"]: p for p in client.get("/api/providers").json()}
        assert providers["ollama"]["removable"] is False
        assert providers["my-cloud"]["removable"] is True
        assert providers["my-cloud"]["has_api_key"] is True

        # Aggregated models include both providers with labels.
        models = client.get("/api/models").json()
        by_provider = {m["provider"]: m for m in models}
        assert by_provider["ollama"]["name"] == "llama3.2"
        assert by_provider["my-cloud"]["name"] == "gpt-fake"
        assert by_provider["my-cloud"]["provider_label"] == "My Cloud"

        # Chat routed explicitly to the new provider.
        conv = client.post("/api/conversations", json={}).json()
        tokens: list[str] = []
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            ws.send_json({"content": "hi", "provider": "my-cloud", "model": "gpt-fake"})
            while True:
                ev = ws.receive_json()
                if ev["type"] == "token":
                    tokens.append(ev["data"])
                elif ev["type"] == "done":
                    break
                elif ev["type"] == "error":
                    raise AssertionError(ev["detail"])
        assert "".join(tokens) == "FROM-OPENAI"

        # Remove it; persists across the registry too.
        assert client.delete("/api/providers/my-cloud").status_code == 204
        remaining = {p["name"] for p in client.get("/api/providers").json()}
        assert "my-cloud" not in remaining

    print("PROVIDER CRUD OK")


if __name__ == "__main__":
    test_openai_sse_parsing()

    # Minimal monkeypatch shim so the file runs without pytest.
    class _MP:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    test_provider_crud_and_routing(_MP())
