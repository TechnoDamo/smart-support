"""Роуты настроек приложения, изменяемых через API."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.db.models import AppSetting, SETTING_DEFAULT_CHAT_MODE
from app.schemas.settings import SetDefaultModeRequest, SetDefaultModeResponse

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/default-new-ticket-mode", response_model=SetDefaultModeResponse)
async def get_default_mode(session: AsyncSession = DbSession):
    r = await session.execute(
        select(AppSetting).where(AppSetting.key == SETTING_DEFAULT_CHAT_MODE)
    )
    s = r.scalar_one()
    return SetDefaultModeResponse(mode_code=s.value, updated_at=s.updated_at)  # type: ignore[arg-type]


@router.put("/default-new-ticket-mode", response_model=SetDefaultModeResponse)
async def set_default_mode(body: SetDefaultModeRequest, session: AsyncSession = DbSession):
    r = await session.execute(
        select(AppSetting).where(AppSetting.key == SETTING_DEFAULT_CHAT_MODE)
    )
    s = r.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if s is None:
        s = AppSetting(key=SETTING_DEFAULT_CHAT_MODE, value=body.mode_code, updated_at=now)
        session.add(s)
    else:
        s.value = body.mode_code
        s.updated_at = now
    await session.flush()
    return SetDefaultModeResponse(mode_code=body.mode_code, updated_at=now)
