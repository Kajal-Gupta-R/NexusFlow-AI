import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.database.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_database_initialized = False
_database_init_lock = asyncio.Lock()


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.database_url.startswith("sqlite"):
            database_path = Path("backend/data")
            database_path.mkdir(parents=True, exist_ok=True)
        engine_options = {"pool_pre_ping": True}
        if settings.database_url.startswith("postgresql"):
            engine_options.update({"pool_size": 5, "max_overflow": 10})
        _engine = create_async_engine(settings.database_url, **engine_options)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    global _database_initialized
    if not _database_initialized:
        async with _database_init_lock:
            if not _database_initialized:
                await initialize_database()
                _database_initialized = True
    async with get_session_factory()() as session:
        yield session


async def initialize_database() -> None:
    global _engine, _session_factory
    try:
        async with get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except SQLAlchemyError:
        settings = get_settings()
        if settings.database_url.startswith("sqlite") or not settings.is_development:
            raise
        if _engine is not None:
            await _engine.dispose()
        _engine = None
        _session_factory = None
        settings.database_url = "sqlite+aiosqlite:///./backend/data/nexusflow.db"
        async with get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    global _engine, _session_factory, _database_initialized
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
    _database_initialized = False
