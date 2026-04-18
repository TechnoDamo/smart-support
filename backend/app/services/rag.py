"""RAG-пайплайн: чанкинг, ingestion, retrieval."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    RagCollection,
    RagDocument,
    RagDocumentChunk,
    RagDocumentVersion,
    RagIngestionJob,
    RagRetrievalEvent,
    RagRetrievalResult,
)
from app.providers.embedding import EmbeddingProvider
from app.providers.object_storage import ObjectStorage
from app.providers.vector_store import VectorStore
from app.services.refs import get_default_rag_collection


# ─── Чанкинг ─────────────────────────────────────────────────────────────────

_WHITESPACE_RE = re.compile(r"\s+")


def _approx_tokens(text: str) -> int:
    """Грубая оценка числа токенов: по словам. Достаточно для разбиения."""
    return len(_WHITESPACE_RE.split(text.strip())) if text.strip() else 0


def chunk_text(text: str, *, chunk_size_tokens: int, overlap_tokens: int) -> list[str]:
    """Делит текст на чанки по приблизительному числу токенов с перекрытием."""
    words = _WHITESPACE_RE.split(text.strip())
    if not words or not words[0]:
        return []
    chunks: list[str] = []
    i = 0
    step = max(chunk_size_tokens - overlap_tokens, 1)
    while i < len(words):
        chunk_words = words[i : i + chunk_size_tokens]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        i += step
    return chunks


# ─── Ingestion ───────────────────────────────────────────────────────────────


def _extract_text_simple(content: bytes, mime_type: str | None) -> str:
    """Минимальная экстракция текста.

    Для MVP поддерживаем только текстовые форматы (txt/markdown).
    Для PDF/DOCX в реальной системе здесь будет OCR / парсер; пока — декод utf-8.
    """
    try:
        return content.decode("utf-8", errors="ignore")
    except Exception:
        return ""


async def ingest_document(
    session: AsyncSession,
    *,
    document: RagDocument,
    job: RagIngestionJob,
    raw_bytes: bytes,
    embedding: EmbeddingProvider,
    vector_store: VectorStore,
    increment_attempts: bool = True,
) -> None:
    """Выполняет синхронный ingestion: extract → chunk → embed → upsert в Qdrant."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    job.status = "processing"
    job.started_at = now
    if increment_attempts:
        job.attempts = (job.attempts or 0) + 1
    await session.flush()

    # Коллекция
    r = await session.execute(
        select(RagCollection).where(RagCollection.id == document.collection_id)
    )
    collection = r.scalar_one()

    try:
        # 1) Извлечение текста
        text = _extract_text_simple(raw_bytes, document.mime_type)
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        # 2) Версия документа
        r = await session.execute(
            select(func.coalesce(func.max(RagDocumentVersion.version), 0))
            .where(RagDocumentVersion.document_id == document.id)
        )
        next_version = int(r.scalar_one()) + 1
        version = RagDocumentVersion(
            document_id=document.id,
            version=next_version,
            content_hash=content_hash,
            extraction_status="processing",
            extracted_text=text,
        )
        session.add(version)
        await session.flush()

        # 3) Разбиение на чанки
        chunks = chunk_text(
            text,
            chunk_size_tokens=settings.rag_chunk_size_tokens,
            overlap_tokens=settings.rag_chunk_overlap_tokens,
        )
        if not chunks:
            version.extraction_status = "ready"
            document.current_version = next_version
            job.status = "done"
            job.finished_at = datetime.now(timezone.utc)
            return

        # 4) Убедиться, что коллекция существует
        await vector_store.ensure_collection(
            collection.qdrant_collection_name,
            collection.vector_size,
            collection.distance_metric,
        )

        # 5) Подготовить BM25-статистику на текущем батче (для корректных sparse)
        embedding.fit_sparse(chunks)

        # 6) Векторизация и upsert
        vectors = await embedding.embed(chunks)
        for idx, (chunk_str, vec) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())
            chunk_row = RagDocumentChunk(
                document_id=document.id,
                document_version_id=version.id,
                collection_id=collection.id,
                chunk_index=idx,
                chunk_text=chunk_str,
                chunk_token_count=_approx_tokens(chunk_str),
                qdrant_point_id=point_id,
                extra_metadata={"source_name": document.source_name},
            )
            session.add(chunk_row)
            await vector_store.upsert(
                collection.qdrant_collection_name,
                point_id,
                vec,
                payload={
                    "document_id": str(document.id),
                    "chunk_index": idx,
                    "source_name": document.source_name,
                },
            )

        version.extraction_status = "ready"
        document.current_version = next_version
        document.updated_at = datetime.now(timezone.utc)
        job.status = "done"
        job.finished_at = datetime.now(timezone.utc)

    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.finished_at = datetime.now(timezone.utc)
        raise


