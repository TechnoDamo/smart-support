"""Роуты RAG: управление документами в базе знаний."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, ProvidersDep
from app.db.models import RagDocument, RagIngestionJob
from app.providers.registry import Providers
from app.schemas.rag import RagDeleteResponse, RagUploadResponse
from app.services.rag import ingest_document, soft_delete_document
from app.services.refs import get_default_rag_collection

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/documents", response_model=RagUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    source_name: str = Form(...),
    source_type: str = Form("file"),
    session: AsyncSession = DbSession,
    providers: Providers = ProvidersDep,
):
    """Загружает документ в базу знаний, сохраняет оригинал в object storage,
    запускает синхронный ingestion (chunk → embed → qdrant)."""
    collection = await get_default_rag_collection(session)
    content = await file.read()

    # Сохраняем оригинал
    object_key = f"rag/{collection.id}/{uuid.uuid4()}_{file.filename}"
    storage_url = await providers.object_storage.save(
        key=object_key,
        content=content,
        content_type=file.content_type,
    )

    # Создаём документ и job
    document = RagDocument(
        collection_id=collection.id,
        source_type=source_type,
        source_name=source_name,
        mime_type=file.content_type,
        storage_url=storage_url,
        source_external_id=object_key,
        current_version=0,  # станет 1 после успешного ingestion
    )
    session.add(document)
    await session.flush()

    job = RagIngestionJob(
        collection_id=collection.id,
        document_id=document.id,
        operation="upsert_document",
        status="queued",
    )
    session.add(job)
    await session.flush()

    # Выполняем синхронно (для MVP). Ошибки логируются в job.
    try:
        await ingest_document(
            session,
            document=document,
            job=job,
            raw_bytes=content,
            embedding=providers.embedding,
            vector_store=providers.vector_store,
        )
    except Exception as exc:  # noqa: BLE001 — пишем в job и отдадим статус
        # статус уже выставлен внутри ingest_document
        await session.flush()
        raise HTTPException(500, f"Ошибка ingestion: {exc}") from exc

    await session.flush()
    return RagUploadResponse(
        document_id=document.id,
        ingestion_job_id=job.id,
        status=job.status,  # type: ignore[arg-type]
    )


@router.get("/documents")
async def list_documents(session: AsyncSession = DbSession):
    r = await session.execute(
        select(RagDocument).where(RagDocument.deleted_at.is_(None))
        .order_by(RagDocument.created_at.desc())
    )
    return [
        {
            "id": str(d.id),
            "collection_id": str(d.collection_id),
            "source_type": d.source_type,
            "source_name": d.source_name,
            "mime_type": d.mime_type,
            "storage_url": d.storage_url,
            "current_version": d.current_version,
            "created_at": d.created_at.isoformat(),
        }
        for d in r.scalars()
    ]


@router.delete("/documents/{document_id}", response_model=RagDeleteResponse)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = DbSession,
    providers: Providers = ProvidersDep,
):
    r = await session.execute(select(RagDocument).where(RagDocument.id == document_id))
    doc = r.scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Документ не найден")
    if doc.deleted_at is not None:
        return RagDeleteResponse(document_id=doc.id, deleted_at=doc.deleted_at)
    await soft_delete_document(session, document=doc, vector_store=providers.vector_store)
    await session.flush()
    return RagDeleteResponse(document_id=doc.id, deleted_at=doc.deleted_at or datetime.now(timezone.utc))
