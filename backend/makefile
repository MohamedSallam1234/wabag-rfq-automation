.PHONY: setup dev serve test lint format push

setup:
	@cd .. && bash scripts/setup.sh

dev:
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

serve:
	uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy src/

format:
	uv run ruff format .
