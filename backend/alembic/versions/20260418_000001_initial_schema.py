"""initial schema

Revision ID: 20260418_000001
Revises:
Create Date: 2026-04-18 23:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260418_000001"
down_revision = None
branch_labels = None
depends_on = None


JSON_TYPE = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
UUID_TYPE = sa.Uuid()
TIMESTAMP_TZ = sa.DateTime(timezone=True)
NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "chat_modes",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "ticket_statuses",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )

    op.create_table(
        "rag_collections",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("qdrant_collection_name", sa.String(length=255), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("vector_size", sa.Integer(), nullable=False),
        sa.Column("distance_metric", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("qdrant_collection_name"),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "chats",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("channel_id", UUID_TYPE, nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", UUID_TYPE, nullable=False),
        sa.Column("mode_id", UUID_TYPE, nullable=False),
        sa.Column("time_started", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
        sa.ForeignKeyConstraint(["mode_id"], ["chat_modes.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_chat_id"),
    )
    op.create_index("idx_chats_mode_id", "chats", ["mode_id"])
    op.create_index("idx_chats_user_id", "chats", ["user_id"])

    op.create_table(
        "tickets",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("chat_id", UUID_TYPE, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status_id", UUID_TYPE, nullable=False),
        sa.Column("time_started", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("time_closed", TIMESTAMP_TZ, nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"]),
        sa.ForeignKeyConstraint(["status_id"], ["ticket_statuses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tickets_chat_id", "tickets", ["chat_id"])
    op.create_index("idx_tickets_chat_id_time_started", "tickets", ["chat_id", "time_started"])
    op.create_index("idx_tickets_status_id", "tickets", ["status_id"])

    op.create_table(
        "messages",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("chat_id", UUID_TYPE, nullable=False),
        sa.Column("ticket_id", UUID_TYPE, nullable=False),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("time", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "seq", name="idx_messages_chat_id_seq"),
    )
    op.create_index("idx_messages_chat_id_time", "messages", ["chat_id", "time"])
    op.create_index("idx_messages_ticket_id", "messages", ["ticket_id"])

    op.create_table(
        "chat_mode_events",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("chat_id", UUID_TYPE, nullable=False),
        sa.Column("from_mode_id", UUID_TYPE, nullable=True),
        sa.Column("to_mode_id", UUID_TYPE, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"]),
        sa.ForeignKeyConstraint(["from_mode_id"], ["chat_modes.id"]),
        sa.ForeignKeyConstraint(["to_mode_id"], ["chat_modes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_mode_events_chat_id", "chat_mode_events", ["chat_id"])
    op.create_index("idx_chat_mode_events_created_at", "chat_mode_events", ["created_at"])

    op.create_table(
        "ticket_status_events",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("ticket_id", UUID_TYPE, nullable=False),
        sa.Column("from_status_id", UUID_TYPE, nullable=True),
        sa.Column("to_status_id", UUID_TYPE, nullable=False),
        sa.Column("changed_by", sa.String(length=32), nullable=False),
        sa.Column("changed_by_user_id", UUID_TYPE, nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["from_status_id"], ["ticket_statuses.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["to_status_id"], ["ticket_statuses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ticket_status_events_created_at", "ticket_status_events", ["created_at"])
    op.create_index("idx_ticket_status_events_ticket_id", "ticket_status_events", ["ticket_id"])

    op.create_table(
        "rag_documents",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("collection_id", UUID_TYPE, nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_external_id", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("storage_url", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", UUID_TYPE, nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("deleted_at", TIMESTAMP_TZ, nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["rag_collections.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rag_document_versions",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("document_id", UUID_TYPE, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version", name="idx_rag_document_versions_document_id_version"),
    )

    op.create_table(
        "rag_document_chunks",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("document_id", UUID_TYPE, nullable=False),
        sa.Column("document_version_id", UUID_TYPE, nullable=False),
        sa.Column("collection_id", UUID_TYPE, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_token_count", sa.Integer(), nullable=True),
        sa.Column("qdrant_point_id", sa.String(length=128), nullable=False),
        sa.Column("metadata", JSON_TYPE, nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("deleted_at", TIMESTAMP_TZ, nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["rag_collections.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"]),
        sa.ForeignKeyConstraint(["document_version_id"], ["rag_document_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_version_id", "chunk_index", name="idx_rag_document_chunks_document_version_id_chunk_index"),
        sa.UniqueConstraint("qdrant_point_id"),
    )

    op.create_table(
        "rag_ingestion_jobs",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("collection_id", UUID_TYPE, nullable=False),
        sa.Column("document_id", UUID_TYPE, nullable=True),
        sa.Column("requested_by_user_id", UUID_TYPE, nullable=True),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", TIMESTAMP_TZ, nullable=True),
        sa.Column("finished_at", TIMESTAMP_TZ, nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["rag_collections.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rag_retrieval_events",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("chat_id", UUID_TYPE, nullable=False),
        sa.Column("ticket_id", UUID_TYPE, nullable=False),
        sa.Column("message_id", UUID_TYPE, nullable=True),
        sa.Column("collection_id", UUID_TYPE, nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("min_score", sa.Float(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"]),
        sa.ForeignKeyConstraint(["collection_id"], ["rag_collections.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rag_retrieval_results",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("retrieval_event_id", UUID_TYPE, nullable=False),
        sa.Column("chunk_id", UUID_TYPE, nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("used_in_answer", sa.Boolean(), nullable=False),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["rag_document_chunks.id"]),
        sa.ForeignKeyConstraint(["retrieval_event_id"], ["rag_retrieval_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("retrieval_event_id", "rank", name="idx_rag_retrieval_results_retrieval_event_id_rank"),
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", UUID_TYPE, nullable=False),
        sa.Column("message_id", UUID_TYPE, nullable=False),
        sa.Column("channel_code", sa.String(length=32), nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", TIMESTAMP_TZ, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP_TZ, server_default=NOW, nullable=False),
        sa.Column("sent_at", TIMESTAMP_TZ, nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_outbox_status_next_attempt", "outbox_messages", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("idx_outbox_status_next_attempt", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_table("rag_retrieval_results")
    op.drop_table("rag_retrieval_events")
    op.drop_table("rag_ingestion_jobs")
    op.drop_table("rag_document_chunks")
    op.drop_table("rag_document_versions")
    op.drop_table("rag_documents")
    op.drop_index("idx_ticket_status_events_ticket_id", table_name="ticket_status_events")
    op.drop_index("idx_ticket_status_events_created_at", table_name="ticket_status_events")
    op.drop_table("ticket_status_events")
    op.drop_index("idx_chat_mode_events_created_at", table_name="chat_mode_events")
    op.drop_index("idx_chat_mode_events_chat_id", table_name="chat_mode_events")
    op.drop_table("chat_mode_events")
    op.drop_index("idx_messages_ticket_id", table_name="messages")
    op.drop_index("idx_messages_chat_id_time", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_tickets_status_id", table_name="tickets")
    op.drop_index("idx_tickets_chat_id_time_started", table_name="tickets")
    op.drop_index("idx_tickets_chat_id", table_name="tickets")
    op.drop_table("tickets")
    op.drop_index("idx_chats_user_id", table_name="chats")
    op.drop_index("idx_chats_mode_id", table_name="chats")
    op.drop_table("chats")
    op.drop_table("app_settings")
    op.drop_table("rag_collections")
    op.drop_table("users")
    op.drop_table("ticket_statuses")
    op.drop_table("chat_modes")
    op.drop_table("channels")
