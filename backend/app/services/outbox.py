"""Обработчик outbox: забирает pending/retry и шлёт через провайдер канала."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import OutboxMessage
from app.providers.channel import ChannelSender


async def process_outbox(session: AsyncSession, sender: ChannelSender, *, limit: int = 50) -> int:
    """Отправляет pending/retry сообщения. Возвращает число успешно отправленных."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    stmt = (
        select(OutboxMessage)
        .where(OutboxMessage.status.in_(("pending", "retry")))
        .where((OutboxMessage.next_attempt_at.is_(None)) | (OutboxMessage.next_attempt_at <= now))
        .limit(limit)
    )
    r = await session.execute(stmt)
    items: list[OutboxMessage] = list(r.scalars())

    sent = 0
    for item in items:
        try:
            await sender.send(
                external_chat_id=int(item.payload["external_chat_id"]),
                text=str(item.payload["text"]),
            )
        except Exception as exc:
            item.attempts += 1
            item.error_message = str(exc)
            if item.attempts >= settings.outbox_max_retries:
                item.status = "failed"
            else:
                item.status = "retry"
                # экспоненциальная задержка, ограниченная 10 минутами
                delay = min(60 * (2 ** (item.attempts - 1)), 600)
                item.next_attempt_at = now + timedelta(seconds=delay)
            continue
        item.status = "sent"
        item.sent_at = datetime.now(timezone.utc)
        item.error_message = None
        sent += 1
    return sent
