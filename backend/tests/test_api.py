"""E2E-тесты HTTP-слоя через ASGI-клиент (без сети)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_analytics_report_empty(client):
    r = await client.get("/analytics/report")
    assert r.status_code == 200
    body = r.json()
    assert body["tickets"]["total"] == 0
    assert body["rag"]["total_documents"] == 0


@pytest.mark.asyncio
async def test_settings_default_mode_roundtrip(client):
    r = await client.get("/settings/default-new-ticket-mode")
    assert r.status_code == 200
    assert r.json()["mode_code"] in {"full_ai", "ai_assist", "no_ai"}

    r = await client.put(
        "/settings/default-new-ticket-mode",
        json={"mode_code": "full_ai"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode_code"] == "full_ai"


@pytest.mark.asyncio
async def test_telegram_webhook_creates_ticket(client):
    update = {
        "message": {
            "text": "Здравствуйте, у меня проблема",
            "chat": {"id": 9001},
            "from": {"id": 9001, "first_name": "Тест"},
        }
    }
    r = await client.post("/integrations/telegram/webhook", json=update)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert "ticket_id" in r.json()

    # Проверяем, что чат и тикет появились
    r = await client.get("/chats")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1

    # Список тикетов
    r = await client.get("/tickets")
    assert r.status_code == 200
    assert r.json()["total"] == 1


@pytest.mark.asyncio
async def test_rag_upload_and_list(client):
    files = {"file": ("faq.txt", "График работы: 9-18".encode("utf-8"), "text/plain")}
    data = {"source_name": "faq.txt"}
    r = await client.post("/rag/documents", files=files, data=data)
    assert r.status_code == 200, r.text
    doc_id = r.json()["document_id"]

    r = await client.get("/rag/documents")
    assert r.status_code == 200
    data = r.json()
    ids = [d["id"] for d in data["items"]]
    assert doc_id in ids

    r = await client.delete(f"/rag/documents/{doc_id}")
    assert r.status_code == 200
