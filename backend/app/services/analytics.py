"""Сборка аналитического отчёта."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Chat,
    ChatMode,
    Message,
    RagDocument,
    RagDocumentChunk,
    RagIngestionJob,
    RagRetrievalEvent,
    RagRetrievalResult,
    Ticket,
    TicketStatus,
    TicketStatusEvent,
    User,
)
from app.schemas.analytics import (
    AiPerformanceBlock,
    AnalyticsReport,
    ChatModeDistribution,
    IngestionJobsCounts,
    MessagesBlock,
    MessagesByEntity,
    RagBlock,
    RetrievalBlock,
    TicketsBlock,
    TicketsByStatus,
    UsersBlock,
)


async def build_report(
    session: AsyncSession,
    *,
    period_from: datetime | None,
    period_to: datetime | None,
) -> AnalyticsReport:
    now = datetime.now(timezone.utc)
    to_ = period_to or now
    from_ = period_from or (to_ - timedelta(days=7))

    # ─── Тикеты ─────────────────────────────────────────────────────────────
    # Карта code → id статусов (и обратная)
    r = await session.execute(select(TicketStatus.id, TicketStatus.code))
    status_code_by_id: dict = {sid: code for sid, code in r.all()}

    total_tickets = (await session.execute(select(func.count(Ticket.id)))).scalar_one()

    by_status_raw = (await session.execute(
        select(Ticket.status_id, func.count(Ticket.id)).group_by(Ticket.status_id)
    )).all()
    by_status_map = {status_code_by_id[sid]: cnt for sid, cnt in by_status_raw}
    by_status = TicketsByStatus(
        pending_ai=by_status_map.get("pending_ai", 0),
        pending_human=by_status_map.get("pending_human", 0),
        pending_user=by_status_map.get("pending_user", 0),
        closed=by_status_map.get("closed", 0),
    )

    opened_in_period = (await session.execute(
        select(func.count(Ticket.id)).where(
            and_(Ticket.time_started >= from_, Ticket.time_started <= to_)
        )
    )).scalar_one()
    closed_in_period = (await session.execute(
        select(func.count(Ticket.id)).where(
            and_(Ticket.time_closed.is_not(None),
                 Ticket.time_closed >= from_, Ticket.time_closed <= to_)
        )
    )).scalar_one()

    r = await session.execute(
        select(Ticket.time_started, Ticket.time_closed).where(
            and_(Ticket.time_closed.is_not(None),
                 Ticket.time_closed >= from_, Ticket.time_closed <= to_)
        )
    )
    durations = [(tc - ts).total_seconds() for ts, tc in r.all() if ts and tc]
    avg_res = sum(durations) / len(durations) if durations else None
    p50 = statistics.median(durations) if durations else None
    if durations:
        ds = sorted(durations)
        idx = max(int(round(0.95 * (len(ds) - 1))), 0)
        p95 = ds[idx]
    else:
        p95 = None

    tickets_block = TicketsBlock(
        total=total_tickets,
        by_status=by_status,
        opened_in_period=opened_in_period,
        closed_in_period=closed_in_period,
        avg_resolution_time_seconds=avg_res,
        resolution_time_p50_seconds=p50,
        resolution_time_p95_seconds=p95,
    )

    # ─── Сообщения ──────────────────────────────────────────────────────────
    total_messages = (await session.execute(select(func.count(Message.id)))).scalar_one()
    in_period = (await session.execute(
        select(func.count(Message.id)).where(
            and_(Message.time >= from_, Message.time <= to_)
        )
    )).scalar_one()
    by_entity_raw = (await session.execute(
        select(Message.entity, func.count(Message.id))
        .where(and_(Message.time >= from_, Message.time <= to_))
        .group_by(Message.entity)
    )).all()
    by_entity_map = dict(by_entity_raw)
    by_entity = MessagesByEntity(
        user=int(by_entity_map.get("user", 0)),
        ai_operator=int(by_entity_map.get("ai_operator", 0)),
        operator=int(by_entity_map.get("operator", 0)),
    )
    # Среднее число сообщений на тикет периода
    r = await session.execute(
        select(func.count(Message.id)).select_from(Message)
        .join(Ticket, Ticket.id == Message.ticket_id)
        .where(and_(Ticket.time_started >= from_, Ticket.time_started <= to_))
    )
    msgs_in_period_tickets = r.scalar_one()
    avg_per_ticket = (msgs_in_period_tickets / opened_in_period) if opened_in_period else None

    messages_block = MessagesBlock(
        total=total_messages,
        in_period=in_period,
        by_entity=by_entity,
        avg_per_ticket=avg_per_ticket,
    )

    # ─── AI Performance ─────────────────────────────────────────────────────
    closed_status_id = next((sid for sid, code in status_code_by_id.items() if code == "closed"), None)
    pending_human_id = next((sid for sid, code in status_code_by_id.items() if code == "pending_human"), None)

    tickets_closed_by_ai = (await session.execute(
        select(func.count(TicketStatusEvent.id.distinct())).where(
            and_(
                TicketStatusEvent.to_status_id == closed_status_id,
                TicketStatusEvent.changed_by == "ai_operator",
                TicketStatusEvent.created_at >= from_, TicketStatusEvent.created_at <= to_,
            )
        )
    )).scalar_one()

    tickets_escalated_to_human = (await session.execute(
        select(func.count(TicketStatusEvent.id.distinct())).where(
            and_(
                TicketStatusEvent.to_status_id == pending_human_id,
                TicketStatusEvent.changed_by == "ai_operator",
                TicketStatusEvent.created_at >= from_, TicketStatusEvent.created_at <= to_,
            )
        )
    )).scalar_one()

    total_ai_decisions = tickets_closed_by_ai + tickets_escalated_to_human
    resolution_rate = (tickets_closed_by_ai / total_ai_decisions) if total_ai_decisions else 0.0
    escalation_rate = (tickets_escalated_to_human / total_ai_decisions) if total_ai_decisions else 0.0

    # avg_messages_before_escalation — среднее число сообщений до эскалации
    r = await session.execute(
        select(TicketStatusEvent.ticket_id, TicketStatusEvent.created_at).where(
            and_(
                TicketStatusEvent.to_status_id == pending_human_id,
                TicketStatusEvent.changed_by == "ai_operator",
                TicketStatusEvent.created_at >= from_, TicketStatusEvent.created_at <= to_,
            )
        )
    )
    esc_events = r.all()
    counts: list[int] = []
    for ticket_id, event_at in esc_events:
        rr = await session.execute(
            select(func.count(Message.id)).where(
                Message.ticket_id == ticket_id, Message.time <= event_at
            )
        )
        counts.append(int(rr.scalar_one()))
    avg_msgs_before_esc = (sum(counts) / len(counts)) if counts else None

    # chat_mode_distribution (текущее распределение чатов)
    r = await session.execute(
        select(ChatMode.code, func.count(Chat.id)).join(Chat, Chat.mode_id == ChatMode.id)
        .group_by(ChatMode.code)
    )
    mode_counts = dict(r.all())
    mode_dist = ChatModeDistribution(
        full_ai=int(mode_counts.get("full_ai", 0)),
        ai_assist=int(mode_counts.get("ai_assist", 0)),
        no_ai=int(mode_counts.get("no_ai", 0)),
    )

    ai_block = AiPerformanceBlock(
        tickets_closed_by_ai=int(tickets_closed_by_ai),
        tickets_escalated_to_human=int(tickets_escalated_to_human),
        resolution_rate=resolution_rate,
        escalation_rate=escalation_rate,
        avg_messages_before_escalation=avg_msgs_before_esc,
        chat_mode_distribution=mode_dist,
    )

    # ─── RAG ────────────────────────────────────────────────────────────────
    total_documents = (await session.execute(select(func.count(RagDocument.id)))).scalar_one()
    active_documents = (await session.execute(
        select(func.count(RagDocument.id)).where(RagDocument.deleted_at.is_(None))
    )).scalar_one()
    deleted_documents = total_documents - active_documents
    total_chunks = (await session.execute(
        select(func.count(RagDocumentChunk.id)).where(RagDocumentChunk.deleted_at.is_(None))
    )).scalar_one()

    r = await session.execute(
        select(RagIngestionJob.status, func.count(RagIngestionJob.id))
        .group_by(RagIngestionJob.status)
    )
    ing_map = dict(r.all())
    ingestion = IngestionJobsCounts(
        queued=int(ing_map.get("queued", 0)),
        processing=int(ing_map.get("processing", 0)),
        done=int(ing_map.get("done", 0)),
        failed=int(ing_map.get("failed", 0)),
    )

    total_events = (await session.execute(select(func.count(RagRetrievalEvent.id)))).scalar_one()
    events_in_period = (await session.execute(
        select(func.count(RagRetrievalEvent.id))
        .where(and_(RagRetrievalEvent.created_at >= from_,
                    RagRetrievalEvent.created_at <= to_))
    )).scalar_one()

    r = await session.execute(
        select(func.avg(RagRetrievalResult.score)).select_from(RagRetrievalResult)
        .join(RagRetrievalEvent, RagRetrievalEvent.id == RagRetrievalResult.retrieval_event_id)
        .where(and_(RagRetrievalEvent.created_at >= from_,
                    RagRetrievalEvent.created_at <= to_))
    )
    avg_score = r.scalar_one_or_none()

    r = await session.execute(
        select(
            func.count(RagRetrievalResult.id),
            func.sum(func.cast(RagRetrievalResult.used_in_answer, type_=func.count().type)),
        ).select_from(RagRetrievalResult)
        .join(RagRetrievalEvent, RagRetrievalEvent.id == RagRetrievalResult.retrieval_event_id)
        .where(and_(RagRetrievalEvent.created_at >= from_,
                    RagRetrievalEvent.created_at <= to_))
    )
    row = r.one()
    total_res = int(row[0] or 0)
    used_res = int(row[1] or 0)
    hit_rate = (used_res / total_res) if total_res else None

    rag_block = RagBlock(
        total_documents=int(total_documents),
        active_documents=int(active_documents),
        deleted_documents=int(deleted_documents),
        total_chunks=int(total_chunks),
        ingestion_jobs=ingestion,
        retrieval=RetrievalBlock(
            total_events=int(total_events),
            events_in_period=int(events_in_period),
            avg_score=float(avg_score) if avg_score is not None else None,
            hit_rate=hit_rate,
        ),
    )

    # ─── Пользователи ───────────────────────────────────────────────────────
    total_users = (await session.execute(select(func.count(User.id)))).scalar_one()
    new_in_period = (await session.execute(
        select(func.count(User.id)).where(
            and_(User.created_at >= from_, User.created_at <= to_)
        )
    )).scalar_one()

    # returning — были до периода, но проявили активность в периоде
    r = await session.execute(
        select(func.count(func.distinct(Chat.user_id))).select_from(Chat)
        .join(Message, Message.chat_id == Chat.id)
        .where(and_(Message.time >= from_, Message.time <= to_))
        .join(User, User.id == Chat.user_id)
        .where(User.created_at < from_)
    )
    returning = int(r.scalar_one() or 0)

    r = await session.execute(select(func.count(Ticket.id)))
    total_tickets_all = int(r.scalar_one())
    avg_tpu = (total_tickets_all / total_users) if total_users else None

    users_block = UsersBlock(
        total=int(total_users),
        new_in_period=int(new_in_period),
        returning_users_in_period=returning,
        avg_tickets_per_user=avg_tpu,
    )

    return AnalyticsReport(
        generated_at=now,
        period={"from": from_, "to": to_},
        tickets=tickets_block,
        messages=messages_block,
        ai_performance=ai_block,
        rag=rag_block,
        users=users_block,
    )
