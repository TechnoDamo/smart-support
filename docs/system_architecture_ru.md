# Архитектура и эксплуатация Smart Support

Документ описывает, как сейчас устроен backend-контур, как поднимается стек, как применяются миграции, как работают Telegram, RAG, фоновый ingestion и object storage.

## 1. Общая схема

Система состоит из следующих основных частей:

- `frontend-support/` — UI оператора.
- `backend/` — FastAPI API, продуктовая логика, AI-оркестратор, RAG, outbox, scheduler.
- `postgres/` — реляционная БД для чатов, тикетов, сообщений, событий, настроек, RAG-метаданных.
- `qdrant/` — векторная БД для dense + sparse retrieval.
- `minio/` — локальное S3-совместимое object storage.
- `embedding/` — локальный OpenAI-совместимый сервер эмбеддингов на vLLM.
- `llm/` — локальный OpenAI-совместимый LLM-сервер на llama.cpp.

Корневой `docker-compose.yml` собирает сервисы через `include:`, а корневой `Makefile` позволяет выбирать:

- где живут AI-компоненты: `AI=cloud | local-embedding | local-llm | local-ai | mock`
- как хранить бинарные объекты: `STORAGE=filesystem | minio`

## 2. Как поднимается стек

### 2.1 Полноценный стек

Примеры:

```bash
make up AI=cloud STORAGE=filesystem OPENAI_API_KEY=...
make up AI=cloud STORAGE=minio OPENAI_API_KEY=...
make up AI=local-ai STORAGE=minio \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024
```

### 2.2 Что происходит при старте backend

`backend/docker-compose.yml` поднимает два ключевых сервиса:

- `migrate` — one-shot контейнер, который делает `alembic upgrade head`
- `api` — контейнер FastAPI

Порядок старта такой:

1. PostgreSQL должен стать healthy.
2. Контейнер `migrate` применяет все Alembic-миграции.
3. Только после этого запускается `api`.
4. Сам `api` больше не создаёт схему через ORM-метаданные.

Это важно: схема БД теперь управляется только через Alembic.

## 3. Миграции

Миграции лежат в `backend/alembic/`.

Основные команды внутри `backend/`:

```bash
make migrate
make current
make revision MESSAGE="описание изменения"
```

Текущий принцип:

- deploy-применение миграций делается отдельным контейнером `migrate`
- локально и в тестах используется тот же Alembic-путь
- `Base.metadata.create_all(...)` больше не участвует в runtime-контуре

## 4. Telegram: webhook и polling

Сейчас для входящих Telegram-сообщений поддерживаются два режима.

### 4.1 Webhook

Маршрут:

- `POST /integrations/telegram/webhook`

Сценарий:

1. Telegram присылает update в backend.
2. Backend создаёт/находит пользователя и чат.
3. Backend сохраняет входящее сообщение.
4. При необходимости создаёт тикет.
5. После фиксации сообщения отдельно запускает AI-оркестратор.

### 4.2 Polling

Если включить:

```env
CHANNEL_TELEGRAM_PROVIDER=telegram
TELEGRAM_POLLING_ENABLED=true
SCHEDULER_TELEGRAM_POLLING_INTERVAL_SECONDS=5
```

scheduler начинает периодически ходить в `getUpdates` и обрабатывать update-ы тем же кодом, что и webhook.

Offset polling хранится в `app_settings`, чтобы после рестарта не перечитывать старые update-ы.

### 4.3 Важное правило

Нужно использовать **либо webhook, либо polling**, но не оба одновременно. Иначе один и тот же update может быть обработан дважды.

## 5. RAG и ingestion

### 5.1 Что хранится где

- исходный файл документа лежит в object storage
- метаданные документа, версий и чанков лежат в PostgreSQL
- dense и sparse векторы лежат в Qdrant

### 5.2 Загрузка документа

`POST /rag/documents` сейчас делает следующее:

1. Сохраняет исходный файл в object storage.
2. Создаёт `rag_document`.
3. Создаёт `rag_ingestion_job`.
4. Выполняет ingestion синхронно в рамках текущего запроса.

То есть upload уже сразу пытается довести job до `done`.

### 5.3 Фоновый ingestion worker

Дополнительно теперь есть фоновый ingestion worker, который подхватывает jobs со статусами:

- `queued`
- `failed`
- `processing`, если job зависла и превысила timeout

Worker:

1. находит документ
2. восстанавливает ключ объекта в object storage
3. загружает исходный файл
4. повторно запускает ingestion
5. ограничивает время обработки через timeout из конфига

Настройки:

```env
RAG_INGESTION_MAX_RETRIES=3
RAG_INGESTION_JOB_TIMEOUT_SECONDS=120
RAG_INGESTION_WORKER_BATCH_SIZE=10
SCHEDULER_INGESTION_RETRY_INTERVAL_SECONDS=120
```

## 6. Outbox

Исходящие сообщения не отправляются напрямую как единственный источник истины.

Сначала backend:

1. создаёт `messages`
2. создаёт `outbox_messages`
3. scheduler отдельным циклом отправляет pending/retry сообщения в канал

Это даёт более устойчивую доставку и ретраи на временных ошибках канала.

## 7. Object storage

Поддерживаются два режима.

### 7.1 Локальная файловая система

```bash
make up STORAGE=filesystem
```

Backend сохраняет файлы в локальный каталог и использует `file://` URL.

### 7.2 MinIO

```bash
make up STORAGE=minio
```

Backend остаётся в режиме `OBJECT_STORAGE_PROVIDER=s3`, а MinIO выглядит для него как обычный S3-совместимый backend.

## 8. Что ещё стоит доделать

Текущий контур уже рабочий, но архитектурно ещё есть разумные следующие шаги:

1. Сделать upload документа полностью асинхронным, чтобы HTTP-ручка только ставила job в очередь.
2. Вынести ingestion worker в отдельный процесс/сервис, а не держать его только внутри scheduler API-процесса.
3. Явно зафиксировать стратегию Telegram: webhook-only или polling-only для окружения.
4. Пересобрать sparse retrieval-путь, потому что текущая BM25-реализация имеет важные ограничения.
