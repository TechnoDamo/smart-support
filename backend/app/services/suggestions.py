"""Генерация подсказок для оператора (режим ai_assist)."""
from __future__ import annotations

import json
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


@dataclass
class SuggestionsResult:
    suggestions: list[Suggestion]


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
        data = json.loads(raw[start : end + 1]) if start >= 0 else {"suggestions": []}

    suggestions: list[Suggestion] = []
    for i, item in enumerate((data.get("suggestions") or [])[:max_suggestions]):
        citations: list[SuggestionCitation] = []
        for c, score in hits:
            citations.append(SuggestionCitation(
                chunk_id=c.id,
                document_id=c.document_id,
                score=float(score),
            ))
        suggestions.append(Suggestion(
            id=f"s{i+1}",
            text=str(item.get("text", "")),
            confidence=item.get("confidence"),
            citations=citations,
        ))
    return SuggestionsResult(suggestions=suggestions)
