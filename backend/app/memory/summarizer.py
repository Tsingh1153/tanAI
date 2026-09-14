"""Rolling summarization: fold overflowing old turns into a running summary."""

from __future__ import annotations

from dataclasses import dataclass

from ..providers import ChatMessage, LLMProvider
from .tokens import estimate_tokens


@dataclass(slots=True)
class CompressionResult:
    summary: str | None
    recent: list[ChatMessage]
    summarized_count: int
    changed: bool


class Summarizer:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def compress(
        self,
        model: str,
        existing_summary: str | None,
        summarized_count: int,
        messages: list[ChatMessage],
        budget: int,
    ) -> CompressionResult:
        """Fold overflowing older turns into the summary; return the live tail."""

        # Turns not yet represented by the existing summary.
        candidates = messages[summarized_count:]

        # Keep as many trailing turns as fit in the budget.
        kept: list[ChatMessage] = []
        used = 0
        keep_start = len(candidates)
        for i in range(len(candidates) - 1, -1, -1):
            cost = estimate_tokens(candidates[i].content) + 4
            if kept and used + cost > budget:
                break
            kept.insert(0, candidates[i])
            used += cost
            keep_start = i

        overflow = candidates[:keep_start]
        if not overflow:
            # Nothing new to compress; reuse whatever summary we already had.
            return CompressionResult(
                summary=existing_summary,
                recent=candidates,
                summarized_count=summarized_count,
                changed=False,
            )

        new_summary = await self._summarize(model, existing_summary, overflow)
        return CompressionResult(
            summary=new_summary,
            recent=kept,
            summarized_count=summarized_count + len(overflow),
            changed=True,
        )

    async def _summarize(
        self,
        model: str,
        existing_summary: str | None,
        overflow: list[ChatMessage],
    ) -> str:
        transcript = "\n".join(f"{m.role}: {m.content}" for m in overflow)
        system = ChatMessage(
            role="system",
            content=(
                "You maintain a running summary of a conversation. Update the "
                "existing summary to incorporate the new excerpt. Preserve key "
                "facts, decisions, names, numbers, and unresolved questions. "
                "Write a concise paragraph; do not add commentary."
            ),
        )
        user = ChatMessage(
            role="user",
            content=(
                f"EXISTING SUMMARY:\n{existing_summary or '(none yet)'}\n\n"
                f"NEW EXCERPT:\n{transcript}\n\nUpdated summary:"
            ),
        )
        summary = await self._provider.complete(model, [system, user])
        return summary.strip()
