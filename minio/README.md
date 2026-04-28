# MinIO

`minio/` даёт локальное S3-compatible объектное хранилище. Оно используется,
когда корневой стек запускается так:

```bash
make up OBJECT_STORAGE=local
```

`OBJECT_STORAGE=filesystem` не поднимает MinIO и пишет файлы в локальную папку
backend. `OBJECT_STORAGE=cloud` не поднимает MinIO и использует S3-переменные из
`.env`.

## Отдельные команды

```bash
cd minio
make up
make health
make logs
make down
```

Значения по умолчанию:

| Параметр | Значение |
| --- | --- |
| S3 API | `http://localhost:9000` |
| Console | `http://localhost:9001` |
| Пользователь | `smart` |
| Пароль | `smartminio123` |
| Bucket | `smart-support` |

`minio-init` автоматически создаёт `${S3_BUCKET}`, когда MinIO становится
healthy.

## Переменные для backend

При `OBJECT_STORAGE=local` корневой `Makefile` передаёт:

```text
OBJECT_STORAGE_PROVIDER=s3
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=${MINIO_ROOT_USER}
S3_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}
S3_BUCKET=${S3_BUCKET}
```

Для backend-а локальный MinIO выглядит как обычное S3-compatible хранилище.
