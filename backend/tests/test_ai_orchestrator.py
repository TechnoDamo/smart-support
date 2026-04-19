"""AI-оркестратор: reply / escalate / защита от мусорного JSON."""
from __future__ import annotations

import uuid

import pytest

from app.db.models import RagDocumentChunk
from app.db.seed import CHANNEL_TELEGRAM
from app.services import ai_orchestrator
from app.services.ai_orchestrator import handle_ticket, maybe_dispatch_ai
from app.services.chats import change_chat_mode, get_or_create_chat, get_or_create_user_by_telegram
from app.services.messages import add_user_message
from app.services.refs import get_ticket_status_code


def _fake_hit(text: str) -> list[tuple[RagDocumentChunk, float]]:
    chunk = RagDocumentChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        chunk_index=0,
        chunk_text=text,
        chunk_token_count=len(text.split()),
        qdrant_point_id=str(uuid.uuid4()),
        extra_metadata={"source_name": "faq.txt"},
    )
    return [(chunk, 0.91)]


@pytest.mark.asyncio
async def test_reply_on_simple_question(db, providers, monkeypatch):
    async def _hits(*args, **kwargs):
        return _fake_hit("График работы службы поддержки: по будням с 9:00 до 18:00.")

    monkeypatch.setattr(
        ai_orchestrator,
        "retrieve",
        _hits,
    )
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
async def test_escalate_on_human_request(db, providers, monkeypatch):
    async def _hits(*args, **kwargs):
        return _fake_hit("База знаний нашла релевантный фрагмент, но пользователь просит человека.")

    monkeypatch.setattr(
        ai_orchestrator,
        "retrieve",
        _hits,
    )
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
async def test_no_knowledge_escalates_to_human(db, providers, monkeypatch):
    async def _no_hits(*args, **kwargs):
        return []

    monkeypatch.setattr(ai_orchestrator, "retrieve", _no_hits)

    user = await get_or_create_user_by_telegram(db, telegram_id=1003)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=1003, user=user)
    await change_chat_mode(db, chat, to_mode_code="full_ai", changed_by="operator")
    _, ticket = await add_user_message(db, chat, "Почему система не запускается?")
    await db.commit()

    decision = await handle_ticket(
        db, ticket=ticket, chat=chat,
        llm=providers.llm, embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    await db.commit()

    assert decision.action == "escalate"
    assert "оператору" in decision.response_text.lower()
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_human"


@pytest.mark.asyncio
async def test_handoff_text_switches_ticket_to_pending_human(db, providers, mock_llm, monkeypatch):
    async def _hits(*args, **kwargs):
        return _fake_hit("Для сброса контроллера удерживайте кнопку RESET 10 секунд.")

    monkeypatch.setattr(ai_orchestrator, "retrieve", _hits)
    mock_llm.queue(
        '{"action":"reply","response_text":"Передаю ваш вопрос оператору, ожидайте.","escalation_reason":null}'
    )

    user = await get_or_create_user_by_telegram(db, telegram_id=1004)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=1004, user=user)
    await change_chat_mode(db, chat, to_mode_code="full_ai", changed_by="operator")
    _, ticket = await add_user_message(db, chat, "Помогите со сбросом контроллера")
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
async def test_escalate_action_with_answer_text_replies_to_user(db, providers, mock_llm, monkeypatch):
    async def _hits(*args, **kwargs):
        return _fake_hit("График работы службы поддержки: по будням с 9:00 до 18:00.")

    monkeypatch.setattr(ai_orchestrator, "retrieve", _hits)
    mock_llm.queue(
        '{"action":"escalate","response_text":"Служба поддержки работает по будням с 9:00 до 18:00.","escalation_reason":"низкая уверенность"}'
    )

    user = await get_or_create_user_by_telegram(db, telegram_id=1005)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=1005, user=user)
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
    assert "9:00" in decision.response_text
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_user"


