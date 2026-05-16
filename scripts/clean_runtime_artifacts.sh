#!/usr/bin/env bash
# Safe cleanup of local runtime artifacts (does not touch .git or .env.example).
set -euo pipefail

rm -rf .data .pytest_cache .ruff_cache .mypy_cache

find . -path './.venv' -prune -o -path './vanna-2.0.2' -prune -o -type d -name '__pycache__' -exec rm -rf {} +

find . -path './.venv' -prune -o -path './vanna-2.0.2' -prune -o -type f \
  \( -name '*.pyc' -o -name '*.pyo' -o -name '*.log' -o -name 'query_results_*.csv' \) -delete

echo "clean_runtime_artifacts.sh: done"
