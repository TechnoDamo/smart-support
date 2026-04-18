# LLM Server

Папка `llm/` содержит локальный OpenAI-совместимый сервер на llama.cpp. Он нужен, когда саму генеративную модель хочется держать локально, а backend должен обращаться к ней так же, как к облачному `/v1/chat/completions`.

## Роль в архитектуре

- backend использует стандартный `LLM_BASE_URL` и `LLM_MODEL`;
- при локальном режиме `LLM_BASE_URL` переключается на `http://llm:8080/v1`;
- модель передаётся как путь к GGUF-файлу внутри контейнера;
- embeddings при этом могут оставаться облачными или тоже быть локальными через `embedding/`.

## Требования

- GGUF-модель на хосте, доступная через volume `LLM_MODELS_DIR`.
- Для CPU-режима достаточно обычного Docker.
- Для GPU-ускорения настройте image/runtime под свою платформу отдельно; базовый compose ниже ориентирован на простой запуск без обязательной GPU-зависимости.

## Быстрый запуск отдельно

```bash
cd llm
LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
LLM_MODELS_DIR=../models \
docker compose up -d
```

Проверка:

```bash
curl http://localhost:8091/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local-llama","messages":[{"role":"user","content":"Привет"}]}'
```

## Запуск в составе всей системы

```bash
make up AI=local-llm OPENAI_API_KEY=sk-... \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  LLM_MODELS_DIR=./models
```

или вместе с локальными embeddings:

```bash
make up AI=local-ai \
  LLM_MODEL=/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  LLM_MODELS_DIR=./models \
  EMBEDDING_MODEL=BAAI/bge-m3 \
  EMBEDDING_VECTOR_SIZE=1024
```

## Практика деплоя

- Самый простой путь — держать GGUF в `./models` корня репозитория и монтировать каталог целиком.
- `LLM_MODEL` должен указывать на путь внутри контейнера, поэтому при монтировании `./models:/models` используйте формат `/models/имя.gguf`.
- `LLM_N_GPU_LAYERS=0` означает CPU-режим. Для частичного offload на GPU увеличьте значение.
