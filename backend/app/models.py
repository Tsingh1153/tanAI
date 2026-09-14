"""SQLAlchemy ORM models.

The schema is intentionally small for the vertical slice: conversations own an
ordered list of messages. UUID string primary keys keep IDs opaque and safe to
expose to the frontend, and timezone-aware timestamps make ordering unambiguous.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    """A single chat thread."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    model: Mapped[str] = mapped_column(String(128))
    # Rolling summary of the oldest turns that have been compressed out of the
    # live window, plus how many leading messages it represents.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """A single turn in a conversation (user, assistant, or system)."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # JSON list of stored image filenames attached to this turn (vision input).
    images_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages"
    )

    @property
    def images(self) -> list[str]:
        """Public image URLs served under /images, for the frontend."""

        if not self.images_json:
            return []
        try:
            names = json.loads(self.images_json)
        except (ValueError, TypeError):
            return []
        return [f"/images/{name}" for name in names]


class Document(Base):
    """A source document indexed for retrieval-augmented generation."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Scope: a conversation id pins the document to that chat; NULL means it has
    # been promoted to the shared "memory" knowledge base available everywhere.
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    num_chunks: Mapped[int] = mapped_column(Integer, default=0)
    # "indexing" | "ready" | "error"
    status: Mapped[str] = mapped_column(String(16), default="indexing")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class Chunk(Base):
    """A retrievable slice of a document plus its embedding vector.

    The embedding is stored as a packed float32 binary blob (``LargeBinary``)
    which is compact and fast to load into NumPy for similarity search. The
    dimensionality is recorded so vectors can be unpacked without guessing.
    """

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    # Source locator within the document (e.g. "p. 3" or "Sheet1!A1").
    locator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    dim: Mapped[int] = mapped_column(Integer)

    document: Mapped["Document"] = relationship(back_populates="chunks")


class Memory(Base):
    """A durable fact or preference remembered across conversations.

    Memories are embedded (for semantic recall), scored by ``importance``, and
    optionally expire. ``pinned`` memories and ``kind == "profile"`` entries are
    always eligible for retrieval regardless of similarity.
    """

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # "fact" | "preference" | "profile"
    kind: Mapped[str] = mapped_column(String(16), default="fact")
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    source_conversation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    dim: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProviderConfig(Base):
    """A user-registered model backend (OpenAI-compatible endpoint).

    Persisted so runtime-added providers survive restarts. The built-in Ollama
    provider is not stored here — it is always present.
    """

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32), default="openai")
    base_url: Mapped[str] = mapped_column(String(1024))
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


class MCPServer(Base):
    """A configured Model Context Protocol server (stdio subprocess)."""

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    command: Mapped[str] = mapped_column(String(512))
    args_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    env_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

