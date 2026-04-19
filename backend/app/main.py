"""Точка входа FastAPI-приложения.

Lifespan:
  1. Инициализация БД-движка и идемпотентный сид справочников.
  2. Старт фонового планировщика (auto-close тикетов, outbox, retry ingestion).
  3. При остановке — аккуратно гасим планировщик и движок.
"""

from __future__ import annotations

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
from app.logging import get_logger
from app.middleware.db_logging import db_logger
from app.middleware.logging_middleware import LoggingMiddleware
from app.services.scheduler import build_scheduler

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()

    # Initialize database engine
    engine = init_engine()

    # Setup database logging
    db_logger.setup(engine.sync_engine)

    # Seed reference data
    maker = get_sessionmaker()
    async with maker() as session:
        await seed_reference_data(session)
        await session.commit()

    # Start scheduler
    scheduler = build_scheduler()
    scheduler.start()

    logger.info(
        "Application started",
        extra={
            "host": settings.app_host,
            "port": settings.app_port,
            "environment": settings.app_env,
            "log_level": settings.log_level,
            "log_format": settings.log_format,
            "graylog_enabled": settings.graylog_enabled,
        },
    )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await dispose_engine()
        logger.info("Application stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Smart Support API",
        version="1.0.0",
        description="Backend сервис умной поддержки: тикеты, чаты, AI-оркестрация, RAG.",
        lifespan=lifespan,
    )

    # Add logging middleware (before CORS to capture all requests)
    app.add_middleware(LoggingMiddleware)

    # Add CORS middleware
    if settings.cors_allowed_origins_list or settings.cors_allow_origin_regex:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins_list,
            allow_origin_regex=settings.cors_allow_origin_regex,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Include routers
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

    @app.get("/logs/test", tags=["_system"])
    async def test_logs() -> dict:
        """Endpoint to test logging at different levels."""
        logger.debug("Debug test message")
        logger.info("Info test message")
        logger.warning("Warning test message")
        logger.error("Error test message")

        # Test with extra fields
        logger.info(
            "Structured log test",
            extra={
                "user_id": "test-user-123",
                "action": "test_logging",
                "details": {"level": "info", "endpoint": "/logs/test"},
            },
        )

        return {
            "status": "ok",
            "message": "Test logs generated",
            "log_level": settings.log_level,
            "log_format": settings.log_format,
            "graylog_enabled": settings.graylog_enabled,
        }

    return app


app = create_app()
