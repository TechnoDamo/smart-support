"""AI-оркестратор: реагирует на тикеты в статусе pending_ai (режим full_ai).

Алгоритм:
  1. Забираем историю сообщений тикета.
  2. Гибридный RAG-поиск по последнему сообщению пользователя.
  3. Вызываем LLM в JSON-режиме.
  4. По action выполняем reply или escalate.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, Message, Ticket
from app.db.seed import TICKET_STATUS_PENDING_HUMAN, TICKET_STATUS_PENDING_USER
from app.prompts import load_prompt
from app.providers.embedding import EmbeddingProvider
from app.providers.llm import LlmMessage, LlmProvider
from app.providers.vector_store import VectorStore
from app.services.messages import add_outgoing_message
from app.services.rag import mark_chunks_used, retrieve
from app.services.refs import get_ticket_status_code


@dataclass
class OrchestratorDecision:
    action: str  # reply | escalate
    response_text: str
    escalation_reason: str | None
    used_chunk_ids: list[uuid.UUID]


def _parse_llm_json(raw: str) -> dict:
    """LLM может вернуть текст с окружающим «мусором». Вытаскиваем первый JSON-объект."""
    raw = raw.strip()
    if raw.startswith("```"):
        # снимаем markdown-ограды
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


async def handle_ticket(
    session: AsyncSession,
    *,
    ticket: Ticket,
    chat: Chat,
    llm: LlmProvider,
    embedding: EmbeddingProvider,
    vector_store: VectorStore,
) -> OrchestratorDecision:
    """Обрабатывает тикет: RAG → LLM → отправка ответа/эскалация."""
    # История переписки тикета
    r = await session.execute(
        select(Message).where(Message.ticket_id == ticket.id).order_by(Message.seq)
    )
    history: list[Message] = list(r.scalars())
    last_user = next((m for m in reversed(history) if m.entity == "user"), None)
    if last_user is None:
        # Защитный случай: нет сообщений пользователя — молча выходим
        return OrchestratorDecision(action="reply", response_text="", escalation_reason=None, used_chunk_ids=[])

    # RAG
    hits = await retrieve(
        session,
        chat_id=chat.id,
        ticket_id=ticket.id,
        message_id=last_user.id,
        query_text=last_user.text,
        embedding=embedding,
        vector_store=vector_store,
    )

    context_blocks = [f"[{i+1}] {chunk.chunk_text}" for i, (chunk, _s) in enumerate(hits)]
    context_str = "\n\n".join(context_blocks) or "(контекст не найден)"

    # LLM-запрос
    system = load_prompt("ai_operator")
    conversation_lines = [f"{m.entity}: {m.text}" for m in history]
    user_payload = (
        f"Контекст из базы знаний:\n{context_str}\n\n"
        f"История переписки:\n" + "\n".join(conversation_lines) + "\n\n"
        f"Последний вопрос пользователя: {last_user.text}"
    )
    raw = await llm.complete(
        [LlmMessage(role="system", content=system),
         LlmMessage(role="user", content=user_payload)],
        json_mode=True,
    )
    data = _parse_llm_json(raw)
    action = data.get("action")
    response_text = (data.get("response_text") or "").strip()
    escalation_reason = data.get("escalation_reason")

    if action not in ("reply", "escalate"):
        # Дефолтно эскалируем при неправильном формате ответа
        action = "escalate"
        escalation_reason = escalation_reason or "Некорректный формат ответа LLM"
        response_text = response_text or "Передаю ваш вопрос оператору, ожидайте."

    if action == "escalate":
        await add_outgoing_message(
            session, chat, ticket,
            text=response_text,
            entity="ai_operator",
            set_status=TICKET_STATUS_PENDING_HUMAN,
        )
    else:
        await add_outgoing_message(
            session, chat, ticket,
            text=response_text,
            entity="ai_operator",
            set_status=TICKET_STATUS_PENDING_USER,
        )
        # отмечаем использованные чанки
        await mark_chunks_used(session, [c.id for c, _s in hits])

    return OrchestratorDecision(
        action=action,
        response_text=response_text,
        escalation_reason=escalation_reason,
        used_chunk_ids=[c.id for c, _s in hits] if action == "reply" else [],
    )


async def maybe_dispatch_ai(
    session: AsyncSession,
    *,
    ticket: Ticket,
    chat: Chat,
    llm: LlmProvider,
    embedding: EmbeddingProvider,
    vector_store: VectorStore,
) -> OrchestratorDecision | None:
    """Запускает AI-оркестратор, если тикет в pending_ai и режим чата full_ai.

    Режим ai_assist не запускает автогенерацию — подсказки только по явному запросу.
    """
    # Импорт здесь, чтобы избежать циклов
    from app.services.chats import get_chat_mode_code_for

    mode = await get_chat_mode_code_for(session, chat)
    status = await get_ticket_status_code(session, ticket.status_id)
    if status != "pending_ai" or mode != "full_ai":
        return None
    return await handle_ticket(
        session, ticket=ticket, chat=chat,
        llm=llm, embedding=embedding, vector_store=vector_store,
    )
