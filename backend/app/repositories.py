"""Repository layer.

The repository pattern isolates all persistence queries behind small, testable
classes. Services depend on these — never on the ORM session directly — so query
logic lives in one place and can be swapped or mocked wholesale.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (
    Chunk,
    Conversation,
    Document,
    Folder,
    MCPServer,
    Memory,
    Message,
    ProviderConfig,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[Conversation]:
        result = await self._session.execute(
            select(Conversation).order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, conversation_id: str) -> Conversation | None:
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        return result.scalar_one_or_none()

    async def create(self, model: str, title: str = "New chat") -> Conversation:
        conversation = Conversation(title=title, model=model)
        self._session.add(conversation)
        await self._session.commit()
        await self._session.refresh(conversation)
        return conversation

    async def update(self, conversation: Conversation, **fields: object) -> Conversation:
        for key, value in fields.items():
            if value is not None:
                setattr(conversation, key, value)
        await self._session.commit()
        await self._session.refresh(conversation)
        return conversation

    async def apply(
        self, conversation: Conversation, fields: dict[str, object]
    ) -> Conversation:
        """Set exactly the given fields, including explicit None (e.g. unfile)."""

        for key, value in fields.items():
            setattr(conversation, key, value)
        await self._session.commit()
        await self._session.refresh(conversation)
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        await self._session.delete(conversation)
        await self._session.commit()

    async def clear_folder(self, folder_id: str) -> None:
        """Detach every conversation from a folder (used when deleting it)."""

        result = await self._session.execute(
            select(Conversation).where(Conversation.folder_id == folder_id)
        )
        for conversation in result.scalars().all():
            conversation.folder_id = None
        await self._session.commit()


class FolderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[Folder]:
        result = await self._session.execute(
            select(Folder).order_by(Folder.created_at)
        )
        return list(result.scalars().all())

    async def get(self, folder_id: str) -> Folder | None:
        result = await self._session.execute(
            select(Folder).where(Folder.id == folder_id)
        )
        return result.scalar_one_or_none()

    async def create(self, name: str) -> Folder:
        folder = Folder(name=name)
        self._session.add(folder)
        await self._session.commit()
        await self._session.refresh(folder)
        return folder

    async def rename(self, folder: Folder, name: str) -> Folder:
        folder.name = name
        await self._session.commit()
        await self._session.refresh(folder)
        return folder

    async def delete(self, folder: Folder) -> None:
        await self._session.delete(folder)
        await self._session.commit()


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        conversation_id: str,
        role: str,
        content: str,
        model: str | None = None,
        image_files: list[str] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model=model,
            images_json=json.dumps(image_files) if image_files else None,
        )
        self._session.add(message)
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def list_for_conversation(self, conversation_id: str) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def delete_from(self, conversation_id: str, message_id: str) -> int:
        """Delete a message and every message after it in the conversation.

        Used by edit ("resend from here") and regenerate ("drop the last reply").
        Deletion is by position in the ordered list to be robust against equal
        timestamps.
        """

        messages = await self.list_for_conversation(conversation_id)
        index = next(
            (i for i, m in enumerate(messages) if m.id == message_id), None
        )
        if index is None:
            return 0
        for message in messages[index:]:
            await self._session.delete(message)
        await self._session.commit()
        return len(messages) - index


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[Document]:
        result = await self._session.execute(
            select(Document).order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_conversation(self, conversation_id: str) -> list[Document]:
        """Documents visible to a chat: its own plus the global (memory) set."""

        result = await self._session.execute(
            select(Document)
            .where(
                (Document.conversation_id == conversation_id)
                | (Document.conversation_id.is_(None))
            )
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def ready_ids_for_conversation(self, conversation_id: str) -> list[str]:
        """IDs of indexed documents available to a chat (own + global)."""

        result = await self._session.execute(
            select(Document.id).where(
                (
                    (Document.conversation_id == conversation_id)
                    | (Document.conversation_id.is_(None))
                )
                & (Document.status == "ready")
            )
        )
        return [row[0] for row in result.all()]

    async def get(self, document_id: str) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        filename: str,
        content_type: str,
        size_bytes: int,
        source_path: str | None = None,
        conversation_id: str | None = None,
    ) -> Document:
        document = Document(
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            source_path=source_path,
            conversation_id=conversation_id,
            status="indexing",
        )
        self._session.add(document)
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def promote_to_global(self, document: Document) -> Document:
        """Detach a document from its chat so it is available everywhere."""

        document.conversation_id = None
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def mark_ready(self, document: Document, num_chunks: int) -> Document:
        document.status = "ready"
        document.num_chunks = num_chunks
        document.error = None
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def mark_error(self, document: Document, error: str) -> Document:
        document.status = "error"
        document.error = error[:2000]
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
        await self._session.commit()


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, chunks: list[Chunk]) -> None:
        self._session.add_all(chunks)
        await self._session.commit()

    async def all_with_documents(
        self, document_ids: list[str] | None = None
    ) -> list[Chunk]:
        """Load chunks (with their parent document) for similarity search.

        A metadata filter on ``document_ids`` narrows the candidate set before
        vectors are ever loaded into memory.
        """

        stmt = select(Chunk).options(selectinload(Chunk.document))
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(Chunk.id))
        return len(result.scalars().all())


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, include_expired: bool = True) -> list[Memory]:
        result = await self._session.execute(
            select(Memory).order_by(
                Memory.pinned.desc(),
                Memory.importance.desc(),
                Memory.created_at.desc(),
            )
        )
        memories = list(result.scalars().all())
        if include_expired:
            return memories
        now = datetime.now(timezone.utc)
        return [m for m in memories if not _is_expired(m, now)]

    async def get(self, memory_id: str) -> Memory | None:
        result = await self._session.execute(
            select(Memory).where(Memory.id == memory_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        content: str,
        kind: str,
        importance: float,
        embedding: bytes,
        dim: int,
        pinned: bool = False,
        source_conversation_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> Memory:
        memory = Memory(
            content=content,
            kind=kind,
            importance=importance,
            embedding=embedding,
            dim=dim,
            pinned=pinned,
            source_conversation_id=source_conversation_id,
            expires_at=expires_at,
        )
        self._session.add(memory)
        await self._session.commit()
        await self._session.refresh(memory)
        return memory

    async def update(self, memory: Memory, **fields: object) -> Memory:
        for key, value in fields.items():
            if value is not None:
                setattr(memory, key, value)
        await self._session.commit()
        await self._session.refresh(memory)
        return memory

    async def touch(self, memories: list[Memory]) -> None:
        """Record that memories were used: bump count and nudge importance up."""

        now = datetime.now(timezone.utc)
        for memory in memories:
            memory.use_count += 1
            memory.last_used_at = now
            memory.importance = min(1.0, memory.importance + 0.02)
        await self._session.commit()

    async def delete(self, memory: Memory) -> None:
        await self._session.delete(memory)
        await self._session.commit()

    async def prune_expired(self) -> int:
        now = datetime.now(timezone.utc)
        expired = [m for m in await self.list() if _is_expired(m, now)]
        for memory in expired:
            await self._session.delete(memory)
        if expired:
            await self._session.commit()
        return len(expired)


class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[ProviderConfig]:
        result = await self._session.execute(
            select(ProviderConfig).order_by(ProviderConfig.created_at)
        )
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> ProviderConfig | None:
        result = await self._session.execute(
            select(ProviderConfig).where(ProviderConfig.name == name)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        label: str,
        base_url: str,
        api_key: str | None,
        kind: str = "openai",
    ) -> ProviderConfig:
        provider = ProviderConfig(
            name=name,
            label=label,
            base_url=base_url,
            api_key=api_key,
            kind=kind,
        )
        self._session.add(provider)
        await self._session.commit()
        await self._session.refresh(provider)
        return provider

    async def delete(self, provider: ProviderConfig) -> None:
        await self._session.delete(provider)
        await self._session.commit()


class MCPServerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[MCPServer]:
        result = await self._session.execute(
            select(MCPServer).order_by(MCPServer.created_at)
        )
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> MCPServer | None:
        result = await self._session.execute(
            select(MCPServer).where(MCPServer.name == name)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str],
    ) -> MCPServer:
        server = MCPServer(
            name=name,
            command=command,
            args_json=json.dumps(args),
            env_json=json.dumps(env),
        )
        self._session.add(server)
        await self._session.commit()
        await self._session.refresh(server)
        return server

    async def delete(self, server: MCPServer) -> None:
        await self._session.delete(server)
        await self._session.commit()


def _is_expired(memory: Memory, now: datetime) -> bool:
    if memory.pinned or memory.expires_at is None:
        return False
    expires = memory.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires < now
