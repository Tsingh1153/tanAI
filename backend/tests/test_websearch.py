"""Web search tests: URL decoding + the use_web grounding path (with fakes)."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_web_test.db",
)

from collections.abc import AsyncIterator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import LLMProvider, ProviderModel  # noqa: E402
from app.rag.embeddings import EmbeddingProvider  # noqa: E402
from app.web.search import SearchResult, _decode_ddg_href  # noqa: E402


def test_ddg_href_decode() -> None:
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc"
    assert _decode_ddg_href(href) == "https://example.com/page"
    assert _decode_ddg_href("//x.com/a").startswith("https://")


class WebProbe(LLMProvider):
    name = "ollama"

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="m")]

    async def stream_chat(self, model, messages) -> AsyncIterator[str]:
        grounded = any(
            m.role == "system" and "WEB SEARCH" in m.content for m in messages
        )
        yield "GROUNDED" if grounded else "PLAIN"

    async def health(self) -> bool:
        return True


class FakeEmbeddings(EmbeddingProvider):
    name = "fake"
    model = "hash"

    async def embed(self, texts):
        return [[0.0] * 4 for _ in texts]

    async def health(self):
        return True


async def _fake_search(query, settings, max_results=None):
    return [SearchResult("Example", "https://example.com", "a snippet about X")]


async def _fake_fetch(url, limit=4000):
    return "full page text here"


def test_use_web_grounding() -> None:
    with TestClient(app) as client:
        registry = build_default_registry(get_settings())
        registry._providers["ollama"] = WebProbe()
        app.state.registry = registry
        app.state.embeddings = FakeEmbeddings()
        # Inject fakes so no real network is used.
        main.web_search = _fake_search
        main.fetch_url_text = _fake_fetch

        conv = client.post("/api/conversations", json={}).json()["id"]
        tokens: list[str] = []
        sources = None
        with client.websocket_connect(f"/ws/chat/{conv}") as ws:
            ws.send_json(
                {"content": "what's new today", "use_web": True, "use_memory": False}
            )
            while True:
                ev = ws.receive_json()
                if ev["type"] == "web_sources":
                    sources = ev["data"]
                elif ev["type"] == "token":
                    tokens.append(ev["data"])
                elif ev["type"] == "done":
                    break
                elif ev["type"] == "error":
                    raise AssertionError(ev["detail"])
        assert sources and sources[0]["url"] == "https://example.com"
        assert "".join(tokens) == "GROUNDED"

    print("WEB SEARCH OK")


if __name__ == "__main__":
    test_ddg_href_decode()
    test_use_web_grounding()
