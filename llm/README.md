# Локальный LLM

`llm/` поднимает локальный OpenAI-compatible LLM-сервер через vLLM на NVIDIA
CUDA. CPU-режимы и llama.cpp намеренно убраны: локальный деплой подразумевает
GPU-хост.

## Настройка

Из корня репозитория:

```bash
make ai-deployment-tools-setup
make download-llm-model
make up LLM=local
```

Или отдельно:

```bash
cd llm
make download-model
make up
make health
```

## Кеш модели

Snapshot модели скачивается в:

```text
${LLM_MODELS_DIR}/${LLM_MODEL_LOCAL}
```

Значения по умолчанию:

```text
LLM_MODELS_DIR=../models
LLM_MODEL_LOCAL=qwen2.5-0.5b-instruct
LLM_MODEL_SOURCE=Qwen/Qwen2.5-0.5B-Instruct
```

При запуске из корневого стека backend получает:

```text
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://llm:8080/v1
LLM_MODEL=${LLM_MODEL_LOCAL}
```

Снаружи vLLM доступен по адресу:

```text
http://localhost:8091/v1
```

## Команды

```bash
make help
make download-model
make check-model
make up
make health
make logs
make down
```

## Основные переменные

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `LLM_MODELS_DIR` | `../models` | Общий кеш моделей на хосте |
| `LLM_MODEL_LOCAL` | `qwen2.5-0.5b-instruct` | Имя папки модели и served model name |
| `LLM_MODEL_SOURCE` | `Qwen/Qwen2.5-0.5B-Instruct` | Hugging Face source для `make download-model` |
| `LLM_PORT` | `8091` | Порт vLLM на хосте |
| `VLLM_IMAGE` | `vllm/vllm-openai:v0.6.3` | Docker image vLLM |
| `LLM_CTX_SIZE` | `2048` | Максимальная длина контекста |
| `LLM_DTYPE` | `bfloat16` | dtype для vLLM |

## Проверка

```bash
curl -s http://localhost:8091/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2.5-0.5b-instruct",
    "messages": [{"role": "user", "content": "Say hello in one sentence"}],
    "max_tokens": 32
  }'
```

Если контейнер сразу завершается, проверьте:

```bash
docker logs smart-support-llm
nvidia-smi
```

Стартовый скрипт падает сразу, если GPU не виден внутри контейнера или если
папка snapshot модели отсутствует.
