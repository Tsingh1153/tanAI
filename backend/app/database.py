"""Async database engine, session factory, and schema bootstrap (SQLite by default)."""

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
    """Create tables if they do not yet exist."""

    # Imported here (not at top) to dodge a circular import while still
    # registering every mapper before create_all runs.
    from . import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_lightweight_migrations)


# create_all never alters existing tables, so backfill columns added in later
# versions. Idempotent: applied only when the column is absent.
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
                sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a scoped async session."""

    async with SessionLocal() as session:
        yield session
