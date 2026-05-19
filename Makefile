# SQL Assistant — developer Makefile
#
# All commands run against the local virtual environment at .venv.
# On Windows + PowerShell where `make` is unavailable, use the equivalent
# commands documented in README.md.

PYTHON      ?= .venv/Scripts/python
PIP         ?= .venv/Scripts/pip
UVICORN     ?= .venv/Scripts/uvicorn
PYTEST      ?= .venv/Scripts/pytest
RUFF        ?= .venv/Scripts/ruff

APP_MODULE  := vai_agent.main:app
HOST        ?= 127.0.0.1
PORT        ?= 8000

# Narrow reload scope so logs/audit/artifacts do not trigger restart loops.
RELOAD_FLAGS := --reload --reload-dir src --reload-dir profiles --reload-exclude "logs/*" --reload-exclude "audit/*" --reload-exclude "activity_audit/*" --reload-exclude ".data/*" --reload-exclude "web/dist/*" --reload-exclude "*.xlsx" --reload-exclude "*.csv" --reload-exclude "*.jsonl"

.PHONY: help venv install lint format test run check clean web-install web-dev web-build web-preview run-api run-full

help:
	@echo "Available targets:"
	@echo "  venv     Create the local virtual environment at .venv"
	@echo "  install  Install runtime + dev dependencies into .venv (editable)"
	@echo "  lint     Run ruff check"
	@echo "  format   Run ruff format"
	@echo "  test     Run pytest"
	@echo "  run      Start the FastAPI app with uvicorn --reload"
	@echo "  check    Run lint + tests (CI-equivalent)"
	@echo "  clean    Remove caches and build artefacts"
	@echo "  web-install / web-dev / web-build / web-preview — Vite UI under web/"
	@echo "  run-api  Uvicorn API (uses .env if present)"
	@echo "  run-full Reminder to run API + web dev in two terminals"

web-install:
	cd web && npm install

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm run build

web-preview:
	cd web && npm run preview

run-api:
	$(UVICORN) $(APP_MODULE) --env-file .env --host 127.0.0.1 --port 8000 $(RELOAD_FLAGS)

run-full:
	@echo "Run API and web dev in separate terminals:"
	@echo "make run-api"
	@echo "make web-dev"

venv:
	python -m venv .venv

install:
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

test:
	$(PYTEST)

run:
	$(UVICORN) $(APP_MODULE) --env-file .env --host $(HOST) --port $(PORT) $(RELOAD_FLAGS)

check: lint test

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
