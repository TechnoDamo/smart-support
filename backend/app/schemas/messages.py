from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ActorEntity


class Message(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    ticket_id: uuid.UUID
    entity: ActorEntity
    seq: int
    text: str
    time: datetime


class SendMessageRequest(BaseModel):
    ticket_id: uuid.UUID
    text: str = Field(min_length=1)
