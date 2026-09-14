"""Example tanAI plugin.

Drop-in demonstration of the plugin contract: define ``register(registry)`` and
add one or more tools. Copy this file, rename it, and add your own tools — they
appear to the agent automatically on the next turn. Delete this file to remove
these example tools.
"""

from __future__ import annotations

import random

from app.agent.tools import ToolContext, ToolError, ToolSpec


async def _word_count(args: dict, ctx: ToolContext) -> str:
    text = args.get("text", "")
    if not text:
        raise ToolError("Missing 'text'.")
    words = len(text.split())
    return f"{words} words, {len(text)} characters."


async def _roll_dice(args: dict, ctx: ToolContext) -> str:
    sides = int(args.get("sides", 6))
    count = int(args.get("count", 1))
    if sides < 2 or count < 1 or count > 100:
        raise ToolError("Use 1–100 dice with at least 2 sides.")
    rolls = [random.randint(1, sides) for _ in range(count)]
    return f"Rolled {count}d{sides}: {rolls} (total {sum(rolls)})."


def register(registry) -> None:
    """Called by the plugin loader with the live tool registry."""

    registry.register(
        ToolSpec(
            name="word_count",
            description="Count the words and characters in a piece of text.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            requires_approval=False,
            handler=_word_count,
        )
    )
    registry.register(
        ToolSpec(
            name="roll_dice",
            description="Roll dice, e.g. 2 six-sided dice.",
            parameters={
                "type": "object",
                "properties": {
                    "sides": {"type": "integer", "default": 6},
                    "count": {"type": "integer", "default": 1},
                },
            },
            requires_approval=False,
            handler=_roll_dice,
        )
    )
