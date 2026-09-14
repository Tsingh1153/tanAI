"""Pluggable LLM provider layer.

The application talks to models only through the ``LLMProvider`` interface, so
new backends (llama.cpp, vLLM, LM Studio, OpenAI-compatible, HF Transformers)
can be added without touching services or routes.
"""

from .base import (
    ChatMessage,
    ChatResult,
    LLMProvider,
    ProviderModel,
    ToolCall,
)
from .openai_provider import OpenAICompatibleProvider
from .registry import (
    ProviderRegistry,
    build_default_registry,
    make_openai_provider,
)

__all__ = [
    "ChatMessage",
    "ChatResult",
    "LLMProvider",
    "ProviderModel",
    "ToolCall",
    "OpenAICompatibleProvider",
    "ProviderRegistry",
    "build_default_registry",
    "make_openai_provider",
]
