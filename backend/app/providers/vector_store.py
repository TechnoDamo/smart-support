"""Векторное хранилище: Qdrant (hybrid search с dense + sparse) и in-memory mock.

Гибридный поиск выполняется так:
  1. Отдельные запросы dense и sparse, каждый возвращает top_k результатов.
  2. Результаты объединяются по алгоритму RRF (Reciprocal Rank Fusion) с весами.
  3. Финальный ранжированный список обрезается до top_k.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import Settings
from app.providers.embedding import EmbeddingVector, SparseVector


@dataclass
class VectorSearchHit:
    point_id: str
    score: float
    payload: dict


class VectorStore(ABC):
    @abstractmethod
    async def ensure_collection(self, name: str, vector_size: int, distance: str) -> None:
        ...

    @abstractmethod
    async def upsert(self, collection: str, point_id: str, vector: EmbeddingVector,
                     payload: dict) -> None:
        ...

    @abstractmethod
    async def delete(self, collection: str, point_ids: list[str]) -> None:
        ...

    @abstractmethod
    async def hybrid_search(self, collection: str, *, dense: list[float], sparse: SparseVector,
                            top_k: int, dense_weight: float, sparse_weight: float
                            ) -> list[VectorSearchHit]:
        ...


def _rrf_fuse(dense_hits: list[tuple[str, float, dict]],
              sparse_hits: list[tuple[str, float, dict]],
              dense_weight: float, sparse_weight: float,
              top_k: int, rrf_k: int = 60) -> list[VectorSearchHit]:
    """Объединение по Reciprocal Rank Fusion с весами."""
    scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}
    for rank, (pid, _s, pl) in enumerate(dense_hits, start=1):
        scores[pid] = scores.get(pid, 0.0) + dense_weight / (rrf_k + rank)
        payloads[pid] = pl
    for rank, (pid, _s, pl) in enumerate(sparse_hits, start=1):
        scores[pid] = scores.get(pid, 0.0) + sparse_weight / (rrf_k + rank)
        payloads.setdefault(pid, pl)
    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [VectorSearchHit(point_id=pid, score=s, payload=payloads[pid]) for pid, s in merged]


class MockVectorStore(VectorStore):
    """In-memory векторное хранилище. Dense — косинусное сходство, Sparse — скалярное."""

    def __init__(self) -> None:
        # collection -> point_id -> (dense, sparse_indices, sparse_values, payload)
        self._data: dict[str, dict[str, tuple[list[float], list[int], list[float], dict]]] = {}

    async def ensure_collection(self, name: str, vector_size: int, distance: str) -> None:
        self._data.setdefault(name, {})

    async def upsert(self, collection: str, point_id: str, vector: EmbeddingVector,
                     payload: dict) -> None:
        self._data.setdefault(collection, {})
        self._data[collection][point_id] = (
            vector.dense, vector.sparse_indices, vector.sparse_values, payload,
        )

    async def delete(self, collection: str, point_ids: list[str]) -> None:
        bucket = self._data.get(collection, {})
        for pid in point_ids:
            bucket.pop(pid, None)

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        import math
        s = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1e-9
        nb = math.sqrt(sum(x * x for x in b)) or 1e-9
        return s / (na * nb)

    @staticmethod
    def _sparse_dot(idx_a: list[int], val_a: list[float],
                    idx_b: list[int], val_b: list[float]) -> float:
        map_b = dict(zip(idx_b, val_b))
        return sum(v * map_b.get(i, 0.0) for i, v in zip(idx_a, val_a))

    async def hybrid_search(self, collection: str, *, dense: list[float], sparse: SparseVector,
                            top_k: int, dense_weight: float, sparse_weight: float
                            ) -> list[VectorSearchHit]:
        bucket = self._data.get(collection, {})
        dense_hits: list[tuple[str, float, dict]] = []
        sparse_hits: list[tuple[str, float, dict]] = []
        for pid, (d, si, sv, pl) in bucket.items():
            dense_hits.append((pid, self._cosine(dense, d), pl))
            sparse_hits.append((pid, self._sparse_dot(sparse.indices, sparse.values, si, sv), pl))
        dense_hits.sort(key=lambda x: x[1], reverse=True)
        sparse_hits.sort(key=lambda x: x[1], reverse=True)
        return _rrf_fuse(dense_hits[:top_k * 2], sparse_hits[:top_k * 2],
                         dense_weight, sparse_weight, top_k)


class QdrantVectorStore(VectorStore):
    """Реальный Qdrant с именованными dense и sparse векторами."""

    def __init__(self, settings: Settings) -> None:
        # Импортируем локально, чтобы mock-сценарии не тянули зависимость
        from qdrant_client import AsyncQdrantClient
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
        self._dense_name = "dense"
        self._sparse_name = "sparse"

    async def ensure_collection(self, name: str, vector_size: int, distance: str) -> None:
        from qdrant_client import models as qm
        distance_map = {
            "cosine": qm.Distance.COSINE,
            "dot": qm.Distance.DOT,
            "euclid": qm.Distance.EUCLID,
        }
        existing = await self._client.get_collections()
        if any(c.name == name for c in existing.collections):
            return
        await self._client.create_collection(
            collection_name=name,
            vectors_config={
                self._dense_name: qm.VectorParams(
                    size=vector_size, distance=distance_map[distance]
                )
            },
            sparse_vectors_config={self._sparse_name: qm.SparseVectorParams()},
        )

    async def upsert(self, collection: str, point_id: str, vector: EmbeddingVector,
                     payload: dict) -> None:
        from qdrant_client import models as qm
        await self._client.upsert(
            collection_name=collection,
            points=[qm.PointStruct(
                id=point_id,
                vector={
                    self._dense_name: vector.dense,
                    self._sparse_name: qm.SparseVector(
                        indices=vector.sparse_indices,
                        values=vector.sparse_values,
                    ),
                },
                payload=payload,
            )],
        )

    async def delete(self, collection: str, point_ids: list[str]) -> None:
        from qdrant_client import models as qm
        if not point_ids:
            return
        await self._client.delete(
            collection_name=collection,
            points_selector=qm.PointIdsList(points=point_ids),
        )

    async def hybrid_search(self, collection: str, *, dense: list[float], sparse: SparseVector,
                            top_k: int, dense_weight: float, sparse_weight: float
                            ) -> list[VectorSearchHit]:
        from qdrant_client import models as qm
        # Два отдельных запроса — и затем RRF на стороне приложения (прозрачно и портируемо).
        dense_res = await self._client.search(
            collection_name=collection,
            query_vector=qm.NamedVector(name=self._dense_name, vector=dense),
            limit=top_k * 2,
            with_payload=True,
        )
        sparse_res = await self._client.search(
            collection_name=collection,
            query_vector=qm.NamedSparseVector(
                name=self._sparse_name,
                vector=qm.SparseVector(indices=sparse.indices, values=sparse.values),
            ),
            limit=top_k * 2,
            with_payload=True,
        )
        dense_hits = [(str(p.id), float(p.score), dict(p.payload or {})) for p in dense_res]
        sparse_hits = [(str(p.id), float(p.score), dict(p.payload or {})) for p in sparse_res]
        return _rrf_fuse(dense_hits, sparse_hits, dense_weight, sparse_weight, top_k)


def build_vector_store(settings: Settings) -> VectorStore:
    if settings.vector_store_provider == "qdrant":
        return QdrantVectorStore(settings)
    return MockVectorStore()
