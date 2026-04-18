"""Провайдеры эмбеддингов.

Возвращают dense + sparse (BM25-совместимые) векторы.
Dense — от внешнего провайдера (OpenAI-compatible) либо детерминированный mock.
Sparse — локально через rank-bm25 / простой токенизатор; это обеспечивает гибридный поиск.
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field

import httpx

from app.config import Settings


@dataclass
class EmbeddingVector:
    dense: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


@dataclass
class SparseVector:
    indices: list[int]
    values: list[float]


_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


@dataclass
class BM25Encoder:
    """Простейший BM25-энкодер для sparse-векторов.

    Словарь строится по мере поступления текстов. Индекс токена в словаре = индекс
    в sparse-векторе. Значение = tf * idf-приближение.
    """
    k1: float = 1.5
    b: float = 0.75
    vocab: dict[str, int] = field(default_factory=dict)
    df: Counter = field(default_factory=Counter)
    total_docs: int = 0
    avg_doc_len: float = 0.0
    _total_len: int = 0

    def _token_id(self, token: str) -> int:
        if token not in self.vocab:
            self.vocab[token] = len(self.vocab)
        return self.vocab[token]

    def fit_add(self, tokens_list: list[list[str]]) -> None:
        """Добавляет документы в статистику."""
        for tokens in tokens_list:
            self.total_docs += 1
            self._total_len += len(tokens)
            for tok in set(tokens):
                self.df[tok] += 1
        self.avg_doc_len = self._total_len / max(self.total_docs, 1)

    def encode(self, tokens: list[str]) -> SparseVector:
        """Превращает документ/запрос в sparse-вектор BM25."""
        if not tokens:
            return SparseVector(indices=[], values=[])
        counts = Counter(tokens)
        doc_len = len(tokens)
        idxs: list[int] = []
        vals: list[float] = []
        for tok, tf in counts.items():
            idx = self._token_id(tok)
            # idf со сглаживанием (+1 в знаменателе и логарифме)
            n = self.df.get(tok, 0)
            idf = math.log(1 + (self.total_docs - n + 0.5) / (n + 0.5))
            denom = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avg_doc_len, 1))
            score = idf * (tf * (self.k1 + 1)) / max(denom, 1e-9)
            idxs.append(idx)
            vals.append(float(score))
        return SparseVector(indices=idxs, values=vals)


class EmbeddingProvider(ABC):
    def __init__(self, vector_size: int) -> None:
        self.vector_size = vector_size
        self.bm25 = BM25Encoder()

    @abstractmethod
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        ...

    def fit_sparse(self, texts: list[str]) -> None:
        self.bm25.fit_add([tokenize(t) for t in texts])

    def encode_sparse(self, text: str) -> SparseVector:
        return self.bm25.encode(tokenize(text))

    async def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        dense = await self.embed_dense(texts)
        out: list[EmbeddingVector] = []
        for d, t in zip(dense, texts):
            s = self.encode_sparse(t)
            out.append(EmbeddingVector(dense=d, sparse_indices=s.indices, sparse_values=s.values))
        return out


class OpenAiCompatibleEmbedding(EmbeddingProvider):
    """Dense-эмбеддинги через /v1/embeddings."""

    def __init__(self, settings: Settings):
        super().__init__(settings.embedding_vector_size)
        self._base_url = settings.embedding_base_url.rstrip("/")
        self._api_key = settings.embedding_api_key
        self._model = settings.embedding_model

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{self._base_url}/embeddings",
                json={"model": self._model, "input": texts},
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            return [item["embedding"] for item in data["data"]]


class MockEmbedding(EmbeddingProvider):
    """Детерминированный mock: вектор выводится из hash текста."""

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = hashlib.sha256((t or "").encode("utf-8")).digest()
            # Растягиваем 32 байта до vector_size делимостью
            raw = (h * ((self.vector_size // len(h)) + 1))[: self.vector_size]
            # Нормируем в диапазон [-1, 1]
            vec = [(b - 128) / 128.0 for b in raw]
            # Нормализация для cosine
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


def build_embedding(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai_compatible":
        return OpenAiCompatibleEmbedding(settings)
    return MockEmbedding(vector_size=settings.embedding_vector_size)
