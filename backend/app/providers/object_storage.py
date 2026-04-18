"""Объектное хранилище: S3 (или совместимые — MinIO) и локальный fallback (файловая система)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.config import Settings


class ObjectStorage(ABC):
    @abstractmethod
    async def save(self, key: str, content: bytes, content_type: str | None = None) -> str:
        """Сохраняет объект, возвращает storage_url."""

    @abstractmethod
    async def load(self, key: str) -> bytes:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...


class LocalFilesystemStorage(ObjectStorage):
    """Простое хранение на диске. Используется как fallback, если нет S3."""

    def __init__(self, base_path: str) -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Ключ может содержать «/», разрешаем вложенные папки
        p = self._base / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    async def save(self, key: str, content: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        path.write_bytes(content)
        # URL вида file:// для локальных файлов
        return f"file://{path.resolve()}"

    async def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


class S3Storage(ObjectStorage):
    """Поддержка S3 и S3-совместимых хранилищ (MinIO и т. п.) через aioboto3."""

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._endpoint_url = settings.s3_endpoint_url or None
        self._region = settings.s3_region
        self._access_key = settings.s3_access_key_id
        self._secret_key = settings.s3_secret_access_key

    def _client(self):
        import aioboto3
        session = aioboto3.Session()
        return session.client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key or None,
            aws_secret_access_key=self._secret_key or None,
        )

    async def save(self, key: str, content: bytes, content_type: str | None = None) -> str:
        async with self._client() as s3:
            params = {"Bucket": self._bucket, "Key": key, "Body": content}
            if content_type:
                params["ContentType"] = content_type
            await s3.put_object(**params)
        return f"s3://{self._bucket}/{key}"

    async def load(self, key: str) -> bytes:
        async with self._client() as s3:
            obj = await s3.get_object(Bucket=self._bucket, Key=key)
            return await obj["Body"].read()

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)


def build_object_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_provider == "s3":
        return S3Storage(settings)
    return LocalFilesystemStorage(settings.object_storage_local_path)
