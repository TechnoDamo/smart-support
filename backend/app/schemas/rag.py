from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class RagDocument(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    source_type: str
    source_name: str
    current_version: int
    created_at: datetime
    deleted_at: Optional[datetime] = None


class RagUploadResponse(BaseModel):
    document_id: uuid.UUID
    ingestion_job_id: uuid.UUID
    status: Literal["queued", "processing", "done", "failed"]


class RagDeleteResponse(BaseModel):
    document_id: uuid.UUID
    deleted_at: datetime
