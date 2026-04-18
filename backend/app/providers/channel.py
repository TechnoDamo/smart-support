"""Провайдеры каналов коммуникации (Telegram и другие)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import Settings


@dataclass
class IncomingMessage:
    """Унифицированное представление входящего сообщения из любого канала."""
    channel_code: str          # telegram, ...
    external_chat_id: int      # telegram_chat_id
    external_user_id: int      # telegram user_id
    user_first_name: str | None
    user_last_name: str | None
    user_username: str | None
    text: str


class ChannelSender(ABC):
    """Отправляет исходящее сообщение в канал."""
    @abstractmethod
    async def send(self, external_chat_id: int, text: str) -> None:
        ...


class TelegramSender(ChannelSender):
    def __init__(self, settings: Settings) -> None:
        self._token = settings.telegram_bot_token
        self._base_url = settings.telegram_api_base_url.rstrip("/")

    async def send(self, external_chat_id: int, text: str) -> None:
        url = f"{self._base_url}/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json={"chat_id": external_chat_id, "text": text})
            r.raise_for_status()


class MockChannelSender(ChannelSender):
    """Mock: хранит историю отправок в памяти."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail_next: int = 0

    async def send(self, external_chat_id: int, text: str) -> None:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise RuntimeError("Mock: эмулируем сбой канала")
        self.sent.append((external_chat_id, text))


def build_channel_sender(settings: Settings) -> ChannelSender:
    if settings.channel_telegram_provider == "telegram":
        return TelegramSender(settings)
    return MockChannelSender()
