"""Аналитический отчёт собирается без ошибок."""
from __future__ import annotations

import pytest

from app.db.seed import CHANNEL_TELEGRAM
from app.services.analytics import build_report
from app.services.chats import get_or_create_chat, get_or_create_user_by_telegram
from app.services.messages import add_outgoing_message, add_user_message


@pytest.mark.asyncio
async def test_report_on_empty_db(db):
    report = await build_report(db, period_from=None, period_to=None)
    assert report.tickets.total == 0
    assert report.messages.total == 0
    assert report.users.total == 0


@pytest.mark.asyncio
async def test_report_with_data(db):
    user = await get_or_create_user_by_telegram(db, telegram_id=777)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=777, user=user)
    _, ticket = await add_user_message(db, chat, "вопрос 1")
    await add_outgoing_message(db, chat, ticket, text="ответ", entity="ai_operator")
    await add_user_message(db, chat, "ещё вопрос")
    await db.commit()

    report = await build_report(db, period_from=None, period_to=None)
    assert report.tickets.total == 1
    assert report.messages.total == 3
    assert report.messages.by_entity.user == 2
    assert report.messages.by_entity.ai_operator == 1
    assert report.users.total == 1
