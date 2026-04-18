"""Роуты чатов: список, детали, смена режима."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.db.models import Chat, ChatMode, ChatModeEvent, Message, Ticket, TicketStatus
from app.schemas.chats import (
    ChangeModeRequest,
    ChangeModeResponse,
    Channel as ChannelSchema,
    Chat as ChatSchema,
    ChatDetails,
    ChatModeEvent as ChatModeEventSchema,
)
from app.schemas.messages import Message as MessageSchema
from app.services.chats import change_chat_mode
from app.services.refs import get_chat_mode_code

router = APIRouter(prefix="/chats", tags=["chats"])


async def _chat_to_schema(session: AsyncSession, chat: Chat) -> ChatSchema:
    mode_code = await get_chat_mode_code(session, chat.mode_id)
    r = await session.execute(
        select(Ticket.id).join(TicketStatus, TicketStatus.id == Ticket.status_id)
        .where(Ticket.chat_id == chat.id, TicketStatus.code != "closed")
        .order_by(Ticket.time_started.desc())
        .limit(1)
    )
    active_ticket_id = r.scalar_one_or_none()
    return ChatSchema(
        id=chat.id,
        telegram_chat_id=chat.telegram_chat_id,
        user_id=chat.user_id,
        channel=ChannelSchema(
            id=chat.channel.id,
            code=chat.channel.code,
            name=chat.channel.name,
        ),
        mode_code=mode_code,  # type: ignore[arg-type]
        active_ticket_id=active_ticket_id,
        updated_at=chat.updated_at,
    )


@router.get("")
async def list_chats(
    session: AsyncSession = DbSession,
    mode_code: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(Chat).order_by(Chat.updated_at.desc())
    if mode_code:
        stmt = stmt.join(ChatMode, ChatMode.id == Chat.mode_id).where(ChatMode.code == mode_code)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = list((await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars())
    items = [await _chat_to_schema(session, c) for c in rows]
    return {"items": [i.model_dump() for i in items],
            "page": page, "page_size": page_size, "total": total}


@router.get("/{chat_id}", response_model=ChatDetails)
async def get_chat(chat_id: uuid.UUID, session: AsyncSession = DbSession):
    r = await session.execute(select(Chat).where(Chat.id == chat_id))
    chat = r.scalar_one_or_none()
    if chat is None:
        raise HTTPException(404, "Чат не найден")
    base = await _chat_to_schema(session, chat)

    r = await session.execute(
        select(ChatModeEvent).where(ChatModeEvent.chat_id == chat_id)
        .order_by(ChatModeEvent.created_at)
    )
    events: list[ChatModeEventSchema] = []
    for e in r.scalars():
        to_code = await get_chat_mode_code(session, e.to_mode_id)
        from_code = (
            await get_chat_mode_code(session, e.from_mode_id)
            if e.from_mode_id is not None else None
        )
        events.append(ChatModeEventSchema(
            from_mode_code=from_code,  # type: ignore[arg-type]
            to_mode_code=to_code,  # type: ignore[arg-type]
            changed_by="operator",  # в текущей модели changed_by не хранится
            reason=e.reason,
            created_at=e.created_at,
        ))

    r = await session.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.seq)
    )
    messages = [
        MessageSchema(
            id=m.id,
            chat_id=m.chat_id,
            ticket_id=m.ticket_id,
            entity=m.entity,  # type: ignore[arg-type]
            seq=m.seq,
            text=m.text,
            time=m.time,
        )
        for m in r.scalars()
    ]
    return ChatDetails(**base.model_dump(), mode_events=events, messages=messages)


@router.post("/{chat_id}/mode", response_model=ChangeModeResponse)
async def change_mode(
    chat_id: uuid.UUID,
    body: ChangeModeRequest,
    session: AsyncSession = DbSession,
):
    r = await session.execute(select(Chat).where(Chat.id == chat_id))
    chat = r.scalar_one_or_none()
    if chat is None:
        raise HTTPException(404, "Чат не найден")
    await change_chat_mode(
        session, chat,
        to_mode_code=body.to_mode_code,
        changed_by="operator",
        reason=body.reason,
    )
    await session.flush()
    return ChangeModeResponse(
        chat_id=chat.id,
        mode_code=body.to_mode_code,
        changed_at=datetime.now(timezone.utc),
    )
