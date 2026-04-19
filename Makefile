.PHONY: help up down logs logs-graylog ps config pull restart up-cloud up-local-embedding up-local-llm up-local-ai up-mock up-minio up-graylog

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
ENV_ARGS += DATABASE_URL=postgresql+asyncpg://$${POSTGRES_USER:-smart}:$${POSTGRES_PASSWORD:-smart}@postgres:5432/$${POSTGRES_DB:-smart}
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
ENV_ARGS += LLM_PROVIDER=$${LLM_PROVIDER:-openai_compatible}
ENV_ARGS += LLM_BASE_URL=$${LLM_BASE_URL:-https://api.openai.com/v1}
ENV_ARGS += EMBEDDING_PROVIDER=$${EMBEDDING_PROVIDER:-openai_compatible}
ENV_ARGS += EMBEDDING_BASE_URL=$${EMBEDDING_BASE_URL:-https://api.openai.com/v1}
else ifeq ($(AI),local-embedding)
ENV_ARGS += LLM_PROVIDER=$${LLM_PROVIDER:-openai_compatible}
ENV_ARGS += LLM_BASE_URL=$${LLM_BASE_URL:-https://api.openai.com/v1}
ENV_ARGS += EMBEDDING_PROVIDER=$${EMBEDDING_PROVIDER:-openai_compatible}
ENV_ARGS += EMBEDDING_BASE_URL=$${EMBEDDING_BASE_URL:-http://embedding:8000/v1}
else ifeq ($(AI),local-llm)
ENV_ARGS += LLM_PROVIDER=$${LLM_PROVIDER:-openai_compatible}
ENV_ARGS += LLM_BASE_URL=$${LLM_BASE_URL:-http://llm:8080/v1}
ENV_ARGS += EMBEDDING_PROVIDER=$${EMBEDDING_PROVIDER:-openai_compatible}
ENV_ARGS += EMBEDDING_BASE_URL=$${EMBEDDING_BASE_URL:-https://api.openai.com/v1}
else ifeq ($(AI),local-ai)
ENV_ARGS += LLM_PROVIDER=$${LLM_PROVIDER:-openai_compatible}
ENV_ARGS += LLM_BASE_URL=$${LLM_BASE_URL:-http://llm:8080/v1}
ENV_ARGS += EMBEDDING_PROVIDER=$${EMBEDDING_PROVIDER:-openai_compatible}
ENV_ARGS += EMBEDDING_BASE_URL=$${EMBEDDING_BASE_URL:-http://embedding:8000/v1}
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
	@echo "  make up AI=local-embedding STORAGE=minio — локальный vLLM + MinIO"
	@echo "  make up AI=local-llm STORAGE=minio       — локальный llama.cpp + MinIO"
	@echo "  make up AI=local-ai STORAGE=minio        — локальные llama.cpp + vLLM + MinIO"
	@echo "  make up AI=mock STORAGE=filesystem       — backend на mock-провайдерах"
	@echo "  make up ... GRAYLOG=true                 — дополнительно поднять Graylog"
	@echo "  make down                                — остановить весь стек"
	@echo "  make logs                                — поток логов всех сервисов"
	@echo "  make logs-graylog                        — поток логов Graylog/Mongo/Elasticsearch"
	@echo "  make ps                                  — список контейнеров"
	@echo "  make config AI=... STORAGE=...           — показать итоговую конфигурацию"
	@echo ""
	@echo "Параметры AI: cloud | local-embedding | local-llm | local-ai | mock"
	@echo "Параметры STORAGE: filesystem | minio"
	@echo "Параметры GRAYLOG: false | true"
	@echo ""
	@echo "Частые параметры:"
	@echo "  OPENAI_API_KEY=...                       — если AI идёт во внешний OpenAI-совместимый сервис"
	@echo "  LLM_MODEL=/models/model.gguf            — если запускается local-llm/local-ai"
	@echo "  EMBEDDING_MODEL=BAAI/bge-m3             — если запускается local-embedding/local-ai"
	@echo "  EMBEDDING_VECTOR_SIZE=1024              — должен совпадать с embedding-моделью"
	@echo "  MINIO_ROOT_USER=smart                   — логин локального object storage"
	@echo "  MINIO_ROOT_PASSWORD=smartminio123       — пароль локального object storage"

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
