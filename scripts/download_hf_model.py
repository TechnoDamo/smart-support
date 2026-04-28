#!/usr/bin/env python3
"""Скачивает snapshot HuggingFace-модели в локальную папку по заданному алиасу."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True, help="HuggingFace repo id")
    parser.add_argument("--local-dir", required=True, help="Локальная директория назначения")
    parser.add_argument("--endpoint", default="https://huggingface.co", help="Базовый URL HF или зеркала")
    parser.add_argument("--token", default=None, help="Токен HF для приватных репозиториев")
    parser.add_argument("--revision", default=None, help="Опциональная ревизия/ветка/тег")
    parser.add_argument("--clean", action="store_true", help="Удалить целевую папку перед загрузкой")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    local_dir = Path(args.local_dir).resolve()
    if args.clean and local_dir.exists():
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    # На macOS большие файлы из Xet-backed репозиториев могут появляться как
    # dataless placeholders. Отключаем Xet, чтобы получить обычные локальные файлы.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    snapshot_download(
        repo_id=args.repo_id,
        local_dir=str(local_dir),
        endpoint=args.endpoint,
        token=args.token or None,
        revision=args.revision or None,
        local_dir_use_symlinks=False,
        force_download=True,
    )

    print(f"Модель скачана: {args.repo_id}")
    print(f"Локальная папка: {local_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
