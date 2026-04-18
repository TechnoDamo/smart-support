"""Загрузчик системных промптов из .txt-файлов."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import get_settings


@lru_cache
def load_prompt(name: str) -> str:
    """Читает промпт по имени (без .txt) из директории PROMPTS_DIR."""
    settings = get_settings()
    path = settings.prompts_path / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Промпт не найден: {path}")
    return path.read_text(encoding="utf-8").strip()
