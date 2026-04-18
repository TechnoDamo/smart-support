# Smart Support Backend

Backend умной поддержки на FastAPI. Управляет чатами, тикетами, AI-оркестрацией и RAG-поиском. Полностью настраивается через переменные окружения: можно работать с облачными OpenAI-совместимыми провайдерами или с локальными LLM/embedding-серверами, а для object storage выбирать локальную файловую систему или S3-совместимое хранилище вроде MinIO.

## Возможности

- FastAPI + SQLAlchemy 2.x async.
- PostgreSQL или SQLite.
- Гибридный RAG: dense-эмбеддинги + BM25 sparse + fusion через RRF.
- AI-оркестратор для `full_ai`.
- Подсказки оператору для `ai_assist`.
- Transactional outbox.
- APScheduler для фоновых задач.
- Полный набор моков для hermetic-тестов.

## Управление Python через uv

Backend теперь использует `uv` как единый менеджер окружения и зависимостей. `requirements.txt` больше не используется, чтобы в проекте не было двух источников истины.

Пример установки `uv` на macOS:

```bash
brew install uv
```

После этого все локальные команды идут через `make` или `uv run`. Если `uv` уже установлен локально и лежит в `~/.local/bin/uv`, `Makefile` тоже его подхватит.

## Быстрый старт локально без Docker

```bash
cd backend
cp .env.example .env
make sync
make run
```

Swagger UI будет на `http://localhost:8081/docs`.

По умолчанию всё поднимается на моках, поэтому для первого запуска не нужны ни OpenAI, ни Qdrant, ни Telegram.

Если backend подключается к Postgres из папки `postgres/` или из корневого стека репозитория, локальный URL должен быть таким:

```bash
DATABASE_URL=postgresql+asyncpg://smart:smart@localhost:5432/smart
```

Если у вас уже есть свой локальный Postgres с другими логином, паролем или названием базы, просто переопределите `DATABASE_URL` под него.

## Docker: как теперь запускать

### Только backend-контейнер

Если инфраструктура уже есть отдельно, можно запустить только API:

```bash
cd backend
docker compose up --build
```

В этом режиме `backend/docker-compose.yml` поднимает только сервис `api`, а адреса БД/Qdrant задаются через переменные окружения.

### Весь стек системы

Полный локальный стек теперь запускается из корня репозитория:

```bash
make up AI=cloud
make up AI=local-embedding
make up AI=local-llm
make up AI=local-ai
make up AI=mock
```

Это предпочтительный путь для среды разработки и демо.

## Конфигурация

Все ключевые параметры лежат в `backend/.env.example`.

| Группа | Параметры | Описание |
|---|---|---|
| БД | `DATABASE_URL` | PostgreSQL или SQLite |
| LLM | `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Любой OpenAI-совместимый endpoint |
| Embeddings | `EMBEDDING_*` | Параметры embedding-провайдера |
| Vector store | `VECTOR_STORE_PROVIDER`, `QDRANT_URL` | `qdrant` или `mock` |
| Object storage | `OBJECT_STORAGE_PROVIDER`, `OBJECT_STORAGE_LOCAL_PATH`, `S3_*` | Локальный диск или S3 |
| Telegram | `CHANNEL_TELEGRAM_PROVIDER`, `TELEGRAM_BOT_TOKEN` | Реальный канал или mock |
| Поведение | `DEFAULT_CHAT_MODE`, `TICKET_INACTIVITY_TIMEOUT_MINUTES`, `OUTBOX_*` | Бизнес-логика и ретраи |

## Тесты

```bash
make test
```

Тесты используют SQLite in-memory и моки всех внешних систем.

Если нужен прямой вызов без `make`, используйте:

```bash
uv run pytest tests/ -q
```

## Структура проекта

```
backend/
├── app/
│   ├── api/routes/
│   ├── db/
│   ├── providers/
│   ├── schemas/
│   ├── services/
│   ├── config.py
│   ├── main.py
│   └── prompts.py
├── prompts/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── uv.lock
```


## Миграции

Теперь backend использует полноценный Alembic-flow. Первичная схема зафиксирована отдельной ревизией в `alembic/versions/`, а при docker-развёртывании миграции выполняются отдельным one-shot сервисом `migrate` до старта `api`.

Основные команды:

```bash
make migrate
make current
make revision MESSAGE="add new field"
make lock
```

`Base.metadata.create_all(...)` больше не используется. В docker-стеке миграции применяет отдельный контейнер, в тестах и локальных CLI-командах используется тот же Alembic-путь. Локально Alembic запускается через `uv run`, а Dockerfile собирает окружение через `uv sync`.

## Частые проблемы локального запуска

### Ошибка `asyncpg.exceptions.InvalidPasswordError`

Проверьте, что `DATABASE_URL` совпадает с реальными кредами вашей локальной БД.

Для инфраструктуры из этого репозитория ожидаются:

- пользователь: `smart`
- пароль: `smart`
- база: `smart`
- порт: `5432`

Если Postgres был инициализирован раньше с другими значениями, есть два варианта:

1. Прописать в `DATABASE_URL` фактические креды уже существующей базы.
2. Пересоздать Postgres data volume и поднять контейнер заново с нужными переменными.

### Бесконечные reload при `make run`

`make run` теперь следит только за `app/` и `prompts/`, поэтому изменения внутри `.uv-cache` и `.venv` не должны больше вызывать перезапуск backend.
