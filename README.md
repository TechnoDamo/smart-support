# Smart Support

![Архитектура системы](docs/architecture.png)

Система поддержки с AI-оператором, гибридным RAG и единым бэкофисом для живых операторов. Один монорепозиторий, один `.env`, одна команда `make up` — и у вас поднят весь стек: API, фронт оператора, Postgres, Qdrant, object storage и (по желанию) локальные LLM/embedding-сервера и Graylog.

> Всё настраивается через переменные. Хотите облачный OpenAI-совместимый провайдер — поднимайте `AI=cloud`. Нужен полностью автономный on-prem — `AI=local-ai`. Нужен только MinIO без локальных моделей — `AI=cloud STORAGE=minio`. Нужен централизованный лог — добавьте `GRAYLOG=true`.

## Содержание

- [Из чего состоит](#из-чего-состоит)
- [Как это работает](#как-это-работает)
- [Быстрый старт](#быстрый-старт)
- [Сценарии запуска](#сценарии-запуска)
- [Graylog: централизованное логирование](#graylog-централизованное-логирование)
- [Управление стеком](#управление-стеком)
- [Конфигурация через .env](#конфигурация-через-env)
- [Где искать детали](#где-искать-детали)

## Из чего состоит

| Компонент | Назначение | Путь |
|-----------|-----------|------|
| **backend** | FastAPI API, AI-оркестратор, RAG, outbox, планировщик | [`backend/`](backend/) |
| **frontend-support** | Next.js UI оператора: Inbox / Knowledge Base / Settings | [`frontend-support/`](frontend-support/) |
| **postgres** | Реляционные данные (чаты, тикеты, документы, outbox). Схема в `schema.dbml` | [`postgres/`](postgres/) |
| **qdrant** | Векторное хранилище для dense + sparse retrieval | [`qdrant/`](qdrant/) |
| **minio** | Локальное S3-совместимое object storage | [`minio/`](minio/) |
| **embedding** | Локальный OpenAI-совместимый embedding-сервер на vLLM | [`embedding/`](embedding/) |
| **llm** | Локальный OpenAI-совместимый LLM-сервер на llama.cpp | [`llm/`](llm/) |
| **graylog** | Централизованное логирование + веб-интерфейс | [`graylog/`](graylog/) |
| **docker-compose.yml** | Корневой orchestrator через `include:` всех подпроектов | корень |
| **Makefile** | Единая точка запуска с переключателями `AI` / `STORAGE` / `GRAYLOG` | корень |

## Как это работает

Схема потоков данных — в картинке в начале README. По шагам:

1. **Входящее сообщение** → backend создаёт/обновляет тикет и кладёт задачу в AI-оркестратор.
2. **Гибридный RAG** достаёт релевантные куски из базы знаний: dense-эмбеддинги + BM25 sparse, ранжирование через Reciprocal Rank Fusion (k=60).
3. **AI-оркестратор** решает: отвечает сам (`full_ai`), подсказывает оператору (`ai_assist`) или эскалирует (`pending_human`).
4. **Outbox** гарантирует доставку ответов в канал (Telegram etc.) даже после падения процесса.
5. **Frontend** опрашивает API и показывает оператору диалог, подсказки и RAG-контекст.

## Быстрый старт

**Требования:** Docker + Docker Compose, Make, Node 22 LTS (для локального фронта), свободные порты `8081, 3000, 5432, 6333, 9000, 9001` (и `19000, 12201` если нужен Graylog).

```bash
# 1. Скопируйте единый .env
cp .env.example .env

# 2. Поднимите стек на моках (без внешних ключей) — для первого запуска
make up AI=mock STORAGE=filesystem

# 3. Откройте Swagger и фронт
open http://localhost:8081/docs
cd frontend-support && nvm use && npm install && npm run dev
```

По умолчанию всё работает на моках, поэтому OpenAI-ключ, Qdrant и Telegram для первого запуска не нужны. Как только захочется реального AI — поднимайте один из сценариев ниже.

## Сценарии запуска

Общая форма:

```bash
make up AI=<режим> STORAGE=<режим> [GRAYLOG=true] [ПЕРЕМЕННЫЕ=...]
```

| `AI=` | `STORAGE=` | Что поднимается | Когда использовать |
|-------|-----------|-----------------|--------------------|
| `cloud` | `filesystem` | backend + postgres + qdrant, AI во внешний OpenAI-совместимый API | dev, быстрый старт, нет S3 |
| `cloud` | `minio` | + MinIO | dev-прод близко, нужен S3 |
| `local-embedding` | `minio` | + vLLM для эмбеддингов | экономим на embedding-счетах |
| `local-llm` | `minio` | + llama.cpp для LLM | экономим на LLM-счетах |
| `local-ai` | `minio` | полностью автономный стек | on-prem / эксперименты |
| `mock` | `filesystem` | чистые моки, без внешних вызовов | тесты, CI, первый запуск |

Примеры:

```bash
# Облачный OpenAI + локальные файлы
make up AI=cloud STORAGE=filesystem OPENAI_API_KEY=sk-...

# Облачный OpenAI + MinIO
make up AI=cloud STORAGE=minio OPENAI_API_KEY=sk-...

# Локальный embedding, облачный LLM
make up AI=local-embedding STORAGE=minio OPENAI_API_KEY=sk-... \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024

# Локальный LLM, облачный embedding
make up AI=local-llm STORAGE=minio OPENAI_API_KEY=sk-... \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf

# Полностью локальный AI
make up AI=local-ai STORAGE=minio \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024

# Моки для тестов
make up AI=mock STORAGE=filesystem
```

Что конкретно означают значения `AI=`, `STORAGE=` и какие переменные они переопределяют — смотрите в [Makefile](Makefile).

## Graylog: централизованное логирование

Опциональный слой. Добавляет Graylog 5.2 + Elasticsearch 7.17 + MongoDB 6 и автоматически создаёт GELF TCP input, в который backend отправляет структурированные JSON-логи.

```bash
# Поднять весь стек вместе с Graylog
make up AI=cloud STORAGE=minio GRAYLOG=true

# Смотреть только логи Graylog / Elasticsearch / Mongo
make logs-graylog
```

После старта:

- Web UI: <http://localhost:19000>
- Логин: `admin`
- Пароль: `admin` (меняется через `GRAYLOG_ADMIN_PASSWORD` в `.env`)
- Input `Smart Support Backend GELF TCP` на порту `12201` создаётся автоматически контейнером `smart-support-graylog-init`.

Подробности, готовые запросы и устранение неполадок — в [graylog/README.md](graylog/README.md).

## Управление стеком

```bash
make up AI=... STORAGE=... [GRAYLOG=true]   # поднять стек
make down                                    # остановить всё (с любыми профилями)
make restart AI=... STORAGE=...              # пересобрать и перезапустить
make logs AI=... STORAGE=...                 # поток логов всех сервисов
make logs-graylog                            # поток логов Graylog / Mongo / ES
make ps AI=... STORAGE=...                   # список контейнеров
make config AI=... STORAGE=...               # итоговый docker-compose (для отладки)
make pull AI=... STORAGE=...                 # обновить образы
make help                                    # шпаргалка по командам
```

Короткие алиасы: `make up-cloud`, `make up-local-ai`, `make up-mock`, `make up-minio`, `make up-graylog`.

## Конфигурация через .env

`.env` в корне — единый источник правды. Его читают:

- корневой `make up ...`;
- локальный backend, если запускать его без Docker из `backend/`;
- все docker-compose сервисы.

Файл разбит на блоки:

- **Инфраструктура** — Postgres / Qdrant / MinIO (логины, порты).
- **Основные параметры backend** — `APP_ENV`, `APP_HOST`, `APP_PORT`, `LOG_LEVEL`, `LOG_FORMAT`, CORS.
- **Graylog** — `GRAYLOG_ENABLED`, хост, порт, протокол, `GRAYLOG_ADMIN_PASSWORD`.
- **База данных** — `DATABASE_URL` (Postgres или SQLite).
- **LLM провайдер** — `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL` и т.п.
- **Embeddings провайдер** — симметрично LLM.
- **Векторное хранилище** — Qdrant / mock.
- **Object storage** — локальный путь или S3/MinIO.
- **Telegram** — токен, polling-интервалы.
- **Поведение** — таймауты тикетов, outbox, RAG-параметры (top-k, размер чанка, веса dense/sparse).
- **Локальный embedding (vLLM)** и **локальный LLM (llama.cpp)** — параметры для `AI=local-*`.

Полный шаблон с комментариями — в [`.env.example`](.env.example).

Для локального запуска backend вне Docker достаточно:
```bash
GRAYLOG_HOST=localhost            # вместо graylog
DATABASE_URL=postgresql+asyncpg://smart:smart@localhost:5432/smart
# или sqlite+aiosqlite:///./smart_support.db — если не нужен Postgres
```

## Где искать детали

- [backend/README.md](backend/README.md) — uv, миграции Alembic, структура API, тесты.
- [frontend-support/README.md](frontend-support/README.md) — Next.js, Node 22 LTS, переменные фронта.
- [postgres/README.md](postgres/README.md) — Postgres + DBML-схема.
- [qdrant/README.md](qdrant/README.md) — Qdrant, коллекции, dense + sparse.
- [minio/README.md](minio/README.md) — локальное S3 на MinIO.
- [embedding/README.md](embedding/README.md) — vLLM embedding server.
- [llm/README.md](llm/README.md) — llama.cpp LLM server.
- [graylog/README.md](graylog/README.md) — Graylog + Elasticsearch + Mongo.
- [docs/](docs/) — более глубокие документы по архитектуре, RAG и retrieval.
