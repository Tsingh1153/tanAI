"""Embedding provider abstraction — swap the backend without touching RAG code."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import OrderedDict

import httpx


class EmbeddingError(RuntimeError):
    """Raised when the embedding backend cannot produce vectors."""


class EmbeddingProvider(ABC):
    name: str = "base"
    #: Human-facing model identifier, surfaced in health/errors.
    model: str = ""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text (order preserved)."""

    @abstractmethod
    async def health(self) -> bool:
        """Return ``True`` if the embedding model is available."""

    async def aclose(self) -> None:
        """Release held resources."""


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embeddings served by a local Ollama model (default nomic-embed-text)."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str = "nomic-embed-text",
        timeout: float = 120.0,
        keep_alive: str = "30m",
    ) -> None:
        self.model = model
        self._keep_alive = keep_alive
        self._base_url = base_url.rstrip("/")
        # trust_env=False keeps localhost off any system proxy (see LLM provider).
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, trust_env=False
        )

    async def health(self) -> bool:
        try:
            vectors = await self.embed(["health check"])
            return len(vectors) == 1 and len(vectors[0]) > 0
        except Exception:
            return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Ollama's /api/embed accepts a batch via the ``input`` array and returns
        # ``embeddings`` in the same order.
        try:
            resp = await self._client.post(
                "/api/embed",
                json={
                    "model": self.model,
                    "input": texts,
                    "keep_alive": self._keep_alive,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(
                f"Embedding model '{self.model}' unavailable "
                f"(HTTP {exc.response.status_code}). "
                f"Try: ollama pull {self.model}"
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Embedding request failed: {exc}") from exc

        data = resp.json()
        vectors = data.get("embeddings")
        if not vectors:
            raise EmbeddingError("Embedding response contained no vectors.")
        return vectors

    async def aclose(self) -> None:
        await self._client.aclose()


class CachedEmbeddings(EmbeddingProvider):
    """LRU cache for single-text embeds.

    One chat turn embeds the same message for memory recall and for RAG; this
    makes the second lookup free. Batches (ingestion) pass straight through so
    document chunks don't evict recent queries.
    """

    def __init__(self, inner: EmbeddingProvider, size: int = 256) -> None:
        self._inner = inner
        self._size = size
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        # Requests in flight, so concurrent lookups of one text share a call.
        self._pending: dict[str, asyncio.Future[list[float]]] = {}
        self.name = inner.name
        self.model = inner.model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if len(texts) != 1:
            return await self._inner.embed(texts)
        text = texts[0]
        hit = self._cache.get(text)
        if hit is not None:
            self._cache.move_to_end(text)
            return [hit]
        pending = self._pending.get(text)
        if pending is not None:
            return [await asyncio.shield(pending)]

        future: asyncio.Future[list[float]] = asyncio.get_running_loop().create_future()
        self._pending[text] = future
        try:
            vector = (await self._inner.embed(texts))[0]
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved when nobody else was waiting
            raise
        finally:
            self._pending.pop(text, None)
        future.set_result(vector)
        self._cache[text] = vector
        if len(self._cache) > self._size:
            self._cache.popitem(last=False)
        return [vector]

    async def health(self) -> bool:
        return await self._inner.health()

    async def aclose(self) -> None:
        await self._inner.aclose()
