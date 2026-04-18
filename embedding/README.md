# Embedding Server

Папка `embedding/` содержит локальный OpenAI-совместимый сервер эмбеддингов на vLLM. Он нужен, когда embeddings не хочется отдавать в облако и удобнее считать их рядом с backend и Qdrant.

## Роль в архитектуре

- backend вызывает `/v1/embeddings` так же, как облачный OpenAI-совместимый API;
- сама embedding-модель выбирается переменной `EMBEDDING_MODEL`;
- размерность обязательно синхронизируется с `EMBEDDING_VECTOR_SIZE`;
- результат уходит в Qdrant, а метаданные о чанках и retrieval остаются в Postgres.

## Быстрый запуск отдельно

```bash
cd embedding
EMBEDDING_MODEL=BAAI/bge-m3 EMBEDDING_VECTOR_SIZE=1024 docker compose up -d
```

По умолчанию сервер публикуется на `localhost:8090`.

Проверка:

```bash
curl http://localhost:8090/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"BAAI/bge-m3","input":"тест"}'
```

## Запуск в составе всей системы

```bash
make up AI=local-embedding OPENAI_API_KEY=sk-... \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024
```

или полностью локально:

```bash
make up AI=local-ai \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024
```

## Важные замечания

- Основной сценарий — NVIDIA GPU и Docker с `nvidia-container-toolkit`.
- CPU-фолбэк допустим только для экспериментов: он существенно медленнее.
- Если модель приватная на Hugging Face, передайте `HUGGING_FACE_HUB_TOKEN`.
- При смене embedding-модели не забудьте обновить `EMBEDDING_VECTOR_SIZE` и переиндексировать коллекцию в Qdrant.
