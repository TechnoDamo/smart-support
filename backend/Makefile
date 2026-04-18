.PHONY: help venv install run test up down logs migrate revision current fmt clean

PY ?= python3.12
VENV ?= .venv
UVICORN ?= $(VENV)/bin/uvicorn
ALEMBIC ?= $(VENV)/bin/alembic

help:
	@echo "Цели:"
	@echo "  make venv       — создать виртуальное окружение"
	@echo "  make install    — установить зависимости"
	@echo "  make run        — запустить API локально (uvicorn)"
	@echo "  make test       — запустить тесты"
	@echo "  make migrate    — применить Alembic-миграции до head"
	@echo "  make current    — показать текущую ревизию БД"
	@echo "  make revision MESSAGE=... — создать новую миграцию"
	@echo "  make up         — поднять docker-compose (api only)"
	@echo "  make down       — остановить docker-compose"
	@echo "  make logs       — логи API из docker-compose"
	@echo "  make clean      — удалить кэши и venv"

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(VENV)/bin/pip install -r requirements.txt

run:
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8081 --reload

test:
	$(VENV)/bin/pytest tests/ -q

migrate:
	$(ALEMBIC) upgrade head

current:
	$(ALEMBIC) current

revision:
	@test -n "$(MESSAGE)" || (echo "Используйте: make revision MESSAGE='описание'" && exit 1)
	$(ALEMBIC) revision --autogenerate -m "$(MESSAGE)"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

clean:
	rm -rf $(VENV) .pytest_cache **/__pycache__ **/**/__pycache__
