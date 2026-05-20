"""Custom LLM context enhancer (Phase 8).

Given a natural-language question and a loaded :class:`Profile`, builds a
compact, structured context string for the LLM planner / generator:

1. **Glossary matching** — links Arabic/English terms to canonical concepts.
2. **Table selection** — scores tables from glossary maps, name mentions,
   examples, relationships, and optional vector memory.
3. **Example retrieval** — ranks training examples by lexical overlap and
   table affinity.
4. **Security context** — global policy plus per-group constraints for the
   calling :class:`~vai_agent.users.User`.
5. **Token-limited assembly** — caps total context size with tiktoken-based
   budgets and priority-aware section truncation.

Vector memory (:class:`~vai_agent.memory.AgentMemory`) is optional; when
provided it boosts table/example selection but the enhancer still works
offline from the profile alone.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from vai_agent.knowledge.profile_models import Example, GlossaryTerm, Profile, Table
    from vai_agent.memory.multi_search import MultiCollectionSearcher
    from vai_agent.users import User

from vai_agent.utils.token_counter import count_tokens

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)

_SECTION_PRIORITY = {
    "security": 1,
    "schema": 2,
    "relationships": 3,
    "business_rules": 4,
    "glossary": 5,
    "examples": 6,
    "sql_style": 7,
}

# Latin tokens shorter than this are ignored for overlap scoring.
_MIN_TERM_LEN = 2

# Relationship expansion runs only when the question suggests a join.
_JOIN_HINTS: frozenset[str] = frozenset({
    "join", "between", "across",
    "لكل", "بين",
})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextEnhancerConfig:
    """Tuning knobs for retrieval breadth and context size."""

    max_tokens: int = 2_500
    max_tables: int = 5
    max_examples: int = 2
    max_glossary_terms: int = 6
    max_business_rules: int = 3
    memory_search_results: int = 5


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class GlossaryMatch(BaseModel):
    """A glossary term that matched the user question."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    matched_on: str
    maps_to_tables: list[str] = Field(default_factory=list)
    maps_to_columns: list[str] = Field(default_factory=list)


class RetrievedExample(BaseModel):
    """A training example selected for the prompt."""

    model_config = ConfigDict(frozen=True)

    id: str
    score: float
    question: str
    sql: str
    required_tables: list[str] = Field(default_factory=list)


class SecurityContext(BaseModel):
    """Policy summary scoped to the caller and selected tables."""

    model_config = ConfigDict(frozen=True)

    allowed_operations: list[str] = Field(default_factory=list)
    allowed_schemas: list[str] = Field(default_factory=list)
    blocked_schemas: list[str] = Field(default_factory=list)
    max_rows: int = 10_000
    default_limit: int = 100
    blocked_columns: list[str] = Field(default_factory=list)
    pii_columns: list[str] = Field(default_factory=list)
    sensitive_columns: list[str] = Field(default_factory=list)
    secret_columns: list[str] = Field(default_factory=list)
    masking_rules: list[str] = Field(default_factory=list)
    row_filters: list[str] = Field(default_factory=list)
    user_groups: list[str] = Field(default_factory=list)


class EnhancementResult(BaseModel):
    """Structured output of :meth:`ContextEnhancer.enhance`."""

    model_config = ConfigDict(frozen=True)

    question: str
    glossary_matches: list[GlossaryMatch] = Field(default_factory=list)
    selected_tables: list[str] = Field(default_factory=list)
    examples: list[RetrievedExample] = Field(default_factory=list)
    security: SecurityContext
    context_text: str
    estimated_tokens: int
    truncated: bool = False
    sections_included: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_question(text: str) -> str:
    return " ".join(text.split()).lower()


def extract_terms(text: str) -> set[str]:
    """Return lowercase word-like tokens (Latin + Arabic)."""
    return {
        t.lower()
        for t in _WORD_RE.findall(text)
        if len(t) >= _MIN_TERM_LEN
    }


