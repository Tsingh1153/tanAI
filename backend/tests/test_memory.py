"""Memory & context-management smoke tests.

Covers three things with fake providers (no Ollama needed):
1. Context compression — long histories roll into a summary.
2. Long-term memory recall — stored memories are injected and surfaced.
3. Automatic extraction + de-duplication of durable facts.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_mem_test.db",
)
# Tiny budget so a couple of turns trigger compression.
os.environ.setdefault("LOCALMIND_HISTORY_TOKEN_BUDGET", "20")

from collections.abc import AsyncIterator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.memory import MemoryService  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import ChatMessage, LLMProvider, ProviderModel  # noqa: E402
from app.rag.embeddings import EmbeddingProvider  # noqa: E402
from app.repositories import MemoryRepository  # noqa: E402

_DIM = 64


class HashEmbeddings(EmbeddingProvider):
    name = "fake"
    model = "hash-test"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * _DIM
            for tok in text.lower().split():
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                vec[h % _DIM] += 1.0
            out.append(vec)
        return out

    async def health(self) -> bool:
        return True


class GroundProbeProvider(LLMProvider):
    """Streams GROUNDED/PLAIN based on presence of a system message."""

    name = "ollama"

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="fake-model")]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        yield "GROUNDED" if any(m.role == "system" for m in messages) else "PLAIN"

    async def health(self) -> bool:
        return True


class JsonMemoryProvider(LLMProvider):
    """complete() returns a fixed JSON memory array for extraction tests."""

    name = "ollama"
    payload = (
        '[{"content": "The user is named Tanay", "kind": "fact", "importance": 0.8}]'
    )

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="fake-model")]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        yield self.payload

    async def health(self) -> bool:
        return True


def _install(provider: LLMProvider) -> None:
    registry = build_default_registry(get_settings())
    registry._providers["ollama"] = provider
    app.state.registry = registry
    app.state.embeddings = HashEmbeddings()


def test_compression_and_memory() -> None:
    # get_settings() is cached and main.py binds it at import, so the env var
    # above can be locked out by another test importing the app first. Force the
    # small budget on the live singleton so this test is order-independent.
    get_settings().history_token_budget = 20

    with TestClient(app) as client:
        _install(GroundProbeProvider())

        # --- Manual memory + recall injection ---
        mem = client.post(
            "/api/memories",
            json={"content": "The user loves hiking", "kind": "preference"},
        ).json()
        assert mem["content"] == "The user loves hiking"

        conv = client.post("/api/conversations", json={}).json()
        memory_event = None
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            ws.send_json({"content": "What are good weekend activities?"})
            while True:
                ev = ws.receive_json()
                if ev["type"] == "memory":
                    memory_event = ev["data"]
                elif ev["type"] == "done":
                    break
                elif ev["type"] == "error":
                    raise AssertionError(ev["detail"])
        assert memory_event, "expected recalled memory event"
        assert any("hiking" in m["content"] for m in memory_event)

        # --- Context compression over several turns ---
        for i in range(4):
            with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
                ws.send_json(
                    {"content": f"Message number {i} with some extra words here"}
                )
                while ws.receive_json()["type"] != "done":
                    pass
        state = client.get(f"/api/conversations/{conv['id']}").json()
        assert state["summarized_count"] > 0, "history was not compressed"
        assert state["summary"], "expected a rolling summary"

    print("MEMORY/COMPRESSION OK")


def test_extraction_and_dedup() -> None:
    async def run() -> None:
        await init_db()
        async with SessionLocal() as session:
            repo = MemoryRepository(session)
            # Start from a clean slate so the fake hash-embedder's shared-word
            # overlap can't produce a spurious duplicate hit.
            for existing in await repo.list():
                await repo.delete(existing)

            service = MemoryService(repo, HashEmbeddings(), get_settings())
            provider = JsonMemoryProvider()
            before = len(await service.list())
            created = await service.extract(
                "conv-x", "Hi, I'm Tanay", "Nice to meet you", provider, "m"
            )
            assert len(created) == 1
            assert "Tanay" in created[0].content

            # Re-running the same exchange must not create a duplicate.
            again = await service.extract(
                "conv-x", "Hi, I'm Tanay", "Nice to meet you", provider, "m"
            )
            assert again == []
            assert len(await service.list()) == before + 1

    asyncio.run(run())
    print("MEMORY EXTRACTION OK")


if __name__ == "__main__":
    test_compression_and_memory()
    test_extraction_and_dedup()
