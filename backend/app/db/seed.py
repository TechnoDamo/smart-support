"""Создание справочных данных: каналы, режимы, статусы, дефолтная RAG-коллекция."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    AppSetting,
    Channel,
    ChatMode,
    RagCollection,
    TicketStatus,
    SETTING_DEFAULT_CHAT_MODE,
)

# Канонические коды
CHANNEL_TELEGRAM = "telegram"

CHAT_MODE_FULL_AI = "full_ai"
CHAT_MODE_AI_ASSIST = "ai_assist"
CHAT_MODE_NO_AI = "no_ai"

TICKET_STATUS_PENDING_AI = "pending_ai"
TICKET_STATUS_PENDING_HUMAN = "pending_human"
TICKET_STATUS_PENDING_USER = "pending_user"
TICKET_STATUS_CLOSED = "closed"

DEFAULT_RAG_COLLECTION_CODE = "support_knowledge"


async def _ensure(session: AsyncSession, model, code: str, **defaults) -> None:
    """Добавляет запись справочника, если её ещё нет (идемпотентно)."""
    stmt = select(model).where(model.code == code)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        session.add(model(code=code, **defaults))


async def seed_reference_data(session: AsyncSession) -> None:
    """Заполняет справочники и настройки по умолчанию. Идемпотентно."""
    settings = get_settings()

    # Каналы
    await _ensure(session, Channel, CHANNEL_TELEGRAM,
                  name="Telegram", description="Бот в Telegram")

    # Режимы чата
    await _ensure(session, ChatMode, CHAT_MODE_FULL_AI,
                  name="Полный AI", description="AI отвечает самостоятельно")
    await _ensure(session, ChatMode, CHAT_MODE_AI_ASSIST,
                  name="AI-ассистент", description="AI подсказывает оператору")
    await _ensure(session, ChatMode, CHAT_MODE_NO_AI,
                  name="Без AI", description="Только оператор-человек")

    # Статусы тикетов
    await _ensure(session, TicketStatus, TICKET_STATUS_PENDING_AI,
                  name="Ожидает AI", description="Ожидает ответа AI-оператора")
    await _ensure(session, TicketStatus, TICKET_STATUS_PENDING_HUMAN,
                  name="Ожидает оператора", description="Передан оператору-человеку")
    await _ensure(session, TicketStatus, TICKET_STATUS_PENDING_USER,
                  name="Ожидает пользователя", description="Ответ отправлен, ждём реакции")
    await _ensure(session, TicketStatus, TICKET_STATUS_CLOSED,
                  name="Закрыт", description="Тикет завершён")

    await session.flush()

    # RAG-коллекция по умолчанию
    stmt = select(RagCollection).where(RagCollection.code == DEFAULT_RAG_COLLECTION_CODE)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        session.add(RagCollection(
            code=DEFAULT_RAG_COLLECTION_CODE,
            name="Основная база знаний поддержки",
            qdrant_collection_name=DEFAULT_RAG_COLLECTION_CODE,
            embedding_model=settings.embedding_model,
            vector_size=settings.embedding_vector_size,
            distance_metric=settings.embedding_distance_metric,
            is_active=True,
        ))

    # Начальная настройка — режим по умолчанию
    stmt = select(AppSetting).where(AppSetting.key == SETTING_DEFAULT_CHAT_MODE)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        session.add(AppSetting(
            key=SETTING_DEFAULT_CHAT_MODE,
            value=settings.default_chat_mode,
        ))