def _table_from_column_ref(ref: str) -> str | None:
    """Parse ``Table.Column`` → ``Table``."""
    if "." not in ref:
        return None
    return ref.split(".", 1)[0].strip()


def _column_refs_for_tables(refs: list[str], tables: set[str]) -> list[str]:
    if not tables:
        return list(refs)
    out: list[str] = []
    for ref in refs:
        tbl = _table_from_column_ref(ref)
        if tbl is None or tbl in tables:
            out.append(ref)
    return out


def _question_suggests_join(q_norm: str) -> bool:
    return any(hint in q_norm for hint in _JOIN_HINTS)


def _table_name_in_question(table_name: str, q_norm: str) -> bool:
    """Check if table name appears as a standalone token in the question."""
    name_lower = table_name.lower()
    if re.search(rf"\b{re.escape(name_lower)}\b", q_norm):
        return True
    idx = q_norm.find(name_lower)
    while idx != -1:
        before_ok = idx == 0 or not q_norm[idx - 1].isalnum()
        after_end = idx + len(name_lower)
        after_ok = after_end >= len(q_norm) or not q_norm[after_end].isalnum()
        if before_ok and after_ok:
            return True
        idx = q_norm.find(name_lower, idx + 1)
    return False


# ---------------------------------------------------------------------------
# Context enhancer
# ---------------------------------------------------------------------------


