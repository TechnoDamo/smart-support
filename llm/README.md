# LLM-сервер (llama.cpp)

Локальный OpenAI-совместимый LLM-сервер на базе [llama.cpp](https://github.com/ggerganov/llama.cpp). Нужен, когда генеративную модель нужно держать on-prem. Backend обращается к нему так же, как к облачному `/v1/chat/completions` — переключение происходит через `LLM_BASE_URL` без изменения кода.

Активируется профилями `local-llm` и `local-ai`.

---

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Шаг 1 — загрузка модели](#шаг-1--загрузка-модели)
- [Шаг 2 — настройка .env](#шаг-2--настройка-env)
- [Шаг 3 — запуск](#шаг-3--запуск)
- [Первый старт: что происходит внутри](#первый-старт-что-происходит-внутри)
- [Мониторинг логов](#мониторинг-логов)
- [Проверка работоспособности](#проверка-работоспособности)
- [Параметры](#параметры)
- [Устранение неполадок](#устранение-неполадок)

---

## Быстрый старт

```bash
# Проверить готовность и получить инструкции по загрузке модели:
make setup-local-llm

# Запустить стек с локальным LLM (облачные embeddings):
make up AI=local-llm STORAGE=filesystem

# Следить за логами:
make logs AI=local-llm STORAGE=filesystem
```

---

## Шаг 1 — загрузка модели

llama.cpp работает с моделями в формате **GGUF**. Файл нужно положить в директорию, указанную в `LLM_MODELS_DIR` (по умолчанию `./models` в корне репозитория).

### Рекомендуемые модели

| Модель | Размер файла | Параметры | Рекомендуется для |
|--------|-------------|-----------|-------------------|
| Qwen2.5-7B-Instruct-Q4_K_M | ~4.7 ГБ | 7B | Основной вариант |
| Qwen2.5-14B-Instruct-Q4_K_M | ~9 ГБ | 14B | Качество выше, нужно больше RAM |
| gemma-2-9b-it-Q4_K_M | ~5.5 ГБ | 9B | Альтернатива |

### Загрузка через wget

```bash
wget -P ./models \
  https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf
```

### Загрузка через huggingface-cli

```bash
pip install huggingface_hub

huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
  qwen2.5-7b-instruct-q4_k_m.gguf \
  --local-dir ./models
```

`huggingface-cli` показывает прогресс загрузки в терминале и поддерживает докачку. Если загрузка прервалась — повторите команду.

---

## Шаг 2 — настройка .env

```env
# Путь к GGUF-файлу внутри контейнера (/models — это смонтированный LLM_MODELS_DIR):
LLM_MODEL=/models/qwen2.5-7b-instruct-q4_k_m.gguf

# Директория с GGUF-файлами на хосте:
LLM_MODELS_DIR=./models

# Порт, на котором llama.cpp будет доступен с хоста:
LLM_PORT=8091

# Размер контекста в токенах (чем больше — тем больше RAM):
LLM_CTX_SIZE=4096

# CPU-режим (0 слоёв на GPU). Для частичного GPU-ускорения увеличьте значение:
LLM_N_GPU_LAYERS=0

# Число потоков CPU:
LLM_THREADS=8
```

---

## Шаг 3 — запуск

```bash
# Только локальный LLM, облачные embeddings:
make up AI=local-llm STORAGE=filesystem

# Полностью локальный стек (LLM + embeddings):
make up AI=local-ai STORAGE=filesystem
```

---

## Первый старт: что происходит внутри

Первый запуск llama.cpp занимает **от 30 секунд до нескольких минут** в зависимости от размера модели и числа CPU. Вот что происходит последовательно:

### 1. Загрузка образа Docker

При первом `make up` Docker скачивает образ `ghcr.io/ggerganov/llama.cpp:server` (~1-2 ГБ). Прогресс виден в терминале прямо во время выполнения команды.

### 2. Инициализация сервера

Сервер читает GGUF-файл и загружает веса модели в оперативную память. В логах это выглядит так:

```
llm_load_print_meta: model type       = 7B
llm_load_print_meta: model fsize      = 4.68 GiB
llm_load_tensors: ggml ctx size =    0.27 MiB
llm_load_tensors: CPU buffer size =  4794.93 MiB
...
llama_new_context_with_model: n_ctx      = 4096
llama_new_context_with_model: n_batch    = 512
...
{"level":"INFO","msg":"HTTP server listening","hostname":"0.0.0.0","port":8080}
```

Строка `HTTP server listening` означает, что сервер готов принимать запросы.

### 3. Healthcheck

Docker проверяет `/health` каждые 30 секунд. Пока сервер не ответил — контейнер `api` не запустится (`depends_on` в корневом compose это гарантирует, если вы добавите условие).

---

## Мониторинг логов

### Следить за запуском llama.cpp в реальном времени

```bash
# Из корня репозитория:
make logs AI=local-llm STORAGE=filesystem

# Только контейнер LLM:
docker logs -f smart-support-llm
```

### Ключевые строки в логах при старте

| Что ищем | Значение |
|----------|----------|
| `llm_load_print_meta: model type` | Модель начала загружаться |
| `llm_load_tensors: CPU buffer size` | Веса загружены в RAM (объём виден здесь) |
| `HTTP server listening` | Сервер готов, можно слать запросы |
| `slot available` | Свободный слот для обработки запроса |

### Следить только за запросами (без шума инициализации)

```bash
docker logs -f smart-support-llm 2>&1 | grep -E "(request|prompt|generated|slot)"
```

### Проверить потребление ресурсов

```bash
docker stats smart-support-llm
```

---

## Проверка работоспособности

```bash
# Проверить /health:
curl http://localhost:8091/health

# Тестовый запрос к API (после старта):
curl http://localhost:8091/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local",
    "messages": [{"role": "user", "content": "Привет, ты работаешь?"}],
    "max_tokens": 100
  }'
```

---

## Параметры

Все параметры задаются в `.env` и автоматически подставляются в команду запуска контейнера.

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `LLM_MODEL` | `/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf` | Путь к GGUF внутри контейнера |
| `LLM_MODELS_DIR` | `./models` | Директория с GGUF-файлами на хосте |
| `LLM_PORT` | `8091` | Внешний порт на хосте |
| `LLM_CTX_SIZE` | `4096` | Размер контекста в токенах |
| `LLM_N_GPU_LAYERS` | `0` | Слоёв на GPU (0 = CPU-режим) |
| `LLM_THREADS` | `8` | Число потоков CPU |
| `LLM_BATCH` | `512` | Размер батча при обработке |

---

## Устранение неполадок

**Контейнер сразу падает с ошибкой "model not found"**
→ Проверьте, что файл `LLM_MODEL` существует внутри контейнера:
```bash
docker run --rm -v ./models:/models ghcr.io/ggerganov/llama.cpp:server ls /models
```

**Сервер стартует очень медленно**
→ Нормально для больших моделей. Модель 7B на CPU загружается ~1-3 мин. Следите за логами — строка `HTTP server listening` означает готовность.

**Out of memory при старте**
→ Уменьшите `LLM_CTX_SIZE` (например до `2048`) или выберите модель меньшего размера (`Q3_K_M` вместо `Q4_K_M`).

**Backend не может подключиться к LLM**
→ В режиме `AI=local-llm` Makefile автоматически устанавливает `LLM_BASE_URL=http://llm:8080/v1`. Убедитесь, что запускаете через `make up`, а не напрямую через `docker compose`.
