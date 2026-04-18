"""Вспомогательные функции для работы со справочниками (коды ↔ id)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AppSetting,
    Channel,
    ChatMode,
    RagCollection,
    TicketStatus,
    SETTING_DEFAULT_CHAT_MODE,
)
from app.db.seed import DEFAULT_RAG_COLLECTION_CODE


async def get_chat_mode_id(session: AsyncSession, code: str) -> uuid.UUID:
    r = await session.execute(select(ChatMode.id).where(ChatMode.code == code))
    v = r.scalar_one_or_none()
    if v is None:
        raise ValueError(f"Неизвестный режим чата: {code}")
    return v


async def get_chat_mode_code(session: AsyncSession, mode_id: uuid.UUID) -> str:
    r = await session.execute(select(ChatMode.code).where(ChatMode.id == mode_id))
    v = r.scalar_one_or_none()
    if v is None:
        raise ValueError(f"Неизвестный режим чата id={mode_id}")
    return v


async def get_ticket_status_id(session: AsyncSession, code: str) -> uuid.UUID:
    r = await session.execute(select(TicketStatus.id).where(TicketStatus.code == code))
    v = r.scalar_one_or_none()
    if v is None:
        raise ValueError(f"Неизвестный статус тикета: {code}")
    return v


async def get_ticket_status_code(session: AsyncSession, status_id: uuid.UUID) -> str:
    r = await session.execute(select(TicketStatus.code).where(TicketStatus.id == status_id))
    v = r.scalar_one_or_none()
    if v is None:
        raise ValueError(f"Неизвестный статус тикета id={status_id}")
    return v


async def get_channel_id(session: AsyncSession, code: str) -> uuid.UUID:
    r = await session.execute(select(Channel.id).where(Channel.code == code))
    v = r.scalar_one_or_none()
    if v is None:
        raise ValueError(f"Неизвестный канал: {code}")
    return v


async def get_default_chat_mode_code(session: AsyncSession) -> str:
    r = await session.execute(
        select(AppSetting.value).where(AppSetting.key == SETTING_DEFAULT_CHAT_MODE)
    )
    return r.scalar_one()


async def get_default_rag_collection(session: AsyncSession) -> RagCollection:
    r = await session.execute(
        select(RagCollection).where(RagCollection.code == DEFAULT_RAG_COLLECTION_CODE)
    )
    c = r.scalar_one_or_none()
    if c is None:
        raise ValueError("RAG-коллекция по умолчанию не найдена")
    return c
