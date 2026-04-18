.PHONY: help check-uv sync run test up down logs migrate revision current lock clean

UV ?= $(shell if command -v uv >/dev/null 2>&1; then command -v uv; elif [ -x "$$HOME/.local/bin/uv" ]; then echo "$$HOME/.local/bin/uv"; else echo uv; fi)
UV_CACHE_DIR ?= .uv-cache
PYTHON_VERSION ?= 3.12
UV_ENV := UV_CACHE_DIR=$(abspath $(UV_CACHE_DIR))
UV_RUN := $(UV_ENV) $(UV) run

help:
	@echo "Цели:"
	@echo "  make sync       — создать .venv и синхронизировать зависимости через uv"
	@echo "  make run        — запустить API локально (uvicorn)"
	@echo "  make test       — запустить тесты"
	@echo "  make migrate    — применить Alembic-миграции до head"
	@echo "  make current    — показать текущую ревизию БД"
	@echo "  make revision MESSAGE=... — создать новую миграцию"
	@echo "  make lock       — обновить uv.lock"
	@echo "  make up         — поднять docker-compose (api only)"
	@echo "  make down       — остановить docker-compose"
	@echo "  make logs       — логи API из docker-compose"
	@echo "  make clean      — удалить .venv и локальные кэши"

check-uv:
	@if [ -x "$(UV)" ] || command -v "$(UV)" >/dev/null 2>&1; then \
		true; \
	else \
		echo "uv не найден. Установите uv и повторите команду."; \
		exit 1; \
	fi

sync: check-uv
	$(UV_ENV) $(UV) venv --python $(PYTHON_VERSION) --clear
	$(UV_ENV) $(UV) sync --extra dev

run: check-uv
	$(UV_RUN) uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload

test: check-uv
	$(UV_RUN) pytest tests/ -q

migrate: check-uv
	$(UV_RUN) alembic upgrade head

current: check-uv
	$(UV_RUN) alembic current

revision: check-uv
	@test -n "$(MESSAGE)" || (echo "Используйте: make revision MESSAGE='описание'" && exit 1)
	$(UV_RUN) alembic revision --autogenerate -m "$(MESSAGE)"

lock: check-uv
	$(UV_ENV) $(UV) lock

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

clean:
	rm -rf .venv .pytest_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
