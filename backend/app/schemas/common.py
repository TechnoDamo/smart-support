"""Общие Pydantic-схемы."""
from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

TicketStatusCode = Literal["pending_ai", "pending_human", "pending_user", "closed"]
ChatModeCode = Literal["full_ai", "no_ai", "ai_assist"]
ActorEntity = Literal["user", "operator", "ai_operator"]


class PagingResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class PagingParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
