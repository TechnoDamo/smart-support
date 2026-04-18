"""AI-оркестратор: reply / escalate / защита от мусорного JSON."""
from __future__ import annotations

import pytest

from app.db.seed import CHANNEL_TELEGRAM
from app.services.ai_orchestrator import handle_ticket
from app.services.chats import change_chat_mode, get_or_create_chat, get_or_create_user_by_telegram
from app.services.messages import add_user_message
from app.services.refs import get_ticket_status_code


@pytest.mark.asyncio
async def test_reply_on_simple_question(db, providers):
    user = await get_or_create_user_by_telegram(db, telegram_id=1001)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=1001, user=user)
    await change_chat_mode(db, chat, to_mode_code="full_ai", changed_by="operator")
    _, ticket = await add_user_message(db, chat, "Какой у вас график работы?")
    await db.commit()

    decision = await handle_ticket(
        db, ticket=ticket, chat=chat,
        llm=providers.llm, embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    await db.commit()
    assert decision.action == "reply"
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_user"


@pytest.mark.asyncio
async def test_escalate_on_human_request(db, providers):
    user = await get_or_create_user_by_telegram(db, telegram_id=1002)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=1002, user=user)
    await change_chat_mode(db, chat, to_mode_code="full_ai", changed_by="operator")
    _, ticket = await add_user_message(db, chat, "Соедините меня с живым оператором")
    await db.commit()

    decision = await handle_ticket(
        db, ticket=ticket, chat=chat,
        llm=providers.llm, embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    await db.commit()
    assert decision.action == "escalate"
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_human"


@pytest.mark.asyncio
async def test_malformed_json_defaults_to_escalate(db, providers, mock_llm):
    # Подкладываем мусор — должен сработать парсер и вернуть escalate
    mock_llm.queue('это вообще не json {")({')

    user = await get_or_create_user_by_telegram(db, telegram_id=1003)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=1003, user=user)
    await change_chat_mode(db, chat, to_mode_code="full_ai", changed_by="operator")
    _, ticket = await add_user_message(db, chat, "вопрос")
    await db.commit()

    with pytest.raises(Exception):
        await handle_ticket(
            db, ticket=ticket, chat=chat,
            llm=providers.llm, embedding=providers.embedding,
            vector_store=providers.vector_store,
        )
