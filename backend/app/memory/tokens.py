"""Lightweight token estimation.

Exact token counts depend on the model's tokenizer, which we don't want to load
just to make budgeting decisions. A ~4-characters-per-token heuristic is a well
established, conservative approximation for English text and code, and it is
plenty accurate for deciding when to compress history.
"""

from __future__ import annotations

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)
