"""Провайдеры LLM. OpenAI-compatible интерфейс подходит и для облака, и для локальных
серверов (Ollama, vLLM, LM Studio) — достаточно указать base_url и model."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import Settings


@dataclass
class LlmMessage:
    role: str  # system | user | assistant
    content: str


class LlmProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[LlmMessage], *, json_mode: bool = False) -> str:
        """Возвращает текст ответа LLM."""


class OpenAiCompatibleLlm(LlmProvider):
    """Стандартный /chat/completions-протокол OpenAI."""

    def __init__(self, settings: Settings):
        self._base_url = settings.llm_base_url.rstrip("/")
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds
        self._temperature = settings.llm_temperature

    async def complete(self, messages: list[LlmMessage], *, json_mode: bool = False) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]


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

    async def complete(self, messages: list[LlmMessage], *, json_mode: bool = False) -> str:
        if self.queued:
            return self.queued.pop(0)

        user_text = next((m.content for m in reversed(messages) if m.role == "user"), "")

        # Эмулируем ответ AI-оператора (JSON-формат)
        if any("AI-оператор" in m.content for m in messages if m.role == "system"):
            low = user_text.lower()
            if any(k in low for k in ("оператор", "человек", "менеджер", "живой")):
                return json.dumps({
                    "action": "escalate",
                    "response_text": "Передаю ваш вопрос оператору, ожидайте.",
                    "escalation_reason": "Пользователь попросил соединить с человеком",
                }, ensure_ascii=False)
            return json.dumps({
                "action": "reply",
                "response_text": f"Принято: {user_text[:80]}",
                "escalation_reason": None,
            }, ensure_ascii=False)

        # Эмулируем ответ для генерации подсказок
        if any("подсказ" in m.content.lower() for m in messages if m.role == "system"):
            return json.dumps({
                "suggestions": [
                    {"text": "Здравствуйте! Мы получили ваш запрос и уже работаем над ним.",
                     "confidence": 0.8},
                    {"text": "Спасибо за обращение, уточните, пожалуйста, детали.",
                     "confidence": 0.7},
                    {"text": "Понял вас, сейчас разберёмся.",
                     "confidence": 0.6},
                ]
            }, ensure_ascii=False)

        # Эмулируем ответ для summary
        return "Пользователь обратился в поддержку, вопрос был обработан."


def build_llm(settings: Settings) -> LlmProvider:
    if settings.llm_provider == "openai_compatible":
        return OpenAiCompatibleLlm(settings)
    return MockLlm()
