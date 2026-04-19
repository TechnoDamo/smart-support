"""Бизнес-логика сообщений: добавление сообщения, синхронизация статуса тикета, outbox."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, Message, OutboxMessage, Ticket
from app.db.seed import (
    TICKET_STATUS_PENDING_AI,
    TICKET_STATUS_PENDING_HUMAN,
    TICKET_STATUS_PENDING_USER,
)
from app.services.chats import get_chat_mode_code_for
from app.services.refs import get_channel_id
from app.services.tickets import change_ticket_status, get_active_ticket, create_ticket, status_code_for_mode


async def _next_seq(session: AsyncSession, chat_id: uuid.UUID) -> int:
    r = await session.execute(
        select(func.coalesce(func.max(Message.seq), 0)).where(Message.chat_id == chat_id)
    )
    return int(r.scalar_one()) + 1


async def add_user_message(session: AsyncSession, chat: Chat, text: str) -> tuple[Message, Ticket]:
    """Регистрирует входящее сообщение пользователя.

    Создаёт тикет, если активного нет. Обновляет статус тикета по режиму чата.
    Возвращает (message, ticket).
    """
    ticket = await get_active_ticket(session, chat.id)
    mode_code = await get_chat_mode_code_for(session, chat)

    if ticket is None:
        # Новый тикет в начальном статусе по режиму
        ticket = await create_ticket(session, chat.id, status_code_for_mode(mode_code))
    else:
        # Если тикет ждал пользователя — возвращаем в pending_ai / pending_human
        from app.services.refs import get_ticket_status_code
        current_code = await get_ticket_status_code(session, ticket.status_id)
        if current_code == TICKET_STATUS_PENDING_USER:
            await change_ticket_status(
                session, ticket, status_code_for_mode(mode_code),
                changed_by="user",
                reason="Новое сообщение пользователя",
            )

    seq = await _next_seq(session, chat.id)
    message = Message(
        chat_id=chat.id,
        ticket_id=ticket.id,
        entity="user",
        seq=seq,
        text=text,
    )
    session.add(message)
    chat.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return message, ticket


async def add_outgoing_message(
    session: AsyncSession,
    chat: Chat,
    ticket: Ticket,
    *,
    text: str,
    entity: str,  # operator | ai_operator
    set_status: str = TICKET_STATUS_PENDING_USER,
) -> Message:
    """Регистрирует исходящее сообщение и ставит его в outbox.

    Меняет статус тикета (по умолчанию на pending_user — ждём пользователя).
    """
    seq = await _next_seq(session, chat.id)
    message = Message(
        chat_id=chat.id,
        ticket_id=ticket.id,
        entity=entity,
        seq=seq,
        text=text,
    )
    session.add(message)
    chat.updated_at = datetime.now(timezone.utc)
    await session.flush()

    await change_ticket_status(
        session, ticket, set_status,
        changed_by=entity,
        reason=None,
    )

    # Добавляем запись в outbox для гарантированной доставки
    # Определяем код канала
    from app.db.models import Channel
    r = await session.execute(select(Channel).where(Channel.id == chat.channel_id))
    channel = r.scalar_one()
    session.add(OutboxMessage(
        message_id=message.id,
        channel_code=channel.code,
        payload={
            "external_chat_id": chat.telegram_chat_id,
            "text": text,
        },
        status="pending",
        next_attempt_at=datetime.now(timezone.utc),
    ))
    return message
