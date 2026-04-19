"""Провайдеры LLM. OpenAI-compatible интерфейс подходит и для облака, и для локальных
серверов (Ollama, vLLM, LM Studio) — достаточно указать base_url и model."""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class LlmMessage:
    role: str  # system | user | assistant
    content: str


class LlmProvider(ABC):
    @abstractmethod
    async def complete(
        self, messages: list[LlmMessage], *, json_mode: bool = False
    ) -> str:
        """Возвращает текст ответа LLM."""


class OpenAiCompatibleLlm(LlmProvider):
    """Стандартный /chat/completions-протокол OpenAI.

    Надёжность:
      - детектирует ``{"error": ...}`` в 200-ответах (роутеры так делают);
      - ретраит сетевые и 5xx-ошибки с экспоненциальной задержкой;
      - бросает ``RuntimeError`` с внятным сообщением, а не ``KeyError``.
    """

    MAX_ATTEMPTS = 4
    BASE_BACKOFF_SECONDS = 0.5

    def __init__(self, settings: Settings):
        self._base_url = settings.llm_base_url.rstrip("/")
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds
        self._temperature = settings.llm_temperature

    async def _post_once(
        self,
        client: httpx.AsyncClient,
        messages: list[LlmMessage],
        json_mode: bool,
    ) -> str:
        payload: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        r = await client.post(
            f"{self._base_url}/chat/completions", json=payload, headers=headers
        )
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError as e:
            raise RuntimeError(
                f"llm provider returned non-JSON body (status={r.status_code}): {r.text[:200]!r}"
            ) from e
        if "error" in data:
            raise RuntimeError(f"llm provider error: {data['error']}")
        if "choices" not in data or not data["choices"]:
            raise RuntimeError(
                f"llm provider missing 'choices'; got keys={list(data)}, body={r.text[:200]!r}"
            )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(
                f"llm provider malformed choice: {data['choices'][0]!r}"
            ) from e

    async def complete(
        self, messages: list[LlmMessage], *, json_mode: bool = False
    ) -> str:
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                try:
                    return await self._post_once(client, messages, json_mode)
                except (httpx.HTTPError, RuntimeError) as exc:
                    last_exc = exc
                    if attempt == self.MAX_ATTEMPTS:
                        break
                    delay = self.BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "llm attempt %d/%d failed (%s); retrying in %.1fs",
                        attempt, self.MAX_ATTEMPTS, exc, delay,
                    )
                    await asyncio.sleep(delay)
        assert last_exc is not None
        raise RuntimeError(
            f"llm provider failed after {self.MAX_ATTEMPTS} attempts: {last_exc}"
        ) from last_exc


class MockLlm(LlmProvider):
    """Детерминированный mock для тестов и локальной разработки.

    Обнаруживает типичные паттерны запросов и возвращает ожидаемый формат ответа.
    """

    def __init__(self) -> None:
        # Очередь «подставных» ответов: если не пуста — берём из неё.
        # Это позволяет тестам задавать нужный выход LLM.
        self.queued: list[str] = []

    def queue(self, response: str) -> None:
        self.queued.append(response)

    async def complete(
        self, messages: list[LlmMessage], *, json_mode: bool = False
    ) -> str:
        if self.queued:
            return self.queued.pop(0)

        user_text = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )

        # Эмулируем ответ для генерации подсказок (должен быть ПЕРВЫМ, т.к. "AI-ассистент" входит в оба условия)
        if any(
            "подсказ" in m.content.lower() for m in messages if m.role == "system"
        ) or any("AI-ассистент" in m.content for m in messages if m.role == "system"):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "text": "Здравствуйте! Мы получили ваш запрос и уже работаем над ним.",
                            "confidence": 0.8,
                        },
                        {
                            "text": "Спасибо за обращение, уточните, пожалуйста, детали.",
                            "confidence": 0.7,
                        },
                        {"text": "Понял вас, сейчас разберёмся.", "confidence": 0.6},
                    ]
                },
                ensure_ascii=False,
            )

        # Эмулируем ответ AI-оператора (JSON-формат)
        if any("AI-оператор" in m.content for m in messages if m.role == "system"):
            low = user_text.lower()
            if any(k in low for k in ("оператор", "человек", "менеджер", "живой")):
                return json.dumps(
                    {
                        "action": "escalate",
                        "response_text": "Передаю ваш вопрос оператору, ожидайте.",
                        "escalation_reason": "Пользователь попросил соединить с человеком",
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "action": "reply",
                    "response_text": f"Принято: {user_text[:80]}",
                    "escalation_reason": None,
                },
                ensure_ascii=False,
            )

        # Эмулируем ответ для summary
        return "Пользователь обратился в поддержку, вопрос был обработан."


def build_llm(settings: Settings) -> LlmProvider:
    if settings.llm_provider == "openai_compatible":
        return OpenAiCompatibleLlm(settings)
    return MockLlm()
