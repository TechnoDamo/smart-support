"""Конфигурация приложения. Все параметры читаются из переменных окружения."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Основные ────────────────────────────────────────────────────────────
    app_env: Literal["dev", "prod", "test"] = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8081
    log_level: str = "INFO"

    # ─── БД ──────────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./smart_support.db"

    # ─── LLM ─────────────────────────────────────────────────────────────────
    llm_provider: Literal["openai_compatible", "mock"] = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 60
    llm_temperature: float = 0.2

    # ─── Embeddings ──────────────────────────────────────────────────────────
    embedding_provider: Literal["openai_compatible", "mock"] = "mock"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_vector_size: int = 1536
    embedding_distance_metric: Literal["cosine", "dot", "euclid"] = "cosine"

    # ─── Векторное хранилище ─────────────────────────────────────────────────
    vector_store_provider: Literal["qdrant", "mock"] = "mock"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # ─── Объектное хранилище ─────────────────────────────────────────────────
    object_storage_provider: Literal["s3", "local"] = "local"
    object_storage_local_path: str = "./storage"
    s3_bucket: str = "smart-support"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # ─── Telegram ────────────────────────────────────────────────────────────
    channel_telegram_provider: Literal["telegram", "mock"] = "mock"
    telegram_bot_token: str = ""
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_polling_enabled: bool = False
    telegram_polling_limit: int = 50
    telegram_polling_timeout_seconds: int = 0
    telegram_polling_request_timeout_seconds: int = 35
    scheduler_telegram_polling_interval_seconds: int = 5

    # ─── Поведение ───────────────────────────────────────────────────────────
    default_chat_mode: Literal["full_ai", "no_ai", "ai_assist"] = "ai_assist"
    ticket_inactivity_timeout_minutes: int = 60

    outbox_max_retries: int = 5
    outbox_retry_interval_seconds: int = 30

    rag_retrieval_top_k: int = 5
    rag_retrieval_min_score: float = 0.2
    rag_chunk_size_tokens: int = 400
    rag_chunk_overlap_tokens: int = 60
    rag_ingestion_max_retries: int = 3
    rag_ingestion_job_timeout_seconds: int = 120
    rag_ingestion_worker_batch_size: int = 10
    rag_hybrid_dense_weight: float = 0.7
    rag_hybrid_sparse_weight: float = 0.3

    scheduler_ticket_close_interval_seconds: int = 60
    scheduler_outbox_interval_seconds: int = 10
    scheduler_ingestion_retry_interval_seconds: int = 120

    prompts_dir: str = "./prompts"

    @property
    def prompts_path(self) -> Path:
        return Path(self.prompts_dir)


@lru_cache
def get_settings() -> Settings:
    """Возвращает единый экземпляр настроек (кэшируется)."""
    return Settings()
