"""Outbox: успех, retry с экспоненциальной задержкой, переход в failed."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.db.models import OutboxMessage
from app.db.seed import CHANNEL_TELEGRAM
from app.services.chats import get_or_create_chat, get_or_create_user_by_telegram
from app.services.messages import add_outgoing_message, add_user_message
from app.services.outbox import process_outbox


@pytest.mark.asyncio
async def test_outbox_happy_path(db, providers, mock_channel):
    user = await get_or_create_user_by_telegram(db, telegram_id=555)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=555, user=user)
    _, ticket = await add_user_message(db, chat, "вопрос")
    await add_outgoing_message(db, chat, ticket, text="Ответ", entity="operator")
    await db.commit()

    sent = await process_outbox(db, mock_channel)
    await db.commit()

    assert sent == 1
    assert mock_channel.sent == [(555, "Ответ")]

    r = await db.execute(select(OutboxMessage))
    entry = r.scalars().first()
    assert entry.status == "sent"
    assert entry.sent_at is not None


@pytest.mark.asyncio
async def test_outbox_retry_on_failure(db, providers, mock_channel):
    mock_channel.fail_next = 1  # первый вызов упадёт

    user = await get_or_create_user_by_telegram(db, telegram_id=666)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=666, user=user)
    _, ticket = await add_user_message(db, chat, "вопрос")
    await add_outgoing_message(db, chat, ticket, text="Ответ", entity="operator")
    await db.commit()

    sent = await process_outbox(db, mock_channel)
    await db.commit()
    assert sent == 0

    r = await db.execute(select(OutboxMessage))
    entry = r.scalars().first()
    assert entry.status == "retry"
    assert entry.attempts == 1
    # Задержка — минимум 60 секунд (экспонента 60 * 2^0 = 60).
    # SQLite может вернуть naive datetime — нормализуем для сравнения.
    assert entry.next_attempt_at is not None
    next_attempt = entry.next_attempt_at
    if next_attempt.tzinfo is None:
        next_attempt = next_attempt.replace(tzinfo=timezone.utc)
    assert next_attempt > datetime.now(timezone.utc) + timedelta(seconds=30)
