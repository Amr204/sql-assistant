"""Tests for :mod:`vai_agent.knowledge.benchmark`."""

from __future__ import annotations

from pathlib import Path

import pytest

from vai_agent.knowledge import ProfileLoader
from vai_agent.knowledge.benchmark import (
    benchmark_eval_questions,
    benchmark_examples,
    write_benchmark_reports,
)
from vai_agent.knowledge.example_generator import (
    generate_eval_questions,
    generate_examples,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


@pytest.fixture(scope="module")
def sample_with_generated_examples():
    profile = ProfileLoader(FIXTURE_ROOT).load("sample")
    examples = generate_examples(profile, min_count=20)
    eval_q = generate_eval_questions(profile, min_count=12)
    return profile.model_copy(
        update={
            "examples": examples,
            "eval_questions": eval_q,
        },
    )


class TestBenchmarkExamples:
    def test_valid_examples_mostly_pass(self, sample_with_generated_examples) -> None:
        report = benchmark_examples(sample_with_generated_examples)
        allowed = [
            r for r in report.results
            if not any(
                ex.id == r.id
                for ex in sample_with_generated_examples.examples.examples
                if ex.difficulty.value == "rejected"
            )
        ]
        passed_allowed = sum(1 for r in allowed if r.passed)
        assert passed_allowed >= len(allowed) * 0.8

    def test_rejected_examples_fail_policy_check_by_design(
        self, sample_with_generated_examples
    ) -> None:
        report = benchmark_examples(sample_with_generated_examples)
        rejected_ids = {
            ex.id
            for ex in sample_with_generated_examples.examples.examples
            if ex.difficulty.value == "rejected"
        }
        for item in report.results:
            if item.id in rejected_ids:
                bn004 = next(c for c in item.checks if c.code == "BN004")
                assert bn004.passed is True


class TestBenchmarkEval:
    def test_eval_report_runs(self, sample_with_generated_examples) -> None:
        report = benchmark_eval_questions(sample_with_generated_examples)
        assert report.summary["total"] >= 12


class TestWriteReports:
    def test_writes_json_and_markdown(self, sample_with_generated_examples, tmp_path) -> None:
        report = benchmark_examples(sample_with_generated_examples)
        json_path, md_path = write_benchmark_reports(report, reports_dir=tmp_path)
        assert json_path.is_file()
        assert md_path.is_file()
        assert "Benchmark Report" in md_path.read_text(encoding="utf-8")
