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

## Сетевые доступы для установки

Локальный LLM не устанавливается как отдельное ПО на хост. Он поднимается как
Docker-контейнер `vllm/vllm-openai`, а snapshot модели скачивается в локальную
папку `models/` командой `make download-llm-model`. Локальные embeddings
работают так же: Docker-контейнер TEI плюс snapshot модели в `models/`.

Для первичной установки на тестовом стенде нужен исходящий HTTPS-доступ
`tcp/443` к адресам ниже. Если стенд должен работать без постоянного Интернета,
рекомендуемый вариант — один раз скачать образы и модели в разрешённой сети,
затем переложить их во внутренний Docker registry / artifact storage.

### Базовые инструменты хоста

Эти адреса нужны для `make ai-deployment-tools-setup`:

| Адрес | Для чего нужен |
| --- | --- |
| `https://get.docker.com` | Bootstrap-скрипт установки Docker |
| `https://download.docker.com` | Docker Engine / Docker Compose packages |
| `https://nvidia.github.io` | NVIDIA Container Toolkit repository и GPG key |
| `https://astral.sh` | Установка `uv` |
| `https://github.com` | Release assets для части installers, включая `uv` |
| `https://objects.githubusercontent.com` | Загрузка GitHub release assets |
| `https://pypi.org` | Python package index |
| `https://files.pythonhosted.org` | Файлы Python packages |

Также нужен доступ к системным пакетным репозиториям ОС стенда. Для Ubuntu это
обычно зеркала `archive.ubuntu.com`, `security.ubuntu.com` или внутренние
корпоративные apt mirrors.

### Docker images

Эти адреса нужны для `docker compose pull/up`:

| Адрес | Для чего нужен |
| --- | --- |
| `https://registry-1.docker.io` | Docker Hub registry |
| `https://auth.docker.io` | Авторизация Docker Hub |
| `https://production.cloudflare.docker.com` | CDN слоёв Docker Hub |
| `https://ghcr.io` | GitHub Container Registry для TEI |
| `https://pkg-containers.githubusercontent.com` | CDN слоёв GitHub Container Registry |
| `https://docker.elastic.co` | Elasticsearch image для Graylog |

Основные images:

```text
vllm/vllm-openai:v0.6.3
ghcr.io/huggingface/text-embeddings-inference:86-1.5
postgres:16
qdrant/qdrant:v1.12.0
python:3.12-slim
```

Опциональные images:

```text
minio/minio:RELEASE.2025-02-28T09-55-16Z
minio/mc:RELEASE.2025-03-12T17-29-24Z
graylog/graylog:5.2
mongo:6
docker.elastic.co/elasticsearch/elasticsearch:7.17.23
curlimages/curl:8.8.0
```

### Модели Hugging Face

Эти адреса нужны для `make download-llm-model` и
`make download-embedding-model`:

| Адрес | Для чего нужен |
| --- | --- |
| `https://huggingface.co` | Metadata, model repositories, small files |
| `https://cdn-lfs.huggingface.co` | Large files из Hugging Face LFS |
| `https://cas-bridge.xethub.hf.co` | Xet-backed model files |
| `https://transfer.xethub.hf.co` | Xet transfer endpoint |
| `https://cas-server.xethub.hf.co` | Xet CAS endpoint |

Модели по умолчанию:

```text
Qwen/Qwen2.5-0.5B-Instruct
BAAI/bge-small-en-v1.5
```

Для приватных или rate-limited загрузок можно задать `HUGGING_FACE_HUB_TOKEN` в
`.env`.

### Сборка backend image

Backend image собирается из `python:3.12-slim` и внутри Dockerfile выполняет
`apt-get update`, `apt-get install`, `pip install uv`, `uv sync`.

Для этого дополнительно нужны:

| Адрес | Для чего нужен |
| --- | --- |
| `https://deb.debian.org` | Debian packages внутри backend image |
| `https://security.debian.org` | Debian security packages внутри backend image |
| `https://pypi.org` | Python dependencies |
| `https://files.pythonhosted.org` | Python package files |

### Опциональные внешние API

Эти адреса не нужны для локального GPU-режима, но могут понадобиться при
соответствующих настройках:

| Адрес | Когда нужен |
| --- | --- |
| `https://api.openai.com` | Если `LLM=cloud` или `EMBEDDING=cloud` с OpenAI |
| `https://api.telegram.org` | Если включается Telegram-интеграция |
| S3 endpoint из `.env` | Если `OBJECT_STORAGE=cloud` |
| Managed PostgreSQL host из `.env` | Если `POSTGRES=cloud` |
| Managed Qdrant host из `.env` | Если `QDRANT=cloud` |

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
