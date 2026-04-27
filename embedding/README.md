# Embedding-сервер (TEI)

Локальный OpenAI-совместимый сервер эмбеддингов на базе [Text Embeddings Inference (TEI)](https://github.com/huggingface/text-embeddings-inference) от HuggingFace. Нужен, когда эмбеддинги не хочется отдавать в облако. Backend вызывает `/v1/embeddings` так же, как облачный OpenAI-совместимый API.

Активируется профилями `local-embedding` и `local-ai`.

---

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Шаг 1 — выбор образа (CPU или GPU)](#шаг-1--выбор-образа-cpu-или-gpu)
- [Шаг 2 — настройка .env](#шаг-2--настройка-env)
- [Шаг 3 — запуск](#шаг-3--запуск)
- [Первый старт: что происходит внутри](#первый-старт-что-происходит-внутри)
- [Мониторинг загрузки модели](#мониторинг-загрузки-модели)
- [Проверка работоспособности](#проверка-работоспособности)
- [Параметры](#параметры)
- [Устранение неполадок](#устранение-неполадок)

---

## Быстрый старт

```bash
# Проверить готовность и получить инструкции:
make setup-local-embedding

# Запустить стек с локальными embeddings (облачный LLM):
make up AI=local-embedding STORAGE=filesystem

# Следить за загрузкой модели:
docker logs -f smart-support-embedding
```

---

## Шаг 1 — выбор образа (CPU или GPU)

TEI распространяется в отдельных образах для CPU и разных поколений GPU. Выбор — через переменную `TEI_IMAGE` в `.env`.

### CPU (без GPU)

Работает на любом хосте. Медленнее GPU в 5-20 раз, но приемлемо для небольших нагрузок и разработки.

```env
TEI_IMAGE=ghcr.io/huggingface/text-embeddings-inference:cpu-1.5
```

### GPU NVIDIA (рекомендуется для продакшена)

Требует установленного [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

```env
# Turing / Ampere (T4, A10, RTX 30xx):
TEI_IMAGE=ghcr.io/huggingface/text-embeddings-inference:turing-1.5

# Hopper / Ampere High-End (A100, H100, RTX 40xx):
TEI_IMAGE=ghcr.io/huggingface/text-embeddings-inference:89-1.5
```

Проверить поколение GPU:
```bash
nvidia-smi --query-gpu=name,compute_cap --format=csv
```

---

## Шаг 2 — настройка .env

```env
# Образ TEI (см. выше):
TEI_IMAGE=ghcr.io/huggingface/text-embeddings-inference:cpu-1.5

# HuggingFace-имя модели:
EMBEDDING_MODEL=minishlab/potion-base-32M

# Размерность выходных векторов — ОБЯЗАТЕЛЬНО совпадает с моделью:
EMBEDDING_VECTOR_SIZE=256

# Локальная папка для кеша скачанных моделей (относительно папки embedding/):
EMBEDDING_MODEL_STORAGE_FOLDER=.data

# Внешний порт TEI на хосте:
EMBEDDING_PORT=8090

# Токен HuggingFace (нужен только для приватных моделей):
HUGGING_FACE_HUB_TOKEN=

# Источник загрузки моделей:
HF_ENDPOINT=https://huggingface.co
```

> **Важно:** если сменили модель — обязательно обновите `EMBEDDING_VECTOR_SIZE` и переиндексируйте коллекцию в Qdrant. Qdrant создаёт коллекцию с фиксированной размерностью при первом старте и не пересоздаёт её автоматически.

---

## Шаг 3 — запуск

```bash
# Локальные embeddings, облачный LLM:
make up AI=local-embedding STORAGE=filesystem

# Полностью локальный стек:
make up AI=local-ai STORAGE=filesystem
```

---

## Первый старт: что происходит внутри

### 1. Загрузка образа Docker

При первом `make up` Docker скачивает образ TEI. CPU-образ весит ~2-4 ГБ, GPU-образ — ~6-10 ГБ. Прогресс виден прямо в терминале.

### 2. Загрузка модели из HuggingFace

TEI скачивает модель автоматически при первом запуске контейнера. Файлы кешируются в папку `embedding/.data` (или `EMBEDDING_MODEL_STORAGE_FOLDER`). При повторных запусках загрузки не происходит — используется кеш.

Что видно в логах во время загрузки:

```
Downloading files: 100%|██████████| 5/5 [00:12<00:00, 2.40s/file]
Loading model...
Starting HTTP server on 0.0.0.0:8000
```

### 3. Готовность

Сервер готов принимать запросы, когда в логах появится:
```
{"timestamp":"...","level":"INFO","message":"Ready"}
```

Healthcheck (`/health`) начинает отвечать `200 OK`. До этого момента контейнер `api` ждёт.

---

## Мониторинг загрузки модели

### Следить за прогрессом в реальном времени

```bash
# Только контейнер embedding:
docker logs -f smart-support-embedding

# Все сервисы стека:
make logs AI=local-embedding STORAGE=filesystem
```

### Ключевые строки в логах

| Что ищем | Значение |
|----------|----------|
| `Downloading files: X%` | Идёт загрузка модели с HuggingFace |
| `Loading model...` | Модель загружена, инициализация |
| `Ready` | Сервер принимает запросы |
| `inference request` | Запрос обработан успешно |

### Проверить, что модель закешировалась

```bash
ls -lh embedding/.data/
# Должны появиться .safetensors или .bin файлы
```

### Мониторинг потребления ресурсов

```bash
# CPU/RAM:
docker stats smart-support-embedding

# GPU (если используется):
watch -n 1 nvidia-smi
```

---

## Проверка работоспособности

```bash
# Проверить /health:
curl http://localhost:8090/health

# Тестовый запрос на эмбеддинг:
curl http://localhost:8090/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "minishlab/potion-base-32M",
    "input": "Тестовый запрос для проверки эмбеддинга"
  }'
```

Ожидаемый ответ — JSON с полем `data[0].embedding` длиной, совпадающей с `EMBEDDING_VECTOR_SIZE`.

---

## Параметры

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `TEI_IMAGE` | `...cpu-1.5` | Образ TEI (CPU или GPU-версия) |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | HuggingFace-имя модели |
| `EMBEDDING_VECTOR_SIZE` | `1536` | Размерность векторов |
| `EMBEDDING_MODEL_STORAGE_FOLDER` | `.data` | Кеш моделей (относительно `embedding/`) |
| `EMBEDDING_PORT` | `8090` | Внешний порт на хосте |
| `HUGGING_FACE_HUB_TOKEN` | пусто | Токен для приватных моделей |
| `HF_ENDPOINT` | `https://huggingface.co` | Источник загрузки |
| `DOCKER_PLATFORM` | `linux/amd64` | Платформа контейнера |

---

## Устранение неполадок

**Загрузка модели зависла**
→ Проверьте сетевое соединение. Если HuggingFace недоступен, можно использовать зеркало:
```env
HF_ENDPOINT=https://hf-mirror.com
```

**Ошибка `model not supported`**
→ Не все модели поддерживаются TEI. TEI работает только с моделями типа BERT/RoBERTa и их производными (dense embedding). Проверьте поддержку на [странице TEI](https://github.com/huggingface/text-embeddings-inference#supported-models).

**Контейнер вылетает с CUDA-ошибкой**
→ Вы используете GPU-образ без GPU или с несовместимым поколением. Переключитесь на CPU-образ или выберите правильный GPU-тег.

**Размерность векторов не совпадает с Qdrant**
→ Qdrant создаёт коллекцию один раз при первом старте. Если сменили модель — нужно пересоздать коллекцию:
```bash
# Удалить данные Qdrant и перезапустить (данные RAG будут утеряны):
docker volume rm smart-support_qdrant_data
make up AI=local-embedding STORAGE=filesystem
```

**Backend не подключается к embedding-серверу**
→ В режиме `AI=local-embedding` Makefile автоматически устанавливает `EMBEDDING_BASE_URL=http://embedding:8000/v1`. Убедитесь, что запускаете через `make up`, а не напрямую через `docker compose`.
