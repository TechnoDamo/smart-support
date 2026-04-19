"""Планировщик: автозакрытие, ingestion worker и Telegram polling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.models import AppSetting, Message, RagDocument, RagDocumentChunk, RagIngestionJob, Ticket
from app.db.seed import CHANNEL_TELEGRAM
from app.services.chats import get_or_create_chat, get_or_create_user_by_telegram
from app.services.messages import add_outgoing_message, add_user_message
from app.services.rag_worker import process_ingestion_jobs
from app.services.refs import get_default_rag_collection, get_ticket_status_code
from app.services.scheduler import close_inactive_tickets
from app.services.telegram_integration import (
    SETTING_TELEGRAM_POLLING_OFFSET,
    SETTING_TELEGRAM_POLLING_WEBHOOK_CLEARED,
    poll_telegram_updates,
)


@pytest.mark.asyncio
async def test_inactive_ticket_is_closed(engine, providers, db):
    """Сообщение старше cutoff → тикет должен закрыться."""
    user = await get_or_create_user_by_telegram(db, telegram_id=888)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=888, user=user)
    _, ticket = await add_user_message(db, chat, "вопрос")
    await add_outgoing_message(db, chat, ticket, text="Ответ", entity="ai_operator")

    past = datetime.now(timezone.utc) - timedelta(hours=24)
    r = await db.execute(select(Message).where(Message.chat_id == chat.id))
    for m in r.scalars():
        m.time = past
    await db.commit()

    closed = await close_inactive_tickets()
    assert closed >= 1

    refetched = (await db.execute(select(Ticket).where(Ticket.id == ticket.id))).scalar_one()
    await db.refresh(refetched)
    code = await get_ticket_status_code(db, refetched.status_id)
    assert code == "closed"


@pytest.mark.asyncio
async def test_ingestion_worker_processes_failed_job(engine, providers, db):
    collection = await get_default_rag_collection(db)
    key = f"rag/{collection.id}/retry_faq.txt"
    content = "График работы поддержки: с 9 до 18".encode("utf-8")
    storage_url = await providers.object_storage.save(key=key, content=content, content_type="text/plain")

    document = RagDocument(
        collection_id=collection.id,
        source_type="file",
        source_name="retry_faq.txt",
        source_external_id=key,
        mime_type="text/plain",
        storage_url=storage_url,
        current_version=0,
    )
    db.add(document)
    await db.flush()

    job = RagIngestionJob(
        collection_id=collection.id,
        document_id=document.id,
        operation="upsert_document",
        status="failed",
        error_message="previous failure",
        attempts=0,
    )
    db.add(job)
    await db.commit()

    processed = await process_ingestion_jobs(
        db,
        embedding=providers.embedding,
        vector_store=providers.vector_store,
        object_storage=providers.object_storage,
    )
    await db.commit()

    assert processed == 1
    await db.refresh(job)
    assert job.status == "done"

    chunks = list((await db.execute(
        select(RagDocumentChunk).where(RagDocumentChunk.document_id == document.id)
    )).scalars())
    assert len(chunks) >= 1


@pytest.mark.asyncio
async def test_telegram_polling_fetches_updates(engine, providers, db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        deleted_webhook = False

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, params=None):
            assert "deleteWebhook" in url
            assert params["drop_pending_updates"] == "false"
            FakeClient.deleted_webhook = True
            return FakeResponse({"ok": True, "result": True})

        async def get(self, url, params=None):
            assert "getUpdates" in url
            assert params["limit"] >= 1
            assert FakeClient.deleted_webhook is True
            return FakeResponse(
                {
                    "ok": True,
                    "result": [
                        {
                            "update_id": 101,
                            "message": {
                                "text": "polling message",
                                "chat": {"id": 7777},
                                "from": {"id": 7777, "first_name": "Poll"},
                            },
                        }
                    ],
                }
            )

    monkeypatch.setattr("app.services.telegram_integration.httpx.AsyncClient", FakeClient)

    processed = await poll_telegram_updates()
    assert processed == 1

    chats = (await db.execute(select(Ticket.id))).scalars().all()
    assert len(chats) == 1

    offset = (await db.execute(
        select(AppSetting.value).where(AppSetting.key == SETTING_TELEGRAM_POLLING_OFFSET)
    )).scalar_one()
    assert offset == "102"

    polling_mode_marker = (
        await db.execute(
            select(AppSetting.value).where(
                AppSetting.key == SETTING_TELEGRAM_POLLING_WEBHOOK_CLEARED
            )
        )
    ).scalar_one_or_none()
    assert polling_mode_marker is not None
