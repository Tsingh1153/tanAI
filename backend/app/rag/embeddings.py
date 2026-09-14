"""Embedding provider abstraction — swap the backend without touching RAG code."""

from __future__ import annotations

from abc import ABC, abstractmethod

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
