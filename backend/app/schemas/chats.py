from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.common import ActorEntity, ChatModeCode
from app.schemas.messages import Message


class Channel(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class Chat(BaseModel):
    id: uuid.UUID
    telegram_chat_id: int
    user_id: uuid.UUID
    channel: Channel
    mode_code: ChatModeCode
    active_ticket_id: Optional[uuid.UUID] = None
    updated_at: datetime


class ChatModeEvent(BaseModel):
    from_mode_code: Optional[ChatModeCode] = None
    to_mode_code: ChatModeCode
    changed_by: ActorEntity
    changed_by_user_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None
    created_at: datetime


class ChatDetails(Chat):
    mode_events: list[ChatModeEvent] = []
    messages: list[Message] = []


class ChangeModeRequest(BaseModel):
    to_mode_code: ChatModeCode
    reason: Optional[str] = None


class ChangeModeResponse(BaseModel):
    chat_id: uuid.UUID
    mode_code: ChatModeCode
    changed_at: datetime
