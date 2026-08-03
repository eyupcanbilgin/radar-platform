.PHONY: test lint smoke

test:
	uv run pytest

lint:
	uv run ruff check && uv run ruff format --check

smoke:
	uv run python scripts/verify_endpoints.py
