from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class SuggestionCitation(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    score: float


class Suggestion(BaseModel):
    id: str
    text: str
    confidence: Optional[float] = None
    citations: list[SuggestionCitation] = []


class SuggestionsRequest(BaseModel):
    ticket_id: uuid.UUID
    draft_context: Optional[str] = None
    max_suggestions: int = Field(default=3, ge=1, le=10)


class SuggestionsResponse(BaseModel):
    suggestions: list[Suggestion]
