"""Запуск миграций Alembic из приложения и тестов."""
from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def upgrade_to_head() -> None:
    """Применяет все миграции до актуальной ревизии."""
    command.upgrade(_alembic_config(), "head")


async def upgrade_to_head_async() -> None:
    """Асинхронная обёртка для запуска Alembic вне event loop-блокировки."""
    await asyncio.to_thread(upgrade_to_head)
