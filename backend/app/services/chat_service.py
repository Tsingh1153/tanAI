"""Chat orchestration: persist the turn, build the prompt, stream the reply."""

from __future__ import annotations

import asyncio
import base64
import os
import uuid
from collections.abc import AsyncIterator

from ..config import Settings, get_settings
from ..memory.summarizer import Summarizer, split_tail
from ..providers import ChatMessage, ProviderRegistry
from ..repositories import ConversationRepository, MessageRepository

# Substrings that identify a vision-capable model by name.
_VISION_HINTS = (
    "vision",
    "llava",
    "-vl",
    "vl-",
    "qwen2-vl",
    "qwen2.5vl",
    "moondream",
    "bakllava",
    "minicpm-v",
    "gemma3",
    "gpt-4o",
    "gpt-4.1",
    "claude",
    "gemini",
)


def _looks_vision(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _VISION_HINTS)


# One lock per conversation; a handful of entries for a single-user app.
_compact_locks: dict[str, asyncio.Lock] = {}


class ConversationNotFound(Exception):
    """Raised when a chat turn targets a missing conversation."""


class ChatService:
    def __init__(
        self,
        conversations: ConversationRepository,
        messages: MessageRepository,
        registry: ProviderRegistry,
        settings: Settings | None = None,
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._registry = registry
        self._settings = settings or get_settings()

    async def _vision_assist(
        self, provider, chosen_model: str, images: list[str], question: str
    ) -> str | None:
        """Describe images with a vision model; return a grounding prime."""

        if not self._settings.vision_assist_enabled:
            return None
        vision_model = await self._pick_vision_model(provider)
        if not vision_model:
            return None
        try:
            described = await provider.complete(
                vision_model,
                [
                    ChatMessage(
                        role="user",
                        content=(
                            "Describe the attached image(s) in thorough, concrete "
                            "detail so someone who cannot see them could reason "
                            f"about them. The user's question is: {question}"
                        ),
                        images=images,
                    )
                ],
            )
        except Exception:
            return None
        described = described.strip()
        if not described:
            return None
        return (
            f"The user attached image(s). A vision model ({vision_model}) "
            f"describes them as follows — treat this as your sight:\n{described}"
        )

    async def _pick_vision_model(self, provider) -> str | None:
        """Configured vision model, else the strongest installed one (small last)."""

        if self._settings.vision_assist_model:
            return self._settings.vision_assist_model
        try:
            models = await provider.list_models()
        except Exception:
            return None
        names = [m.name for m in models if _looks_vision(m.name)]
        if not names:
            return None
        # Prefer richer vision models over tiny ones like moondream.
        preference = ("llama3.2-vision", "llava", "-vl", "vl", "minicpm-v", "gemma3")
        for hint in preference:
            for name in names:
                if hint in name.lower():
                    return name
        return names[0]

    def _save_images(self, data_urls: list[str]) -> list[str]:
        """Persist data-URL images to disk; return their filenames."""

        os.makedirs(self._settings.images_dir, exist_ok=True)
        names: list[str] = []
        for url in data_urls:
            mime, _, payload = url.partition(",")
            if not payload:  # not a data URL; skip defensively
                continue
            ext = "png"
            if "image/" in mime:
                ext = mime.split("image/")[1].split(";")[0] or "png"
            name = f"{uuid.uuid4()}.{ext}"
            with open(os.path.join(self._settings.images_dir, name), "wb") as fh:
                fh.write(base64.b64decode(payload))
            names.append(name)
        return names

    async def stream_turn(
        self,
        conversation_id: str,
        user_content: str,
        model: str | None = None,
        provider_name: str | None = None,
        system_primes: list[str] | None = None,
        images: list[str] | None = None,
        persist_user: bool = True,
        context_primes: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Run one user->assistant turn, yielding assistant tokens.

        Persists the user turn before generation and the assistant turn after,
        and auto-titles from the first message. Summarizing old turns is left to
        compact(), which callers run after the reply so it never delays the
        first token.

        Prompt order keeps the prefix stable across turns so Ollama can reuse its
        KV cache: system_primes (e.g. persona) -> summary -> history ->
        context_primes (per-turn memory/RAG/web) -> the new user message.
        """

        conversation = await self._conversations.get(
            conversation_id, with_messages=False
        )
        if conversation is None:
            raise ConversationNotFound(conversation_id)

        chosen_model = model or conversation.model
        provider = self._registry.get(provider_name)

        # Persist first so history survives a mid-generation failure; regenerate
        # reuses the last user turn and skips this.
        if persist_user:
            image_files = self._save_images(images) if images else None
            await self._messages.add(
                conversation_id, "user", user_content, image_files=image_files
            )

        history_rows = await self._messages.list_for_conversation(conversation_id)
        history = [ChatMessage(role=m.role, content=m.content) for m in history_rows]

        # Vision handling for the current turn's images.
        context: list[str] = list(context_primes or [])
        if images and history:
            if _looks_vision(chosen_model):
                history[-1].images = images
            else:
                # Text-only model: describe images via a vision model, then let
                # the strong text model reason over the description.
                vision_prime = await self._vision_assist(
                    provider, chosen_model, images, user_content
                )
                if vision_prime:
                    context.append(vision_prime)
                else:
                    history[-1].images = images  # fallback (may be ignored)

        live = history[conversation.summarized_count :]
        budget = self._settings.history_token_budget
        if budget:
            # Turns past the budget get summarized after this reply; until then
            # they stay in, capped so a slow or failed summary can't overrun
            # num_ctx.
            _, live = split_tail(live, budget * 2)

        prompt: list[ChatMessage] = [
            ChatMessage(role="system", content=p) for p in system_primes or [] if p
        ]
        if conversation.summary:
            prompt.append(
                ChatMessage(
                    role="system",
                    content=f"Summary of earlier conversation:\n{conversation.summary}",
                )
            )
        context_msgs = [ChatMessage(role="system", content=p) for p in context if p]
        if live and live[-1].role == "user":
            prompt.extend(live[:-1])
            prompt.extend(context_msgs)
            prompt.append(live[-1])
        else:
            prompt.extend(live)
            prompt.extend(context_msgs)

        parts: list[str] = []
        async for token in provider.stream_chat(chosen_model, prompt):
            parts.append(token)
            yield token

        full_reply = "".join(parts)
        await self._messages.add(
            conversation_id, "assistant", full_reply, model=chosen_model
        )

        # Derive a title from the opening user message on the first exchange.
        if conversation.title == "New chat":
            title = user_content.strip().splitlines()[0][:60] or "New chat"
            await self._conversations.update(conversation, title=title)

        # Keep the persisted model in sync if the caller overrode it.
        if chosen_model != conversation.model:
            await self._conversations.update(conversation, model=chosen_model)

    async def compact(
        self,
        conversation_id: str,
        model: str | None = None,
        provider_name: str | None = None,
    ) -> bool:
        """Fold turns past the history budget into the rolling summary.

        Serialized per conversation so overlapping turns can't summarize the
        same messages twice. Returns True if the summary changed.
        """

        budget = self._settings.history_token_budget
        if not budget:
            return False
        lock = _compact_locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            conversation = await self._conversations.get(
                conversation_id, with_messages=False
            )
            if conversation is None:
                return False
            rows = await self._messages.list_for_conversation(conversation_id)
            history = [ChatMessage(role=m.role, content=m.content) for m in rows]
            overflow, _ = split_tail(history[conversation.summarized_count :], budget)
            if not overflow:
                return False
            # Fold down to half the budget, not just under it. The live window
            # then stays put for several turns instead of sliding every turn,
            # so Ollama keeps reusing its KV cache and summaries run less often.
            result = await Summarizer(self._registry.get(provider_name)).compress(
                model or conversation.model,
                conversation.summary,
                conversation.summarized_count,
                history,
                budget // 2,
            )
            if result.changed:
                await self._conversations.update(
                    conversation,
                    summary=result.summary,
                    summarized_count=result.summarized_count,
                )
            return result.changed
