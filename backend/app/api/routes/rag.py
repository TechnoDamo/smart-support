"""Роуты RAG: управление документами в базе знаний."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, ProvidersDep
from app.db.models import RagDocument as RagDocumentModel
from app.db.models import RagIngestionJob
from app.providers.registry import Providers
from app.schemas.common import PagingResponse
from app.schemas.rag import (
    RagDeleteResponse,
    RagDocument as RagDocumentSchema,
    RagUploadResponse,
)
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
    document = RagDocumentModel(
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


@router.get("/documents", response_model=PagingResponse[RagDocumentSchema])
async def list_documents(
    session: AsyncSession = DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    include_deleted: bool = Query(False),
):
    stmt = select(RagDocumentModel).order_by(RagDocumentModel.created_at.desc())
    if not include_deleted:
        stmt = stmt.where(RagDocumentModel.deleted_at.is_(None))

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = list(
        (
            await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        ).scalars()
    )

    items = [
        RagDocumentSchema(
            id=d.id,
            collection_id=d.collection_id,
            source_type=d.source_type,
            source_name=d.source_name,
            current_version=d.current_version,
            created_at=d.created_at,
            deleted_at=d.deleted_at,
        )
        for d in rows
    ]

    return PagingResponse[RagDocumentSchema](
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )

    items = [
        RagDocument(
            id=d.id,
            collection_id=d.collection_id,
            source_type=d.source_type,
            source_name=d.source_name,
            current_version=d.current_version,
            created_at=d.created_at,
            deleted_at=d.deleted_at,
        )
        for d in rows
    ]

    return PagingResponse[RagDocument](
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.delete("/documents/{document_id}", response_model=RagDeleteResponse)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = DbSession,
    providers: Providers = ProvidersDep,
):
    r = await session.execute(
        select(RagDocumentModel).where(RagDocumentModel.id == document_id)
    )
    doc = r.scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Документ не найден")
    if doc.deleted_at is not None:
        return RagDeleteResponse(document_id=doc.id, deleted_at=doc.deleted_at)
    await soft_delete_document(
        session, document=doc, vector_store=providers.vector_store
    )
    await session.flush()
    return RagDeleteResponse(
        document_id=doc.id, deleted_at=doc.deleted_at or datetime.now(timezone.utc)
    )
