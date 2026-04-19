# План реализации backend (Python / FastAPI)

> Живой документ. Обновляется по мере выполнения. Цель — чтобы любой новый
> агент мог открыть этот файл, понять текущее состояние и продолжить работу
> без потери контекста.

## Рабочая директория

`backend/` в основном репозитории `/Users/damir/Desktop/smart-support`.
Ветка: `dev`.

## Общие требования (из диалога с пользователем)

1. **Python + FastAPI**, SQLAlchemy 2.x async.
2. **Вся конфигурация через env** — можно запускать с облачными или локальными LLM / embedding моделями (OpenAI-совместимый API).
3. **Хранение файлов конфигурируемо** — локальная файловая система как fallback (не требовать S3).
4. **Комментарии в коде — только на русском.**
5. **Инструкции по развёртыванию — на русском, максимально простые.**
6. **RAG**: одновременно dense-векторы и sparse BM25 (гибридный поиск, RRF fusion). Модель эмбеддингов не меняется.
7. **Тесты** для всех компонентов (pytest + pytest-asyncio).
8. **Моки** для всех внешних систем: LLM, embedding, vector store, object storage, канал (Telegram).
9. **Качество кода senior-инженерное**: чистые слои, читаемо, минимум магии.

## Карта статусов

Легенда: ✅ готово, 🚧 в работе, ⏳ ждёт очереди, ❌ заблокировано.

### 1. Foundation ✅

- ✅ `backend/pyproject.toml` — runtime/dev зависимости и `pytest`-настройки; `uv` является единственным менеджером Python-окружения.
- ✅ `/.env.example` — единый шаблон конфигурации всего проекта с русскими комментариями.
- ✅ `backend/app/config.py` — Pydantic Settings + `@lru_cache get_settings()`.
- ✅ `backend/app/prompts.py` — `load_prompt(name)` читает из `PROMPTS_DIR`.
- ✅ `backend/prompts/ai_operator.txt` — системный промпт, JSON-ответ `{action, response_text, escalation_reason}`.
- ✅ `backend/prompts/ticket_summary.txt` — промпт саммари тикета.
- ✅ `backend/prompts/suggestions.txt` — промпт подсказок оператору.

### 2. Database ✅

- ✅ `app/db/session.py` — `init_engine`, `session_scope`, `get_session` (FastAPI dep).
- ✅ `app/db/models.py` — все модели (чаты, тикеты, сообщения, rag_*, outbox, справочники). `RagDocumentChunk.extra_metadata` маппится на колонку `metadata`.
- ✅ `app/db/seed.py` — идемпотентный сид; константы `TICKET_STATUS_*`, `CHAT_MODE_*`, `DEFAULT_RAG_COLLECTION_CODE`.

### 3. Providers (с моками) ✅

- ✅ `app/providers/llm.py` — `LlmProvider` ABC, `LlmMessage`, `OpenAICompatibleLlm`, `MockLlm` (c очередью ответов и автоэскалацией по ключевым словам).
- ✅ `app/providers/embedding.py` — `BM25Encoder` (k1=1.5, b=0.75), `EmbeddingProvider`, `OpenAICompatibleEmbedding`, `MockEmbedding` (SHA256-детерминированные векторы).
- ✅ `app/providers/vector_store.py` — `VectorStore`, RRF-fusion, `QdrantVectorStore` (named vectors dense+sparse), `InMemoryVectorStore` (для тестов).
- ✅ `app/providers/object_storage.py` — `LocalFilesystemStorage` (возвращает `file://...`), `S3Storage` (aioboto3).
- ✅ `app/providers/channel.py` — `ChannelSender`, `TelegramChannelSender`, `MockChannelSender` (с полем `sent` и счётчиком `fail_next`).
- ✅ `app/providers/registry.py` — датакласс `Providers`, `get_providers()`, `override_providers()` для тестов.

### 4. Schemas (Pydantic v2) ✅

- ✅ `common.py`, `tickets.py`, `chats.py`, `messages.py`, `suggestions.py`, `rag.py`, `settings.py`, `analytics.py`.

### 5. Services ✅

