"""Latency benchmark for the chat hot path. Runs without Ollama.

Model calls are faked with fixed delays so the numbers isolate tanAI's own
overhead and scheduling, not model speed:

- embedding call: EMBED_MS per request
- web search + page fetch: WEB_MS
- summarization LLM call: SUMMARY_MS
- chat stream: first token immediately

Reports:
1. RAG search latency over a large chunk index (real SQLite, real numpy).
2. Time to first token for a long chat with memory, web and RAG all on.
3. How much of each prompt matches the previous turn's prompt from the start,
   which is the part Ollama can reuse from its KV cache instead of re-processing.

Usage: cd backend && .venv/bin/python bench/bench_latency.py
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="tanai-bench-")
os.environ["LOCALMIND_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/bench.db"
os.environ["LOCALMIND_DOCUMENTS_DIR"] = os.path.join(_TMP, "docs")
os.environ["LOCALMIND_IMAGES_DIR"] = os.path.join(_TMP, "images")
os.environ["LOCALMIND_AGENT_WORKSPACE_DIR"] = os.path.join(_TMP, "agent")
os.environ["LOCALMIND_PLUGINS_DIR"] = os.path.join(_TMP, "plugins")
os.environ["LOCALMIND_WARM_UP"] = "false"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections.abc import AsyncIterator  # noqa: E402
from dataclasses import dataclass  # noqa: E402

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Chunk, Document, Memory  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import ChatMessage, LLMProvider, ProviderModel  # noqa: E402
from app.rag import RagService  # noqa: E402
from app.rag.embeddings import EmbeddingProvider  # noqa: E402
from app.rag.retriever import pack_vector  # noqa: E402
from app.repositories import ChunkRepository  # noqa: E402

DIM = 768  # nomic-embed-text
DOCS = 40
CHUNKS_PER_DOC = 250  # 10k chunks, roughly 40 long PDFs
MEMORIES = 200
EMBED_MS = 25
WEB_MS = 400
SUMMARY_MS = 1500
HISTORY_TURNS = 30
TURNS = 10

_rng = np.random.default_rng(0)
_WORDS = [f"w{i}" for i in range(4000)]


def _text(n: int = 120) -> str:
    return " ".join(_rng.choice(_WORDS, n))


def _vec() -> list[float]:
    return _rng.standard_normal(DIM).astype(np.float32).tolist()


class SlowEmbeddings(EmbeddingProvider):
    name = "fake"
    model = "bench"
    calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        SlowEmbeddings.calls += 1
        await asyncio.sleep(EMBED_MS / 1000)
        return [_vec() for _ in texts]

    async def health(self) -> bool:
        return True


class BenchProvider(LLMProvider):
    name = "ollama"
    prompts: list[list[ChatMessage]] = []

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="bench-model")]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        first = messages[0].content if messages else ""
        if first.startswith("You maintain a running summary"):
            await asyncio.sleep(SUMMARY_MS / 1000)
            yield "Summary of the chat so far."
            return
        if first.startswith("Extract durable facts"):
            yield "[]"
            return
        BenchProvider.prompts.append(list(messages))
        for tok in ["Sure", ", ", "here ", "you ", "go."]:
            yield tok

    async def health(self) -> bool:
        return True


@dataclass
class _Result:
    title: str
    url: str
    snippet: str


async def _fake_search(query, settings):
    await asyncio.sleep(WEB_MS / 1000)
    return [_Result(f"r{i}", f"https://example.com/{i}", "snippet") for i in range(3)]


async def _fake_fetch(url):
    return "page text " * 50


async def _seed() -> tuple[str, list[str]]:
    async with SessionLocal() as session:
        doc_ids = []
        for d in range(DOCS):
            doc = Document(
                filename=f"doc{d}.pdf",
                content_type="application/pdf",
                size_bytes=1,
                status="ready",
                num_chunks=CHUNKS_PER_DOC,
            )
            session.add(doc)
            await session.flush()
            doc_ids.append(doc.id)
            for c in range(CHUNKS_PER_DOC):
                blob, dim = pack_vector(_vec())
                session.add(
                    Chunk(
                        document_id=doc.id,
                        ordinal=c,
                        content=_text(),
                        embedding=blob,
                        dim=dim,
                    )
                )
        for _ in range(MEMORIES):
            blob, dim = pack_vector(_vec())
            session.add(Memory(content=_text(12), embedding=blob, dim=dim))
        await session.commit()
    return doc_ids[0], doc_ids


def bench_rag(doc_ids: list[str]) -> float:
    async def run() -> list[float]:
        times = []
        emb = SlowEmbeddings()
        for i in range(15):
            async with SessionLocal() as session:
                rag = RagService(ChunkRepository(session), emb)
                t0 = time.perf_counter()
                await rag.search(f"query {i} w1 w2 w3", 5, doc_ids)
                times.append((time.perf_counter() - t0) * 1000 - EMBED_MS)
        return times[1:]  # drop the first (cold) query

    return statistics.median(asyncio.run(run()))


def _prefix_reuse(prev: list[ChatMessage], cur: list[ChatMessage]) -> tuple[int, int]:
    """(chars shared with the previous prompt from the start, total chars)."""

    same = 0
    for x, y in zip(prev, cur):
        if (x.role, x.content) != (y.role, y.content):
            break
        same += len(y.content)
    return same, sum(len(m.content) for m in cur)


def bench_turns(client: TestClient) -> tuple[float, float]:
    conv = client.post("/api/conversations", json={"model": "bench-model"}).json()
    # Attach every document to this chat so RAG searches the full index.
    asyncio.run(_attach_all(conv["id"]))
    # Build a long history the slow way would have to summarize.
    asyncio.run(_seed_history(conv["id"]))

    ttfts = []
    BenchProvider.prompts.clear()
    for i in range(TURNS):
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            t0 = time.perf_counter()
            ws.send_json(
                {
                    "content": f"Follow-up question {i} about w1 w2 and w3",
                    "model": "bench-model",
                    "use_rag": True,
                    "use_web": True,
                    "use_memory": True,
                }
            )
            first = None
            while True:
                ev = ws.receive_json()
                if ev["type"] == "token" and first is None:
                    first = time.perf_counter()
                if ev["type"] == "error":
                    raise RuntimeError(ev["detail"])
                if ev["type"] == "done":
                    break
            ttfts.append((first - t0) * 1000)
        time.sleep(0.3)  # let post-reply work settle, like a user reading
    reuse = [
        _prefix_reuse(a, b)
        for a, b in zip(BenchProvider.prompts, BenchProvider.prompts[1:])
    ]
    share = sum(r[0] for r in reuse) / sum(r[1] for r in reuse)
    fresh = statistics.mean(r[1] - r[0] for r in reuse) / 4  # ~4 chars per token
    print("per-turn ttft ms:", [round(t) for t in ttfts])
    return statistics.mean(ttfts[1:]), share, fresh


async def _attach_all(conversation_id: str) -> None:
    from sqlalchemy import update

    async with SessionLocal() as session:
        await session.execute(update(Document).values(conversation_id=conversation_id))
        await session.commit()


async def _seed_history(conversation_id: str) -> None:
    from app.repositories import MessageRepository

    async with SessionLocal() as session:
        repo = MessageRepository(session)
        for i in range(HISTORY_TURNS):
            await repo.add(conversation_id, "user", f"Question {i}: " + _text(60))
            await repo.add(conversation_id, "assistant", f"Answer {i}: " + _text(120))


def main_() -> None:
    settings = get_settings()
    settings.web_search_enabled = True
    main.web_search = _fake_search
    main.fetch_url_text = _fake_fetch

    with TestClient(main.app) as client:
        registry = build_default_registry(settings)
        registry._providers["ollama"] = BenchProvider()
        main.app.state.registry = registry
        main.app.state.embeddings = SlowEmbeddings()
        try:  # wrap like the app's lifespan does, on versions that have it
            from app.rag.embeddings import CachedEmbeddings

            main.app.state.embeddings = CachedEmbeddings(SlowEmbeddings())
        except ImportError:
            pass

        _, doc_ids = asyncio.run(_seed())
        rag_ms = bench_rag(doc_ids)
        SlowEmbeddings.calls = 0
        ttft_ms, share, fresh = bench_turns(client)
        embed_calls = SlowEmbeddings.calls / TURNS

    print(f"chunks indexed:               {DOCS * CHUNKS_PER_DOC}")
    print(f"RAG search (excl. embed):     {rag_ms:8.1f} ms  (median)")
    print(f"time to first token:          {ttft_ms:8.1f} ms  (mean)")
    print(f"embedding calls per turn:     {embed_calls:8.1f}")
    print(f"prompt reusable from KV cache:{share * 100:8.1f} %")
    print(f"prompt tokens to prefill/turn:{fresh:8.0f}")
    print(f"simulated: embed {EMBED_MS} ms, web {WEB_MS} ms, summary {SUMMARY_MS} ms")


if __name__ == "__main__":
    main_()
