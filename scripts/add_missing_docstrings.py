#!/usr/bin/env python3
"""Add one-line PEP 257 docstrings to public functions/classes that lack them."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "vai_agent"

OVERRIDES: dict[str, str] = {
    "allow_request": "Return whether the request is within rate limits.",
    "try_acquire_concurrency": "Increment in-flight counter; fail when at limit.",
    "release_concurrency": "Decrement in-flight counter and prune idle keys.",
    "get_rate_limiter": "Return the process-wide rate limiter singleton.",
    "require_runtime": "Return Vanna runtime or raise 503 if agent is not ready.",
    "build_request_context": "Build Vanna RequestContext from the HTTP request.",
    "get_settings": "Return cached application settings for this process.",
    "create_app": "Build the FastAPI application and initialise runtime state.",
    "check_prompt_injection": "Return whether question text passes injection heuristics.",
    "validate": "Validate SQL against policy; optionally rewrite with TOP.",
    "check": "Check SQL for PII/sensitive column policy violations.",
    "execute": "Execute pre-validated SQL and return a safe QueryResult.",
    "close": "Close the connection pool if it was created.",
    "get_connection": "Yield a pooled pyodbc connection (context manager).",
    "resolve": "Resolve the caller User from headers or dev defaults.",
    "format": "Format a log record as a single JSON line.",
    "filter": "Return True when the record should be written to the file handler.",
    "ready": "Return readiness flags for profile, agent, memory, and tools.",
    "ask": "Handle POST /api/v1/chat (SQL fast path or guarded Vanna agent).",
    "extract_answer": "Extract assistant text from a Vanna or legacy payload dict.",
}


def _humanize(name: str) -> str:
    if name in OVERRIDES:
        return OVERRIDES[name]
    if name.startswith("get_"):
        return f"Return {name[4:].replace('_', ' ')}."
    if name.startswith("set_"):
        return f"Set {name[4:].replace('_', ' ')}."
    if name.startswith("is_"):
        return f"Return True when {name[3:].replace('_', ' ')}."
    if name.startswith("has_"):
        return f"Return True if {name[4:].replace('_', ' ')}."
    if name.startswith("build_"):
        return f"Build {name[6:].replace('_', ' ')}."
    if name.startswith("parse_"):
        return f"Parse {name[6:].replace('_', ' ')}."
    if name.startswith("emit_"):
        return f"Emit {name[5:].replace('_', ' ')}."
    words = name.replace("_", " ")
    return f"{words.capitalize()}."


def _class_summary(name: str) -> str:
    if name.endswith("Error"):
        return f"Raised when {name[:-5].replace('_', ' ').lower()} fails."
    if name.endswith("Result") or name.endswith("Response"):
        return f"{name.replace('_', ' ')} payload."
    if name.endswith("Request"):
        return f"{name.replace('_', ' ')} body."
    return f"{name.replace('_', ' ')}."


def _body_insert_line(node: ast.AST) -> int | None:
    """Return 1-based line number where the docstring block should be inserted."""
    body = getattr(node, "body", None)
    if not body:
        return None
    return body[0].lineno


def _indent_for_line(lines: list[str], lineno: int) -> str:
    """Return indentation prefix for the line where the docstring is inserted."""
    line = lines[lineno - 1]
    return line[: len(line) - len(line.lstrip())]


def process_file(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0

    lines = source.splitlines(keepends=True)
    inserts: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node):
                continue
            insert_at = _body_insert_line(node)
            if insert_at is None:
                continue
            doc = _humanize(node.name)
            line = f'{_indent_for_line(lines, insert_at)}"""{doc}"""\n'
            inserts.append((insert_at, line))
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node):
                continue
            insert_at = _body_insert_line(node)
            if insert_at is None:
                continue
            doc = _class_summary(node.name)
            line = f'{_indent_for_line(lines, insert_at)}"""{doc}"""\n'
            inserts.append((insert_at, line))

    if not inserts:
        return 0

    for insert_at, doc_line in sorted(inserts, key=lambda x: -x[0]):
        idx = insert_at - 1
        lines.insert(idx, doc_line)

    path.write_text("".join(lines), encoding="utf-8")
    return len(inserts)


def main() -> int:
    total = 0
    for path in sorted(SRC.rglob("*.py")):
        n = process_file(path)
        if n:
            print(f"{path.relative_to(REPO)}: +{n}")
            total += n
    print(f"Added {total} docstrings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
