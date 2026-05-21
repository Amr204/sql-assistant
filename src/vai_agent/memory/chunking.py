"""Profile → memory chunks.

A *chunk* is the atomic unit stored in ChromaDB: one document string,
one stable ID, and a metadata dict.  The chunker converts every facet
of a :class:`~vai_agent.knowledge.profile_models.Profile` into a flat
list of :class:`ProfileChunk` objects so the caller can batch-insert
them without caring about the profile structure.

Chunk ID convention:  ``<profile_id>:<kind>:<slug>``

where ``slug`` is a short, deterministic identifier derived from the
chunk content (table name, example id, …).  The convention makes IDs
human-readable while still being collision-free within a profile.

Kinds
-----
* ``schema_table``  — one chunk per table (columns + PK + FK narrative)
* ``relationship``  — one chunk per FK relationship
* ``business_rule`` — one chunk per business rule
* ``glossary``      — one chunk per glossary term
* ``metric``        — one chunk per metric
* ``example``       — one chunk per training example (question + SQL)
* ``table_profile`` — one chunk per per-table profile file
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from vai_agent.knowledge.profile_models import Profile


class ChunkingStrategy(StrEnum):
    """How profile text is split before vector indexing."""

    EARLY = "early"


@dataclass(frozen=True)
class ProfileChunk:
    """A single document unit ready for insertion into ChromaDB.

    ``document``  is the text that gets embedded.
    ``id``        is stable and globally unique within the collection.
    ``metadata``  carries filtering / display information.
    """

    document: str
    id: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _safe_slug(text: str, max_len: int = 60) -> str:
    """Turn arbitrary text into a safe, short slug for use in IDs."""
    slug = re.sub(r"\s+", "_", text.lower().strip())
    slug = re.sub(r"[^\w\-]", "", slug)
    return slug[:max_len] or "chunk"


def chunk_profile(
    profile: Profile,
    *,
    strategy: ChunkingStrategy = ChunkingStrategy.EARLY,
) -> list[ProfileChunk]:
    """Convert every knowledge facet of *profile* into :class:`ProfileChunk` objects.

    The order of the returned list is deterministic: same profile →
    same list (important for idempotent upsert into ChromaDB).
    """
    pid = profile.meta.profile_id
    chunks: list[ProfileChunk] = []

    chunks.extend(_chunk_tables(pid, profile))
    chunks.extend(_chunk_relationships(pid, profile))
    chunks.extend(_chunk_business_rules(pid, profile))
    chunks.extend(_chunk_glossary(pid, profile))
    chunks.extend(_chunk_metrics(pid, profile))
    chunks.extend(_chunk_examples(pid, profile))
    chunks.extend(_chunk_table_profiles(pid, profile))

    return chunks


# ---------------------------------------------------------------------------
# Per-facet chunkers
# ---------------------------------------------------------------------------


def _chunk_tables(pid: str, profile: Profile) -> list[ProfileChunk]:
    chunks: list[ProfileChunk] = []
    for table in profile.database_schema.tables:
        col_lines = [
            f"  - {c.name} ({c.type})"
            + (" NOT NULL" if not c.nullable else "")
            + (f" [default: {c.default}]" if c.default else "")
            for c in table.columns
        ]
        pk_text = f"Primary key: {', '.join(table.primary_key)}" if table.primary_key else ""
        fk_text = "\n".join(
            f"Foreign key: {', '.join(fk.columns)} → {fk.references_table}({', '.join(fk.references_columns)})"
            for fk in table.foreign_keys
        )
        doc_parts = [
            f"Table: {table.schema_name}.{table.name}",
            table.description or "",
            pk_text,
            "Columns:\n" + "\n".join(col_lines),
            fk_text,
        ]
        doc = "\n".join(p for p in doc_parts if p)
        chunks.append(ProfileChunk(
            document=doc,
            id=f"{pid}:schema_table:{_safe_slug(table.name)}",
            metadata={
                "profile_id": pid,
                "kind": "schema_table",
                "table": table.name,
                "schema": table.schema_name,
            },
        ))
    return chunks


def _chunk_relationships(pid: str, profile: Profile) -> list[ProfileChunk]:
    chunks: list[ProfileChunk] = []
    for rel in profile.relationships.relationships:
        doc = (
            f"Relationship: {rel.from_table}({', '.join(rel.from_columns)}) → "
            f"{rel.to_table}({', '.join(rel.to_columns)}) "
            f"[{rel.kind.value}, {rel.cardinality.value}, confidence: {rel.confidence.value}]"
            + (f"\n{rel.reason}" if rel.reason else "")
        )
        chunks.append(ProfileChunk(
            document=doc,
            id=f"{pid}:relationship:{rel.id}",
            metadata={
                "profile_id": pid,
                "kind": "relationship",
                "from_table": rel.from_table,
                "to_table": rel.to_table,
                "rel_id": rel.id,
            },
        ))
    return chunks


def _chunk_business_rules(pid: str, profile: Profile) -> list[ProfileChunk]:
    chunks: list[ProfileChunk] = []
    for rule in profile.business_rules.rules:
        doc = f"Business rule [{rule.id}]: {rule.description}"
        if rule.tables:
            doc += f"\nApplies to tables: {', '.join(rule.tables)}"
        if rule.needs_review:
            doc += "\n[Needs human review]"
        chunks.append(ProfileChunk(
            document=doc,
            id=f"{pid}:business_rule:{_safe_slug(rule.id)}",
            metadata={
                "profile_id": pid,
                "kind": "business_rule",
                "rule_id": rule.id,
                "confidence": rule.confidence.value,
                "needs_review": rule.needs_review,
            },
        ))
    # Status/type meanings
    for meaning in (*profile.business_rules.status_meanings, *profile.business_rules.type_meanings):
        values_text = "; ".join(f"{k}={v}" for k, v in meaning.values.items())
        doc = (
            f"Code meanings for {meaning.table}.{meaning.column}:\n{values_text}"
        )
        slug = _safe_slug(f"{meaning.table}_{meaning.column}")
        chunks.append(ProfileChunk(
            document=doc,
            id=f"{pid}:business_rule:meanings_{slug}",
            metadata={
                "profile_id": pid,
                "kind": "business_rule",
                "table": meaning.table,
                "column": meaning.column,
            },
        ))
    return chunks


def _chunk_glossary(pid: str, profile: Profile) -> list[ProfileChunk]:
    chunks: list[ProfileChunk] = []
    for term in profile.glossary.terms:
        parts = [f"Glossary term: {term.canonical}"]
        if term.ar:
            parts.append("Arabic: " + ", ".join(term.ar))
        if term.en:
            parts.append("English: " + ", ".join(term.en))
        if term.synonyms:
            parts.append("Synonyms: " + ", ".join(term.synonyms))
        if term.maps_to.tables:
            parts.append("Maps to tables: " + ", ".join(term.maps_to.tables))
        if term.maps_to.columns:
            parts.append("Maps to columns: " + ", ".join(term.maps_to.columns))
        if term.common_phrases:
            parts.append("Common phrases: " + "; ".join(term.common_phrases))
        chunks.append(ProfileChunk(
            document="\n".join(parts),
            id=f"{pid}:glossary:{_safe_slug(term.canonical)}",
            metadata={
                "profile_id": pid,
                "kind": "glossary",
                "canonical": term.canonical,
            },
        ))
    return chunks


def _chunk_metrics(pid: str, profile: Profile) -> list[ProfileChunk]:
    chunks: list[ProfileChunk] = []
    for m in profile.metrics.metrics:
        parts = [f"Metric: {m.name_en}"]
        if m.name_ar:
            parts.append(f"Arabic name: {m.name_ar}")
        if m.description:
            parts.append(f"Description: {m.description}")
        parts.append(f"SQL expression: {m.sql_expression}")
        if m.required_tables:
            parts.append("Required tables: " + ", ".join(m.required_tables))
        if m.caveats:
            parts.append("Caveats: " + "; ".join(m.caveats))
        chunks.append(ProfileChunk(
            document="\n".join(parts),
            id=f"{pid}:metric:{_safe_slug(m.id)}",
            metadata={
                "profile_id": pid,
                "kind": "metric",
                "metric_id": m.id,
                "confidence": m.confidence.value,
            },
        ))
    return chunks


def _chunk_examples(pid: str, profile: Profile) -> list[ProfileChunk]:
    chunks: list[ProfileChunk] = []
    for ex in profile.examples.examples:
        parts: list[str] = []
        if ex.question_ar:
            parts.append(f"Question (Arabic): {ex.question_ar}")
        if ex.question_en:
            parts.append(f"Question (English): {ex.question_en}")
        if ex.intent:
            parts.append(f"Intent: {ex.intent}")
        parts.append(f"SQL:\n{ex.sql.strip()}")
        if ex.explanation:
            parts.append(f"Explanation: {ex.explanation}")
        if ex.required_tables:
            parts.append("Tables: " + ", ".join(ex.required_tables))
        chunks.append(ProfileChunk(
            document="\n".join(parts),
            id=f"{pid}:example:{_safe_slug(ex.id)}",
            metadata={
                "profile_id": pid,
                "kind": "example",
                "example_id": ex.id,
                "difficulty": ex.difficulty.value,
                "confidence": ex.confidence.value,
            },
        ))
    return chunks


def _chunk_table_profiles(pid: str, profile: Profile) -> list[ProfileChunk]:
    chunks: list[ProfileChunk] = []
    for name, tp in profile.tables.items():
        parts = [f"Table profile: {name}"]
        if tp.business_name_ar:
            parts.append(f"Business name (Arabic): {tp.business_name_ar}")
        if tp.business_name_en:
            parts.append(f"Business name (English): {tp.business_name_en}")
        if tp.description:
            parts.append(f"Description: {tp.description}")
        if tp.grain:
            parts.append(f"Grain: {tp.grain}")
        if tp.common_questions:
            parts.append("Common questions:\n" + "\n".join(f"  - {q}" for q in tp.common_questions))
        if tp.common_filters:
            parts.append("Common filters:\n" + "\n".join(f"  - {f}" for f in tp.common_filters))
        chunks.append(ProfileChunk(
            document="\n".join(parts),
            id=f"{pid}:table_profile:{_safe_slug(name)}",
            metadata={
                "profile_id": pid,
                "kind": "table_profile",
                "table": name,
                "confidence": tp.confidence.value,
            },
        ))
    return chunks
