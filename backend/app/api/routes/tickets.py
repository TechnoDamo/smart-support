"""Роуты тикетов: просмотр, переименование, переоткрытие/закрытие."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.db.models import Ticket, TicketStatus, TicketStatusEvent
from app.schemas.common import PagingResponse
from app.schemas.tickets import (
    Ticket as TicketSchema,
    TicketDetails,
    TicketRenameRequest,
    TicketRenameResponse,
    TicketStatusEvent as TicketStatusEventSchema,
)
from app.services.refs import get_ticket_status_code, get_ticket_status_id
from app.services.tickets import change_ticket_status

router = APIRouter(prefix="/tickets", tags=["tickets"])


async def _ticket_to_schema(session: AsyncSession, t: Ticket) -> TicketSchema:
    code = await get_ticket_status_code(session, t.status_id)
    return TicketSchema(
        id=t.id,
        title=t.title,
        summary=t.summary,
        status_code=code,  # type: ignore[arg-type]
        chat_id=t.chat_id,
        time_started=t.time_started,
        time_closed=t.time_closed,
    )


@router.get("", response_model=PagingResponse[TicketSchema])
async def list_tickets(
    session: AsyncSession = DbSession,
    status_code: str | None = Query(None),
    chat_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(Ticket).order_by(Ticket.time_started.desc())
    if chat_id is not None:
        stmt = stmt.where(Ticket.chat_id == chat_id)
    if status_code:
        status_id = await get_ticket_status_id(session, status_code)
        stmt = stmt.where(Ticket.status_id == status_id)

    # total
    from sqlalchemy import func
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    rows = list((await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars())
    items = [await _ticket_to_schema(session, t) for t in rows]
    return PagingResponse[TicketSchema](items=items, page=page, page_size=page_size, total=total)


@router.get("/{ticket_id}", response_model=TicketDetails)
async def get_ticket(ticket_id: uuid.UUID, session: AsyncSession = DbSession):
    r = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
    t = r.scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Тикет не найден")

    base = await _ticket_to_schema(session, t)

    # События статуса
    r = await session.execute(
        select(TicketStatusEvent).where(TicketStatusEvent.ticket_id == ticket_id)
        .order_by(TicketStatusEvent.created_at)
    )
    events: list[TicketStatusEventSchema] = []
    for e in r.scalars():
        to_code = await get_ticket_status_code(session, e.to_status_id)
        from_code = (
            await get_ticket_status_code(session, e.from_status_id)
            if e.from_status_id is not None else None
        )
        events.append(TicketStatusEventSchema(
            from_status_code=from_code,  # type: ignore[arg-type]
            to_status_code=to_code,  # type: ignore[arg-type]
            changed_by=e.changed_by,  # type: ignore[arg-type]
            changed_by_user_id=e.changed_by_user_id,
            reason=e.reason,
            created_at=e.created_at,
        ))
    return TicketDetails(**base.model_dump(), status_events=events)


@router.patch("/{ticket_id}/rename", response_model=TicketRenameResponse)
async def rename_ticket(
    ticket_id: uuid.UUID,
    body: TicketRenameRequest,
    session: AsyncSession = DbSession,
):
    r = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
    t = r.scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Тикет не найден")
    t.title = body.title
    t.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return TicketRenameResponse(id=t.id, title=t.title, updated_at=t.updated_at)


@router.post("/{ticket_id}/close", response_model=TicketSchema)
async def close_ticket(
    ticket_id: uuid.UUID,
    reason: str | None = None,
    session: AsyncSession = DbSession,
):
    r = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
    t = r.scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Тикет не найден")
    await change_ticket_status(
        session, t, "closed",
        changed_by="operator",
        reason=reason or "Закрыт вручную",
    )
    await session.flush()
    return await _ticket_to_schema(session, t)
