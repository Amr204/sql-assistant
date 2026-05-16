"""Benchmark profile examples and eval questions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from vai_agent.knowledge import ProfileError, ProfileLoader
from vai_agent.knowledge.benchmark import (
    benchmark_eval_questions,
    benchmark_examples,
    write_benchmark_reports,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark_questions",
        description="Static benchmark of examples.yaml / eval_questions.yaml.",
    )
    parser.add_argument("--profile", required=True, help="Profile id.")
    parser.add_argument(
        "--profiles-root",
        default="profiles",
        type=Path,
    )
    parser.add_argument(
        "--source",
        choices=("examples", "eval", "both"),
        default="both",
        help="Which YAML file(s) to benchmark (default: both).",
    )
    parser.add_argument(
        "--reports-dir",
        default="reports",
        type=Path,
        help="Output directory for benchmark_report.md and benchmark_results.json.",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit 1 when any item fails an error-severity check.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    args = _build_parser().parse_args(argv)

    loader = ProfileLoader(args.profiles_root)
    try:
        profile = loader.load(args.profile)
    except ProfileError as exc:
        print(f"FAILED to load profile {args.profile!r}: {exc}", file=err)
        return 2

    exit_code = 0
    combined_results = []

    if args.source in ("examples", "both"):
        if not profile.examples.examples:
            print("No examples found — run generate_examples first.", file=err)
            exit_code = 1
        else:
            report = benchmark_examples(profile)
            write_benchmark_reports(report, reports_dir=args.reports_dir)
            combined_results.extend(report.results)
            print(
                f"examples: {report.summary['passed']}/{report.summary['total']} passed",
                file=out,
            )
            if report.summary["failed"]:
                exit_code = 1

    if args.source in ("eval", "both"):
        if not profile.eval_questions.questions:
            print("No eval_questions found — run generate_examples first.", file=err)
            if args.source == "eval":
                exit_code = 1
        else:
            report = benchmark_eval_questions(profile)
            eval_dir = args.reports_dir / "eval"
            write_benchmark_reports(report, reports_dir=eval_dir)
            combined_results.extend(report.results)
            print(
                f"eval: {report.summary['passed']}/{report.summary['total']} passed "
                f"→ {eval_dir}",
                file=out,
            )
            if report.summary["failed"]:
                exit_code = 1

    if args.fail_on_error and exit_code:
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