- ✅ `refs.py` — lookup code↔id.
- ✅ `tickets.py` — `status_code_for_mode`, `change_ticket_status` (+ запись event-а).
- ✅ `chats.py` — `change_chat_mode` (синхронизирует статус активного тикета).
- ✅ `messages.py` — `add_user_message`, `add_outgoing_message` (пишет в outbox).
- ✅ `outbox.py` — `process_outbox` с экспоненциальной задержкой.
- ✅ `rag.py` — `chunk_text`, `ingest_document`, `retrieve`, `mark_chunks_used`, `soft_delete_document`.
- ✅ `ai_orchestrator.py` — `handle_ticket`, `maybe_dispatch_ai` (только `full_ai + pending_ai`).
- ✅ `suggestions.py` — `generate_suggestions` для режима `ai_assist`.
- ✅ `scheduler.py` — APScheduler, 3 задачи: автозакрытие по неактивности, outbox, retry failed ingestion.
- ✅ `analytics.py` — `build_report` (tickets, messages, ai_performance, rag, users).

### 6. API (FastAPI routes) ✅

- ✅ `app/api/__init__.py`
- ✅ `app/api/deps.py` — `db_session`, `providers_dep`.
- ✅ `app/api/routes/tickets.py` — `GET /tickets`, `GET /tickets/{id}`, `PATCH /tickets/{id}/rename`, `POST /tickets/{id}/close`.
- ✅ `app/api/routes/chats.py` — `GET /chats`, `GET /chats/{id}`, `POST /chats/{id}/mode`.
- ✅ `app/api/routes/messages.py` — `GET /chats/{id}/messages`, `POST /chats/{id}/messages`.
- ✅ `app/api/routes/suggestions.py` — `POST /chats/{id}/suggestions`.
- ✅ `app/api/routes/settings.py` — `GET/PUT /settings/default-new-ticket-mode`.
- ✅ `app/api/routes/rag.py` — загрузка, список, soft-delete документов.
- ✅ `app/api/routes/analytics.py` — `GET /analytics/report`.
- ✅ `app/api/routes/telegram.py` — `POST /integrations/telegram/webhook` (создаёт юзера/чат/тикет и стартует AI в фоне).
- ✅ `app/main.py` — FastAPI app + lifespan (init_engine, seed, start/stop scheduler).

### 7. Tests ✅

Все тесты зелёные (**23/23, ~1.6s**). Используется SQLite in-memory + StaticPool (одна БД на сессию), все провайдеры — моки, http-вызовы — через `httpx.AsyncClient` поверх ASGI-транспорта (без сети).

- ✅ `tests/conftest.py` — фикстуры `engine`, `db`, `providers`, `client`; моки внедряются через `override_providers`.
- ✅ `tests/test_seed_and_refs.py` — сид справочников, lookup-и.
- ✅ `tests/test_messages_flow.py` — создание тикета, смена режима → синхронизация статуса, outbox-запись, возврат в `pending_ai` по новому сообщению пользователя.
- ✅ `tests/test_ai_orchestrator.py` — reply, escalate по ключевым словам, защита на мусорный JSON.
- ✅ `tests/test_rag.py` — чанкинг, полный ingestion + retrieve на mock-эмбеддингах и in-memory store.
- ✅ `tests/test_outbox.py` — happy-path и retry с экспоненциальной задержкой.
- ✅ `tests/test_scheduler.py` — автозакрытие по неактивности.
- ✅ `tests/test_analytics.py` — отчёт собирается и на пустой БД, и на заполненной.
- ✅ `tests/test_api.py` — `/health`, `/analytics/report`, `/settings`, `/integrations/telegram/webhook`, `/rag/documents`.

Запуск: `make test` или `uv run pytest tests/ -q`.

### 8. Deployment ✅

- ✅ `backend/Dockerfile` — Python 3.12 slim, сборка окружения через `uv sync`, каталог `/app/storage` для local-провайдера.
- ✅ `backend/docker-compose.yml` — `api` + `postgres:16` + `qdrant:v1.12.0`, healthcheck-и, volumes.
- ✅ `backend/.dockerignore`, `backend/.gitignore`.
- ✅ `backend/Makefile` — `make sync run test migrate current revision lock up down logs clean`.
- ✅ `backend/README.md` — русские инструкции по быстрому старту, Docker, Telegram и конфигу.
- ✅ Alembic подключён: схема создаётся миграциями, docker-стек применяет их через отдельный сервис `migrate`, `Base.metadata.create_all` из startup убран.

## Ключевые архитектурные решения

