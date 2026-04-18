"""Фоновый обработчик ingestion jobs."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import RagDocument, RagIngestionJob
from app.providers.embedding import EmbeddingProvider
from app.providers.object_storage import ObjectStorage
from app.providers.vector_store import VectorStore
from app.services.rag import ingest_document


def _storage_key_from_document(document: RagDocument) -> str:
    """Определяет ключ объекта для повторной загрузки из object storage."""
    if document.source_external_id:
        return document.source_external_id
    if not document.storage_url:
        raise ValueError("У документа нет storage_url/source_external_id")

    parsed = urlparse(document.storage_url)
    if parsed.scheme == "s3":
        return parsed.path.lstrip("/")
    if parsed.scheme == "file":
        base = Path(get_settings().object_storage_local_path).resolve()
        path = Path(parsed.path).resolve()
        return str(path.relative_to(base))
    raise ValueError(f"Неподдерживаемая схема storage_url: {parsed.scheme}")


async def _claim_ingestion_jobs(session: AsyncSession, *, limit: int) -> list[RagIngestionJob]:
    settings = get_settings()
    stale_before = datetime.now(timezone.utc) - timedelta(seconds=settings.rag_ingestion_job_timeout_seconds)
    result = await session.execute(
        select(RagIngestionJob)
        .where(RagIngestionJob.operation == "upsert_document")
        .where(
            or_(
                RagIngestionJob.status == "queued",
                RagIngestionJob.status == "failed",
                ((RagIngestionJob.status == "processing") & (RagIngestionJob.started_at.is_(None))) |
                ((RagIngestionJob.status == "processing") &
                 (RagIngestionJob.started_at.is_not(None)) &
                 (RagIngestionJob.started_at <= stale_before)),
            )
        )
        .where(RagIngestionJob.attempts < settings.rag_ingestion_max_retries)
        .order_by(RagIngestionJob.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars())


async def process_ingestion_jobs(
    session: AsyncSession,
    *,
    embedding: EmbeddingProvider,
    vector_store: VectorStore,
    object_storage: ObjectStorage,
) -> int:
    """Подбирает незавершённые ingestion jobs и пытается довести их до done."""
    settings = get_settings()
    jobs = await _claim_ingestion_jobs(session, limit=settings.rag_ingestion_worker_batch_size)
    processed = 0

    for job in jobs:
        document = (await session.execute(
            select(RagDocument).where(RagDocument.id == job.document_id)
        )).scalar_one_or_none()
        if document is None:
            job.status = "failed"
            job.error_message = "Документ для ingestion job не найден"
            continue

        try:
            job.status = "processing"
            job.started_at = datetime.now(timezone.utc)
            job.finished_at = None
            job.error_message = None
            job.attempts = (job.attempts or 0) + 1
            await session.flush()

            key = _storage_key_from_document(document)
            async with asyncio.timeout(settings.rag_ingestion_job_timeout_seconds):
                raw_bytes = await object_storage.load(key)
                await ingest_document(
                    session,
                    document=document,
                    job=job,
                    raw_bytes=raw_bytes,
                    embedding=embedding,
                    vector_store=vector_store,
                    increment_attempts=False,
                )
            processed += 1
        except TimeoutError:
            job.status = "failed"
            job.error_message = (
                f"Превышен лимит времени ingestion: "
                f"{settings.rag_ingestion_job_timeout_seconds} секунд"
            )
            job.finished_at = datetime.now(timezone.utc)
        except Exception as exc:  # noqa: BLE001
            if job.status != "failed":
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = datetime.now(timezone.utc)

    return processed
