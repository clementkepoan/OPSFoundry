.PHONY: install run up down test lint

install:
	pip install -e ".[dev]"

run:
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up --build

down:
	docker compose down

test:
	pytest

lint:
	ruff check .
