"""Provider interface and shared value objects — the seam every model backend implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(slots=True)
class ToolCall:
    """A model's request to invoke a tool."""

    id: str
    name: str
    arguments: dict


@dataclass(slots=True)
class ChatMessage:
    """A provider-agnostic chat message; tool_* fields are ignored off the agent path."""

    role: str
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    # Data-URL images ("data:image/png;base64,...") attached to this turn, for
    # vision-capable models. Ignored by text-only models/paths.
    images: list[str] | None = None


@dataclass(slots=True)
class ChatResult:
    """A non-streaming completion, possibly requesting tool calls."""

    content: str
    tool_calls: list[ToolCall]


@dataclass(slots=True)
class ProviderModel:
    """Metadata about a model exposed by a provider."""

    name: str
    size: int | None = None
    modified_at: str | None = None


class LLMProvider(ABC):
    """Abstract base for all model backends."""

    #: Stable identifier used by the registry (e.g. ``"ollama"``).
    name: str = "base"
    #: Human-facing label shown in the UI (e.g. ``"Ollama (local)"``).
    label: str = "base"
    #: Provider family, e.g. ``"ollama"`` or ``"openai"``. Informational.
    kind: str = "base"

    @abstractmethod
    async def list_models(self) -> list[ProviderModel]:
        """Return the models this provider can serve."""

    @abstractmethod
    def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        """Yield response tokens as they are generated.

        Implementations return an async generator; callers ``async for`` over it.
        """

    @abstractmethod
    async def health(self) -> bool:
        """Return ``True`` if the backend is reachable."""

    async def complete(self, model: str, messages: list["ChatMessage"]) -> str:
        """Collect a full completion as one string (drains stream_chat)."""

        parts: list[str] = []
        async for token in self.stream_chat(model, messages):
            parts.append(token)
        return "".join(parts)

    async def chat(
        self,
        model: str,
        messages: list["ChatMessage"],
        tools: list[dict] | None = None,
    ) -> "ChatResult":
        """Non-streaming completion with optional tools; default ignores tools."""

        content = await self.complete(model, messages)
        return ChatResult(content=content, tool_calls=[])

    async def aclose(self) -> None:
        """Release any held resources (HTTP clients, sockets)."""
