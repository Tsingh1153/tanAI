"""Pydantic request/response schemas.

These are the API's public contract, kept separate from ORM models so the
persistence layer can evolve independently of the wire format. ``from_attributes``
lets us build responses directly from ORM instances.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    model: str | None = None
    images: list[str] = Field(default_factory=list)
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    model: str
    summary: str | None = None
    summarized_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConversationWithMessages(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationCreate(BaseModel):
    title: str | None = None
    model: str | None = None


class ConversationUpdate(BaseModel):
    title: str | None = None
    model: str | None = None


class ChatRequest(BaseModel):
    """Payload for a REST-initiated chat turn (non-streaming fallback)."""

    content: str
    model: str | None = None
    provider: str | None = None


class ModelInfo(BaseModel):
    name: str
    provider: str
    provider_label: str
    size: int | None = None
    modified_at: str | None = None


class ProviderOut(BaseModel):
    name: str
    label: str
    kind: str
    base_url: str | None = None
    online: bool
    has_api_key: bool = False
    removable: bool = True


class ProviderCreate(BaseModel):
    label: str
    base_url: str
    api_key: str | None = None
    name: str | None = None


class MCPServerOut(BaseModel):
    name: str
    command: str
    connected: bool
    error: str | None = None
    tools: list[str] = Field(default_factory=list)


class MCPServerCreate(BaseModel):
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class PluginInfo(BaseModel):
    loaded: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)


class ImageGenRequest(BaseModel):
    prompt: str
    n: int = 1


class HealthOut(BaseModel):
    status: str
    provider: str
    provider_online: bool
    default_model: str
    embedding_model: str
    embedding_online: bool
    indexed_chunks: int
    hardware: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    size_bytes: int
    num_chunks: int
    status: str
    error: str | None = None
    # None => promoted to the global "memory" knowledge base; else chat-scoped.
    conversation_id: str | None = None
    created_at: datetime


class RetrievedSource(BaseModel):
    """A retrieved chunk surfaced to the client as a citation."""

    document_id: str
    filename: str
    locator: str | None = None
    score: float
    snippet: str


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    document_ids: list[str] | None = None


class SearchResponse(BaseModel):
    results: list[RetrievedSource] = Field(default_factory=list)


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    content: str
    importance: float
    pinned: bool
    use_count: int
    source_conversation_id: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None


class MemoryCreate(BaseModel):
    content: str
    kind: str = "fact"
    importance: float = 0.6
    pinned: bool = False


class MemoryUpdate(BaseModel):
    content: str | None = None
    kind: str | None = None
    importance: float | None = None
    pinned: bool | None = None
