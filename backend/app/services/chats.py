"""Бизнес-логика чатов: поиск/создание, смена режима, взаимосвязь со статусом тикета."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, ChatMode, ChatModeEvent, User
from app.services.refs import (
    get_channel_id,
    get_chat_mode_code,
    get_chat_mode_id,
    get_default_chat_mode_code,
)
from app.services.tickets import (
    change_ticket_status,
    get_active_ticket,
    status_code_for_mode,
)


async def get_or_create_user_by_telegram(
    session: AsyncSession,
    *,
    telegram_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
) -> User:
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
    )
    session.add(user)
    await session.flush()
    return user


async def get_or_create_chat(
    session: AsyncSession,
    *,
    channel_code: str,
    telegram_chat_id: int,
    user: User,
) -> Chat:
    r = await session.execute(select(Chat).where(Chat.telegram_chat_id == telegram_chat_id))
    chat = r.scalar_one_or_none()
    if chat is not None:
        return chat
    channel_id = await get_channel_id(session, channel_code)
    default_mode = await get_default_chat_mode_code(session)
    mode_id = await get_chat_mode_id(session, default_mode)
    chat = Chat(
        channel_id=channel_id,
        telegram_chat_id=telegram_chat_id,
        user_id=user.id,
        mode_id=mode_id,
    )
    session.add(chat)
    await session.flush()
    return chat


async def change_chat_mode(
    session: AsyncSession,
    chat: Chat,
    *,
    to_mode_code: str,
    changed_by: str,
    changed_by_user_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> ChatModeEvent:
    """Меняет режим чата и синхронизирует статус активного тикета (если есть)."""
    new_mode_id = await get_chat_mode_id(session, to_mode_code)
    if chat.mode_id == new_mode_id:
        # Режим не изменился — создаём пустое событие только если явно нужно
        return ChatModeEvent(chat_id=chat.id, from_mode_id=chat.mode_id,
                             to_mode_id=new_mode_id, reason=reason)
    event = ChatModeEvent(
        chat_id=chat.id,
        from_mode_id=chat.mode_id,
        to_mode_id=new_mode_id,
        reason=reason,
    )
    session.add(event)
    chat.mode_id = new_mode_id
    chat.updated_at = datetime.now(timezone.utc)

    # Синхронизация статуса активного тикета (если он есть и не закрыт)
    active = await get_active_ticket(session, chat.id)
    if active is not None:
        target_status = status_code_for_mode(to_mode_code)
        await change_ticket_status(
            session, active, target_status,
            changed_by=changed_by,
            changed_by_user_id=changed_by_user_id,
            reason=f"Изменение режима чата на {to_mode_code}",
        )
    await session.flush()
    return event


async def get_chat_mode_code_for(session: AsyncSession, chat: Chat) -> str:
    return await get_chat_mode_code(session, chat.mode_id)
