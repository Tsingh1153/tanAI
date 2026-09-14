"""Query-time retrieval and prompt grounding.

Turns a user question into (1) a system prompt containing the most relevant
retrieved passages and instructions to answer from them with citations, and
(2) a list of sources for the UI. Keeping prompt construction here means the
chat layer stays oblivious to RAG mechanics — it just receives an optional
system prime.
"""

from __future__ import annotations

from ..repositories import ChunkRepository
from ..schemas import RetrievedSource
from .embeddings import EmbeddingProvider
from .retriever import ScoredChunk, retrieve

_SNIPPET_CHARS = 240


class RagService:
    def __init__(
        self, chunks: ChunkRepository, embeddings: EmbeddingProvider
    ) -> None:
        self._chunks = chunks
        self._embeddings = embeddings

    async def search(
        self,
        query: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
    ) -> list[ScoredChunk]:
        candidates = await self._chunks.all_with_documents(document_ids)
        if not candidates:
            return []
        query_vector = (await self._embeddings.embed([query]))[0]
        return retrieve(query_vector, query, candidates, top_k)

    @staticmethod
    def _to_sources(scored: list[ScoredChunk]) -> list[RetrievedSource]:
        sources: list[RetrievedSource] = []
        for item in scored:
            chunk = item.chunk
            snippet = chunk.content.strip().replace("\n", " ")
            if len(snippet) > _SNIPPET_CHARS:
                snippet = snippet[:_SNIPPET_CHARS] + "…"
            sources.append(
                RetrievedSource(
                    document_id=chunk.document_id,
                    filename=chunk.document.filename,
                    locator=chunk.locator,
                    score=round(item.score, 4),
                    snippet=snippet,
                )
            )
        return sources

    async def build_context(
        self,
        query: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
    ) -> tuple[str | None, list[RetrievedSource]]:
        """Return (system_prompt, sources). Prompt is None if nothing indexed."""

        scored = await self.search(query, top_k, document_ids)
        if not scored:
            return None, []

        blocks: list[str] = []
        for i, item in enumerate(scored, start=1):
            chunk = item.chunk
            cite = chunk.document.filename
            if chunk.locator:
                cite += f", {chunk.locator}"
            blocks.append(f"[{i}] (source: {cite})\n{chunk.content}")

        context = "\n\n".join(blocks)
        system_prompt = (
            "You are answering using the CONTEXT below, retrieved from the "
            "user's own documents. Ground your answer in this context and cite "
            "the sources you use with bracketed numbers like [1] or [2]. If the "
            "context does not contain the answer, say so plainly and answer from "
            "general knowledge, making clear which parts are not from the "
            "documents.\n\n"
            f"CONTEXT:\n{context}"
        )
        return system_prompt, self._to_sources(scored)
