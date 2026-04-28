# Qdrant

Qdrant хранит векторные представления RAG-коллекций. В нашей схеме backend использует гибридный поиск: dense-векторы от embedding-модели плюс sparse BM25-векторы, после чего объединяет результаты через RRF.

## Роль в архитектуре

- `dense` named vector — плотный embedding запроса или чанка.
- `sparse` named vector — локально посчитанный BM25-профиль.
- `payload` — служебные поля для обратной связи с Postgres (`document_id`, `chunk_index`, `source_name`).
- идентификатор point дублируется в `rag_document_chunks.qdrant_point_id`.

Qdrant не хранит бизнес-истину по документам: это делает Postgres. Он отвечает только за retrieval и similarity-search.

## Быстрый запуск отдельно

```bash
cd qdrant
docker compose --profile local-qdrant up -d
```

По умолчанию:
- HTTP API: `http://localhost:6333`
- gRPC: `localhost:6334`
- dashboard: `http://localhost:6333/dashboard`

Если нужен API key:

```bash
QDRANT_API_KEY=secret docker compose --profile local-qdrant up -d
```

Остановка:

```bash
docker compose --profile local-qdrant down
docker compose --profile local-qdrant down -v
```

## Запуск в составе всей системы

Из корня проекта:

```bash
make up QDRANT=local
```

Qdrant будет доступен backend-у как `http://qdrant:6333` внутри docker-сети `smart-support`.

## Практика деплоя

- Коллекция создаётся backend-ом автоматически при первом ingestion.
- При смене embedding-модели и размерности нужно либо пересоздать коллекцию, либо заводить новую коллекцию и переиндексировать документы.
- Для production имеет смысл включить `QDRANT_API_KEY` и вынести volume на управляемое хранилище.
