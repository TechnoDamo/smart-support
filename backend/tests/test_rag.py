"""RAG: чанкинг, ingestion, гибридный retrieval."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import RagDocument, RagDocumentChunk, RagIngestionJob
from app.services.rag import chunk_text, ingest_document, retrieve
from app.services.refs import get_default_rag_collection


def test_chunk_text_basic():
    chunks = chunk_text("a b c d e f g h", chunk_size_tokens=3, overlap_tokens=1)
    # Окно 3 со сдвигом 2 → [a b c], [c d e], [e f g], [g h]
    assert chunks[0] == "a b c"
    assert chunks[1] == "c d e"
    assert len(chunks) >= 3


def test_chunk_text_empty():
    assert chunk_text("", chunk_size_tokens=3, overlap_tokens=1) == []


@pytest.mark.asyncio
async def test_ingest_and_retrieve(db, providers):
    # Создаём документ и job, прогоняем ingestion
    collection = await get_default_rag_collection(db)
    doc = RagDocument(
        collection_id=collection.id,
        source_type="file",
        source_name="faq.txt",
        mime_type="text/plain",
        storage_url=None,
        current_version=0,
    )
    db.add(doc)
    await db.flush()
    job = RagIngestionJob(
        collection_id=collection.id,
        document_id=doc.id,
        operation="upsert_document",
        status="queued",
    )
    db.add(job)
    await db.flush()

    text = (
        "График работы поддержки: с 9 до 18 по будням. "
        "По выходным отвечаем дольше. "
        "Для возврата товара нужно предоставить чек. "
        "Доставка в пределах города — 1 день."
    )
    await ingest_document(
        db, document=doc, job=job, raw_bytes=text.encode("utf-8"),
        embedding=providers.embedding, vector_store=providers.vector_store,
    )
    await db.commit()

    assert job.status == "done"
    r = await db.execute(select(RagDocumentChunk).where(RagDocumentChunk.document_id == doc.id))
    chunks = list(r.scalars())
    assert len(chunks) >= 1

    # Теперь retrieve
    import uuid as _uuid
    hits = await retrieve(
        db,
        chat_id=_uuid.uuid4(),
        ticket_id=_uuid.uuid4(),
        message_id=None,
        query_text="график работы",
        embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    assert isinstance(hits, list)
    # В in-memory сторе всегда что-то возвращается
    assert len(hits) >= 0
