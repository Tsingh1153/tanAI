"""Document ingestion orchestration.

Given a persisted ``Document`` row and the file on disk, this parses the file,
chunks it, embeds every chunk (in batches, to bound request size and memory),
and stores the vectors. Success/failure is recorded on the document's ``status``
so the UI can show indexing progress and surface errors.
"""

from __future__ import annotations

from ..models import Chunk, Document
from ..repositories import ChunkRepository, DocumentRepository
from .chunker import chunk_segments
from .embeddings import EmbeddingProvider
from .parsers import extract_segments
from .retriever import pack_vector

_EMBED_BATCH = 64


class IngestionService:
    def __init__(
        self,
        documents: DocumentRepository,
        chunks: ChunkRepository,
        embeddings: EmbeddingProvider,
    ) -> None:
        self._documents = documents
        self._chunks = chunks
        self._embeddings = embeddings

    async def _embed_all(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = texts[start : start + _EMBED_BATCH]
            vectors.extend(await self._embeddings.embed(batch))
        return vectors

    async def ingest(self, document: Document, path: str) -> Document:
        """Parse, chunk, embed, and store; update document status."""

        try:
            segments = extract_segments(path, document.filename)
            text_chunks = chunk_segments(segments)
            if not text_chunks:
                return await self._documents.mark_error(
                    document, "No extractable text found in document."
                )

            vectors = await self._embed_all([c.content for c in text_chunks])

            chunk_rows: list[Chunk] = []
            for text_chunk, vector in zip(text_chunks, vectors):
                blob, dim = pack_vector(vector)
                chunk_rows.append(
                    Chunk(
                        document_id=document.id,
                        ordinal=text_chunk.ordinal,
                        content=text_chunk.content,
                        locator=text_chunk.locator,
                        embedding=blob,
                        dim=dim,
                    )
                )

            await self._chunks.add_many(chunk_rows)
            return await self._documents.mark_ready(document, len(chunk_rows))
        except Exception as exc:  # any parse/embed failure -> visible error state
            return await self._documents.mark_error(document, str(exc))
