"""Chat orchestration.

The service ties together persistence (repositories) and inference (provider):
it records the user turn, compresses history when it grows too long, replays the
(possibly summarized) conversation to the model, streams the assistant's tokens
back to the caller, and persists the completed reply. It knows nothing about HTTP
or WebSockets, so the same logic serves both transports and is trivial to
unit-test with a fake provider.
"""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import AsyncIterator

from ..config import Settings, get_settings
from ..memory.summarizer import Summarizer
from ..memory.tokens import estimate_tokens
from ..providers import ChatMessage, ProviderRegistry
from ..repositories import ConversationRepository, MessageRepository


# Substrings that identify a vision-capable model by name.
_VISION_HINTS = (
    "vision", "llava", "-vl", "vl-", "qwen2-vl", "qwen2.5vl", "moondream",
    "bakllava", "minicpm-v", "gemma3", "gpt-4o", "gpt-4.1", "claude", "gemini",
)


def _looks_vision(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _VISION_HINTS)


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
        """Configured vision model, or the first installed one that looks visual."""

        if self._settings.vision_assist_model:
            return self._settings.vision_assist_model
        try:
            models = await provider.list_models()
        except Exception:
            return None
        for model in models:
            if _looks_vision(model.name):
                return model.name
        return None

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
    ) -> AsyncIterator[str]:
        """Run one user->assistant turn, yielding assistant tokens.

        Side effects: persists the user message before generation and the full
        assistant message after; compresses old turns into the conversation
        summary when the live window exceeds the token budget; auto-titles the
        thread from the first user message.

        ``system_primes`` are optional, non-persisted system messages (memory,
        retrieved context) injected ahead of the transcript.
        """

        conversation = await self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)

        chosen_model = model or conversation.model
        provider = self._registry.get(provider_name)

        # Persist the user's turn first so history is correct even if the model
        # call fails midway. Images are saved to disk for redisplay. Regenerate
        # reuses the existing last user turn, so it skips this.
        if persist_user:
            image_files = self._save_images(images) if images else None
            await self._messages.add(
                conversation_id, "user", user_content, image_files=image_files
            )

        history_rows = await self._messages.list_for_conversation(conversation_id)
        history = [
            ChatMessage(role=m.role, content=m.content) for m in history_rows
        ]

        # Vision handling for the current turn's images.
        primes: list[str] = list(system_primes or [])
        if images and history:
            if _looks_vision(chosen_model):
                # The chosen model can see images directly.
                history[-1].images = images
            else:
                # Text-only model: route images through a vision model to get a
                # description, then let the strong text model reason over it.
                vision_prime = await self._vision_assist(
                    provider, chosen_model, images, user_content
                )
                if vision_prime:
                    primes.append(vision_prime)
                else:
                    history[-1].images = images  # fallback (may be ignored)

        # --- Context compression ---
        summary_text = conversation.summary
        recent = history[conversation.summarized_count :]
        budget = self._settings.history_token_budget
        total_tokens = sum(estimate_tokens(m.content) for m in history)
        if budget and (total_tokens > budget or conversation.summarized_count):
            result = await Summarizer(provider).compress(
                chosen_model,
                conversation.summary,
                conversation.summarized_count,
                history,
                budget,
            )
            recent = result.recent
            summary_text = result.summary
            if result.changed:
                await self._conversations.update(
                    conversation,
                    summary=result.summary,
                    summarized_count=result.summarized_count,
                )

        # --- Assemble prompt: primes -> summary -> live turns ---
        prompt: list[ChatMessage] = []
        for prime in primes:
            if prime:
                prompt.append(ChatMessage(role="system", content=prime))
        if summary_text:
            prompt.append(
                ChatMessage(
                    role="system",
                    content=f"Summary of earlier conversation:\n{summary_text}",
                )
            )
        prompt.extend(recent)

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
