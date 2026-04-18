from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ChatModeCode


class SetDefaultModeRequest(BaseModel):
    mode_code: ChatModeCode


class SetDefaultModeResponse(BaseModel):
    mode_code: ChatModeCode
    updated_at: datetime
