"""SQLAlchemy-модели предметной области.

Схема полностью соответствует db/schema.dbml. Комментарии на русском.
UUID и JSON типизированы кросс-диалектно (работают и в PostgreSQL, и в SQLite).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _timestamp(default: bool = True) -> Mapped[datetime]:
    kwargs = {"nullable": False}
    if default:
        kwargs["server_default"] = func.now()
    return mapped_column(DateTime(timezone=True), **kwargs)


def _json_type():
    """JSONB в PostgreSQL, JSON в SQLite."""
    return JSONB().with_variant(JSON(), "sqlite")


# ─── Справочники ─────────────────────────────────────────────────────────────


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()


class ChatMode(Base):
    __tablename__ = "chat_modes"
    id: Mapped[uuid.UUID] = _uuid_pk()
    # full_ai | no_ai | ai_assist
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()


class TicketStatus(Base):
    __tablename__ = "ticket_statuses"
    id: Mapped[uuid.UUID] = _uuid_pk()
    # pending_ai | pending_human | pending_user | closed
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()


# ─── Пользователи, чаты, тикеты, сообщения ───────────────────────────────────


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    username: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()


class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[uuid.UUID] = _uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"), nullable=False)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    mode_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_modes.id"), nullable=False)
    time_started: Mapped[datetime] = _timestamp()
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()

    channel: Mapped[Channel] = relationship(lazy="joined")
    mode: Mapped[ChatMode] = relationship(lazy="joined")

    __table_args__ = (
        Index("idx_chats_mode_id", "mode_id"),
        Index("idx_chats_user_id", "user_id"),
    )


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[uuid.UUID] = _uuid_pk()
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    status_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ticket_statuses.id"), nullable=False)
    time_started: Mapped[datetime] = _timestamp()
    time_closed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()

    status: Mapped[TicketStatus] = relationship(lazy="joined")

    __table_args__ = (
        Index("idx_tickets_chat_id", "chat_id"),
        Index("idx_tickets_chat_id_time_started", "chat_id", "time_started"),
        Index("idx_tickets_status_id", "status_id"),
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _uuid_pk()
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id"), nullable=False)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    # user | ai_operator | operator
    entity: Mapped[str] = mapped_column(String(32), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    time: Mapped[datetime] = _timestamp()
    created_at: Mapped[datetime] = _timestamp()

    __table_args__ = (
        Index("idx_messages_chat_id_time", "chat_id", "time"),
        Index("idx_messages_ticket_id", "ticket_id"),
        UniqueConstraint("chat_id", "seq", name="idx_messages_chat_id_seq"),
    )


# ─── События (аудит) ─────────────────────────────────────────────────────────


class ChatModeEvent(Base):
    __tablename__ = "chat_mode_events"
    id: Mapped[uuid.UUID] = _uuid_pk()
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id"), nullable=False)
    from_mode_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("chat_modes.id"))
    to_mode_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_modes.id"), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()


class TicketStatusEvent(Base):
    __tablename__ = "ticket_status_events"
    id: Mapped[uuid.UUID] = _uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    from_status_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("ticket_statuses.id"))
    to_status_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ticket_statuses.id"), nullable=False)
    # user | ai_operator | operator
    changed_by: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()


# ─── RAG ─────────────────────────────────────────────────────────────────────


class RagCollection(Base):
    __tablename__ = "rag_collections"
    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    qdrant_collection_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    vector_size: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()


class RagDocument(Base):
    __tablename__ = "rag_documents"
    id: Mapped[uuid.UUID] = _uuid_pk()
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_collections.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_external_id: Mapped[Optional[str]] = mapped_column(String(255))
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    storage_url: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RagDocumentVersion(Base):
    __tablename__ = "rag_document_versions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_documents.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # pending | processing | ready | failed
    extraction_status: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()

    __table_args__ = (
        UniqueConstraint("document_id", "version", name="idx_rag_document_versions_document_id_version"),
    )


class RagDocumentChunk(Base):
    __tablename__ = "rag_document_chunks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_documents.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_document_versions.id"), nullable=False)
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_collections.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_token_count: Mapped[Optional[int]] = mapped_column(Integer)
    qdrant_point_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", _json_type())
    created_at: Mapped[datetime] = _timestamp()
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "chunk_index",
            name="idx_rag_document_chunks_document_version_id_chunk_index",
        ),
    )


class RagIngestionJob(Base):
    __tablename__ = "rag_ingestion_jobs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_collections.id"), nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("rag_documents.id"))
    requested_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    # upsert_document | delete_document | reindex_collection
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    # queued | processing | done | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _timestamp()


class RagRetrievalEvent(Base):
    __tablename__ = "rag_retrieval_events"
    id: Mapped[uuid.UUID] = _uuid_pk()
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id"), nullable=False)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("messages.id"))
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_collections.id"), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    min_score: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = _timestamp()


class RagRetrievalResult(Base):
    __tablename__ = "rag_retrieval_results"
    id: Mapped[uuid.UUID] = _uuid_pk()
    retrieval_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_retrieval_events.id"), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_document_chunks.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    used_in_answer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _timestamp()

    __table_args__ = (
        UniqueConstraint(
            "retrieval_event_id", "rank",
            name="idx_rag_retrieval_results_retrieval_event_id_rank",
        ),
    )


# ─── Outbox ──────────────────────────────────────────────────────────────────


class OutboxMessage(Base):
    """Transactional outbox: гарантированная доставка исходящих сообщений."""
    __tablename__ = "outbox_messages"
    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), nullable=False)
    channel_code: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    # pending | retry | sent | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_outbox_status_next_attempt", "status", "next_attempt_at"),
    )


# ─── Настройки ───────────────────────────────────────────────────────────────


class AppSetting(Base):
    """Ключ-значение для настроек, изменяемых через API (например, режим по умолчанию)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = _timestamp()


# Ключи настроек
SETTING_DEFAULT_CHAT_MODE = "default_new_ticket_mode"
