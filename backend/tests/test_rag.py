"""RAG smoke tests.

Exercises the full retrieval pipeline — upload, parse, chunk, embed, index,
search, and grounded chat — using a deterministic hashing embedder and a fake
LLM. Runs without Ollama.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_rag_test.db",
)
os.environ.setdefault(
    "LOCALMIND_DOCUMENTS_DIR",
    os.path.join(tempfile.gettempdir(), "localmind_rag_docs"),
)

from collections.abc import AsyncIterator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import ChatMessage, LLMProvider, ProviderModel  # noqa: E402
from app.rag.embeddings import EmbeddingProvider  # noqa: E402
from app.config import get_settings  # noqa: E402

_DIM = 64


class HashEmbeddings(EmbeddingProvider):
    """Deterministic bag-of-hashed-words embedder: shared words -> similarity."""

    name = "fake"
    model = "hash-test"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * _DIM
            for token in text.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vec[h % _DIM] += 1.0
            vectors.append(vec)
        return vectors

    async def health(self) -> bool:
        return True


class GroundProbeProvider(LLMProvider):
    """Fake LLM that reveals whether a system (RAG) prime was injected."""

    name = "ollama"

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="fake-model")]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        grounded = any(m.role == "system" for m in messages)
        yield "GROUNDED" if grounded else "PLAIN"

    async def health(self) -> bool:
        return True


def _install_fakes() -> None:
    registry = build_default_registry(get_settings())
    registry._providers["ollama"] = GroundProbeProvider()
    app.state.registry = registry
    app.state.embeddings = HashEmbeddings()


def test_rag_flow() -> None:
    with TestClient(app) as client:
        _install_fakes()

        # --- Upload & index a document ---
        doc_text = (
            "Photosynthesis is the process by which plants convert sunlight "
            "into chemical energy stored as glucose.\n\n"
            "The mitochondrion is the powerhouse of the cell and produces ATP "
            "through cellular respiration.\n\n"
            "The Great Barrier Reef is the world's largest coral reef system "
            "located off the coast of Australia."
        )
        files = {"file": ("biology.txt", doc_text, "text/plain")}
        doc = client.post("/api/documents", files=files).json()
        assert doc["status"] == "ready", doc
        assert doc["num_chunks"] >= 1

        # --- Health reflects the index ---
        health = client.get("/api/health").json()
        assert health["embedding_online"] is True
        assert health["indexed_chunks"] >= 1

        # --- Semantic-ish search returns the right passage ---
        results = client.post(
            "/api/search", json={"query": "how do plants make energy", "top_k": 3}
        ).json()["results"]
        assert results, "expected at least one search result"
        assert "photosynthesis" in results[0]["snippet"].lower()
        assert results[0]["filename"] == "biology.txt"

        # --- Grounded chat: sources event + system prime injected ---
        conv = client.post("/api/conversations", json={}).json()
        tokens: list[str] = []
        sources = None
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            ws.send_json(
                {"content": "Tell me about photosynthesis", "use_rag": True}
            )
            while True:
                event = ws.receive_json()
                if event["type"] == "sources":
                    sources = event["data"]
                elif event["type"] == "token":
                    tokens.append(event["data"])
                elif event["type"] == "done":
                    break
                elif event["type"] == "error":
                    raise AssertionError(event["detail"])
        assert sources, "expected sources event"
        assert "".join(tokens) == "GROUNDED", "system prime was not injected"

        # --- Delete cleans up ---
        assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
        assert client.get("/api/health").json()["indexed_chunks"] == 0

    print("RAG SMOKE OK")


def _run_turn(client, conv_id: str) -> list:
    """Send one RAG turn and return the sources event data (or [])."""
    sources: list = []
    with client.websocket_connect(f"/ws/chat/{conv_id}") as ws:
        ws.send_json({"content": "photosynthesis", "use_rag": True})
        while True:
            ev = ws.receive_json()
            if ev["type"] == "sources":
                sources = ev["data"]
            elif ev["type"] == "done":
                break
            elif ev["type"] == "error":
                raise AssertionError(ev["detail"])
    return sources


def test_document_scoping() -> None:
    with TestClient(app) as client:
        _install_fakes()

        conv_a = client.post("/api/conversations", json={}).json()["id"]
        conv_b = client.post("/api/conversations", json={}).json()["id"]

        # Upload a document scoped to conversation A only.
        files = {"file": ("scoped.txt", "Photosynthesis converts sunlight.", "text/plain")}
        doc = client.post(
            "/api/documents", files=files, data={"conversation_id": conv_a}
        ).json()
        assert doc["conversation_id"] == conv_a
        assert doc["status"] == "ready"

        # A sees it; B does not.
        assert _run_turn(client, conv_a), "chat A should retrieve its own doc"
        assert _run_turn(client, conv_b) == [], "chat B must not see A's doc"

        # Promote to global memory -> now B sees it too.
        client.post(f"/api/documents/{doc['id']}/memory")
        assert _run_turn(client, conv_b), "after promotion B should see the doc"

    print("DOC SCOPING OK")


if __name__ == "__main__":
    test_rag_flow()
    test_document_scoping()
