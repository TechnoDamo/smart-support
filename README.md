# Smart Support

Монорепозиторий системы поддержки: backend на FastAPI, operator UI на Next.js, PostgreSQL для транзакционных данных, Qdrant для гибридного RAG, локальный или облачный object storage, а также опциональные локальные AI-сервисы для LLM и embeddings.

## Архитектура верхнего уровня

- `backend/` — API, бизнес-логика, AI-оркестратор, RAG, outbox, планировщик.
- `frontend-support/` — операторский интерфейс.
- `postgres/` — реляционная БД и схема в `schema.dbml`.
- `qdrant/` — векторная БД для dense+sparse retrieval.
- `minio/` — локальное S3-совместимое object storage.
- `embedding/` — локальный OpenAI-совместимый embedding-сервер на vLLM.
- `llm/` — локальный OpenAI-совместимый LLM-сервер на llama.cpp.
- `graylog/` — централизованная система логирования с веб-интерфейсом.
- `docker-compose.yml` — корневой orchestrator через `include:`.
- `Makefile` — единая точка запуска всего стека с переключением локальных/облачных AI-компонентов и object storage.

## Быстрый запуск всей системы

Перед запуском:

```bash
cp .env.example .env
```

Теперь `.env` в корне репозитория — единый источник конфигурации для всего проекта:
- корневого `make up ...`;
- локального запуска backend из `backend/`;
- docker-compose сервисов.

### Включение Graylog (централизованное логирование)

Для включения Graylog добавьте в `.env`:
```bash
# Graylog Configuration
GRAYLOG_ENABLED=true
GRAYLOG_HOST=localhost
GRAYLOG_PORT=12201
GRAYLOG_PROTOCOL=tcp
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Graylog будет доступен по адресу: http://localhost:19000
- Логин: `admin`
- Пароль: `admin`

### 1. Облачные AI-провайдеры + локальные файлы

```bash
make up AI=cloud STORAGE=filesystem OPENAI_API_KEY=sk-...
```

### 2. Облачные AI-провайдеры + локальный MinIO

```bash
make up AI=cloud STORAGE=minio OPENAI_API_KEY=sk-...
```

Что поднимется:
- `api`
- `postgres`
- `qdrant`
- `minio`

### 3. Локальный embedding, облачная LLM

```bash
make up AI=local-embedding STORAGE=minio OPENAI_API_KEY=sk-... \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024
```

### 4. Локальная LLM, облачные embeddings

```bash
make up AI=local-llm STORAGE=minio OPENAI_API_KEY=sk-... \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf
```

### 5. Полностью локальные AI-компоненты

```bash
make up AI=local-ai STORAGE=minio \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024
```

### 6. Режим моков

```bash
make up AI=mock STORAGE=filesystem
```

## Управление стеком

```bash
make down
make logs AI=local-ai STORAGE=minio
make ps AI=local-embedding STORAGE=minio
make config AI=local-llm STORAGE=filesystem
```

## Где смотреть детали

- [backend/README.md](/Users/damir/Desktop/smart-support/backend/README.md)
- [postgres/README.md](/Users/damir/Desktop/smart-support/postgres/README.md)
- [qdrant/README.md](/Users/damir/Desktop/smart-support/qdrant/README.md)
- [minio/README.md](/Users/damir/Desktop/smart-support/minio/README.md)
- [embedding/README.md](/Users/damir/Desktop/smart-support/embedding/README.md)
- [llm/README.md](/Users/damir/Desktop/smart-support/llm/README.md)
- [graylog/README.md](/Users/damir/Desktop/smart-support/graylog/README.md)
