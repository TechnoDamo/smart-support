from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Period(BaseModel):
    from_: datetime
    to: datetime

    model_config = {"populate_by_name": True, "serialize_by_alias": True}

    # 'from' — зарезервированное слово в Python; мапим на alias 'from' в JSON.
    def model_dump(self, **kwargs):  # type: ignore[override]
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)


class TicketsByStatus(BaseModel):
    pending_ai: int
    pending_human: int
    pending_user: int
    closed: int


class TicketsBlock(BaseModel):
    total: int
    by_status: TicketsByStatus
    opened_in_period: int
    closed_in_period: int
    avg_resolution_time_seconds: Optional[float] = None
    resolution_time_p50_seconds: Optional[float] = None
    resolution_time_p95_seconds: Optional[float] = None


class MessagesByEntity(BaseModel):
    user: int
    ai_operator: int
    operator: int


class MessagesBlock(BaseModel):
    total: int
    in_period: int
    by_entity: MessagesByEntity
    avg_per_ticket: Optional[float] = None


class ChatModeDistribution(BaseModel):
    full_ai: int
    ai_assist: int
    no_ai: int


class AiPerformanceBlock(BaseModel):
    tickets_closed_by_ai: int
    tickets_escalated_to_human: int
    resolution_rate: float
    escalation_rate: float
    avg_messages_before_escalation: Optional[float] = None
    chat_mode_distribution: ChatModeDistribution


class IngestionJobsCounts(BaseModel):
    queued: int
    processing: int
    done: int
    failed: int


class RetrievalBlock(BaseModel):
    total_events: int
    events_in_period: int
    avg_score: Optional[float] = None
    hit_rate: Optional[float] = None


class RagBlock(BaseModel):
    total_documents: int
    active_documents: int
    deleted_documents: int
    total_chunks: int
    ingestion_jobs: IngestionJobsCounts
    retrieval: RetrievalBlock


class UsersBlock(BaseModel):
    total: int
    new_in_period: int
    returning_users_in_period: int
    avg_tickets_per_user: Optional[float] = None


class AnalyticsReport(BaseModel):
    generated_at: datetime
    period: dict  # {"from": datetime, "to": datetime}
    tickets: TicketsBlock
    messages: MessagesBlock
    ai_performance: AiPerformanceBlock
    rag: RagBlock
    users: UsersBlock