class ContextEnhancer:
    """Build token-bounded LLM context from profile knowledge (+ optional memory)."""

    def __init__(
        self,
        profile: Profile,
        *,
        memory: MultiCollectionSearcher | None = None,
        config: ContextEnhancerConfig | None = None,
    ) -> None:
        self._profile = profile
        self._memory = memory
        self._config = config or ContextEnhancerConfig()
        self._table_by_name: dict[str, Table] = {
            f"{t.schema_name}.{t.name}": t for t in profile.database_schema.tables
        }
        self._table_by_simple_name: dict[str, Table] = {
            t.name: t for t in profile.database_schema.tables
        }

    def enhance(self, question: str, user: User) -> EnhancementResult:
        """Analyse *question* and return structured context for the LLM."""
        q_norm = _normalise_question(question)
        q_terms = extract_terms(question)

        glossary_matches = self._match_glossary(question, q_norm, q_terms)
        expand_relationships = _question_suggests_join(q_norm)
        memory_hits = self._memory_search(question) if self._memory else []

        table_scores = self._score_tables(
            question,
            q_norm,
            q_terms,
            glossary_matches,
            memory_hits,
            expand_relationships=expand_relationships,
        )
        selected_tables = self._select_top_tables(table_scores)

        examples = self._retrieve_examples(question, q_norm, q_terms, selected_tables, memory_hits)
        security = self._build_security_context(user, set(selected_tables))

        sections = self._build_sections(
            glossary_matches=glossary_matches,
            selected_tables=selected_tables,
            examples=examples,
            security=security,
            table_scores=table_scores,
        )
        context_text, truncated, included = self._apply_token_budget(sections)

        return EnhancementResult(
            question=question,
            glossary_matches=glossary_matches,
            selected_tables=selected_tables,
            examples=examples,
            security=security,
            context_text=context_text,
            estimated_tokens=count_tokens(context_text),
            truncated=truncated,
            sections_included=included,
        )

    # ------------------------------------------------------------------
    # Glossary
    # ------------------------------------------------------------------

    def _match_glossary(
        self,
        question: str,
        q_norm: str,
        q_terms: set[str],
    ) -> list[GlossaryMatch]:
        matches: list[tuple[int, GlossaryMatch]] = []

        for term in self._profile.glossary.terms:
            hit = self._glossary_term_hit(term, question, q_norm, self._profile, q_terms)
            if hit is not None:
                matched_on, priority = hit
                matches.append((
                    priority,
                    GlossaryMatch(
                        canonical=term.canonical,
                        matched_on=matched_on,
                        maps_to_tables=list(term.maps_to.tables),
                        maps_to_columns=list(term.maps_to.columns),
                    ),
                ))

        matches.sort(key=lambda x: (-x[0], x[1].canonical))
        cap = self._config.max_glossary_terms
        return [m for _, m in matches[:cap]]

    @staticmethod
    def _glossary_term_hit(
        term: GlossaryTerm,
        question: str,
        q_norm: str,
        profile: Profile,
        q_terms: set[str],
    ) -> tuple[str, int] | None:
        """Return (matched_on, priority) or None. Higher priority wins ties."""
        # Longest phrase first — avoids partial phrase false negatives.
        for phrase in sorted(term.common_phrases, key=len, reverse=True):
            if phrase and phrase.lower() in q_norm:
                return phrase, 100 + len(phrase)

        for label, variants, priority in (
            ("ar", term.ar, 80),
            ("en", term.en, 70),
            ("synonym", term.synonyms, 60),
            ("canonical", [term.canonical], 50),
        ):
            for variant in variants:
                v = variant.strip()
                if not v:
                    continue
                v_lower = v.lower()
                if (
                    _WORD_RE.fullmatch(v)
                    and len(v) >= _MIN_TERM_LEN
                    and v_lower in q_terms
                ):
                    return f"{label}:{v}", priority
                if v_lower in q_norm:
                    return f"{label}:{v}", priority

        for table_name in term.maps_to.tables:
            tp = profile.tables.get(table_name)
            if tp is None:
                continue
            for label in (tp.business_name_ar, tp.business_name_en):
                if label and label.lower() in q_norm:
                    return f"table_profile:{label}", 90

        return None

    # ------------------------------------------------------------------
    # Table selection
    # ------------------------------------------------------------------

    def _memory_search(self, question: str) -> list[dict[str, Any]]:
        assert self._memory is not None
        try:
            return self._memory.search(
                question,
                n_results=self._config.memory_search_results,
            )
        except Exception:
            logger.warning("memory search failed; continuing without memory", exc_info=True)
            return []

    def _score_tables(
        self,
        question: str,
        q_norm: str,
        q_terms: set[str],
        glossary_matches: list[GlossaryMatch],
        memory_hits: list[dict[str, Any]],
        *,
        expand_relationships: bool,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        known_tables = {t.name for t in self._profile.database_schema.tables}

        def bump(table: str, amount: float) -> None:
            if table in known_tables:
                scores[table] = scores.get(table, 0.0) + amount

        for match in glossary_matches:
            for table in match.maps_to_tables:
                bump(table, 8.0)

        for table in self._profile.database_schema.tables:
            if _table_name_in_question(table.name, q_norm):
                bump(table.name, 10.0)

            tp = self._profile.tables.get(table.name)
            if tp:
                for label in (tp.business_name_en, tp.business_name_ar):
                    if label and label.lower() in q_norm:
                        bump(table.name, 6.0)

        for ex in self._profile.examples.examples:
            ex_score = self._score_example(question, q_norm, q_terms, ex, set())
            if ex_score >= 4.0:
                for table in ex.required_tables:
                    bump(table, 4.0)

        for hit in memory_hits:
            meta = hit.get("metadata") or {}
            table = meta.get("table") or meta.get("from_table") or meta.get("to_table")
            if isinstance(table, str):
                bump(table, 3.0)

        if expand_relationships and scores:
            seeds = set(scores)
            for rel in self._profile.relationships.relationships:
                if rel.from_table in seeds:
                    bump(rel.to_table, 2.0)
                if rel.to_table in seeds:
                    bump(rel.from_table, 2.0)

        return scores

    def _select_top_tables(self, scores: dict[str, float]) -> list[str]:
        if not scores:
            return []
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [name for name, _ in ranked[: self._config.max_tables]]

    # ------------------------------------------------------------------
    # Examples
    # ------------------------------------------------------------------

    def _retrieve_examples(
        self,
        question: str,
        q_norm: str,
        q_terms: set[str],
        selected_tables: list[str],
        memory_hits: list[dict[str, Any]],
    ) -> list[RetrievedExample]:
        table_set = set(selected_tables)
        scored: list[tuple[float, RetrievedExample]] = []

        semantic_map: dict[str, float] = {}
        for hit in memory_hits:
            meta = hit.get("metadata") or {}
            if meta.get("kind") != "example":
                continue
            eid = meta.get("example_id")
            if not eid:
                continue
            dist = float(hit.get("distance", 1.0))
            semantic_map[str(eid)] = max(semantic_map.get(str(eid), 0.0), max(0.0, 1.0 - dist))

        for ex in self._profile.examples.examples:
            sem = semantic_map.get(ex.id, 0.0)
            score = self._score_example(
                question, q_norm, q_terms, ex, table_set, semantic_score=sem,
            )
            if score <= 0:
                continue
            display_q = ex.question_en or ex.question_ar or ""
            scored.append((
                score,
                RetrievedExample(
                    id=ex.id,
                    score=score,
                    question=display_q,
                    sql=ex.sql.strip(),
                    required_tables=list(ex.required_tables),
                ),
            ))

        scored.sort(key=lambda x: (-x[0], x[1].id))
        seen: set[str] = set()
        out: list[RetrievedExample] = []
        for _, item in scored:
            if item.id in seen:
                continue
            seen.add(item.id)
            out.append(item)
            if len(out) >= self._config.max_examples:
                break
        return out

    @staticmethod
    def _score_example(
        question: str,
        q_norm: str,
        q_terms: set[str],
        ex: Example,
        selected_tables: set[str],
        semantic_score: float = 0.0,
    ) -> float:
        _ = question
        score = 0.0
        for field in (ex.question_en, ex.question_ar):
            if not field:
                continue
            field_norm = field.lower()
            if field_norm in q_norm:
                score += 10.0
            elif q_norm in field_norm and len(q_norm) >= 10:
                score += 5.0
            overlap = len(extract_terms(field) & q_terms)
            score += overlap * 2.0

        score += semantic_score * 8.0

        if ex.required_tables and selected_tables:
            overlap = len(set(ex.required_tables) & selected_tables)
            score += overlap * 5.0
        elif ex.required_tables:
            for table in ex.required_tables:
                if table.lower() in q_norm:
                    score += 3.0

        return score

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    def _build_security_context(self, user: User, selected_tables: set[str]) -> SecurityContext:
        policy = self._profile.security_policy
        user_groups = list(user.groups)

        blocked_columns: set[str] = set()
        for group in policy.user_access_groups:
            if user_groups and group.name not in user_groups:
                continue
            blocked_columns.update(group.blocked_columns)

        masking: list[str] = []
        for rule in policy.masking_rules:
            if rule.applies_to_groups and not any(g in user_groups for g in rule.applies_to_groups):
                continue
            masking.append(f"{rule.column} ({rule.mask_type.value})")

        row_filters: list[str] = []
        for rf in policy.row_filters:
            if rf.applies_to_groups and not any(g in user_groups for g in rf.applies_to_groups):
                continue
            row_filters.append(f"{rf.table}: {rf.expression}")

        pii = _column_refs_for_tables(list(policy.pii_columns), selected_tables)
        sensitive = _column_refs_for_tables(list(policy.sensitive_columns), selected_tables)
        secret = _column_refs_for_tables(list(policy.secret_columns), selected_tables)
        blocked = _column_refs_for_tables(sorted(blocked_columns), selected_tables)

        return SecurityContext(
            allowed_operations=list(policy.allowed_operations),
            allowed_schemas=list(policy.allowed_schemas),
            blocked_schemas=list(policy.blocked_schemas),
            max_rows=policy.max_rows,
            default_limit=policy.default_limit,
            blocked_columns=blocked,
            pii_columns=pii,
            sensitive_columns=sensitive,
            secret_columns=secret,
            masking_rules=masking,
            row_filters=row_filters,
            user_groups=user_groups,
        )

    # ------------------------------------------------------------------
    # Context assembly
    # ------------------------------------------------------------------

    def _build_sections(
        self,
        *,
        glossary_matches: list[GlossaryMatch],
        selected_tables: list[str],
        examples: list[RetrievedExample],
        security: SecurityContext,
        table_scores: dict[str, float],
    ) -> list[tuple[str, str]]:
        """Return (section_name, content) pairs in priority order."""
        sections: list[tuple[str, str]] = []

        sec_lines = [
            "## Security constraints",
            f"Allowed operations: {', '.join(security.allowed_operations) or 'SELECT'}",
            f"Allowed schemas: {', '.join(security.allowed_schemas) or 'dbo'}",
            f"Blocked schemas: {', '.join(security.blocked_schemas) or 'none'}",
            f"Max rows: {security.max_rows}; default TOP/limit: {security.default_limit}",
        ]
        if security.user_groups:
            sec_lines.append(f"User groups: {', '.join(security.user_groups)}")
        if security.blocked_columns:
            sec_lines.append("Blocked columns for this user: " + ", ".join(security.blocked_columns))
        if security.pii_columns:
            sec_lines.append("PII columns (do not select): " + ", ".join(security.pii_columns))
        if security.sensitive_columns:
            sec_lines.append("Sensitive columns: " + ", ".join(security.sensitive_columns))
        if security.secret_columns:
            sec_lines.append("Secret columns: " + ", ".join(security.secret_columns))
        if security.masking_rules:
            sec_lines.append("Masking rules: " + "; ".join(security.masking_rules))
        if security.row_filters:
            sec_lines.append("Row filters: " + "; ".join(security.row_filters))
        sections.append(("security", "\n".join(sec_lines)))

        if glossary_matches:
            gloss_lines = ["## Glossary mappings"]
            for m in glossary_matches:
                line = f"- {m.canonical} (matched: {m.matched_on})"
                if m.maps_to_tables:
                    line += f" → tables: {', '.join(m.maps_to_tables)}"
                if m.maps_to_columns:
                    line += f"; columns: {', '.join(m.maps_to_columns)}"
                gloss_lines.append(line)
            sections.append(("glossary", "\n".join(gloss_lines)))

        if selected_tables:
            schema_lines = ["## Relevant schema (selected tables only)"]
            for name in selected_tables:
                table = self._find_table(name)
                if table is None:
                    continue
                score = table_scores.get(name, 0.0)
                schema_lines.append(self._format_table_schema(table, score, profile=self._profile))
            sections.append(("schema", "\n".join(schema_lines)))

            rel_lines = self._format_relationships(selected_tables)
            if rel_lines:
                sections.append(("relationships", rel_lines))

            rule_lines = self._format_business_rules(selected_tables)
            if rule_lines:
                sections.append(("business_rules", rule_lines))

        if examples:
            ex_lines = ["## Similar examples"]
            for ex in examples:
                ex_lines.append(
                    f"### Example {ex.id} (score={ex.score:.1f})\n"
                    f"Q: {ex.question}\n"
                    f"SQL:\n{ex.sql}"
                )
            sections.append(("examples", "\n".join(ex_lines)))

        style = self._profile.sql_style
        style_lines = [
            "## SQL style",
            f"Dialect: {style.dialect}; pagination: {style.pagination_style}; "
            f"no SELECT *: {style.no_select_star}; schema-qualified: {style.schema_qualified_tables}",
        ]
        sections.append(("sql_style", "\n".join(style_lines)))

        return sections

    def _find_table(self, name: str) -> Table | None:
        return self._table_by_name.get(name) or self._table_by_simple_name.get(name)

    @staticmethod
    def _format_table_schema(
        table: Table,
        score: float,
        *,
        profile: Profile | None = None,
    ) -> str:
        """Schema snippet with types; merge per-column business hints from ``profile.tables``."""

        hints: dict[str, Any] = {}
        if profile and profile.tables:
            tp = profile.tables.get(table.name)
            if tp:
                hints = {ic.name: ic for ic in tp.important_columns}

        col_lines: list[str] = []
        for c in table.columns:
            line = f"  - {c.name} ({c.type})"
            if not c.nullable:
                line += " NOT NULL"
            desc = c.description or ""
            ic = hints.get(c.name)
            if ic is not None:
                if ic.business_description:
                    desc = ic.business_description
                elif ic.business_name_ar:
                    desc = ic.business_name_ar
            if desc:
                line += f" -- {desc}"
            col_lines.append(line)
        pk = f"PK: {', '.join(table.primary_key)}" if table.primary_key else ""
        fk_parts = [
            f"FK {', '.join(fk.columns)} → {fk.references_table}({', '.join(fk.references_columns)})"
            for fk in table.foreign_keys
        ]
        header = f"### {table.schema_name}.{table.name} (relevance={score:.1f})"
        body = "\n".join(
            p
            for p in [
                table.description or "",
                pk,
                "Columns:\n" + "\n".join(col_lines),
                *fk_parts,
            ]
            if p
        )
        return f"{header}\n{body}"

    def _format_relationships(self, selected_tables: list[str]) -> str:
        selected = set(selected_tables)
        lines = ["## Relationships (between selected tables)"]
        found = False
        for rel in self._profile.relationships.relationships:
            if rel.from_table in selected and rel.to_table in selected:
                found = True
                lines.append(
                    f"- {rel.from_table}({', '.join(rel.from_columns)}) → "
                    f"{rel.to_table}({', '.join(rel.to_columns)}) [{rel.kind.value}]"
                )
        return "\n".join(lines) if found else ""

    def _format_business_rules(self, selected_tables: list[str]) -> str:
        selected = set(selected_tables)
        lines = ["## Business rules"]
        count = 0
        for rule in self._profile.business_rules.rules:
            if rule.tables and not (set(rule.tables) & selected):
                continue
            lines.append(f"- [{rule.id}] {rule.description}")
            count += 1
            if count >= self._config.max_business_rules:
                break
        return "\n".join(lines) if count else ""

    def _apply_token_budget(
        self,
        sections: list[tuple[str, str]],
    ) -> tuple[str, bool, list[str]]:
        budget = self._config.max_tokens
        sorted_sections = sorted(
            sections,
            key=lambda s: _SECTION_PRIORITY.get(s[0], 99),
        )

        parts: list[str] = []
        included: list[str] = []
        used_tokens = 0
        truncated = False

        for name, content in sorted_sections:
            section_tokens = count_tokens(content)
            if used_tokens + section_tokens <= budget:
                parts.append(content)
                included.append(name)
                used_tokens += section_tokens
                continue

            remaining = budget - used_tokens
            if remaining < 50:
                truncated = True
                continue

            truncated_content = self._smart_truncate(content, remaining)
            if truncated_content:
                parts.append(truncated_content)
                included.append(name)
                used_tokens += count_tokens(truncated_content)
            truncated = True

        return "\n\n".join(parts), truncated, included

    @staticmethod
    def _smart_truncate(content: str, max_tokens: int) -> str:
        """Truncate at paragraph boundaries instead of mid-sentence."""
        paragraphs = content.split("\n\n")
        result: list[str] = []
        used = 0
        for para in paragraphs:
            para_tokens = count_tokens(para)
            if used + para_tokens <= max_tokens:
                result.append(para)
                used += para_tokens
            else:
                break
        return "\n\n".join(result) if result else ""
