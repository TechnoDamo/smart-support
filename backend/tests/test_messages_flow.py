"""Поток сообщений: создание тикета, смена статуса, добавление в outbox."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import OutboxMessage, Ticket
from app.db.seed import CHANNEL_TELEGRAM
from app.services.chats import change_chat_mode, get_or_create_chat, get_or_create_user_by_telegram
from app.services.messages import add_outgoing_message, add_user_message
from app.services.refs import get_ticket_status_code


@pytest.mark.asyncio
async def test_user_message_creates_ticket_in_mode_status(db):
    user = await get_or_create_user_by_telegram(db, telegram_id=111, first_name="Ivan")
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=111, user=user)
    # Дефолтный режим — ai_assist, следовательно тикет → pending_ai
    message, ticket = await add_user_message(db, chat, "Здравствуйте, нужна помощь")
    await db.commit()

    assert message.entity == "user"
    assert message.seq == 1
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_ai"


@pytest.mark.asyncio
async def test_mode_change_syncs_ticket_status(db):
    user = await get_or_create_user_by_telegram(db, telegram_id=222)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=222, user=user)
    _, ticket = await add_user_message(db, chat, "вопрос")
    await change_chat_mode(db, chat, to_mode_code="no_ai", changed_by="operator",
                           reason="тест")
    await db.commit()

    refetched = (await db.execute(select(Ticket).where(Ticket.id == ticket.id))).scalar_one()
    code = await get_ticket_status_code(db, refetched.status_id)
    assert code == "pending_human"


@pytest.mark.asyncio
async def test_outgoing_creates_outbox_entry(db):
    user = await get_or_create_user_by_telegram(db, telegram_id=333)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=333, user=user)
    _, ticket = await add_user_message(db, chat, "вопрос")
    msg = await add_outgoing_message(db, chat, ticket, text="Ответ", entity="operator")
    await db.commit()

    r = await db.execute(select(OutboxMessage).where(OutboxMessage.message_id == msg.id))
    entry = r.scalar_one()
    assert entry.status == "pending"
    assert entry.payload["text"] == "Ответ"
    assert entry.payload["external_chat_id"] == 333


@pytest.mark.asyncio
async def test_pending_user_returns_to_pending_ai_on_user_reply(db):
    user = await get_or_create_user_by_telegram(db, telegram_id=444)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=444, user=user)
    _, ticket = await add_user_message(db, chat, "вопрос")
    # AI отвечает и ставит pending_user
    await add_outgoing_message(db, chat, ticket, text="Ответ", entity="ai_operator",
                                set_status="pending_user")
    # Пользователь отвечает снова
    _, ticket2 = await add_user_message(db, chat, "ещё вопрос")
    assert ticket.id == ticket2.id
    code = await get_ticket_status_code(db, ticket2.status_id)
    assert code == "pending_ai"
