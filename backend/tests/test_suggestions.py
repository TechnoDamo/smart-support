"""Подсказки оператору: retrieval + fallback при сбоях LLM."""

from __future__ import annotations

import pytest

from app.db.models import RagDocument, RagIngestionJob
from app.services.rag import ingest_document
from app.services.refs import get_default_rag_collection
from app.services.suggestions import generate_suggestions
from app.services.telegram_integration import process_telegram_update


@pytest.mark.asyncio
async def test_generate_suggestions_falls_back_to_retrieved_context(db, providers, mock_llm):
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

    await ingest_document(
        db,
        document=doc,
        job=job,
        raw_bytes=(
            "Для сброса контроллера удерживайте кнопку RESET 10 секунд, "
            "пока индикатор не начнет мигать зеленым."
        ).encode("utf-8"),
        embedding=providers.embedding,
        vector_store=providers.vector_store,
    )

    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1710000000,
            "chat": {"id": 123456, "type": "private"},
            "from": {"id": 123456, "is_bot": False, "first_name": "Test"},
            "text": "Как сбросить контроллер?",
        },
    }
    created = await process_telegram_update(db, update)
    await db.commit()

    mock_llm.queue("this is not valid json")
    result = await generate_suggestions(
        db,
        chat_id=created["chat_obj_id"],
        ticket_id=created["ticket_obj_id"],
        draft_context="Подскажу шаги для безопасного сброса.",
        max_suggestions=3,
        llm=providers.llm,
        embedding=providers.embedding,
        vector_store=providers.vector_store,
    )

    assert result.suggestions
    assert any("RESET" in item.text or "сброс" in item.text.lower() for item in result.suggestions)
    assert all(item.citations for item in result.suggestions)