- **Слоистая структура**: `api/` (HTTP) → `services/` (логика) → `db/` (персистентность) + `providers/` (внешние системы через интерфейсы).
- **Transactional Outbox**: исходящие сообщения сначала пишутся в `outbox_messages` в той же транзакции, что и `messages`; APScheduler раз в N секунд отправляет и помечает `sent_at`.
- **Hybrid RAG**: BM25 сам строим (`rank-bm25` как ориентир, но своя реализация в `BM25Encoder` — чтобы жить в одном процессе с FastAPI и знать словарь). Dense через OpenAI-совместимый endpoint (или `MockEmbedding` в тестах). Слияние через Reciprocal Rank Fusion с константой `k=60`.
- **Тесты — hermetic**: по умолчанию sqlite-in-memory + все моки. Реальные Qdrant / LLM включаются только переменной `E2E=1` (опционально).
- **Схема БД версионируется миграциями**: Alembic-ревизии в `backend/alembic/versions/`, сид справочников остаётся идемпотентным отдельным шагом.
- **Русские комментарии только**: линтер не проверяет, но стараемся держать единообразно.

## Текущий blocker / вопросы

Нет. Backend-реализация функционально завершена: 23/23 тестов зелёные.

## Что можно улучшить далее (не критично для MVP)

- Добавить Alembic, если схема начнёт меняться.
- Rate limiting и auth на публичных эндпоинтах (на MVP отсутствует сознательно).
- Миграция outbox-воркера на отдельный процесс для изоляции от API.
- Метрики (Prometheus).
- CI workflow (GitHub Actions) на прогон `make test`.

## Итерация 2 — расширение (2026-04-18, в работе)

По запросу пользователя добавляем:

### A. Парсинг файлов для RAG 🚧
- `pypdf` для PDF, `python-docx` для DOCX, plain utf-8 для md/txt.
- Опциональный OCR сканированных PDF через `pytesseract` с флагом `RAG_PDF_OCR_ENABLED`.
- `app/services/extractors.py` — абстракция `extract_text(filename, mime_type, content) -> str`.
- Новые конфиги: `RAG_MAX_UPLOAD_BYTES`, `RAG_ALLOWED_MIME_TYPES`, `RAG_PDF_OCR_ENABLED`.

### B. Логирование + Graylog 🚧
- Structured JSON-логи, human-readable в dev.
- Request-ID middleware (X-Request-ID).
- Логирование сервисных операций на INFO, DB-операций на DEBUG.
- Поддержка GELF UDP/TCP с флагами `GRAYLOG_ENABLED`, `GRAYLOG_HOST`, `GRAYLOG_PORT`, `GRAYLOG_PROTOCOL`.
- Per-module level overrides через `LOG_LEVELS="app.services.rag=DEBUG,..."`.
- Папка `docs/logging/` (RU): обзор, Graylog compose snippet, troubleshooting.

### C. Переход на uv ✅
- `pyproject.toml` хранит runtime/dev зависимости как единственный источник истины, `uv.lock` фиксирует разрешённый набор пакетов.
- Dockerfile использует `uv` вместо pip.
- Локальная разработка идёт через `uv sync --extra dev` и `uv run ...`.
- `requirements.txt` удалён, чтобы не было второго источника истины и дрейфа зависимостей.

### D. Folder-per-service deployment 🚧
- `postgres/` — compose, README (RU), `schema.dbml` (копия).
- `qdrant/` — compose, README (RU).
- `embedding/` — vLLM compose (GPU primary, CPU fallback), README (RU), модель через env.
- `llm/` — llama.cpp compose (CPU/GPU), README (RU), GGUF через volume mount.
- Корневой `docker-compose.yml` с `include:` на per-service файлы.
- Корневой `Makefile` с profile-based таргетами:
  - `make up` / `make down` / `make logs` (основной стек — API + postgres + qdrant, AI берём из облака по `.env`).
  - `make up-postgres` / `make up-qdrant` (по отдельности).
  - `make up-local-llm` / `make up-local-embedding` / `make up-local-ai`.
  - `make up-all` (всё, включая graylog).

## История изменений этого файла

- 2026-04-18 — создан, зафиксировано состояние после services/analytics.py.
- 2026-04-18 — добавлены API-роуты, FastAPI main, тесты (23/23), Docker/Compose, Makefile, README.
