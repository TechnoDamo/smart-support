"""Роуты сообщений: получение истории и отправка оператором."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, ProvidersDep
from app.db.models import Chat, Message, Ticket
from app.db.session import session_scope
from app.providers.registry import Providers
from app.schemas.messages import Message as MessageSchema, SendMessageRequest
from app.services.ai_orchestrator import maybe_dispatch_ai
from app.services.messages import add_outgoing_message

router = APIRouter(prefix="/chats", tags=["messages"])


async def _ai_dispatch_task(ticket_id: uuid.UUID, chat_id: uuid.UUID) -> None:
    """Фоновая задача: запуск AI-оркестратора после нового пользовательского сообщения.

    Выполняется вне исходной HTTP-транзакции (своя сессия).
    """
    from app.providers.registry import get_providers
    providers = get_providers()
    async with session_scope() as session:
        r = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = r.scalar_one_or_none()
        r = await session.execute(select(Chat).where(Chat.id == chat_id))
        chat = r.scalar_one_or_none()
        if ticket is None or chat is None:
            return
        await maybe_dispatch_ai(
            session, ticket=ticket, chat=chat,
            llm=providers.llm,
            embedding=providers.embedding,
            vector_store=providers.vector_store,
        )


@router.get("/{chat_id}/messages", response_model=list[MessageSchema])
async def list_messages(chat_id: uuid.UUID, session: AsyncSession = DbSession):
    r = await session.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.seq)
    )
    return [
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


@router.post("/{chat_id}/messages", response_model=MessageSchema)
async def send_operator_message(
    chat_id: uuid.UUID,
    body: SendMessageRequest,
    background: BackgroundTasks,
    session: AsyncSession = DbSession,
    providers: Providers = ProvidersDep,
):
    """Отправка сообщения оператором в чат (режимы ai_assist/no_ai).

    В режиме full_ai ручная отправка оператора допустима (например, вмешательство),
    но AI-оркестратор не запускается в ответ на это сообщение.
    """
    r = await session.execute(select(Chat).where(Chat.id == chat_id))
    chat = r.scalar_one_or_none()
    if chat is None:
        raise HTTPException(404, "Чат не найден")
    r = await session.execute(select(Ticket).where(Ticket.id == body.ticket_id))
    ticket = r.scalar_one_or_none()
    if ticket is None or ticket.chat_id != chat_id:
        raise HTTPException(404, "Тикет не найден в этом чате")

    message = await add_outgoing_message(
        session, chat, ticket,
        text=body.text,
        entity="operator",
        set_status="pending_user",
    )
    await session.flush()
    return MessageSchema(
        id=message.id,
        chat_id=message.chat_id,
        ticket_id=message.ticket_id,
        entity=message.entity,  # type: ignore[arg-type]
        seq=message.seq,
        text=message.text,
        time=message.time,
    )
