"""Общие фикстуры для тестов.

Используем:
  - SQLite в отдельном файле на каждый тест, чтобы Alembic шёл тем же путём, что и runtime.
  - Все провайдеры — mocks (инъекция через override_providers).
  - FastAPI TestClient поверх httpx.AsyncClient.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Принудительно используем тестовую конфигурацию до импорта app.*
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_bootstrap.db")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("VECTOR_STORE_PROVIDER", "mock")
os.environ.setdefault("OBJECT_STORAGE_PROVIDER", "local")
os.environ.setdefault("OBJECT_STORAGE_LOCAL_PATH", "./storage_test")
os.environ.setdefault("CHANNEL_TELEGRAM_PROVIDER", "mock")
os.environ.setdefault("PROMPTS_DIR", "./prompts")

from app.config import get_settings  # noqa: E402
from app.db import session as session_mod  # noqa: E402
from app.db.migrations import upgrade_to_head_async  # noqa: E402
from app.db.seed import seed_reference_data  # noqa: E402
from app.providers.channel import MockChannelSender  # noqa: E402
from app.providers.embedding import MockEmbedding  # noqa: E402
from app.providers.llm import MockLlm  # noqa: E402
from app.providers.object_storage import LocalFilesystemStorage  # noqa: E402
from app.providers.registry import (  # noqa: E402
    Providers,
    override_providers,
    reset_providers,
)
from app.providers.vector_store import MockVectorStore  # noqa: E402


# Сбрасываем кэш настроек, чтобы новые env-переменные подхватились
get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest_asyncio.fixture
async def engine(tmp_path):
    """Свежая SQLite-база в отдельном файле на каждый тест."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url
    get_settings.cache_clear()  # type: ignore[attr-defined]

    eng = create_async_engine(
        db_url,
        future=True,
    )
    # Привязываем движок к модулю сессии, чтобы API-слой использовал тот же.
    session_mod._engine = eng  # type: ignore[attr-defined]
    session_mod._sessionmaker = async_sessionmaker(eng, expire_on_commit=False)  # type: ignore[attr-defined]
    await upgrade_to_head_async()
    # Сид справочников
    maker = session_mod._sessionmaker  # type: ignore[attr-defined]
    async with maker() as s:
        await seed_reference_data(s)
        await s.commit()
    yield eng
    await eng.dispose()
    session_mod._engine = None  # type: ignore[attr-defined]
    session_mod._sessionmaker = None  # type: ignore[attr-defined]


@pytest_asyncio.fixture
async def db(engine) -> AsyncIterator[AsyncSession]:
    """Сессия для прямых обращений из теста."""
    maker = session_mod._sessionmaker  # type: ignore[attr-defined]
    async with maker() as s:
        yield s
        await s.rollback()


@pytest.fixture
def mock_llm() -> MockLlm:
    return MockLlm()


@pytest.fixture
def mock_embedding() -> MockEmbedding:
    return MockEmbedding(vector_size=64)  # маленький размер — быстрее тесты


@pytest.fixture
def mock_vector_store() -> MockVectorStore:
    return MockVectorStore()


@pytest.fixture
def mock_channel() -> MockChannelSender:
    return MockChannelSender()


@pytest.fixture
def providers(tmp_path, mock_llm, mock_embedding, mock_vector_store, mock_channel) -> Providers:
    local_storage = LocalFilesystemStorage(str(tmp_path / "object_storage"))
    p = Providers(
        llm=mock_llm,
        embedding=mock_embedding,
        vector_store=mock_vector_store,
        object_storage=local_storage,
        channel_sender=mock_channel,
    )
    override_providers(p)
    yield p
    reset_providers()


@pytest_asyncio.fixture
async def client(engine, providers) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент поверх ASGI-приложения (без сети)."""
    from app.main import create_app
    app = create_app()
    # Отключаем lifespan (БД и сид уже сделаны в фикстуре engine; планировщик не нужен в unit-тестах).
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
