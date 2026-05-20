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

# Reload excludes live in vai_agent.cli.run_api (uvicorn.run; Windows-safe).

.PHONY: help venv install lint format test run run-api check clean web-install web-dev web-build web-preview

help:
	@echo "Available targets:"
	@echo "  venv     Create the local virtual environment at .venv"
	@echo "  install  Install runtime + dev dependencies into .venv (editable)"
	@echo "  lint     Run ruff check"
	@echo "  format   Run ruff format"
	@echo "  test     Run pytest"
	@echo "  run      Start API + Vite dev (one command; open http://127.0.0.1:5173)"
	@echo "  run-api  API only (serves web/dist at /app; rebuild UI after changes)"
	@echo "  check    Run lint + tests (CI-equivalent)"
	@echo "  clean    Remove caches and build artefacts"
	@echo "  web-install / web-dev / web-build / web-preview — Vite UI under web/"

web-install:
	cd web && npm install

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm run build

web-preview:
	cd web && npm run preview

run:
	$(PYTHON) scripts/dev.py

run-api:
	$(PYTHON) scripts/dev.py --api-only

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

check: lint test

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
