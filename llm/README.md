# LLM-сервер (vLLM)

Локальный OpenAI-совместимый LLM-сервер на базе [vLLM](https://github.com/vllm-project/vllm). Обслуживает HuggingFace-модели и поддерживает как CPU (без GPU), так и NVIDIA GPU. Backend обращается к нему через стандартный `/v1/chat/completions` — переключение происходит через `LLM_BASE_URL` без изменения кода.

Активируется профилями `local-llm` и `local-ai`.

---

## Содержание

- [Быстрый старт](#быстрый-старт)
- [CPU или GPU](#cpu-или-gpu)
- [Настройка .env](#настройка-env)
- [Запуск](#запуск)
- [Первый старт: что происходит внутри](#первый-старт-что-происходит-внутри)
- [Мониторинг логов](#мониторинг-логов)
- [Проверка работоспособности](#проверка-работоспособности)
- [Параметры](#параметры)
- [Рекомендуемые модели](#рекомендуемые-модели)
- [Устранение неполадок](#устранение-неполадок)

---

## Быстрый старт

```bash
# Проверить конфигурацию и получить инструкции:
make setup-local-llm

# Запустить стек с локальным LLM (облачные embeddings):
make up AI=local-llm STORAGE=filesystem

# Следить за загрузкой модели и стартом сервера:
docker logs -f smart-support-llm
```

---

## CPU или GPU

vLLM переключается между CPU и GPU через две переменные в `.env`:

```env
# CPU-режим (без GPU, работает везде):
LLM_DEVICE=cpu
LLM_DTYPE=float32

# GPU-режим (NVIDIA, требует nvidia-container-toolkit):
LLM_DEVICE=cuda
LLM_DTYPE=bfloat16
```

На CPU vLLM работает медленнее, чем на GPU, но вполне пригоден для разработки и умеренной нагрузки. Модель `Qwen/Qwen2.5-0.5B-Instruct` (~1 ГБ) на CPU отвечает за 2-10 секунд на запрос.

---

## Настройка .env

```env
# Образ vLLM:
VLLM_IMAGE=vllm/vllm-openai:v0.6.3

# Директория для кеша моделей (HuggingFace скачивает сюда):
LLM_MODEL_STORAGE_FOLDER=./models

# Порт сервера на хосте:
LLM_PORT=8091

# Максимальная длина контекста в токенах (меньше = меньше RAM):
LLM_CTX_SIZE=2048

# Устройство и тип данных:
LLM_DEVICE=cpu
LLM_DTYPE=float32

# Объём RAM под KV-кеш (ГБ):
VLLM_CPU_KVCACHE_SPACE=4

# HuggingFace model ID для локального сервера:
LLM_MODEL_LOCAL=Qwen/Qwen2.5-0.5B-Instruct
```

> `LLM_MODEL_LOCAL` и `LLM_MODEL` — разные переменные. `LLM_MODEL` используется для облачного провайдера (`deepseek-chat`, `gpt-4o-mini` и т.п.). При запуске `AI=local-llm` Makefile автоматически подставляет `LLM_MODEL_LOCAL` в качестве имени модели для backend, чтобы оно совпадало с тем, что загрузил vLLM.

---

## Запуск

```bash
# Локальный LLM + облачные embeddings:
make up AI=local-llm STORAGE=filesystem

# Полностью локальный стек (LLM + embeddings):
make up AI=local-ai STORAGE=filesystem
```

---

## Первый старт: что происходит внутри

### 1. Загрузка образа Docker

При первом запуске Docker скачивает `vllm/vllm-openai:v0.6.3` (~8-12 ГБ — образ включает CUDA-библиотеки, даже в CPU-режиме). Прогресс виден в терминале во время `make up`.

### 2. Загрузка модели из HuggingFace

После старта контейнера vLLM скачивает модель в `/models` (смонтированный `LLM_MODEL_STORAGE_FOLDER`). При повторных запусках модель берётся из кеша — скачивания не будет.

В логах это выглядит так:

```
INFO     Downloading shards: 100%|██████████| 1/1 [00:45<00:00]
INFO     Loading model weights took 0.98 GB
INFO     Starting to serve on 0.0.0.0:8080.
```

### 3. Инициализация движка

vLLM инициализирует KV-кеш и прогревает движок. На CPU это занимает дополнительно 30-60 секунд:

```
INFO     # CPU blocks: 512, ...
INFO     Warming up model for 1 steps with batch size 256...
INFO     Application startup complete.
```

Строка `Application startup complete` означает, что сервер готов принимать запросы.

### Ориентировочное время первого старта

| Ситуация | Время |
|----------|-------|
| Первый запуск, скачивание 0.5B модели | 3-10 мин (зависит от сети) |
| Повторный запуск, модель в кеше | 1-3 мин |
| GPU-режим, модель в кеше | 20-60 сек |

---

## Мониторинг логов

### Следить за стартом в реальном времени

```bash
# Только контейнер LLM:
docker logs -f smart-support-llm

# Все сервисы стека:
make logs AI=local-llm STORAGE=filesystem
```

### Ключевые строки в логах

| Что ищем | Значение |
|----------|----------|
| `Downloading shards` | Идёт загрузка модели |
| `Loading model weights took` | Модель загружена, показан размер |
| `CPU blocks:` / `GPU blocks:` | KV-кеш выделен |
| `Warming up model` | Прогрев движка |
| `Application startup complete` | Сервер готов |
| `Received request` | Запрос принят и обрабатывается |

### Следить только за запросами

```bash
docker logs -f smart-support-llm 2>&1 | grep -E "(Received|Generated|request)"
```

### Мониторинг ресурсов

```bash
# CPU и RAM:
docker stats smart-support-llm

# GPU (если используется):
watch -n 1 nvidia-smi
```

---

## Проверка работоспособности

```bash
# Healthcheck:
curl http://localhost:8091/health

# Список загруженных моделей:
curl http://localhost:8091/v1/models

# Тестовый запрос:
curl http://localhost:8091/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-0.5B-Instruct",
    "messages": [{"role": "user", "content": "Привет, ты работаешь?"}],
    "max_tokens": 50
  }'
```

---

## Параметры

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `VLLM_IMAGE` | `vllm/vllm-openai:v0.6.3` | Образ vLLM |
| `LLM_MODEL_LOCAL` | `Qwen/Qwen2.5-0.5B-Instruct` | HuggingFace model ID |
| `LLM_MODEL_STORAGE_FOLDER` | `./models` | Кеш моделей на хосте |
| `LLM_PORT` | `8091` | Внешний порт на хосте |
| `LLM_CTX_SIZE` | `2048` | Максимальная длина контекста |
| `LLM_DEVICE` | `cpu` | Устройство: `cpu` или `cuda` |
| `LLM_DTYPE` | `float32` | Тип данных: `float32` (CPU) / `bfloat16` (GPU) |
| `VLLM_CPU_KVCACHE_SPACE` | `4` | RAM под KV-кеш в ГБ (только для CPU) |
| `HUGGING_FACE_HUB_TOKEN` | пусто | Токен для приватных моделей |
| `HF_ENDPOINT` | `https://huggingface.co` | Источник загрузки моделей |

---

## Рекомендуемые модели

| Модель | RAM (CPU, fp32) | Качество | Назначение |
|--------|----------------|----------|-----------|
| `Qwen/Qwen2.5-0.5B-Instruct` | ~2 ГБ | Базовое | Тестирование, разработка |
| `Qwen/Qwen2.5-1.5B-Instruct` | ~6 ГБ | Хорошее | Лёгкий продакшен |
| `Qwen/Qwen2.5-7B-Instruct` | ~28 ГБ | Высокое | Основной продакшен (CPU) |
| `Qwen/Qwen2.5-7B-Instruct` | ~16 ГБ VRAM | Высокое | GPU-продакшен (bfloat16) |

Все модели поддерживают русский язык и JSON-режим, необходимый для AI-оркестратора.

---

## Устранение неполадок

**Контейнер не стартует: `CUDA error` или `no CUDA devices`**
→ Вы используете GPU-режим на машине без GPU. Переключитесь на CPU в `.env`:
```env
LLM_DEVICE=cpu
LLM_DTYPE=float32
```

**`Out of memory` при старте**
→ Уменьшите `LLM_CTX_SIZE` (например до `1024`) или `VLLM_CPU_KVCACHE_SPACE` (например до `2`). Либо выберите меньшую модель.

**Backend возвращает `404 model not found`**
→ Имя модели в запросе не совпадает с загруженной. Убедитесь, что запускаете через `make up` (не напрямую `docker compose`) — Makefile автоматически согласовывает `LLM_MODEL` с `LLM_MODEL_LOCAL`.

**Загрузка модели зависла**
→ Проверьте сеть. Для использования зеркала HuggingFace:
```env
HF_ENDPOINT=https://hf-mirror.com
```
