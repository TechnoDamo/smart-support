"""Webhook Telegram: приём сообщений пользователя → запуск AI-оркестратора."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request

from app.api.deps import DbSession
from app.services.telegram_integration import dispatch_ai_for_ticket, process_telegram_update

router = APIRouter(prefix="/integrations/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    session=DbSession,
):
    """Минимально-совместимый приём обновлений Telegram Bot API."""
    result = await process_telegram_update(session, await request.json())
    if result.get("skipped"):
        return {"ok": True, "skipped": True}

    background.add_task(
        dispatch_ai_for_ticket,
        result["ticket_obj_id"],
        result["chat_obj_id"],
    )
    return {
        "ok": True,
        "message_id": result["message_id"],
        "ticket_id": result["ticket_id"],
    }
