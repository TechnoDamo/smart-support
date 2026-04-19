"""Интеграция с Telegram: обработка webhook и опциональный polling."""

from __future__ import annotations

import hashlib
import logging
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

logger = logging.getLogger(__name__)

SETTING_TELEGRAM_POLLING_OFFSET = "telegram_polling_offset"
SETTING_TELEGRAM_POLLING_WEBHOOK_CLEARED = "telegram_polling_webhook_cleared"


async def dispatch_ai_for_ticket(ticket_id, chat_id) -> None:
    """Отдельно запускает AI после фиксации входящего сообщения.

    Любые ошибки логируются с трейсбэком — фоновая задача не должна
    «проглатывать» сбои провайдеров молча.
    """
    try:
        providers = get_providers()
        async with session_scope() as session:
            ticket = (
                await session.execute(select(Ticket).where(Ticket.id == ticket_id))
            ).scalar_one_or_none()
            chat = (
                await session.execute(select(Chat).where(Chat.id == chat_id))
            ).scalar_one_or_none()
            if ticket is None or chat is None:
                logger.warning(
                    "dispatch_ai_for_ticket: ticket=%s or chat=%s not found",
                    ticket_id, chat_id,
                )
                return
            await maybe_dispatch_ai(
                session,
                ticket=ticket,
                chat=chat,
                llm=providers.llm,
                embedding=providers.embedding,
                vector_store=providers.vector_store,
            )
    except Exception:
        logger.exception(
            "dispatch_ai_for_ticket failed (ticket=%s, chat=%s)",
            ticket_id, chat_id,
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
    value = (
        await session.execute(
            select(AppSetting.value).where(
                AppSetting.key == SETTING_TELEGRAM_POLLING_OFFSET
            )
        )
    ).scalar_one_or_none()
    return int(value) if value is not None else None


async def _set_polling_offset(session: AsyncSession, offset: int) -> None:
    setting = (
        await session.execute(
            select(AppSetting).where(AppSetting.key == SETTING_TELEGRAM_POLLING_OFFSET)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if setting is None:
        session.add(
            AppSetting(
                key=SETTING_TELEGRAM_POLLING_OFFSET, value=str(offset), updated_at=now
            )
        )
    else:
        setting.value = str(offset)
        setting.updated_at = now


def _polling_marker(bot_token: str) -> str:
    """Возвращает безопасный маркер токена для app_settings."""
    return hashlib.sha256(bot_token.encode("utf-8")).hexdigest()


async def _get_app_setting_value(session: AsyncSession, key: str) -> str | None:
    return (
        await session.execute(select(AppSetting.value).where(AppSetting.key == key))
    ).scalar_one_or_none()


async def _set_app_setting_value(session: AsyncSession, key: str, value: str) -> None:
    setting = (
        await session.execute(select(AppSetting).where(AppSetting.key == key))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if setting is None:
        session.add(AppSetting(key=key, value=value, updated_at=now))
    else:
        setting.value = value
        setting.updated_at = now


async def _delete_telegram_webhook(
    client: httpx.AsyncClient,
    *,
    settings,
) -> None:
    """Удаляет webhook у бота, чтобы polling работал без конфликта 409."""
    url = (
        f"{settings.telegram_api_base_url.rstrip('/')}"
        f"/bot{settings.telegram_bot_token}/deleteWebhook"
    )
    response = await client.post(
        url,
        params={"drop_pending_updates": "false"},
    )
    response.raise_for_status()


async def _ensure_polling_mode(client: httpx.AsyncClient, *, settings) -> None:
    """Гарантирует, что Telegram-бот переведён в polling-only режим."""
    marker = _polling_marker(settings.telegram_bot_token)
    async with session_scope() as session:
        current = await _get_app_setting_value(
            session, SETTING_TELEGRAM_POLLING_WEBHOOK_CLEARED
        )
        if current == marker:
            return

    await _delete_telegram_webhook(client, settings=settings)

    async with session_scope() as session:
        await _set_app_setting_value(
            session, SETTING_TELEGRAM_POLLING_WEBHOOK_CLEARED, marker
        )


async def poll_telegram_updates() -> int:
    """Забирает пачку update-ов через getUpdates и обрабатывает их последовательно."""
    import logging

    logger = logging.getLogger(__name__)

    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, skipping polling")
        return 0

    logger.debug("Polling Telegram for updates...")

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
    async with httpx.AsyncClient(
        timeout=settings.telegram_polling_request_timeout_seconds
    ) as client:
        await _ensure_polling_mode(client, settings=settings)
        response = await client.get(url, params=params)
        if response.status_code == 409:
            logger.warning(
                "Telegram getUpdates returned 409 Conflict, deleting webhook and retrying once"
            )
            await _delete_telegram_webhook(client, settings=settings)
            async with session_scope() as session:
                await _set_app_setting_value(
                    session,
                    SETTING_TELEGRAM_POLLING_WEBHOOK_CLEARED,
                    _polling_marker(settings.telegram_bot_token),
                )
            response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    updates = payload.get("result") or []
    if updates:
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Received {len(updates)} update(s) from Telegram")
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

    if processed > 0:
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Processed {processed} message(s) from Telegram")

    return processed
