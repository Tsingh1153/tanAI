"""Image generator interface and shared value objects."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ImageGenError(RuntimeError):
    """Raised when an image cannot be generated."""


class ImageGenerator(ABC):
    #: Backend identifier for display ("automatic1111", "openai").
    name: str = "base"

    @abstractmethod
    async def generate(self, prompt: str, size: int, steps: int, n: int) -> list[bytes]:
        """Return ``n`` generated images as raw PNG bytes."""

    @abstractmethod
    async def health(self) -> bool:
        """Return ``True`` if the backend is reachable."""

    async def aclose(self) -> None:
        """Release held resources."""
