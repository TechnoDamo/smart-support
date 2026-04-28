.PHONY: help up down logs ps config pull restart health

COMPOSE ?= docker compose
PROFILE := local-object-storage
LOAD_ENV := set -a; \
	if [ -f ../.env ]; then . ../.env; fi; \
	if [ -f ./.env ]; then . ./.env; fi; \
	set +a;

help:
	@echo "MinIO commands:"
	@echo "  make up       — start local S3-compatible object storage"
	@echo "  make down     — stop MinIO"
	@echo "  make logs     — follow logs"
	@echo "  make health   — check local S3 API health"
	@echo ""
	@echo "Root usage:"
	@echo "  make up OBJECT_STORAGE=local"

up:
	@$(LOAD_ENV) $(COMPOSE) --profile $(PROFILE) up -d

down:
	@$(LOAD_ENV) $(COMPOSE) --profile $(PROFILE) down

logs:
	@$(LOAD_ENV) $(COMPOSE) --profile $(PROFILE) logs -f

ps:
	@$(LOAD_ENV) $(COMPOSE) --profile $(PROFILE) ps

config:
	@$(LOAD_ENV) $(COMPOSE) --profile $(PROFILE) config

pull:
	@$(LOAD_ENV) $(COMPOSE) --profile $(PROFILE) pull

restart:
	@$(LOAD_ENV) $(COMPOSE) --profile $(PROFILE) up -d --force-recreate

health:
	@$(LOAD_ENV) curl -fsS "http://localhost:$${MINIO_API_PORT:-9000}/minio/health/live" && echo ""
