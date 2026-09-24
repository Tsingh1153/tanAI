"""Heuristic detection of when a turn should use web search or agent tools.

Cheap, deterministic signals so the app can enable these skills automatically from
the user's message instead of relying on manual toggles.
"""

from __future__ import annotations

import re

# Signals that the answer needs current or external information.
_WEB_RE = re.compile(
    r"\b(latest|current(?:ly)?|today|tonight|now|recent(?:ly)?|news|headline|"
    r"price|prices|stock|stocks|weather|forecast|score|standings|"
    r"release date|who is the|this (?:year|week|month)|"
    r"20[2-9]\d)\b",
    re.IGNORECASE,
)
_WEB_EXTRA = re.compile(r"https?://|\bsearch (?:the web|online|for)\b", re.IGNORECASE)

# Signals that the turn wants an action (run code, touch files, fetch a URL).
_AGENT_RE = re.compile(
    r"\b(run|execute)\b.*\b(code|script|python|program|command)\b|"
    r"\buse python\b|"
    r"\b(read|open|write|create|save|edit|list|delete)\b.*\b(file|files|folder|directory)\b|"
    r"\b(fetch|scrape|download)\b.*\bhttps?://|"
    r"\bhttps?://\S+\b.*\b(summar|extract|read|open)",
    re.IGNORECASE,
)


def wants_web(content: str) -> bool:
    return bool(_WEB_RE.search(content) or _WEB_EXTRA.search(content))


def wants_agent(content: str) -> bool:
    return bool(_AGENT_RE.search(content))
