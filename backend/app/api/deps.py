"""FastAPI-зависимости: БД-сессия и контейнер провайдеров."""
from __future__ import annotations

from typing import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.providers.registry import Providers, get_providers


async def db_session() -> AsyncIterator[AsyncSession]:
    async for s in get_session():
        yield s


def providers_dep() -> Providers:
    return get_providers()


# Типы для Depends, чтобы не дублировать запись
DbSession = Depends(db_session)
ProvidersDep = Depends(providers_dep)
