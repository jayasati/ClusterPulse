.PHONY: setup lint format typecheck test run-agent run-collector up down

setup:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	black .

typecheck:
	mypy .

test:
	pytest

up:
	docker compose up --build

down:
	docker compose down
