"""Точка входа FastAPI-приложения.

Lifespan:
  1. Инициализация БД-движка и идемпотентный сид справочников.
  2. Старт фонового планировщика (auto-close тикетов, outbox, retry ingestion).
  3. При остановке — аккуратно гасим планировщик и движок.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import (
    analytics,
    chats,
    messages,
    rag,
    settings as settings_routes,
    suggestions,
    telegram,
    tickets,
)
from app.config import get_settings
from app.db.seed import seed_reference_data
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.services.scheduler import build_scheduler

logger = logging.getLogger("smart-support")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    engine = init_engine()
    maker = get_sessionmaker()
    async with maker() as session:
        await seed_reference_data(session)
        await session.commit()

    # Планировщик
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Приложение запущено: %s:%s", settings.app_host, settings.app_port)
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await dispose_engine()
        logger.info("Приложение остановлено")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Support API",
        version="1.0.0",
        description="Backend сервис умной поддержки: тикеты, чаты, AI-оркестрация, RAG.",
        lifespan=lifespan,
    )

    app.include_router(tickets.router)
    app.include_router(chats.router)
    app.include_router(messages.router)
    app.include_router(suggestions.router)
    app.include_router(settings_routes.router)
    app.include_router(rag.router)
    app.include_router(analytics.router)
    app.include_router(telegram.router)

    @app.get("/health", tags=["_system"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