async def soft_delete_document(
    session: AsyncSession,
    *,
    document: RagDocument,
    vector_store: VectorStore,
) -> None:
    """Мягкое удаление документа + удаление точек в векторном хранилище."""
    now = datetime.now(timezone.utc)
    document.deleted_at = now

    r = await session.execute(
        select(RagDocumentChunk)
        .where(RagDocumentChunk.document_id == document.id,
               RagDocumentChunk.deleted_at.is_(None))
    )
    chunks = list(r.scalars())
    if not chunks:
        return

    # Удаляем из Qdrant пачкой
    collection_id = chunks[0].collection_id
    r = await session.execute(select(RagCollection).where(RagCollection.id == collection_id))
    collection = r.scalar_one()
    await vector_store.delete(
        collection.qdrant_collection_name,
        [c.qdrant_point_id for c in chunks],
    )
    for c in chunks:
        c.deleted_at = now


# ─── Retrieval ───────────────────────────────────────────────────────────────


async def retrieve(
    session: AsyncSession,
    *,
    chat_id: uuid.UUID,
    ticket_id: uuid.UUID,
    message_id: uuid.UUID | None,
    query_text: str,
    embedding: EmbeddingProvider,
    vector_store: VectorStore,
) -> list[tuple[RagDocumentChunk, float]]:
    """Гибридный поиск (dense + sparse BM25) + запись событий в БД.

    Возвращает список (chunk, score) в порядке релевантности.
    """
    settings = get_settings()
    collection = await get_default_rag_collection(session)

    # BM25 нужно строить по уже проиндексированным чанкам, чтобы запрос получил
    # адекватные веса. Для MVP: если BM25 пустой, подтягиваем тексты чанков.
    if embedding.bm25.total_docs == 0:
        r = await session.execute(
            select(RagDocumentChunk.chunk_text)
            .where(RagDocumentChunk.collection_id == collection.id,
                   RagDocumentChunk.deleted_at.is_(None))
        )
        corpus = [row[0] for row in r.all()]
        if corpus:
            embedding.fit_sparse(corpus)

    # Эмбеддинг запроса
    [qvec] = await embedding.embed([query_text])
    from app.providers.embedding import SparseVector
    sparse = SparseVector(indices=qvec.sparse_indices, values=qvec.sparse_values)

    hits = await vector_store.hybrid_search(
        collection.qdrant_collection_name,
        dense=qvec.dense,
        sparse=sparse,
        top_k=settings.rag_retrieval_top_k,
        dense_weight=settings.rag_hybrid_dense_weight,
        sparse_weight=settings.rag_hybrid_sparse_weight,
    )

    # Отфильтровать по min_score
    hits = [h for h in hits if h.score >= settings.rag_retrieval_min_score]

    # Записываем retrieval-событие
    event = RagRetrievalEvent(
        chat_id=chat_id,
        ticket_id=ticket_id,
        message_id=message_id,
        collection_id=collection.id,
        query_text=query_text,
        top_k=settings.rag_retrieval_top_k,
        min_score=settings.rag_retrieval_min_score,
    )
    session.add(event)
    await session.flush()

    # Резолвим chunk_id по qdrant_point_id
    out: list[tuple[RagDocumentChunk, float]] = []
    for rank, hit in enumerate(hits, start=1):
        r = await session.execute(
            select(RagDocumentChunk).where(RagDocumentChunk.qdrant_point_id == hit.point_id)
        )
        chunk = r.scalar_one_or_none()
        if chunk is None:
            continue
        session.add(RagRetrievalResult(
            retrieval_event_id=event.id,
            chunk_id=chunk.id,
            rank=rank,
            score=hit.score,
            used_in_answer=False,
        ))
        out.append((chunk, hit.score))
    return out


async def mark_chunks_used(session: AsyncSession, retrieval_event_chunk_ids: list[uuid.UUID]) -> None:
    """После использования чанков в ответе — помечаем used_in_answer=true."""
    if not retrieval_event_chunk_ids:
        return
    stmt = select(RagRetrievalResult).where(RagRetrievalResult.chunk_id.in_(retrieval_event_chunk_ids))
    r = await session.execute(stmt)
    for res in r.scalars():
        res.used_in_answer = True
