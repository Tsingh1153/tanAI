"""Auto model router: classify a turn and pick the best available model.

Cheap and deterministic — a keyword/shape heuristic, no extra model call — so it
adds no latency. Given the models the user actually has installed, it maps a
category to the best match by name, falling back to the default when nothing fits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Ordered name-substring preferences per category. First installed match wins.
_PREFERENCES: dict[str, tuple[str, ...]] = {
    "code": ("coder", "code", "deepseek", "starcoder", "qwen"),
    "math": ("math", "deepseek", "qwen", "wizardmath"),
    "vision": (
        "vision",
        "llava",
        "-vl",
        "vl-",
        "moondream",
        "minicpm-v",
        "bakllava",
        "gemma3",
    ),
    "long_context": ("llama3.1", "llama3.2", "llama3", "qwen", "mistral"),
    "general": (),
}

_CODE_RE = re.compile(
    r"```|\b(code|function|class|bug|debug|compile|regex|refactor|stack ?trace|"
    r"exception|api|sql|python|javascript|typescript|java|rust|golang|c\+\+)\b",
    re.IGNORECASE,
)
_MATH_RE = re.compile(
    r"\$.+\$|\b(solve|equation|integral|derivative|probability|calculate|"
    r"theorem|prove|matrix|factorial|algebra|calculus)\b|[0-9]\s*[+\-*/^=]\s*[0-9]",
    re.IGNORECASE,
)

# Above this estimated prompt size, favor a long-context model.
_LONG_CONTEXT_TOKENS = 6000


@dataclass(slots=True)
class Route:
    model: str
    provider: str
    category: str
    reason: str


def classify(content: str, has_images: bool, approx_tokens: int) -> str:
    """Bucket a turn into a routing category (priority: vision > code > math > length)."""

    if has_images:
        return "vision"
    if _CODE_RE.search(content):
        return "code"
    if _MATH_RE.search(content):
        return "math"
    if approx_tokens >= _LONG_CONTEXT_TOKENS:
        return "long_context"
    return "general"


def choose_model(
    category: str,
    available: list[tuple[str, str]],
    default_model: str,
) -> Route | None:
    """Pick the best (model, provider) for a category from installed models.

    ``available`` is a list of (model_name, provider_name). Falls back to the
    configured default model, then to whatever is installed.
    """

    if not available:
        return None

    for hint in _PREFERENCES.get(category, ()):
        for name, provider in available:
            if hint in name.lower():
                return Route(
                    model=name,
                    provider=provider,
                    category=category,
                    reason=f"{category} → matched '{hint}'",
                )

    for name, provider in available:
        if name == default_model:
            return Route(name, provider, category, f"{category} → default model")

    name, provider = available[0]
    return Route(name, provider, category, f"{category} → only available model")


def route(
    content: str,
    has_images: bool,
    approx_tokens: int,
    available: list[tuple[str, str]],
    default_model: str,
) -> Route | None:
    category = classify(content, has_images, approx_tokens)
    return choose_model(category, available, default_model)
