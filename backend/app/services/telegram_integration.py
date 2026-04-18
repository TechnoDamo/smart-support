"""Интеграция с Telegram: обработка webhook и опциональный polling."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AppSetting, Chat, Ticket
from app.db.seed import CHANNEL_TELEGRAM
from app.db.session import session_scope
from app.providers.registry import get_providers
from app.services.ai_orchestrator import maybe_dispatch_ai
from app.services.chats import get_or_create_chat, get_or_create_user_by_telegram
from app.services.messages import add_user_message

SETTING_TELEGRAM_POLLING_OFFSET = "telegram_polling_offset"


async def dispatch_ai_for_ticket(ticket_id, chat_id) -> None:
    """Отдельно запускает AI после фиксации входящего сообщения."""
    providers = get_providers()
    async with session_scope() as session:
        ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
        chat = (await session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
        if ticket is None or chat is None:
            return
        await maybe_dispatch_ai(
            session,
            ticket=ticket,
            chat=chat,
            llm=providers.llm,
            embedding=providers.embedding,
            vector_store=providers.vector_store,
        )


async def process_telegram_update(session: AsyncSession, update: dict) -> dict:
    """Превращает Telegram update в пользователя, чат, сообщение и тикет."""
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return {"ok": True, "skipped": True}

    chat_payload = msg.get("chat") or {}
    from_payload = msg.get("from") or {}
    telegram_chat_id = int(chat_payload["id"])
    telegram_user_id = int(from_payload.get("id") or telegram_chat_id)
    text = str(msg["text"])

    user = await get_or_create_user_by_telegram(
        session,
        telegram_id=telegram_user_id,
        first_name=from_payload.get("first_name"),
        last_name=from_payload.get("last_name"),
        username=from_payload.get("username"),
    )
    chat = await get_or_create_chat(
        session,
        channel_code=CHANNEL_TELEGRAM,
        telegram_chat_id=telegram_chat_id,
        user=user,
    )
    message, ticket = await add_user_message(session, chat, text)
    await session.flush()
    return {
        "ok": True,
        "skipped": False,
        "message_id": str(message.id),
        "ticket_id": str(ticket.id),
        "chat_id": str(chat.id),
        "ticket_obj_id": ticket.id,
        "chat_obj_id": chat.id,
    }


async def _get_polling_offset(session: AsyncSession) -> int | None:
    value = (await session.execute(
        select(AppSetting.value).where(AppSetting.key == SETTING_TELEGRAM_POLLING_OFFSET)
    )).scalar_one_or_none()
    return int(value) if value is not None else None


async def _set_polling_offset(session: AsyncSession, offset: int) -> None:
    setting = (await session.execute(
        select(AppSetting).where(AppSetting.key == SETTING_TELEGRAM_POLLING_OFFSET)
    )).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if setting is None:
        session.add(AppSetting(key=SETTING_TELEGRAM_POLLING_OFFSET, value=str(offset), updated_at=now))
    else:
        setting.value = str(offset)
        setting.updated_at = now


async def poll_telegram_updates() -> int:
    """Забирает пачку update-ов через getUpdates и обрабатывает их последовательно."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        return 0

    async with session_scope() as session:
        offset = await _get_polling_offset(session)

    params = {
        "limit": settings.telegram_polling_limit,
        "timeout": settings.telegram_polling_timeout_seconds,
        "allowed_updates": ["message", "edited_message"],
    }
    if offset is not None:
        params["offset"] = offset

    url = f"{settings.telegram_api_base_url.rstrip('/')}/bot{settings.telegram_bot_token}/getUpdates"
    async with httpx.AsyncClient(timeout=settings.telegram_polling_request_timeout_seconds) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    updates = payload.get("result") or []
    processed = 0
    for update in updates:
        update_id = int(update.get("update_id", 0))
        ticket_id = None
        chat_id = None
        async with session_scope() as session:
            result = await process_telegram_update(session, update)
            await _set_polling_offset(session, update_id + 1)
            if not result.get("skipped"):
                ticket_id = result["ticket_obj_id"]
                chat_id = result["chat_obj_id"]
                processed += 1
        if ticket_id is not None and chat_id is not None:
            await dispatch_ai_for_ticket(ticket_id, chat_id)
    return processed
