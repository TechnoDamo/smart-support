"""Реестр провайдеров: единая точка создания и внедрения зависимостей.

Используется и приложением, и тестами. В тестах провайдеры подменяются на моки
через override_providers().
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, get_settings
from app.providers.channel import ChannelSender, build_channel_sender
from app.providers.embedding import EmbeddingProvider, build_embedding
from app.providers.llm import LlmProvider, build_llm
from app.providers.object_storage import ObjectStorage, build_object_storage
from app.providers.vector_store import VectorStore, build_vector_store


@dataclass
class Providers:
    llm: LlmProvider
    embedding: EmbeddingProvider
    vector_store: VectorStore
    object_storage: ObjectStorage
    channel_sender: ChannelSender


_providers: Providers | None = None


def build_providers(settings: Settings | None = None) -> Providers:
    s = settings or get_settings()
    return Providers(
        llm=build_llm(s),
        embedding=build_embedding(s),
        vector_store=build_vector_store(s),
        object_storage=build_object_storage(s),
        channel_sender=build_channel_sender(s),
    )


def get_providers() -> Providers:
    global _providers
    if _providers is None:
        _providers = build_providers()
    return _providers


def override_providers(providers: Providers) -> None:
    """Используется тестами и фикстурами."""
    global _providers
    _providers = providers


def reset_providers() -> None:
    global _providers
    _providers = None
