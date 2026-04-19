"""Роуты подсказок оператору (режим ai_assist)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, ProvidersDep
from app.db.models import Chat, Ticket
from app.providers.registry import Providers
from app.schemas.suggestions import SuggestionsRequest, SuggestionsResponse
from app.services.suggestions import generate_suggestions

router = APIRouter(prefix="/chats", tags=["suggestions"])


@router.post("/{chat_id}/suggestions", response_model=SuggestionsResponse)
async def suggest(
    chat_id: uuid.UUID,
    body: SuggestionsRequest,
    session: AsyncSession = DbSession,
    providers: Providers = ProvidersDep,
):
    r = await session.execute(select(Chat).where(Chat.id == chat_id))
    chat = r.scalar_one_or_none()
    if chat is None:
        raise HTTPException(404, "Чат не найден")
    r = await session.execute(select(Ticket).where(Ticket.id == body.ticket_id))
    ticket = r.scalar_one_or_none()
    if ticket is None or ticket.chat_id != chat_id:
        raise HTTPException(404, "Тикет не найден в этом чате")
    result = await generate_suggestions(
        session,
        chat_id=chat_id,
        ticket_id=body.ticket_id,
        draft_context=body.draft_context,
        max_suggestions=body.max_suggestions,
        llm=providers.llm,
        embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    return SuggestionsResponse(suggestions=result.suggestions)
