# Локальные embeddings

`embedding/` поднимает OpenAI-compatible embedding-сервер через Hugging Face TEI
на NVIDIA CUDA. Локальный деплой подразумевает GPU-хост.

## Настройка

Из корня репозитория:

```bash
make ai-deployment-tools-setup
make download-embedding-model
make up EMBEDDING=local
```

Или отдельно:

```bash
cd embedding
make download-model
make up
make health
```

## Кеш модели

Snapshot модели скачивается в:

```text
${EMBEDDING_MODELS_DIR}/${EMBEDDING_MODEL_LOCAL}
```

Значения по умолчанию:

```text
EMBEDDING_MODELS_DIR=../models
EMBEDDING_MODEL_LOCAL=bge-small-en-v1.5
EMBEDDING_MODEL_SOURCE=BAAI/bge-small-en-v1.5
EMBEDDING_VECTOR_SIZE=384
```

При запуске из корневого стека backend получает:

```text
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=http://embedding:8000/v1
EMBEDDING_MODEL=${EMBEDDING_MODEL_LOCAL}
```

Снаружи TEI доступен по адресу:

```text
http://localhost:8090/v1
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
| `EMBEDDING_MODELS_DIR` | `../models` | Общий кеш моделей на хосте |
| `EMBEDDING_MODEL_LOCAL` | `bge-small-en-v1.5` | Имя папки модели в общем кеше |
| `EMBEDDING_MODEL_SOURCE` | `BAAI/bge-small-en-v1.5` | Hugging Face source для `make download-model` |
| `EMBEDDING_VECTOR_SIZE` | `384` | Размерность векторов для backend и Qdrant |
| `EMBEDDING_PORT` | `8090` | Порт TEI на хосте |
| `TEI_IMAGE` | `ghcr.io/huggingface/text-embeddings-inference:86-1.5` | Docker image TEI |

Подсказки по TEI image:

| GPU | Image |
| --- | --- |
| RTX 3090 / Ampere | `ghcr.io/huggingface/text-embeddings-inference:86-1.5` |
| T4 / Turing | `ghcr.io/huggingface/text-embeddings-inference:turing-1.5` |

## Проверка

```bash
curl -s http://localhost:8090/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "bge-small-en-v1.5",
    "input": "hello"
  }'
```

Если меняете embedding-модель, обновите `EMBEDDING_VECTOR_SIZE` и пересоздайте
или переиндексируйте коллекции Qdrant.
