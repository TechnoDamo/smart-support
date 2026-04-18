"""Планировщик: автозакрытие тикетов, outbox, ingestion worker и Telegram polling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Message, Ticket
from app.db.seed import TICKET_STATUS_CLOSED, TICKET_STATUS_PENDING_USER
from app.db.session import session_scope
from app.prompts import load_prompt
from app.providers.llm import LlmMessage
from app.providers.registry import get_providers
from app.services.outbox import process_outbox
from app.services.rag_worker import process_ingestion_jobs
from app.services.refs import get_ticket_status_id
from app.services.telegram_integration import poll_telegram_updates
from app.services.tickets import change_ticket_status


async def _close_inactive_tickets() -> int:
    """Закрывает тикеты, долго висящие в pending_user. Возвращает число закрытых."""
    settings = get_settings()
    providers = get_providers()
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.ticket_inactivity_timeout_minutes
    )
    closed = 0
    async with session_scope() as session:
        pending_user_id = await get_ticket_status_id(session, TICKET_STATUS_PENDING_USER)
        r = await session.execute(
            select(Ticket).where(Ticket.status_id == pending_user_id)
        )
        tickets: list[Ticket] = list(r.scalars())
        for t in tickets:
            rr = await session.execute(
                select(Message.time).where(Message.ticket_id == t.id)
                .order_by(Message.seq.desc()).limit(1)
            )
            last_time = rr.scalar_one_or_none()
            if last_time is None:
                continue
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            if last_time > cutoff:
                continue

            rr = await session.execute(
                select(Message).where(Message.ticket_id == t.id).order_by(Message.seq)
            )
            history = list(rr.scalars())
            convo = "\n".join(f"{m.entity}: {m.text}" for m in history)
            system = load_prompt("ticket_summary")
            try:
                summary = await providers.llm.complete(
                    [LlmMessage(role="system", content=system),
                     LlmMessage(role="user", content=convo)]
                )
            except Exception:
                summary = ""
            t.summary = summary.strip() if summary else None
            await change_ticket_status(
                session, t, TICKET_STATUS_CLOSED,
                changed_by="ai_operator",
                reason="auto_close_inactivity",
            )
            closed += 1
    return closed


async def _process_outbox_tick() -> int:
    providers = get_providers()
    async with session_scope() as session:
        return await process_outbox(session, providers.channel_sender)


async def _process_ingestion_jobs_tick() -> int:
    providers = get_providers()
    async with session_scope() as session:
        return await process_ingestion_jobs(
            session,
            embedding=providers.embedding,
            vector_store=providers.vector_store,
            object_storage=providers.object_storage,
        )


async def _poll_telegram_tick() -> int:
    return await poll_telegram_updates()


def build_scheduler() -> AsyncIOScheduler:
    s = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _close_inactive_tickets, "interval",
        seconds=s.scheduler_ticket_close_interval_seconds,
        id="close_inactive_tickets",
        max_instances=1,
    )
    scheduler.add_job(
        _process_outbox_tick, "interval",
        seconds=s.scheduler_outbox_interval_seconds,
        id="process_outbox",
        max_instances=1,
    )
    scheduler.add_job(
        _process_ingestion_jobs_tick, "interval",
        seconds=s.scheduler_ingestion_retry_interval_seconds,
        id="process_ingestion_jobs",
        max_instances=1,
    )
    if s.channel_telegram_provider == "telegram" and s.telegram_polling_enabled:
        scheduler.add_job(
            _poll_telegram_tick, "interval",
            seconds=s.scheduler_telegram_polling_interval_seconds,
            id="poll_telegram",
            max_instances=1,
        )
    return scheduler


close_inactive_tickets = _close_inactive_tickets
process_outbox_tick = _process_outbox_tick
process_ingestion_jobs_tick = _process_ingestion_jobs_tick
poll_telegram_tick = _poll_telegram_tick
