.PHONY: help setup download-model check-model up down logs ps config health

COMPOSE ?= docker compose
COMPOSE_PROJECT_NAME ?= smart-support
PROFILE := local-llm
SERVICE := llm
LOAD_ENV := set -a; \
	if [ -f ../.env ]; then . ../.env; fi; \
	set +a;

help:
	@echo "Команды для локального LLM-сервера (vLLM / CUDA):"
	@echo "  make setup           — показать текущую конфигурацию"
	@echo "  make download-model  — скачать HF snapshot модели"
	@echo "  make check-model     — проверить наличие скачанной модели"
	@echo "  make up              — поднять vLLM-сервер"
	@echo "  make down            — остановить и удалить контейнер"
	@echo "  make logs            — смотреть логи"
	@echo "  make ps              — состояние контейнера"
	@echo "  make config          — итоговый docker-compose-конфиг"
	@echo "  make health          — проверить /health"

setup:
	@$(LOAD_ENV) \
	  models_dir=$${LLM_MODELS_DIR:-../models}; \
	  model_alias=$${LLM_MODEL_LOCAL:-qwen2.5-0.5b-instruct}; \
	  model_source=$${LLM_MODEL_SOURCE:-Qwen/Qwen2.5-0.5B-Instruct}; \
	  echo "=== Настройка локального LLM (vLLM / CUDA) ==="; \
	  echo ""; \
	  echo "Образ:       $${VLLM_IMAGE:-vllm/vllm-openai:v0.6.3}"; \
	  echo "Модель:      $$model_alias"; \
	  echo "HF-источник: $$model_source"; \
	  echo "Тип данных:  $${LLM_DTYPE:-bfloat16}"; \
	  echo "Контекст:    $${LLM_CTX_SIZE:-2048} токенов"; \
	  echo "Папка:       $$models_dir/$$model_alias"; \
	  echo ""; \
	  echo "Быстрый старт:"; \
	  echo "  make download-model"; \
	  echo "  make up"; \
	  echo "  make health"

download-model:
	@$(LOAD_ENV) \
	  if ! command -v uv >/dev/null 2>&1; then \
	    echo "Ошибка: нужен uv. Запустите: make ai-deployment-tools-setup из корня проекта."; \
	    exit 1; \
	  fi; \
	  models_dir=$${LLM_MODELS_DIR:-../models}; \
	  model_alias=$${LLM_MODEL_LOCAL:-qwen2.5-0.5b-instruct}; \
	  model_source=$${LLM_MODEL_SOURCE:-Qwen/Qwen2.5-0.5B-Instruct}; \
	  mkdir -p "$$models_dir"; \
	  echo "Скачиваем LLM snapshot '$$model_source' → $$models_dir/$$model_alias"; \
	  HF_ENDPOINT="$${HF_ENDPOINT:-https://huggingface.co}" \
	  HUGGING_FACE_HUB_TOKEN="$${HUGGING_FACE_HUB_TOKEN:-}" \
	  uv run --quiet --with huggingface_hub python ../scripts/download_hf_model.py \
	    --repo-id "$$model_source" \
	    --local-dir "$$models_dir/$$model_alias" \
	    --endpoint "$${HF_ENDPOINT:-https://huggingface.co}" \
	    --token "$${HUGGING_FACE_HUB_TOKEN:-}" \
	    --clean

check-model:
	@$(LOAD_ENV) \
	  models_dir=$${LLM_MODELS_DIR:-../models}; \
	  model_alias=$${LLM_MODEL_LOCAL:-qwen2.5-0.5b-instruct}; \
	  model_dir="$$models_dir/$$model_alias"; \
	  if [ ! -f "$$model_dir/config.json" ]; then \
	    echo "Ошибка: модель не найдена в $$model_dir"; \
	    echo "Сначала выполните: make -C llm download-model"; \
	    exit 1; \
	  fi; \
	  echo "LLM-модель найдена: $$model_dir"

up: check-model
	@$(LOAD_ENV) COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) \
	  $(COMPOSE) --profile $(PROFILE) up -d $(SERVICE)

down:
	@$(LOAD_ENV) COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) \
	  $(COMPOSE) --profile $(PROFILE) stop $(SERVICE) 2>/dev/null || true
	@$(LOAD_ENV) COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) \
	  $(COMPOSE) --profile $(PROFILE) rm -f $(SERVICE) 2>/dev/null || true

logs:
	@$(LOAD_ENV) COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) \
	  $(COMPOSE) --profile $(PROFILE) logs -f $(SERVICE)

ps:
	@$(LOAD_ENV) COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) \
	  $(COMPOSE) --profile $(PROFILE) ps $(SERVICE)

config:
	@$(LOAD_ENV) COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) \
	  $(COMPOSE) --profile $(PROFILE) config

health:
	@$(LOAD_ENV) curl -fsS "http://localhost:$${LLM_PORT:-8091}/health" && echo ""
