"""Give every test a clean database.

All test modules import the app, which binds one module-level engine to whichever
LOCALMIND_DATABASE_URL wins the import race. That single SQLite file also persists
between runs, so rows (notably globally-promoted documents) leak across tests. This
autouse fixture drops and recreates every table before each test for real isolation.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _clean_database():
    from app.database import Base, engine

    async def reset() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset())
    yield
