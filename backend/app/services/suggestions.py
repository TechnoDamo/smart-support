"""Генерация подсказок для оператора (режим ai_assist)."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, RagDocumentChunk
from app.prompts import load_prompt
from app.providers.embedding import EmbeddingProvider
from app.providers.llm import LlmMessage, LlmProvider
from app.providers.vector_store import VectorStore
from app.schemas.suggestions import Suggestion, SuggestionCitation
from app.services.rag import retrieve

logger = logging.getLogger(__name__)


@dataclass
class SuggestionsResult:
    suggestions: list[Suggestion]


def _unique_citations(
    hits: list[tuple[RagDocumentChunk, float]], *, limit: int = 3
) -> list[SuggestionCitation]:
    citations: list[SuggestionCitation] = []
    seen_chunk_ids: set[uuid.UUID] = set()
    for chunk, score in hits:
        if chunk.id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk.id)
        citations.append(
            SuggestionCitation(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                score=float(score),
            )
        )
        if len(citations) >= limit:
            break
    return citations


def _truncate_text(text: str, *, limit: int = 320) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _fallback_suggestions(
    *,
    draft_context: str | None,
    last_user_text: str | None,
    hits: list[tuple[RagDocumentChunk, float]],
    max_suggestions: int,
) -> list[Suggestion]:
    citations = _unique_citations(hits)
    lead_context = hits[0][0].chunk_text if hits else ""
    lead_context = _truncate_text(lead_context, limit=260)
    draft_prefix = f"{draft_context.strip()} " if draft_context and draft_context.strip() else ""
    user_suffix = (
        f" Пользователь спрашивает: {last_user_text.strip()}"
        if last_user_text and last_user_text.strip()
        else ""
    )

    variants: list[str] = []
    if lead_context:
        variants.extend(
            [
                f"{draft_prefix}{lead_context}",
                f"{draft_prefix}Судя по базе знаний, {lead_context[:1].lower()}{lead_context[1:]}",
                f"{draft_prefix}Кратко: {lead_context}",
            ]
        )
    else:
        variants.extend(
            [
                f"{draft_prefix}Я уточню детали и вернусь к вам с точным решением.{user_suffix}".strip(),
                f"{draft_prefix}Проверяю информацию по вашему запросу и скоро подскажу следующий шаг.{user_suffix}".strip(),
                f"{draft_prefix}Чтобы ответить точно, мне нужно свериться с базой знаний и параметрами устройства.{user_suffix}".strip(),
            ]
        )

    suggestions: list[Suggestion] = []
    for index, text in enumerate(variants[:max_suggestions], start=1):
        suggestions.append(
            Suggestion(
                id=f"fallback-s{index}",
                text=text.strip(),
                confidence=max(0.4, 0.8 - (index - 1) * 0.1),
                citations=citations,
            )
        )
    return suggestions


async def generate_suggestions(
    session: AsyncSession,
    *,
    chat_id: uuid.UUID,
    ticket_id: uuid.UUID,
    draft_context: str | None,
    max_suggestions: int,
    llm: LlmProvider,
    embedding: EmbeddingProvider,
    vector_store: VectorStore,
) -> SuggestionsResult:
    # Используем последнее сообщение пользователя + draft в качестве запроса
    r = await session.execute(
        select(Message)
        .where(Message.ticket_id == ticket_id, Message.entity == "user")
        .order_by(Message.seq.desc())
        .limit(1)
    )
    last_user = r.scalar_one_or_none()
    query = (draft_context or "") + " " + (last_user.text if last_user else "")
    query = query.strip() or "вопрос пользователя"

    hits = await retrieve(
        session,
        chat_id=chat_id,
        ticket_id=ticket_id,
        message_id=(last_user.id if last_user else None),
        query_text=query,
        embedding=embedding,
        vector_store=vector_store,
    )

    context_blocks = [f"[{i+1}] {c.chunk_text}" for i, (c, _s) in enumerate(hits)]
    context_str = "\n\n".join(context_blocks) or "(контекст не найден)"

    system = load_prompt("suggestions")
    user_payload = (
        f"Контекст из базы знаний:\n{context_str}\n\n"
        f"Черновик оператора: {draft_context or '(нет)'}\n"
        f"Последнее сообщение пользователя: {last_user.text if last_user else '(нет)'}\n"
        f"max_suggestions={max_suggestions}"
    )
    citations = _unique_citations(hits)

    try:
        raw = await llm.complete(
            [LlmMessage(role="system", content=system),
             LlmMessage(role="user", content=user_payload)],
            json_mode=True,
        )
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            data = json.loads(raw[start : end + 1]) if start >= 0 and end >= start else {"suggestions": []}

        suggestions: list[Suggestion] = []
        for i, item in enumerate((data.get("suggestions") or [])[:max_suggestions]):
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            suggestions.append(
                Suggestion(
                    id=f"s{i+1}",
                    text=text,
                    confidence=item.get("confidence"),
                    citations=citations,
                )
            )
        if suggestions:
            return SuggestionsResult(suggestions=suggestions)
        logger.warning("LLM returned no usable suggestions, using fallback")
    except Exception:  # noqa: BLE001
        logger.exception("LLM suggestions failed, using fallback")

    return SuggestionsResult(
        suggestions=_fallback_suggestions(
            draft_context=draft_context,
            last_user_text=(last_user.text if last_user else None),
            hits=hits,
            max_suggestions=max_suggestions,
        )
    )