@pytest.mark.asyncio
async def test_malformed_json_falls_back_to_context_reply(db, providers, mock_llm, monkeypatch):
    async def _hits(*args, **kwargs):
        return _fake_hit("Для сброса контроллера удерживайте кнопку RESET 10 секунд.")

    monkeypatch.setattr(ai_orchestrator, "retrieve", _hits)
    mock_llm.queue('это вообще не json {")({')

    user = await get_or_create_user_by_telegram(db, telegram_id=1006)
    chat = await get_or_create_chat(db, channel_code=CHANNEL_TELEGRAM,
                                    telegram_chat_id=1006, user=user)
    await change_chat_mode(db, chat, to_mode_code="full_ai", changed_by="operator")
    _, ticket = await add_user_message(db, chat, "Как сбросить контроллер?")
    await db.commit()

    decision = await handle_ticket(
        db, ticket=ticket, chat=chat,
        llm=providers.llm, embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    await db.commit()

    assert decision.action == "reply"
    assert "базе знаний" in decision.response_text.lower()
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_user"


@pytest.mark.asyncio
async def test_pending_ai_dispatches_even_in_ai_assist_mode(db, providers, monkeypatch):
    async def _hits(*args, **kwargs):
        return _fake_hit("ГОСТ Р 52931-2008 упоминается в требованиях к техническим средствам.")

    monkeypatch.setattr(ai_orchestrator, "retrieve", _hits)

    user = await get_or_create_user_by_telegram(db, telegram_id=1007)
    chat = await get_or_create_chat(
        db,
        channel_code=CHANNEL_TELEGRAM,
        telegram_chat_id=1007,
        user=user,
    )
    # По умолчанию чат создаётся в ai_assist, но статус тикета — pending_ai.
    _, ticket = await add_user_message(db, chat, "ГОСТ Р 52931")
    await db.commit()

    decision = await maybe_dispatch_ai(
        db,
        ticket=ticket,
        chat=chat,
        llm=providers.llm,
        embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    await db.commit()

    assert decision is not None
    assert decision.action == "reply"
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_user"


@pytest.mark.asyncio
async def test_pending_ai_unknown_question_moves_to_pending_human(db, providers, monkeypatch):
    async def _no_hits(*args, **kwargs):
        return []

    monkeypatch.setattr(ai_orchestrator, "retrieve", _no_hits)

    user = await get_or_create_user_by_telegram(db, telegram_id=1008)
    chat = await get_or_create_chat(
        db,
        channel_code=CHANNEL_TELEGRAM,
        telegram_chat_id=1008,
        user=user,
    )
    _, ticket = await add_user_message(db, chat, "Что у вас по неизвестной внутренней ошибке XJ-443?")
    await db.commit()

    decision = await maybe_dispatch_ai(
        db,
        ticket=ticket,
        chat=chat,
        llm=providers.llm,
        embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    await db.commit()

    assert decision is not None
    assert decision.action == "escalate"
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_human"


@pytest.mark.asyncio
async def test_pending_ai_explicit_human_request_replies_and_moves_to_pending_human(
    db, providers, monkeypatch
):
    async def _hits(*args, **kwargs):
        return _fake_hit("Если пользователь просит человека, нужно передать тикет оператору.")

    monkeypatch.setattr(ai_orchestrator, "retrieve", _hits)

    user = await get_or_create_user_by_telegram(db, telegram_id=1009)
    chat = await get_or_create_chat(
        db,
        channel_code=CHANNEL_TELEGRAM,
        telegram_chat_id=1009,
        user=user,
    )
    _, ticket = await add_user_message(db, chat, "Позови человека")
    await db.commit()

    decision = await maybe_dispatch_ai(
        db,
        ticket=ticket,
        chat=chat,
        llm=providers.llm,
        embedding=providers.embedding,
        vector_store=providers.vector_store,
    )
    await db.commit()

    assert decision is not None
    assert decision.action == "escalate"
    assert "оператор" in decision.response_text.lower()
    code = await get_ticket_status_code(db, ticket.status_id)
    assert code == "pending_human"
