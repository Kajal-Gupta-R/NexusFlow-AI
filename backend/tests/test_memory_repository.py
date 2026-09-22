import pytest
import pytest_asyncio
from app.database.models import Base
from app.database.repository import MemoryRepository
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'memory.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield MemoryRepository(session)
    await engine.dispose()


@pytest.mark.asyncio
async def test_memory_creation_deduplicates_and_retrieves(repository) -> None:
    first = await repository.create_memory("user-a", "Prefers concise answers", "preference", [1.0, 0.0])
    duplicate = await repository.create_memory("user-a", "Prefers concise answers", "preference", [1.0, 0.0])

    assert first.memory_id == duplicate.memory_id
    matches = await repository.retrieve_memories("user-a", [1.0, 0.0], "concise answers")
    assert [item.memory_text for item in matches] == ["Prefers concise answers"]


@pytest.mark.asyncio
async def test_memory_ownership_isolated(repository) -> None:
    memory = await repository.create_memory("user-a", "Uses Python", "fact", None)

    assert await repository.list_memories("user-b") == []
    assert await repository.delete_memory("user-b", memory.memory_id) is False
    assert await repository.delete_memory("user-a", memory.memory_id) is True


@pytest.mark.asyncio
async def test_sensitive_memory_is_rejected(repository) -> None:
    with pytest.raises(ValueError):
        await repository.create_memory("user-a", "OPENAI_API_KEY=secret-value", "secret", None)
