# MinIO

`minio/` даёт локальное S3-совместимое объектное хранилище, чтобы backend мог работать не только с файловой системой, но и с настоящим bucket-based storage так же просто, как с Postgres.

## Роль в архитектуре

- backend остаётся на `OBJECT_STORAGE_PROVIDER=s3`;
- вместо AWS S3 используется локальный MinIO;
- документы RAG и исходные файлы кладутся в bucket `${S3_BUCKET}`;
- backend хранит в Postgres только `storage_url` и метаданные, а сами бинарные объекты лежат в MinIO.

## Быстрый запуск отдельно

```bash
cd minio
docker compose --profile local-object-storage up -d
```

По умолчанию:
- S3 API: `http://localhost:9000`
- Web console: `http://localhost:9001`
- логин: `smart`
- пароль: `smartminio123`
- bucket: `smart-support`

Сервис `minio-init` автоматически создаёт bucket при первом старте.

Остановка:

```bash
docker compose --profile local-object-storage down
docker compose --profile local-object-storage down -v
```

## Запуск в составе всей системы

Из корня проекта:

```bash
make up AI=cloud STORAGE=minio
```

или вместе с локальными AI-сервисами:

```bash
make up AI=local-ai STORAGE=minio \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024
```

## Что backend получает автоматически

При `STORAGE=minio` root `Makefile` прокинет:

- `OBJECT_STORAGE_PROVIDER=s3`
- `S3_ENDPOINT_URL=http://minio:9000`
- `S3_ACCESS_KEY_ID=${MINIO_ROOT_USER}`
- `S3_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}`
- `S3_BUCKET=${S3_BUCKET}`

То есть для backend-а MinIO выглядит как обычный S3.
