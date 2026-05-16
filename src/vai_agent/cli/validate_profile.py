"""``validate_profile`` CLI implementation.

The thin wrapper at ``scripts/validate_profile.py`` simply calls
:func:`main` so the same code path is exercised by tests and end users.

Exit codes:

* ``0`` — profile loaded and contains no errors (warnings are allowed)
* ``1`` — validation errors found (or warnings under ``--strict``)
* ``2`` — profile could not be loaded at all (missing dir, malformed YAML, ...)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from vai_agent.knowledge import (
    ProfileError,
    ProfileLoader,
    ValidationReport,
    validate_profile,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_profile",
        description="Validate a SQL Assistant database profile.",
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="Profile id (the directory name under --profiles-root).",
    )
    parser.add_argument(
        "--profiles-root",
        default="profiles",
        type=Path,
        help="Root directory containing profile folders (default: ./profiles).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (non-zero exit when any warning is present).",
    )
    return parser


def _print_report(report: ValidationReport, *, strict: bool, stream: TextIO) -> None:
    print(f"profile: {report.profile_id}", file=stream)
    print(f"  errors:   {len(report.errors)}", file=stream)
    print(f"  warnings: {len(report.warnings)}", file=stream)
    print(file=stream)

    if not report.issues:
        print("  OK - no issues found.", file=stream)
        return

    for issue in report.issues:
        marker = "ERROR" if issue.severity.value == "error" else "WARN "
        print(
            f"  [{marker}] {issue.code}  {issue.location}\n"
            f"         {issue.message}",
            file=stream,
        )

    if strict and report.warnings and not report.errors:
        print("\n  --strict: warnings will cause a non-zero exit.", file=stream)


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the CLI. Returns the exit code (does not call ``sys.exit``)."""

    out = stdout or sys.stdout
    err = stderr or sys.stderr

    parser = _build_parser()
    args = parser.parse_args(argv)

    loader = ProfileLoader(args.profiles_root)
    try:
        profile = loader.load(args.profile)
    except ProfileError as exc:
        print(f"FAILED to load profile {args.profile!r}: {exc}", file=err)
        return 2

    report = validate_profile(profile)
    _print_report(report, strict=args.strict, stream=out)

    if report.errors:
        return 1
    if args.strict and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
