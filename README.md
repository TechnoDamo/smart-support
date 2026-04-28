# Smart Support

Smart Support — Docker Compose стек для автоматизации поддержки: PostgreSQL,
Qdrant, объектное хранилище, локальные GPU AI-сервисы и опциональный Graylog.

Корневой `Makefile` — единая точка запуска. У каждой внешней зависимости есть
отдельный флаг деплоя:

| Флаг | Значения | По умолчанию | Что означает |
| --- | --- | --- | --- |
| `LLM` | `local`, `cloud` | `local` | `local` поднимает vLLM на CUDA; `cloud` использует OpenAI-compatible API из `.env`. |
| `EMBEDDING` | `local`, `cloud` | `local` | `local` поднимает TEI на CUDA; `cloud` использует OpenAI-compatible API из `.env`. |
| `POSTGRES` | `local`, `cloud` | `local` | `local` поднимает PostgreSQL; `cloud` использует `DATABASE_URL`. |
| `QDRANT` | `local`, `cloud` | `local` | `local` поднимает Qdrant; `cloud` использует `QDRANT_URL` и `QDRANT_API_KEY`. |
| `OBJECT_STORAGE` | `filesystem`, `local`, `cloud` | `filesystem` | `filesystem` пишет в `./storage`; `local` поднимает MinIO; `cloud` использует S3-переменные из `.env`. |
| `GRAYLOG` | `local`, `false` | `false` | `local` поднимает Graylog, Mongo и Elasticsearch. |

## Быстрый запуск на GPU-сервере

Подключиться к серверу:

```bash
ssh root@vm-5735.user-project-2032.cloud.intcld.ru
```

Первый чистый деплой через Git:

```bash
ssh root@vm-5735.user-project-2032.cloud.intcld.ru
cd /root
git clone <repo-url> smart-support
cd smart-support
cp .env.example .env
make ai-deployment-tools-setup
make download-llm-model
make download-embedding-model
make up
```

Обычное обновление уже склонированного репозитория:

```bash
ssh root@vm-5735.user-project-2032.cloud.intcld.ru
cd /root/smart-support
git pull
make download-llm-model
make download-embedding-model
make up
```

Для отправки локальной незакоммиченной рабочей копии используйте `rsync`.
Команда ниже не отправляет модели, `.env`, Git-метаданные и локальные runtime
папки, но отправляет `.env.example`:

```bash
rsync -avz --progress \
  --exclude 'models/' \
  --exclude '.*/' \
  --exclude '.env' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  --exclude '*.log' \
  --exclude 'backend/storage/' \
  --exclude 'graylog/elasticsearch_data/' \
  --exclude 'graylog/mongodb_data/' \
  --exclude 'graylog/graylog_data/' \
  --exclude 'graylog/graylog_journal/' \
  ./ root@vm-5735.user-project-2032.cloud.intcld.ru:/root/smart-support/
```

После `rsync` на сервере:

```bash
cd /root/smart-support
cp -n .env.example .env
make ai-deployment-tools-setup
make download-llm-model
make download-embedding-model
make up
```

Дефолтный `make up` поднимает локальные PostgreSQL, Qdrant, vLLM, TEI и backend
с файловым объектным хранилищем.

## Частые сценарии запуска

Полностью локальный GPU-стек с файловым хранилищем:

```bash
make up
```

MinIO вместо файлового хранилища:

```bash
make up OBJECT_STORAGE=local
```

Облачные LLM и embedding API, но локальные PostgreSQL и Qdrant:

```bash
make up LLM=cloud EMBEDDING=cloud
```

Облачная инфраструктура и облачные AI API:

```bash
make up \
  LLM=cloud \
  EMBEDDING=cloud \
  POSTGRES=cloud \
  QDRANT=cloud \
  OBJECT_STORAGE=cloud
```

Включить Graylog:

```bash
make up GRAYLOG=local
make logs-graylog
```

## Команды Make

```bash
make help
make up
make down
make logs
make ps
make config
make pull
make restart
make ai-deployment-tools-setup
make download-llm-model
make download-embedding-model
```

Отдельные сервисы тоже имеют свои команды:

```bash
make -C llm help
make -C embedding help
make -C minio help
```

## Порты

| Сервис | URL |
| --- | --- |
| Backend API | `http://localhost:8081` |
| vLLM | `http://localhost:8091/v1` |
| TEI embeddings | `http://localhost:8090/v1` |
| Qdrant | `http://localhost:6333` |
| MinIO API | `http://localhost:9000` |
| MinIO console | `http://localhost:9001` |
| Graylog | `http://localhost:19000` |

## Настройки

- Локальный LLM работает только через vLLM на CUDA. Snapshot модели скачивается
  командой `make download-llm-model`.
- Локальные embeddings работают только через TEI на CUDA. Snapshot модели
  скачивается командой `make download-embedding-model`.
- Оба сервиса используют общий корневой кеш `models/`: из папок `llm/` и
  `embedding/` он монтируется как `../models`.
- Для cloud-режима заполните нужные переменные в `.env`: `LLM_BASE_URL`,
  `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`,
  `EMBEDDING_MODEL`, `DATABASE_URL`, `QDRANT_URL` и S3-переменные.

Документация по сервисам:

- [llm/README.md](llm/README.md)
- [embedding/README.md](embedding/README.md)
- [minio/README.md](minio/README.md)
- [postgres/README.md](postgres/README.md)
- [qdrant/README.md](qdrant/README.md)
- [graylog/README.md](graylog/README.md)
