.PHONY: help up down logs logs-graylog ps config pull restart \
        up-cloud up-local-embedding up-local-llm up-local-ai up-mock up-minio up-graylog \
        setup-local-llm setup-local-embedding setup-local-ai

AI ?= cloud
STORAGE ?= filesystem
GRAYLOG ?= false
COMPOSE ?= docker compose
COMPOSE_FILE ?= docker-compose.yml
LOAD_ENV := set -a; \
	if [ -f ./.env ]; then . ./.env; fi; \
	set +a;

PROFILE_ARGS := $(if $(filter local-ai,$(AI)),--profile local-ai,)
PROFILE_ARGS += $(if $(filter local-embedding,$(AI)),--profile local-embedding,)
PROFILE_ARGS += $(if $(filter local-llm,$(AI)),--profile local-llm,)
PROFILE_ARGS += $(if $(filter minio,$(STORAGE)),--profile local-object-storage,)
PROFILE_ARGS += $(if $(filter true,$(GRAYLOG)),--profile graylog,)
ALL_PROFILE_ARGS := --profile local-ai --profile local-embedding --profile local-llm --profile local-object-storage --profile graylog

ENV_ARGS := VECTOR_STORE_PROVIDER=$${VECTOR_STORE_PROVIDER:-qdrant}
ENV_ARGS += CHANNEL_TELEGRAM_PROVIDER=$${CHANNEL_TELEGRAM_PROVIDER:-mock}
ENV_ARGS += DATABASE_URL=postgresql+asyncpg://$${POSTGRES_USER:-smart}:$${POSTGRES_PASSWORD:-smart}@postgres:5432/$${POSTGRES_DB:-smart_support_db}
ENV_ARGS += QDRANT_URL=http://qdrant:6333
ENV_ARGS += QDRANT_API_KEY=$${QDRANT_API_KEY:-}
ENV_ARGS += PROMPTS_DIR=/app/prompts

ifeq ($(GRAYLOG),true)
ENV_ARGS += GRAYLOG_ENABLED=true
ENV_ARGS += GRAYLOG_HOST=graylog
ENV_ARGS += GRAYLOG_PORT=12201
ENV_ARGS += GRAYLOG_PROTOCOL=tcp
endif

