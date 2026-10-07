"""In-memory chunk index so a query doesn't reload every embedding from SQLite.

Holds the normalized embedding matrix and each chunk's token set. It is rebuilt
lazily when chunks change: ingestion calls ``invalidate()``, and a cheap row
count catches deletions (including cascades and tests resetting the schema).
"""

from __future__ import annotations

import asyncio

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Chunk
from .retriever import blend, lexical_scores, tokenize, unpack_vector


class ChunkIndex:
    def __init__(self) -> None:
        self._generation = 0
        self._built_for: tuple[int, int] | None = None
        self._ids: list[str] = []
        self._doc_ids = np.empty(0, dtype=object)
        self._matrix = np.empty((0, 0), dtype=np.float32)
        self._terms: list[set[str]] = []
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._generation += 1

    async def _ensure(self, session: AsyncSession) -> None:
        count = (await session.execute(select(func.count(Chunk.id)))).scalar_one()
        if self._built_for == (self._generation, count):
            return
        async with self._lock:
            if self._built_for == (self._generation, count):
                return  # another query rebuilt it while we waited
            generation = self._generation
            rows = (
                await session.execute(
                    select(Chunk.id, Chunk.document_id, Chunk.content, Chunk.embedding)
                )
            ).all()
            if rows:
                matrix = np.vstack([unpack_vector(r.embedding) for r in rows])
                matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
            else:
                matrix = np.empty((0, 0), dtype=np.float32)
            self._ids = [r.id for r in rows]
            self._doc_ids = np.array([r.document_id for r in rows], dtype=object)
            self._matrix = matrix
            self._terms = [tokenize(r.content) for r in rows]
            self._built_for = (generation, len(rows))

    async def search(
        self,
        session: AsyncSession,
        query_embedding: list[float],
        query_text: str,
        top_k: int,
        document_ids: list[str] | None = None,
        alpha: float = 0.65,
    ) -> list[tuple[str, float]]:
        """Return (chunk_id, score) for the best chunks, best first."""

        await self._ensure(session)
        if not self._ids:
            return []
        rows = np.arange(len(self._ids))
        matrix = self._matrix
        if document_ids:
            rows = np.flatnonzero(np.isin(self._doc_ids, document_ids))
            if rows.size == 0:
                return []
            if rows.size < len(self._ids):
                matrix = matrix[rows]

        query = np.array(query_embedding, dtype=np.float32)  # copy: normalized in place
        query /= np.linalg.norm(query) + 1e-9
        semantic = matrix @ query
        lexical = lexical_scores(tokenize(query_text), [self._terms[i] for i in rows])
        order, combined = blend(semantic, lexical, top_k, alpha)
        return [(self._ids[rows[i]], float(combined[i])) for i in order]


chunk_index = ChunkIndex()
