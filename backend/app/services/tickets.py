"""Бизнес-логика тикетов: создание, смена статуса, получение активного."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, TicketStatus, TicketStatusEvent
from app.db.seed import (
    TICKET_STATUS_PENDING_AI,
    TICKET_STATUS_PENDING_HUMAN,
    TICKET_STATUS_PENDING_USER,
    TICKET_STATUS_CLOSED,
)
from app.services.refs import get_ticket_status_id, get_ticket_status_code

ACTIVE_STATUS_CODES = (
    TICKET_STATUS_PENDING_AI,
    TICKET_STATUS_PENDING_HUMAN,
    TICKET_STATUS_PENDING_USER,
)


async def get_active_ticket(session: AsyncSession, chat_id: uuid.UUID) -> Optional[Ticket]:
    """Возвращает активный тикет чата (статус не closed), если есть."""
    stmt = (
        select(Ticket)
        .join(TicketStatus, TicketStatus.id == Ticket.status_id)
        .where(Ticket.chat_id == chat_id, TicketStatus.code.in_(ACTIVE_STATUS_CODES))
    )
    r = await session.execute(stmt)
    return r.scalars().first()


async def create_ticket(
    session: AsyncSession,
    chat_id: uuid.UUID,
    initial_status_code: str,
) -> Ticket:
    """Создаёт новый тикет и записывает событие начального статуса."""
    status_id = await get_ticket_status_id(session, initial_status_code)
    ticket = Ticket(chat_id=chat_id, status_id=status_id, title=None)
    session.add(ticket)
    await session.flush()
    # title по умолчанию = "Тикет <id>"
    ticket.title = f"Тикет {ticket.id}"
    session.add(TicketStatusEvent(
        ticket_id=ticket.id,
        from_status_id=None,
        to_status_id=status_id,
        changed_by="user",  # тикет создан по входящему сообщению пользователя
        reason="Первое сообщение пользователя",
    ))
    await session.flush()
    return ticket


async def change_ticket_status(
    session: AsyncSession,
    ticket: Ticket,
    to_code: str,
    *,
    changed_by: str,
    changed_by_user_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> None:
    """Меняет статус тикета и пишет аудит-событие."""
    from_status_id = ticket.status_id
    to_status_id = await get_ticket_status_id(session, to_code)
    if from_status_id == to_status_id:
        return
    ticket.status_id = to_status_id
    ticket.updated_at = datetime.now(timezone.utc)
    if to_code == TICKET_STATUS_CLOSED and ticket.time_closed is None:
        ticket.time_closed = datetime.now(timezone.utc)
    session.add(TicketStatusEvent(
        ticket_id=ticket.id,
        from_status_id=from_status_id,
        to_status_id=to_status_id,
        changed_by=changed_by,
        changed_by_user_id=changed_by_user_id,
        reason=reason,
    ))


def status_code_for_mode(mode_code: str) -> str:
    """Маппинг режима чата в ожидаемый статус активного тикета."""
    if mode_code == "no_ai":
        return TICKET_STATUS_PENDING_HUMAN
    # full_ai и ai_assist → pending_ai (AI берёт в работу либо готовит контекст)
    return TICKET_STATUS_PENDING_AI


async def get_status_code(session: AsyncSession, ticket: Ticket) -> str:
    return await get_ticket_status_code(session, ticket.status_id)
