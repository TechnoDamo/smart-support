"""Роут аналитики: сводный отчёт по всей системе."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.schemas.analytics import AnalyticsReport
from app.services.analytics import build_report

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/report", response_model=AnalyticsReport)
async def analytics_report(
    period_from: datetime | None = Query(None, description="Начало периода (ISO 8601, UTC)"),
    period_to: datetime | None = Query(None, description="Конец периода (ISO 8601, UTC)"),
    session: AsyncSession = DbSession,
):
    return await build_report(session, period_from=period_from, period_to=period_to)
