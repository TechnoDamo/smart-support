# PostgreSQL

PostgreSQL хранит все транзакционные данные системы: пользователей, чаты, тикеты, сообщения, аудит, outbox и метаданные RAG. Это источник истины для бизнес-состояния, тогда как сами векторы лежат в Qdrant.

## Роль в архитектуре

- `users`, `chats`, `tickets`, `messages` — ядро саппорт-процессов.
- `chat_mode_events`, `ticket_status_events` — аудит переходов.
- `outbox_messages` — гарантированная отправка ответов в каналы.
- `rag_*` — документы, версии, ingestion jobs, retrieval events, ссылки на точки в Qdrant.
- `app_settings` — прикладные настройки, включая режим новых тикетов.

Полная схема лежит в [postgres/schema.dbml](/Users/damir/Desktop/smart-support/postgres/schema.dbml).

## Быстрый запуск отдельно

```bash
cd postgres
docker compose up -d
```

По умолчанию:
- хост: `localhost:5432`
- пользователь: `smart`
- пароль: `smart`
- база: `smart`

Остановка:

```bash
docker compose down
docker compose down -v
```

## Запуск в составе всей системы

Из корня проекта:

```bash
make up AI=cloud
```

Postgres поднимется автоматически вместе с `api` и `qdrant`, а при необходимости и с локальными AI-сервисами.

## Практика деплоя

- Для локальной разработки достаточно дефолтных volume и порта `5432`.
- Для отдельного окружения меняйте `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` через переменные окружения.
- Таблицы создаются самим backend-ом при старте через `Base.metadata.create_all`, поэтому отдельный SQL bootstrap не нужен.

## Бэкап

```bash
docker exec smart-support-postgres pg_dump -U smart smart > backup.sql
cat backup.sql | docker exec -i smart-support-postgres psql -U smart smart
```
