"""Generate ``examples.yaml`` and ``eval_questions.yaml`` for a profile."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from vai_agent.knowledge import ProfileError, ProfileLoader
from vai_agent.knowledge.example_generator import (
    generate_eval_questions,
    generate_examples,
    write_eval_questions_yaml,
    write_examples_yaml,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_examples",
        description="Generate examples.yaml and eval_questions.yaml from schema metadata.",
    )
    parser.add_argument("--profile", required=True, help="Profile id under --profiles-root.")
    parser.add_argument(
        "--profiles-root",
        default="profiles",
        type=Path,
        help="Root directory containing profile folders.",
    )
    parser.add_argument(
        "--min-examples",
        type=int,
        default=150,
        help="Minimum training examples to generate (default: 150).",
    )
    parser.add_argument(
        "--min-eval",
        type=int,
        default=30,
        help="Minimum eval questions to generate (default: 30).",
    )
    parser.add_argument(
        "--skip-examples",
        action="store_true",
        help="Do not write examples.yaml.",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Do not write eval_questions.yaml.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing YAML files.",
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

    profile_dir = loader.profile_dir(args.profile)

    if not args.skip_examples:
        ex_path = profile_dir / "examples.yaml"
        if ex_path.exists() and not args.overwrite:
            print(f"Refusing to overwrite {ex_path} (use --overwrite).", file=err)
            return 1
        examples = generate_examples(profile, min_count=args.min_examples)
        write_examples_yaml(ex_path, examples)
        print(f"Wrote {len(examples.examples)} examples → {ex_path}", file=out)

    if not args.skip_eval:
        eval_path = profile_dir / "eval_questions.yaml"
        if eval_path.exists() and not args.overwrite:
            print(f"Refusing to overwrite {eval_path} (use --overwrite).", file=err)
            return 1
        eval_doc = generate_eval_questions(profile, min_count=args.min_eval)
        write_eval_questions_yaml(eval_path, eval_doc)
        print(f"Wrote {len(eval_doc.questions)} eval questions → {eval_path}", file=out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
