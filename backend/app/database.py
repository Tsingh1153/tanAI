"""Async database engine, session factory, and schema bootstrap.

We use SQLAlchemy 2.0's async engine so request handlers never block the event
loop on database I/O. The default backend is SQLite (via aiosqlite) which keeps
the app fully local and file-based, but any async SQLAlchemy URL (e.g. Postgres
via asyncpg) works without code changes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

# ``future=True`` opts into 2.0-style behavior; ``echo`` is off for clean logs.
engine = create_async_engine(settings.database_url, echo=False, future=True)

# ``expire_on_commit=False`` lets us keep using ORM objects after commit, which
# matters when we serialize a freshly-created row into a response model.
SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


async def init_db() -> None:
    """Create tables if they do not yet exist.

    Importing ``models`` here (not at module top) avoids a circular import while
    still ensuring every mapped class is registered before ``create_all`` runs.
    """

    from . import models  # noqa: F401  (registers mappers)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_lightweight_migrations)


# Columns added after a table's first release. ``create_all`` creates missing
# tables but never alters existing ones, so we additively backfill new columns on
# databases created by an earlier version. Each entry is idempotent — applied
# only when the column is absent — so this is safe to run on every startup.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "conversations": {
        "summary": "TEXT",
        "summarized_count": "INTEGER NOT NULL DEFAULT 0",
        "pinned": "BOOLEAN NOT NULL DEFAULT 0",
        "folder_id": "VARCHAR(36)",
    },
    "documents": {
        "conversation_id": "VARCHAR(36)",
    },
    "messages": {
        "images_json": "TEXT",
    },
}


def _apply_lightweight_migrations(sync_conn: Connection) -> None:
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    for table, columns in _ADDITIVE_COLUMNS.items():
        if table not in existing_tables:
            continue  # a brand-new DB already has the current schema
        present = {col["name"] for col in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name not in present:
                sync_conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a scoped async session."""

    async with SessionLocal() as session:
        yield session