ifeq ($(STORAGE),filesystem)
ENV_ARGS += OBJECT_STORAGE_PROVIDER=local
ENV_ARGS += OBJECT_STORAGE_LOCAL_PATH=$${OBJECT_STORAGE_LOCAL_PATH:-/app/storage}
else ifeq ($(STORAGE),minio)
ENV_ARGS += OBJECT_STORAGE_PROVIDER=s3
ENV_ARGS += S3_BUCKET=$${S3_BUCKET:-smart-support}
ENV_ARGS += S3_REGION=$${S3_REGION:-us-east-1}
ENV_ARGS += S3_ENDPOINT_URL=$${S3_ENDPOINT_URL:-http://minio:9000}
ENV_ARGS += S3_ACCESS_KEY_ID=$${S3_ACCESS_KEY_ID:-$${MINIO_ROOT_USER:-smart}}
ENV_ARGS += S3_SECRET_ACCESS_KEY=$${S3_SECRET_ACCESS_KEY:-$${MINIO_ROOT_PASSWORD:-smartminio123}}
else
$(error Unsupported STORAGE=$(STORAGE). Use one of: filesystem, minio)
endif

ifeq ($(AI),cloud)
# Облачный провайдер: URL и провайдер берутся из .env (LLM_BASE_URL, EMBEDDING_BASE_URL).
ENV_ARGS += LLM_PROVIDER=$${LLM_PROVIDER:-openai_compatible}
ENV_ARGS += LLM_BASE_URL=$${LLM_BASE_URL:-https://api.openai.com/v1}
ENV_ARGS += EMBEDDING_PROVIDER=$${EMBEDDING_PROVIDER:-openai_compatible}
ENV_ARGS += EMBEDDING_BASE_URL=$${EMBEDDING_BASE_URL:-https://api.openai.com/v1}
else ifeq ($(AI),local-embedding)
# LLM из .env, embedding жёстко на внутренний TEI-контейнер.
ENV_ARGS += LLM_PROVIDER=$${LLM_PROVIDER:-openai_compatible}
ENV_ARGS += LLM_BASE_URL=$${LLM_BASE_URL:-https://api.openai.com/v1}
ENV_ARGS += EMBEDDING_PROVIDER=openai_compatible
ENV_ARGS += EMBEDDING_BASE_URL=http://embedding:8000/v1
else ifeq ($(AI),local-llm)
# Embedding из .env, LLM жёстко на внутренний vLLM-контейнер.
# LLM_MODEL переключается на локальную модель, чтобы имя совпадало с --served-model-name.
ENV_ARGS += LLM_PROVIDER=openai_compatible
ENV_ARGS += LLM_BASE_URL=http://llm:8080/v1
ENV_ARGS += LLM_MODEL=$${LLM_MODEL_LOCAL:-Qwen/Qwen2.5-0.5B-Instruct}
ENV_ARGS += EMBEDDING_PROVIDER=$${EMBEDDING_PROVIDER:-openai_compatible}
ENV_ARGS += EMBEDDING_BASE_URL=$${EMBEDDING_BASE_URL:-https://api.openai.com/v1}
else ifeq ($(AI),local-ai)
# LLM и embedding жёстко на внутренние контейнеры — полностью автономный стек.
ENV_ARGS += LLM_PROVIDER=openai_compatible
ENV_ARGS += LLM_BASE_URL=http://llm:8080/v1
ENV_ARGS += LLM_MODEL=$${LLM_MODEL_LOCAL:-Qwen/Qwen2.5-0.5B-Instruct}
ENV_ARGS += EMBEDDING_PROVIDER=openai_compatible
ENV_ARGS += EMBEDDING_BASE_URL=http://embedding:8000/v1
else ifeq ($(AI),mock)
ENV_ARGS += LLM_PROVIDER=$${LLM_PROVIDER:-mock}
ENV_ARGS += EMBEDDING_PROVIDER=$${EMBEDDING_PROVIDER:-mock}
ENV_ARGS += VECTOR_STORE_PROVIDER=mock
else
$(error Unsupported AI=$(AI). Use one of: cloud, local-embedding, local-llm, local-ai, mock)
endif

help:
	@echo "Корневые команды Smart Support:"
	@echo "  make up AI=cloud STORAGE=filesystem      — backend + postgres + qdrant + локальные файлы"
	@echo "  make up AI=cloud STORAGE=minio           — backend + postgres + qdrant + MinIO"
	@echo "  make up AI=local-embedding STORAGE=minio — локальный TEI embedding + MinIO"
	@echo "  make up AI=local-llm STORAGE=minio       — локальный llama.cpp + MinIO"
	@echo "  make up AI=local-ai STORAGE=minio        — локальные llama.cpp + TEI + MinIO"
	@echo "  make up AI=mock STORAGE=filesystem       — backend на mock-провайдерах"
	@echo "  make up ... GRAYLOG=true                 — дополнительно поднять Graylog"
	@echo "  make down                                — остановить весь стек"
	@echo "  make logs AI=... STORAGE=...             — поток логов всех сервисов"
	@echo "  make logs-graylog                        — поток логов Graylog/Mongo/Elasticsearch"
	@echo "  make ps AI=... STORAGE=...               — список контейнеров"
	@echo "  make config AI=... STORAGE=...           — итоговый docker-compose (для отладки)"
	@echo ""
	@echo "Настройка локальных сервисов (перед первым запуском):"
	@echo "  make setup-local-llm                     — проверка и инструкции по загрузке GGUF-модели"
	@echo "  make setup-local-embedding               — проверка и инструкции по настройке TEI"
	@echo "  make setup-local-ai                      — оба сервиса сразу"
	@echo ""
	@echo "Параметры AI: cloud | local-embedding | local-llm | local-ai | mock"
	@echo "Параметры STORAGE: filesystem | minio"
	@echo "Параметры GRAYLOG: false | true"
	@echo ""
	@echo "Ключевые переменные .env:"
	@echo "  LLM_BASE_URL, LLM_API_KEY, LLM_MODEL    — облачный LLM-провайдер"
	@echo "  LLM_MODEL=/models/model.gguf            — путь к GGUF для local-llm/local-ai"
	@echo "  EMBEDDING_MODEL=..., EMBEDDING_VECTOR_SIZE=... — модель и размерность"
	@echo "  TEI_IMAGE=...                           — образ TEI (cpu-1.5 / turing-1.5 / 89-1.5)"
	@echo ""
	@echo "Подробности: llm/README.md, embedding/README.md"

up:
	@$(LOAD_ENV) env $(ENV_ARGS) $(COMPOSE) -f $(COMPOSE_FILE) $(PROFILE_ARGS) up -d --build

down:
	@$(LOAD_ENV) $(COMPOSE) -f $(COMPOSE_FILE) $(ALL_PROFILE_ARGS) down

logs:
	@$(LOAD_ENV) $(COMPOSE) -f $(COMPOSE_FILE) $(PROFILE_ARGS) logs -f

logs-graylog:
	@$(LOAD_ENV) $(COMPOSE) -f $(COMPOSE_FILE) --profile graylog logs -f graylog mongodb elasticsearch

ps:
	@$(LOAD_ENV) $(COMPOSE) -f $(COMPOSE_FILE) $(PROFILE_ARGS) ps

config:
	@$(LOAD_ENV) env $(ENV_ARGS) $(COMPOSE) -f $(COMPOSE_FILE) $(PROFILE_ARGS) config

pull:
	@$(LOAD_ENV) env $(ENV_ARGS) $(COMPOSE) -f $(COMPOSE_FILE) $(PROFILE_ARGS) pull

restart:
	@$(LOAD_ENV) env $(ENV_ARGS) $(COMPOSE) -f $(COMPOSE_FILE) $(PROFILE_ARGS) up -d --build --force-recreate

up-cloud:
	@$(MAKE) up AI=cloud

up-local-embedding:
	@$(MAKE) up AI=local-embedding

up-local-llm:
	@$(MAKE) up AI=local-llm

up-local-ai:
	@$(MAKE) up AI=local-ai

up-mock:
	@$(MAKE) up AI=mock

up-minio:
	@$(MAKE) up STORAGE=minio

up-graylog:
	@$(MAKE) up GRAYLOG=true

setup-local-llm:
	@$(LOAD_ENV) \
	  storage_dir=$${LLM_MODEL_STORAGE_FOLDER:-./models}; \
	  model=$${LLM_MODEL_LOCAL:-Qwen/Qwen2.5-0.5B-Instruct}; \
	  mkdir -p "$$storage_dir"; \
	  echo "=== Настройка локального LLM (vLLM) ==="; \
	  echo ""; \
	  echo "Образ vLLM:        $${VLLM_IMAGE:-vllm/vllm-openai:v0.6.3}"; \
	  echo "Модель:            $$model"; \
	  echo "Устройство:        $${LLM_DEVICE:-cpu}"; \
	  echo "Тип данных:        $${LLM_DTYPE:-float32}"; \
	  echo "Кеш моделей:       $$storage_dir"; \
	  echo ""; \
	  echo "Модель скачается автоматически при первом запуске из HuggingFace."; \
	  echo ""; \
	  echo "Для GPU замените в .env:"; \
	  echo "  LLM_DEVICE=cuda"; \
	  echo "  LLM_DTYPE=bfloat16"; \
	  echo ""; \
	  echo "Запуск:"; \
	  echo "  make up AI=local-llm STORAGE=filesystem"; \
	  echo ""; \
	  echo "Подробности и мониторинг первого запуска: llm/README.md"

setup-local-embedding:
	@$(LOAD_ENV) \
	  cache_dir=$${EMBEDDING_MODEL_STORAGE_FOLDER:-.data}; \
	  mkdir -p "embedding/$$cache_dir"; \
	  echo "=== Настройка локального Embedding (TEI) ==="; \
	  echo ""; \
	  echo "Модель:         $${EMBEDDING_MODEL:-BAAI/bge-small-en-v1.5}"; \
	  echo "Образ TEI:      $${TEI_IMAGE:-ghcr.io/huggingface/text-embeddings-inference:cpu-1.5}"; \
	  echo "Кеш моделей:    embedding/$$cache_dir"; \
	  echo ""; \
	  echo "Модель загружается автоматически при первом запуске с HuggingFace."; \
	  echo ""; \
	  echo "Выбор образа TEI (.env → TEI_IMAGE):"; \
	  echo "  CPU:             ghcr.io/huggingface/text-embeddings-inference:cpu-1.5"; \
	  echo "  GPU (T4):        ghcr.io/huggingface/text-embeddings-inference:turing-1.5"; \
	  echo "  GPU (A100/H100): ghcr.io/huggingface/text-embeddings-inference:89-1.5"; \
	  echo ""; \
	  echo "Для GPU нужен nvidia-container-toolkit:"; \
	  echo "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"; \
	  echo ""; \
	  echo "Запуск:"; \
	  echo "  make up AI=local-embedding STORAGE=filesystem"; \
	  echo ""; \
	  echo "Подробности и мониторинг загрузки модели: embedding/README.md"

setup-local-ai:
	@$(MAKE) setup-local-llm
	@echo ""
	@$(MAKE) setup-local-embedding
