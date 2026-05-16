# Safe cleanup of local runtime artifacts (does not touch .git or .env.example).
# Skips .venv to avoid breaking the active interpreter.

$ErrorActionPreference = "SilentlyContinue"

Remove-Item -Recurse -Force .data -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .pytest_cache -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .ruff_cache -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .mypy_cache -ErrorAction SilentlyContinue

Get-ChildItem -Recurse -Directory -Filter __pycache__ |
    Where-Object { $_.FullName -notmatch '[\\/]\.venv[\\/]' } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem -Recurse -File -Include *.pyc, *.pyo, *.log, "query_results_*.csv" |
    Where-Object { $_.FullName -notmatch '[\\/]\.venv[\\/]' } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "clean_runtime_artifacts.ps1: done"
