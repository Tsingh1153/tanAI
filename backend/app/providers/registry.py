"""Provider registry.

Owns the set of live providers. Created at startup with the built-in Ollama
backend, then extended with any user-registered OpenAI-compatible endpoints
loaded from the database. Providers can be added and removed at runtime, which
is what lets the app switch backends (and add a cloud key) without a restart.
"""

from __future__ import annotations

from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAICompatibleProvider
from ..config import Settings


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default: str | None = None

    def register(self, provider: LLMProvider, *, default: bool = False) -> None:
        self._providers[provider.name] = provider
        if default or self._default is None:
            self._default = provider.name

    async def unregister(self, name: str) -> None:
        provider = self._providers.pop(name, None)
        if provider is not None:
            await provider.aclose()
        if self._default == name:
            self._default = next(iter(self._providers), None)

    def get(self, name: str | None = None) -> LLMProvider:
        key = name or self._default
        if key is None or key not in self._providers:
            # Fall back to the default rather than failing a chat because a
            # since-removed provider was requested.
            if self._default and self._default in self._providers:
                return self._providers[self._default]
            raise KeyError(f"No provider registered for {name!r}")
        return self._providers[key]

    def has(self, name: str) -> bool:
        return name in self._providers

    def all(self) -> list[LLMProvider]:
        return list(self._providers.values())

    def names(self) -> list[str]:
        return list(self._providers)

    async def aclose(self) -> None:
        for provider in self._providers.values():
            await provider.aclose()


def build_default_registry(settings: Settings) -> ProviderRegistry:
    """Construct the registry with the always-on local Ollama backend."""

    registry = ProviderRegistry()
    registry.register(
        OllamaProvider(
            settings.ollama_base_url,
            settings.request_timeout,
            settings.num_ctx,
            settings.ollama_keep_alive,
            settings.num_predict,
        ),
        default=True,
    )
    return registry


def make_openai_provider(
    name: str,
    base_url: str,
    api_key: str | None,
    label: str | None,
    timeout: float,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        base_url=base_url,
        api_key=api_key,
        label=label,
        timeout=timeout,
    )
