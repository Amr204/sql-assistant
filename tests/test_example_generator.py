"""Tests for :mod:`vai_agent.knowledge.example_generator`."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from vai_agent.knowledge import ProfileLoader
from vai_agent.knowledge.example_generator import (
    generate_eval_questions,
    generate_examples,
    write_eval_questions_yaml,
    write_examples_yaml,
)
from vai_agent.memory.chunking import chunk_profile

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"
DBNWIND_ROOT = Path(__file__).parent.parent / "profiles"


@pytest.fixture(scope="module")
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture(scope="module")
def dbnwind_profile():
    if not (DBNWIND_ROOT / "dbnwind").is_dir():
        pytest.skip("dbnwind profile not present")
    return ProfileLoader(DBNWIND_ROOT).load("dbnwind")


class TestGenerateExamples:
    def test_sample_generates_minimum(self, sample_profile) -> None:
        doc = generate_examples(sample_profile, min_count=20)
        assert len(doc.examples) >= 20

    def test_all_examples_have_bilingual_questions(self, sample_profile) -> None:
        doc = generate_examples(sample_profile, min_count=15)
        for ex in doc.examples:
            assert ex.question_ar
            assert ex.question_en

    def test_rejected_examples_present(self, sample_profile) -> None:
        doc = generate_examples(sample_profile, min_count=15)
        rejected = [ex for ex in doc.examples if ex.difficulty.value == "rejected"]
        assert len(rejected) >= 3

    def test_sql_is_select_or_rejected(self, sample_profile) -> None:
        doc = generate_examples(sample_profile, min_count=15)
        for ex in doc.examples:
            first = ex.sql.strip().split()[0].upper() if ex.sql.strip() else ""
            if ex.difficulty.value == "rejected":
                assert first in {"DELETE", "DROP", "SELECT", "INSERT"} or ";" in ex.sql
            else:
                assert first in {"SELECT", "WITH"}

    def test_dbnwind_reaches_150(self, dbnwind_profile) -> None:
        doc = generate_examples(dbnwind_profile, min_count=150)
        assert len(doc.examples) >= 150

    def test_intents_are_diverse(self, sample_profile) -> None:
        doc = generate_examples(sample_profile, min_count=20)
        intents = {ex.intent for ex in doc.examples if ex.intent}
        assert {"lookup", "aggregation", "join"}.issubset(intents)


class TestGenerateEvalQuestions:
    def test_generates_minimum(self, sample_profile) -> None:
        doc = generate_eval_questions(sample_profile, min_count=10)
        assert len(doc.questions) >= 10

    def test_includes_must_reject(self, sample_profile) -> None:
        doc = generate_eval_questions(sample_profile, min_count=10)
        assert any(q.must_reject for q in doc.questions)


class TestWriteYaml:
    def test_round_trip_examples(self, sample_profile, tmp_path) -> None:
        doc = generate_examples(sample_profile, min_count=10)
        path = tmp_path / "examples.yaml"
        write_examples_yaml(path, doc)
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert len(loaded["examples"]) == len(doc.examples)

    def test_eval_not_in_memory_chunks(self, sample_profile, tmp_path) -> None:
        eval_doc = generate_eval_questions(sample_profile, min_count=5)
        write_eval_questions_yaml(tmp_path / "eval_questions.yaml", eval_doc)
        profile = sample_profile.model_copy(
            update={"eval_questions": eval_doc},
        )
        kinds = {c.metadata.get("kind") for c in chunk_profile(profile)}
        assert "eval" not in kinds
