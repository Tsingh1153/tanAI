"""Chunk index cache: stays in sync with the chunks table; embed cache dedupes."""

from __future__ import annotations

import asyncio
import os
import tempfile

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_index_test.db",
)

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Chunk, Document  # noqa: E402
from app.rag.embeddings import CachedEmbeddings, EmbeddingProvider  # noqa: E402
from app.rag.index import chunk_index  # noqa: E402
from app.rag.retriever import pack_vector  # noqa: E402
from app.repositories import DocumentRepository  # noqa: E402


async def _add_doc(session, name: str, texts: list[str], vectors) -> Document:
    doc = Document(filename=name, content_type="text/plain", status="ready")
    session.add(doc)
    await session.flush()
    for i, (text, vec) in enumerate(zip(texts, vectors)):
        blob, dim = pack_vector(vec)
        session.add(
            Chunk(document_id=doc.id, ordinal=i, content=text, embedding=blob, dim=dim)
        )
    await session.commit()
    return doc


def test_index_tracks_inserts_deletes_and_scope() -> None:
    async def run() -> None:
        await init_db()
        async with SessionLocal() as session:
            a = await _add_doc(session, "a.txt", ["apples red"], [[1.0, 0.0]])
            chunk_index.invalidate()  # what ingestion does after writing
            hits = await chunk_index.search(session, [1.0, 0.0], "apples", 5)
            assert len(hits) == 1

            b = await _add_doc(session, "b.txt", ["bananas yellow"], [[0.0, 1.0]])
            chunk_index.invalidate()
            hits = await chunk_index.search(session, [0.0, 1.0], "bananas", 5)
            assert len(hits) == 2
            top_text = (await session.get(Chunk, hits[0][0])).content
            assert top_text == "bananas yellow"

            # Scope filter only returns chunks from the allowed documents.
            scoped = await chunk_index.search(session, [0.0, 1.0], "x", 5, [a.id])
            assert len(scoped) == 1
            assert (await session.get(Chunk, scoped[0][0])).document_id == a.id

            # A delete without an explicit invalidate is still picked up.
            await DocumentRepository(session).delete(b)
            hits = await chunk_index.search(session, [0.0, 1.0], "bananas", 5)
            assert len(hits) == 1
            assert (await session.get(Chunk, hits[0][0])).document_id == a.id

    asyncio.run(run())


class _CountingEmbeddings(EmbeddingProvider):
    calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        _CountingEmbeddings.calls += 1
        return [[float(len(t)), 1.0] for t in texts]

    async def health(self) -> bool:
        return True


def test_cached_embeddings_dedupes_single_queries() -> None:
    async def run() -> None:
        cached = CachedEmbeddings(_CountingEmbeddings(), size=2)
        await cached.embed(["hello"])
        await cached.embed(["hello"])
        assert _CountingEmbeddings.calls == 1
        # Batches bypass the cache.
        await cached.embed(["hello", "world"])
        assert _CountingEmbeddings.calls == 2
        # LRU eviction.
        await cached.embed(["a"])
        await cached.embed(["b"])
        await cached.embed(["hello"])
        assert _CountingEmbeddings.calls == 5

    asyncio.run(run())


def test_cached_embeddings_shares_concurrent_lookups() -> None:
    class Slow(_CountingEmbeddings):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            await asyncio.sleep(0.01)
            return await super().embed(texts)

    async def run() -> None:
        _CountingEmbeddings.calls = 0
        cached = CachedEmbeddings(Slow())
        a, b = await asyncio.gather(cached.embed(["same"]), cached.embed(["same"]))
        assert a == b
        assert _CountingEmbeddings.calls == 1

    asyncio.run(run())
