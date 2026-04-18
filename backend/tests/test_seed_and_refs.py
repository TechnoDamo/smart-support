"""Сид-данные и справочные lookup-функции работают."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import ChatMode, TicketStatus
from app.services.refs import (
    get_channel_id,
    get_chat_mode_id,
    get_default_chat_mode_code,
    get_default_rag_collection,
    get_ticket_status_id,
)


@pytest.mark.asyncio
async def test_seed_contains_all_statuses(db):
    r = await db.execute(select(TicketStatus.code))
    codes = {c for (c,) in r.all()}
    assert codes == {"pending_ai", "pending_human", "pending_user", "closed"}


@pytest.mark.asyncio
async def test_seed_contains_all_modes(db):
    r = await db.execute(select(ChatMode.code))
    codes = {c for (c,) in r.all()}
    assert codes == {"full_ai", "no_ai", "ai_assist"}


@pytest.mark.asyncio
async def test_refs_lookups(db):
    # Прямые lookup-и по кодам
    assert await get_channel_id(db, "telegram")
    assert await get_chat_mode_id(db, "full_ai")
    assert await get_ticket_status_id(db, "pending_ai")
    assert await get_default_chat_mode_code(db) in {"full_ai", "ai_assist", "no_ai"}
    coll = await get_default_rag_collection(db)
    assert coll.code == "support_knowledge"
