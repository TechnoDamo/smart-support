"""RAG-пайплайн: чанкинг, ingestion, retrieval."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
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
from app.providers.embedding import EmbeddingProvider, tokenize
from app.providers.object_storage import ObjectStorage
from app.providers.vector_store import VectorStore
from app.services.refs import get_default_rag_collection

logger = logging.getLogger(__name__)


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


def _normalize_query_text(query_text: str) -> str:
    return " ".join((query_text or "").split())


def _lexical_query_terms(query_text: str) -> list[tuple[str, float]]:
    """Возвращает набор сильных lexical-сигналов для точных технических запросов."""
    normalized_query = _normalize_query_text(query_text)
    terms: list[tuple[str, float]] = []
    seen: set[str] = set()

    if normalized_query and len(normalized_query) <= 120:
        lowered = normalized_query.lower()
        terms.append((lowered, 6.0))
        seen.add(lowered)

    for token in tokenize(query_text):
        if token in seen:
            continue
        seen.add(token)
        if any(ch.isdigit() for ch in token) and len(token) >= 3:
            terms.append((token, 4.0))
        elif len(token) >= 5:
            terms.append((token, 1.5))

    return terms[:8]


def _lexical_score(text: str, weighted_terms: list[tuple[str, float]]) -> float:
    """Подсчитывает lexical-score по наличию значимых терминов в тексте чанка."""
    if not weighted_terms:
        return 0.0
    lowered = (text or "").lower()
    if not lowered:
        return 0.0

    matched_weight = sum(weight for term, weight in weighted_terms if term in lowered)
    max_weight = sum(weight for _term, weight in weighted_terms) or 1.0
    return min(matched_weight / max_weight, 1.0)


async def _retrieve_lexical_candidates(
    session: AsyncSession,
    *,
    collection_id: uuid.UUID,
    query_text: str,
    limit: int,
) -> list[tuple[RagDocumentChunk, float]]:
    """Находит lexical-кандидаты по `ILIKE` и даёт им отдельный скор."""
    weighted_terms = _lexical_query_terms(query_text)
    if not weighted_terms:
        return []

    filters = [
        RagDocumentChunk.chunk_text.ilike(f"%{term.replace('%', '').replace('_', '')}%")
        for term, _weight in weighted_terms
        if term
    ]
    if not filters:
        return []

    result = await session.execute(
        select(RagDocumentChunk)
        .where(
            RagDocumentChunk.collection_id == collection_id,
            RagDocumentChunk.deleted_at.is_(None),
            or_(*filters),
        )
        .limit(max(limit, 10))
    )

    candidates: list[tuple[RagDocumentChunk, float]] = []
    for chunk in result.scalars():
        score = _lexical_score(chunk.chunk_text, weighted_terms)
        if score > 0:
            candidates.append((chunk, score))

    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[:limit]


# ─── Ingestion ───────────────────────────────────────────────────────────────


def _extract_text(content: bytes, mime_type: str | None) -> str:
    """Извлекает текст из содержимого на основе MIME типа.

    Поддерживает:
    - application/pdf → pypdf.PdfReader
    - application/vnd.openxmlformats‑officedocument.wordprocessingml.document → docx.Document
    - text/* → декодирование UTF‑8
    - fallback: попытка декодирования UTF‑8

    Raises:
        ValueError: если парсинг не удался или неподдерживаемый формат.
    """
    if mime_type is None:
        # Пытаемся декодировать как UTF‑8
        try:
            return content.decode("utf-8", errors="ignore")
        except Exception:
            raise ValueError(
                "Не удалось декодировать бинарное содержимое без указания MIME типа"
            )

    # PDF
    if mime_type == "application/pdf":
        try:
            import pypdf
        except ImportError:
            raise ValueError("Для извлечения текста из PDF требуется библиотека pypdf")
        try:
            from io import BytesIO

            pdf = pypdf.PdfReader(BytesIO(content))
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            return text.strip()
        except Exception as e:
            raise ValueError(f"Ошибка извлечения текста из PDF: {e}")

    # DOCX
    if (
        mime_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        try:
            import docx
        except ImportError:
            raise ValueError(
                "Для извлечения текста из DOCX требуется библиотека python‑docx"
            )
        try:
            from io import BytesIO

            doc = docx.Document(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            return text.strip()
        except Exception as e:
            raise ValueError(f"Ошибка извлечения текста из DOCX: {e}")

    # Текстовые файлы
    if mime_type.startswith("text/"):
        try:
            return content.decode("utf-8", errors="ignore")
        except Exception as e:
            raise ValueError(f"Ошибка декодирования текстового содержимого: {e}")

    # Fallback: пытаемся декодировать как UTF‑8
    try:
        return content.decode("utf-8", errors="ignore")
    except Exception:
        raise ValueError(
            f"Неподдерживаемый MIME тип {mime_type} и не удалось декодировать как UTF‑8"
        )


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
        # 1) Создание версии документа (статус processing до извлечения)
        r = await session.execute(
            select(func.coalesce(func.max(RagDocumentVersion.version), 0)).where(
                RagDocumentVersion.document_id == document.id
            )
        )
        next_version = int(r.scalar_one()) + 1
        version = RagDocumentVersion(
            document_id=document.id,
            version=next_version,
            content_hash="",  # временно, заполнится после успешного извлечения
            extraction_status="processing",
            extracted_text=None,
        )
        session.add(version)
        await session.flush()

        # 2) Извлечение текста
        try:
            text = _extract_text(raw_bytes, document.mime_type)
        except Exception as e:
            version.extraction_status = "failed"
            version.error_message = str(e)
            raise
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        version.content_hash = content_hash
        version.extracted_text = text
        version.extraction_status = "ready"

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
        try:
            if version.extraction_status == "processing":
                version.extraction_status = "failed"
                version.error_message = str(exc)
        except NameError:
            # version not defined, ignore
            pass
        await session.flush()
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
        select(RagDocumentChunk).where(
            RagDocumentChunk.document_id == document.id,
            RagDocumentChunk.deleted_at.is_(None),
        )
    )
    chunks = list(r.scalars())
    if not chunks:
        return

    # Удаляем из Qdrant пачкой
    collection_id = chunks[0].collection_id
    r = await session.execute(
        select(RagCollection).where(RagCollection.id == collection_id)
    )
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
            select(RagDocumentChunk.chunk_text).where(
                RagDocumentChunk.collection_id == collection.id,
                RagDocumentChunk.deleted_at.is_(None),
            )
        )
        corpus = [row[0] for row in r.all()]
        if corpus:
            embedding.fit_sparse(corpus)

    # Эмбеддинг запроса
    [qvec] = await embedding.embed([query_text])
    from app.providers.embedding import SparseVector

    sparse = SparseVector(indices=qvec.sparse_indices, values=qvec.sparse_values)

    vector_hits = await vector_store.hybrid_search(
        collection.qdrant_collection_name,
        dense=qvec.dense,
        sparse=sparse,
        top_k=settings.rag_retrieval_top_k,
        dense_weight=settings.rag_hybrid_dense_weight,
        sparse_weight=settings.rag_hybrid_sparse_weight,
    )

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
    ranked_chunks: dict[uuid.UUID, tuple[RagDocumentChunk, float]] = {}
    orphan_point_ids: list[str] = []
    for hit in vector_hits:
        r = await session.execute(
            select(RagDocumentChunk).where(
                RagDocumentChunk.qdrant_point_id == hit.point_id,
                RagDocumentChunk.deleted_at.is_(None),
            )
        )
        chunk = r.scalar_one_or_none()
        if chunk is None:
            orphan_point_ids.append(hit.point_id)
            continue
        ranked_chunks[chunk.id] = (
            chunk,
            max(hit.score, ranked_chunks.get(chunk.id, (chunk, 0.0))[1]),
        )

    lexical_hits = await _retrieve_lexical_candidates(
        session,
        collection_id=collection.id,
        query_text=query_text,
        limit=settings.rag_retrieval_top_k * 4,
    )
    for chunk, lexical_score in lexical_hits:
        current = ranked_chunks.get(chunk.id)
        if current is None:
            ranked_chunks[chunk.id] = (chunk, lexical_score)
            continue
        ranked_chunks[chunk.id] = (chunk, max(current[1], lexical_score))

    out = sorted(
        (
            (chunk, score)
            for chunk, score in ranked_chunks.values()
            if score >= settings.rag_retrieval_min_score
        ),
        key=lambda item: item[1],
        reverse=True,
    )[: settings.rag_retrieval_top_k]

    for rank, (chunk, score) in enumerate(out, start=1):
        session.add(
            RagRetrievalResult(
                retrieval_event_id=event.id,
                chunk_id=chunk.id,
                rank=rank,
                score=score,
                used_in_answer=False,
            )
        )

    # Если Qdrant содержит осиротевшие точки, тихо чистим их, чтобы они не
    # ухудшали качество retrieval в следующих запросах.
    if orphan_point_ids:
        try:
            await vector_store.delete(collection.qdrant_collection_name, orphan_point_ids)
            logger.warning(
                "Удалены осиротевшие Qdrant points: %s",
                ", ".join(orphan_point_ids),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось удалить осиротевшие Qdrant points")
    return out


async def mark_chunks_used(
    session: AsyncSession, retrieval_event_chunk_ids: list[uuid.UUID]
) -> None:
    """После использования чанков в ответе — помечаем used_in_answer=true."""
    if not retrieval_event_chunk_ids:
        return
    stmt = select(RagRetrievalResult).where(
        RagRetrievalResult.chunk_id.in_(retrieval_event_chunk_ids)
    )
    r = await session.execute(stmt)
    for res in r.scalars():
        res.used_in_answer = True
