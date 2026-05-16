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

.PHONY: help venv install lint format test run check clean

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
	$(UVICORN) $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

check: lint test

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
