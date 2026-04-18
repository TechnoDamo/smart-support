from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ActorEntity, TicketStatusCode


class Ticket(BaseModel):
    id: uuid.UUID
    title: Optional[str] = None
    summary: Optional[str] = None
    status_code: TicketStatusCode
    chat_id: uuid.UUID
    time_started: datetime
    time_closed: Optional[datetime] = None


class TicketStatusEvent(BaseModel):
    from_status_code: Optional[TicketStatusCode] = None
    to_status_code: TicketStatusCode
    changed_by: ActorEntity
    changed_by_user_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None
    created_at: datetime


class TicketDetails(Ticket):
    status_events: list[TicketStatusEvent] = []


class TicketRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class TicketRenameResponse(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: datetime
