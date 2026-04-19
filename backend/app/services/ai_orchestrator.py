"""AI-оркестратор: реагирует на тикеты в статусе pending_ai.

Алгоритм:
  1. Забираем историю сообщений тикета.
  2. Гибридный RAG-поиск по последнему сообщению пользователя.
  3. Вызываем LLM в JSON-режиме.
  4. По action выполняем reply или escalate.
"""
from __future__ import annotations

import json
import logging
import re
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

logger = logging.getLogger(__name__)

_DEFAULT_ESCALATION_TEXT = "Передаю ваш вопрос оператору, ожидайте."
_HUMAN_REQUEST_RE = re.compile(
    r"(оператор|человек|менеджер|специалист|сотрудник|жив[ао]й)",
    re.IGNORECASE,
)
_HANDOFF_RE = re.compile(
    r"(переда(ю|м)|перев(о|е)д|соедин|оператор|специалист|человек|ожидайте)",
    re.IGNORECASE,
)


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


def _user_requested_human(text: str) -> bool:
    """Определяет, просит ли пользователь передать диалог человеку."""
    return bool(_HUMAN_REQUEST_RE.search(text or ""))


def _looks_like_handoff(text: str) -> bool:
    """Определяет, похоже ли сообщение на текст о передаче диалога человеку."""
    return bool(_HANDOFF_RE.search(text or ""))


def _build_context_fallback(hits: list[tuple]) -> str:
    """Собирает короткий ответ напрямую из найденных фрагментов базы знаний."""
    snippets: list[str] = []
    for chunk, _score in hits[:2]:
        snippet = " ".join((chunk.chunk_text or "").split())
        if not snippet:
            continue
        if len(snippet) > 260:
            snippet = snippet[:257].rstrip() + "..."
        snippets.append(snippet)

    if not snippets:
        return "Я нашёл информацию в базе знаний, но не смог корректно сформировать ответ."

    bullet_list = "\n".join(f"- {snippet}" for snippet in snippets)
    return f"Вот что удалось найти в базе знаний:\n{bullet_list}"


async def _finish_with_reply(
    session: AsyncSession,
    *,
    chat: Chat,
    ticket: Ticket,
    hits: list[tuple],
    response_text: str,
) -> OrchestratorDecision:
    """Фиксирует AI-ответ и переводит тикет в ожидание пользователя."""
    await add_outgoing_message(
        session,
        chat,
        ticket,
        text=response_text,
        entity="ai_operator",
        set_status=TICKET_STATUS_PENDING_USER,
    )
    await mark_chunks_used(session, [chunk.id for chunk, _score in hits])
    return OrchestratorDecision(
        action="reply",
        response_text=response_text,
        escalation_reason=None,
        used_chunk_ids=[chunk.id for chunk, _score in hits],
    )


async def _finish_with_escalation(
    session: AsyncSession,
    *,
    chat: Chat,
    ticket: Ticket,
    reason: str,
    response_text: str | None = None,
) -> OrchestratorDecision:
    """Фиксирует передачу тикета человеку и переводит его в pending_human."""
    final_text = (response_text or _DEFAULT_ESCALATION_TEXT).strip() or _DEFAULT_ESCALATION_TEXT
    await add_outgoing_message(
        session,
        chat,
        ticket,
        text=final_text,
        entity="ai_operator",
        set_status=TICKET_STATUS_PENDING_HUMAN,
    )
    return OrchestratorDecision(
        action="escalate",
        response_text=final_text,
        escalation_reason=reason,
        used_chunk_ids=[],
    )


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

    if _user_requested_human(last_user.text):
        return await _finish_with_escalation(
            session,
            chat=chat,
            ticket=ticket,
            reason="Пользователь попросил соединить с человеком",
        )

    if not hits:
        return await _finish_with_escalation(
            session,
            chat=chat,
            ticket=ticket,
            reason="Недостаточно данных в базе знаний для уверенного ответа",
        )

    context_blocks = [f"[{i+1}] {chunk.chunk_text}" for i, (chunk, _s) in enumerate(hits)]
    context_str = "\n\n".join(context_blocks) or "(контекст не найден)"

    # LLM-запрос
    system = (
        load_prompt("ai_operator")
        + "\n\n"
        + "Если найден хотя бы один релевантный фрагмент базы знаний и пользователь не просит"
        + " соединить его с человеком, нужно отвечать самостоятельно."
    )
    conversation_lines = [f"{m.entity}: {m.text}" for m in history]
    user_payload = (
        f"Контекст из базы знаний:\n{context_str}\n\n"
        f"История переписки:\n" + "\n".join(conversation_lines) + "\n\n"
        f"Последний вопрос пользователя: {last_user.text}"
    )
    try:
        raw = await llm.complete(
            [LlmMessage(role="system", content=system),
             LlmMessage(role="user", content=user_payload)],
            json_mode=True,
        )
        data = _parse_llm_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI-оркестратор не смог разобрать ответ модели")
        return await _finish_with_reply(
            session,
            chat=chat,
            ticket=ticket,
            hits=hits,
            response_text=_build_context_fallback(hits),
        )

    action = data.get("action")
    response_text = (data.get("response_text") or "").strip()
    escalation_reason = (data.get("escalation_reason") or "").strip() or None

    if action == "reply":
        if _looks_like_handoff(response_text):
            return await _finish_with_escalation(
                session,
                chat=chat,
                ticket=ticket,
                reason="AI сообщил о передаче диалога человеку",
                response_text=response_text,
            )
        final_response = response_text or _build_context_fallback(hits)
        return await _finish_with_reply(
            session,
            chat=chat,
            ticket=ticket,
            hits=hits,
            response_text=final_response,
        )

    if action == "escalate":
        if _looks_like_handoff(response_text) or not response_text:
            return await _finish_with_escalation(
                session,
                chat=chat,
                ticket=ticket,
                reason=escalation_reason or "AI решил передать вопрос человеку",
                response_text=response_text,
            )
        logger.warning(
            "AI вернул action=escalate, но с текстом ответа; продолжаем как reply (ticket=%s)",
            ticket.id,
        )
        return await _finish_with_reply(
            session,
            chat=chat,
            ticket=ticket,
            hits=hits,
            response_text=response_text,
        )

    logger.warning(
        "AI вернул некорректный action=%r; используем ответ из контекста (ticket=%s)",
        action,
        ticket.id,
    )
    return await _finish_with_reply(
        session,
        chat=chat,
        ticket=ticket,
        hits=hits,
        response_text=response_text or _build_context_fallback(hits),
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
    """Запускает AI-оркестратор для любого тикета в статусе pending_ai.

    Статус `pending_ai` является источником истины: если тикет в этом статусе,
    значит именно AI должен либо ответить пользователю, либо перевести тикет
    в `pending_human`.
    """
    status = await get_ticket_status_code(session, ticket.status_id)
    if status != "pending_ai":
        return None
    return await handle_ticket(
        session, ticket=ticket, chat=chat,
        llm=llm, embedding=embedding, vector_store=vector_store,
    )
