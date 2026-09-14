"""Long-term memory: storage, retrieval, injection, and extraction.

Memories are short natural-language statements about the user ("prefers Python",
"works at Acme") embedded for semantic recall. At query time the most relevant
memories — plus all pinned/profile ones — are injected into the prompt. After
each exchange, an extraction pass asks the model to surface any new durable facts,
which are de-duplicated against existing memories before being stored.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np

from ..config import Settings
from ..models import Memory
from ..providers import ChatMessage, LLMProvider
from ..rag.embeddings import EmbeddingProvider
from ..rag.retriever import pack_vector, retrieve, unpack_vector
from ..repositories import MemoryRepository

_MAX_INJECTED = 8


class MemoryService:
    def __init__(
        self,
        memories: MemoryRepository,
        embeddings: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._memories = memories
        self._embeddings = embeddings
        self._settings = settings

    # --- CRUD -------------------------------------------------------------- #
    async def list(self) -> list[Memory]:
        return await self._memories.list()

    async def create(
        self,
        content: str,
        kind: str = "fact",
        importance: float = 0.6,
        pinned: bool = False,
        source_conversation_id: str | None = None,
        expiring: bool = False,
    ) -> Memory:
        blob, dim, _ = await self._embed(content)
        expires_at = None
        if expiring and self._settings.memory_ttl_days:
            expires_at = datetime.now(timezone.utc) + timedelta(
                days=self._settings.memory_ttl_days
            )
        return await self._memories.create(
            content=content,
            kind=kind,
            importance=importance,
            embedding=blob,
            dim=dim,
            pinned=pinned,
            source_conversation_id=source_conversation_id,
            expires_at=expires_at,
        )

    async def update(self, memory: Memory, fields: dict[str, object]) -> Memory:
        # Re-embed when the content changes so retrieval stays accurate.
        new_content = fields.get("content")
        if isinstance(new_content, str) and new_content != memory.content:
            blob, dim, _ = await self._embed(new_content)
            memory.embedding = blob
            memory.dim = dim
        return await self._memories.update(memory, **fields)

    async def delete(self, memory: Memory) -> None:
        await self._memories.delete(memory)

    # --- Retrieval / injection -------------------------------------------- #
    async def retrieve(self, query: str, top_k: int) -> list[Memory]:
        active = await self._memories.list(include_expired=False)
        if not active:
            return []

        always = [m for m in active if m.pinned or m.kind == "profile"]
        rest = [m for m in active if not (m.pinned or m.kind == "profile")]

        selected: list[Memory] = list(always)
        if rest and query.strip():
            query_vector = (await self._embeddings.embed([query]))[0]
            for scored in retrieve(query_vector, query, rest, top_k):
                selected.append(scored.chunk)  # duck-typed: Memory has embedding

        # De-duplicate (pinned/profile may also rank in vector search) and cap.
        unique: dict[str, Memory] = {m.id: m for m in selected}
        chosen = list(unique.values())[:_MAX_INJECTED]

        await self._memories.touch(chosen)
        return chosen

    async def build_prompt(
        self, query: str, top_k: int
    ) -> tuple[str | None, list[Memory]]:
        memories = await self.retrieve(query, top_k)
        if not memories:
            return None, []
        lines = "\n".join(f"- {m.content}" for m in memories)
        prompt = (
            "LONG-TERM MEMORY about the user, gathered from past conversations. "
            "Use it naturally where relevant; do not invent details beyond it.\n"
            f"{lines}"
        )
        return prompt, memories

    # --- Automatic extraction --------------------------------------------- #
    async def extract(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        provider: LLMProvider,
        model: str,
    ) -> list[Memory]:
        """Capture durable new facts from an exchange; return created memories."""

        raw = await provider.complete(model, self._extract_messages(
            user_content, assistant_content
        ))
        candidates = _parse_memory_json(raw)
        if not candidates:
            return []

        existing = await self._memories.list()
        existing_matrix = (
            np.vstack([unpack_vector(m.embedding) for m in existing])
            if existing
            else None
        )

        created: list[Memory] = []
        for item in candidates:
            content = item.get("content", "").strip()
            if not content:
                continue
            blob, dim, vector = await self._embed(content)
            if self._is_duplicate(vector, existing_matrix):
                continue
            memory = await self._memories.create(
                content=content,
                kind=item.get("kind", "fact"),
                importance=float(item.get("importance", 0.6)),
                embedding=blob,
                dim=dim,
                source_conversation_id=conversation_id,
                expires_at=self._auto_expiry(),
            )
            created.append(memory)
            # Extend the dedup matrix so multiple new items don't collide.
            row = vector.reshape(1, -1)
            existing_matrix = (
                row if existing_matrix is None else np.vstack([existing_matrix, row])
            )
        return created

    # --- Internals --------------------------------------------------------- #
    async def _embed(self, text: str) -> tuple[bytes, int, np.ndarray]:
        vector = (await self._embeddings.embed([text]))[0]
        blob, dim = pack_vector(vector)
        return blob, dim, np.asarray(vector, dtype=np.float32)

    def _auto_expiry(self) -> datetime | None:
        if self._settings.memory_ttl_days:
            return datetime.now(timezone.utc) + timedelta(
                days=self._settings.memory_ttl_days
            )
        return None

    def _is_duplicate(
        self, vector: np.ndarray, matrix: np.ndarray | None
    ) -> bool:
        if matrix is None or matrix.size == 0:
            return False
        v = vector / (np.linalg.norm(vector) + 1e-9)
        m = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
        best = float(np.max(m @ v))
        return best >= self._settings.memory_dedup_threshold

    @staticmethod
    def _extract_messages(
        user_content: str, assistant_content: str
    ) -> list[ChatMessage]:
        system = ChatMessage(
            role="system",
            content=(
                "Extract durable facts or preferences about the USER that would "
                "be useful to remember in future conversations (name, role, "
                "preferences, ongoing projects, goals, hard constraints). Ignore "
                "transient or trivial details. Respond with ONLY a JSON array of "
                'objects: [{"content": string, "kind": "fact"|"preference", '
                '"importance": number between 0 and 1}]. If nothing is worth '
                "remembering, respond with []."
            ),
        )
        user = ChatMessage(
            role="user",
            content=(
                f"USER said: {user_content}\n\n"
                f"ASSISTANT replied: {assistant_content}\n\nJSON:"
            ),
        )
        return [system, user]


def _parse_memory_json(raw: str) -> list[dict]:
    """Best-effort extraction of a JSON array from a model response."""

    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)]
