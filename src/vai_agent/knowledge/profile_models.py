"""Pydantic models for the SQL Assistant *Database Profile* files.

A profile is a directory ``profiles/<profile_id>/`` containing one YAML
file per knowledge facet (schema, relationships, business rules, glossary,
metrics, examples, security policy, SQL style) plus optional per-table
detail files under ``tables/``.

Design notes
------------
* Every model uses ``extra="forbid"`` so typos in YAML are surfaced
  immediately. ``populate_by_name=True`` so callers can use either the
  Python field name or the YAML alias (e.g. ``schema`` / ``schema_name``).
* "Schema" is overloaded in this domain: it means both "the SQL namespace
  a table lives in" and "the database schema document". To keep things
  clear we use ``schema_name`` (aliased to ``schema`` in YAML) for the
  former, and the document model is named :class:`DatabaseSchema`.
* The aggregate :class:`Profile` is what :class:`ProfileLoader` returns
  to callers.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _ProfileBase(BaseModel):
    """Shared config for every profile model."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class Cardinality(StrEnum):
    one_to_one = "one_to_one"
    one_to_many = "one_to_many"
    many_to_one = "many_to_one"
    many_to_many = "many_to_many"


class JoinType(StrEnum):
    inner = "inner"
    left = "left"
    right = "right"
    full = "full"


class RelationshipKind(StrEnum):
    foreign_key = "foreign_key"
    inferred = "inferred"


class Difficulty(StrEnum):
    simple = "simple"
    medium = "medium"
    advanced = "advanced"
    analytical = "analytical"
    operational = "operational"
    rejected = "rejected"


class MaskType(StrEnum):
    hash = "hash"
    partial = "partial"
    redact = "redact"


# ---------------------------------------------------------------------------
# profile.yaml
# ---------------------------------------------------------------------------


class LanguageSettings(_ProfileBase):
    primary: str = "ar"
    secondary: str | None = "en"


class ProfileMeta(_ProfileBase):
    """Top-level metadata for the profile (``profile.yaml``)."""

    profile_id: str
    database_name: str
    database_type: str = Field(default="mssql", description="DBMS family (mssql, postgres, ...).")
    dialect: str = Field(default="tsql", description="SQL dialect for generation.")
    default_schema: str = "dbo"
    default_row_limit: int = Field(default=100, ge=1)
    hard_row_limit: int = Field(default=10_000, ge=1)
    timezone: str = "UTC"
    language_settings: LanguageSettings = Field(default_factory=LanguageSettings)
    created_at: datetime | None = None
    generated_from: str | None = None

    @model_validator(mode="after")
    def _hard_limit_must_not_be_lower_than_default(self) -> ProfileMeta:
        if self.hard_row_limit < self.default_row_limit:
            raise ValueError(
                "hard_row_limit must be >= default_row_limit "
                f"(got {self.hard_row_limit} < {self.default_row_limit})"
            )
        return self


# ---------------------------------------------------------------------------
# schema.generated.yaml
# ---------------------------------------------------------------------------


class Column(_ProfileBase):
    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    description: str | None = None


class ForeignKeyDef(_ProfileBase):
    name: str | None = None
    columns: list[str]
    references_table: str
    references_schema: str | None = None
    references_columns: list[str]

    @model_validator(mode="after")
    def _columns_must_match(self) -> ForeignKeyDef:
        if len(self.columns) != len(self.references_columns):
            raise ValueError(
                "foreign key column count mismatch: "
                f"{len(self.columns)} local vs {len(self.references_columns)} referenced"
            )
        return self


class IndexDef(_ProfileBase):
    name: str | None = None
    columns: list[str]
    unique: bool = False


class UniqueConstraintDef(_ProfileBase):
    name: str | None = None
    columns: list[str]


class Table(_ProfileBase):
    name: str
    schema_name: str = Field(default="dbo", alias="schema")
    description: str | None = None
    columns: list[Column]
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyDef] = Field(default_factory=list)
    indexes: list[IndexDef] = Field(default_factory=list)
    unique_constraints: list[UniqueConstraintDef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _pk_columns_must_exist(self) -> Table:
        names = {c.name for c in self.columns}
        missing = [c for c in self.primary_key if c not in names]
        if missing:
            raise ValueError(
                f"primary key of table {self.name!r} references unknown column(s): {missing}"
            )
        return self


class View(_ProfileBase):
    name: str
    schema_name: str = Field(default="dbo", alias="schema")
    columns: list[Column] = Field(default_factory=list)
    definition: str | None = None


class StoredProcedure(_ProfileBase):
    name: str
    schema_name: str = Field(default="dbo", alias="schema")
    definition: str | None = None


class DatabaseSchema(_ProfileBase):
    """Contents of ``schema.generated.yaml``."""

    tables: list[Table] = Field(default_factory=list)
    views: list[View] = Field(default_factory=list)
    stored_procedures: list[StoredProcedure] = Field(default_factory=list)

    def table(self, name: str) -> Table | None:
        for t in self.tables:
            if t.name == name:
                return t
        return None

    def has_table(self, name: str) -> bool:
        return self.table(name) is not None

    def has_column(self, table: str, column: str) -> bool:
        t = self.table(table)
        if t is None:
            return False
        return any(c.name == column for c in t.columns)


# ---------------------------------------------------------------------------
# relationships.yaml
# ---------------------------------------------------------------------------


class Relationship(_ProfileBase):
    id: str
    from_table: str
    from_columns: list[str]
    to_table: str
    to_columns: list[str]
    kind: RelationshipKind = RelationshipKind.foreign_key
    cardinality: Cardinality = Cardinality.many_to_one
    join_type: JoinType = JoinType.inner
    confidence: Confidence = Confidence.high
    reason: str | None = None

    @model_validator(mode="after")
    def _columns_must_match(self) -> Relationship:
        if len(self.from_columns) != len(self.to_columns):
            raise ValueError(
                f"relationship {self.id!r} has unbalanced columns: "
                f"{len(self.from_columns)} from vs {len(self.to_columns)} to"
            )
        return self


class RelationshipsDocument(_ProfileBase):
    relationships: list[Relationship] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# business_rules.yaml
# ---------------------------------------------------------------------------


class CodeMeaning(_ProfileBase):
    """Maps an enum-like column value to its business meaning."""

    table: str
    column: str
    values: dict[str, str]


class BusinessRule(_ProfileBase):
    id: str
    description: str
    confidence: Confidence = Confidence.medium
    needs_review: bool = False
    tables: list[str] = Field(default_factory=list)


class BusinessRulesDocument(_ProfileBase):
    status_meanings: list[CodeMeaning] = Field(default_factory=list)
    type_meanings: list[CodeMeaning] = Field(default_factory=list)
    rules: list[BusinessRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# glossary.yaml
# ---------------------------------------------------------------------------


class GlossaryMapping(_ProfileBase):
    tables: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)


class GlossaryTerm(_ProfileBase):
    canonical: str
    ar: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    maps_to: GlossaryMapping = Field(default_factory=GlossaryMapping)
    common_phrases: list[str] = Field(default_factory=list)


class GlossaryDocument(_ProfileBase):
    terms: list[GlossaryTerm] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# metrics.yaml
# ---------------------------------------------------------------------------


class Metric(_ProfileBase):
    id: str
    name_ar: str | None = None
    name_en: str
    description: str | None = None
    sql_expression: str
    required_tables: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.medium


class MetricsDocument(_ProfileBase):
    metrics: list[Metric] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# examples.yaml
# ---------------------------------------------------------------------------


class Example(_ProfileBase):
    id: str
    question_ar: str | None = None
    question_en: str | None = None
    intent: str | None = None
    difficulty: Difficulty = Difficulty.simple
    required_tables: list[str] = Field(default_factory=list)
    required_columns: list[str] = Field(default_factory=list)
    sql: str
    explanation: str | None = None
    safety_notes: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.medium

    @model_validator(mode="after")
    def _must_have_at_least_one_question(self) -> Example:
        if not (self.question_ar or self.question_en):
            raise ValueError(
                f"example {self.id!r} must include question_ar or question_en"
            )
        return self


class ExamplesDocument(_ProfileBase):
    examples: list[Example] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# eval_questions.yaml  (evaluation only — never seeded to memory)
# ---------------------------------------------------------------------------


class EvalQuestion(_ProfileBase):
    """A held-out question for benchmark / accuracy evaluation."""

    id: str
    question_ar: str | None = None
    question_en: str | None = None
    expected_tables: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    must_reject: bool = Field(
        default=False,
        description="When true, a correct agent must refuse or block the request.",
    )
    reference_sql: str | None = Field(
        default=None,
        description="Optional gold SQL used only by the benchmark static checks.",
    )

    @model_validator(mode="after")
    def _must_have_at_least_one_question(self) -> EvalQuestion:
        if not (self.question_ar or self.question_en):
            raise ValueError(
                f"eval question {self.id!r} must include question_ar or question_en"
            )
        return self


class EvalQuestionsDocument(_ProfileBase):
    questions: list[EvalQuestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# security_policy.yaml
# ---------------------------------------------------------------------------


class AccessGroup(_ProfileBase):
    name: str
    description: str | None = None
    allowed_schemas: list[str] = Field(default_factory=list)
    allowed_tables: list[str] = Field(default_factory=list)
    blocked_columns: list[str] = Field(default_factory=list)


class MaskingRule(_ProfileBase):
    column: str = Field(description="'Table.Column' identifier of the target column.")
    mask_type: MaskType = MaskType.redact
    applies_to_groups: list[str] = Field(default_factory=list)


class RowFilter(_ProfileBase):
    table: str
    expression: str
    applies_to_groups: list[str] = Field(default_factory=list)


class SecurityPolicy(_ProfileBase):
    """Contents of ``security_policy.yaml``.

    Defaults are intentionally restrictive: SELECT-only, common system
    schemas blocked, and a hard row cap of 10,000.
    """

    allowed_schemas: list[str] = Field(default_factory=lambda: ["dbo"])
    blocked_schemas: list[str] = Field(
        default_factory=lambda: ["sys", "INFORMATION_SCHEMA"]
    )
    allowed_tables: list[str] = Field(default_factory=list)
    blocked_tables: list[str] = Field(default_factory=list)
    pii_columns: list[str] = Field(default_factory=list)
    sensitive_columns: list[str] = Field(default_factory=list)
    secret_columns: list[str] = Field(default_factory=list)
    allowed_operations: list[str] = Field(default_factory=lambda: ["SELECT"])
    blocked_operations: list[str] = Field(
        default_factory=lambda: [
            "INSERT", "UPDATE", "DELETE", "MERGE",
            "DROP", "ALTER", "TRUNCATE", "EXEC",
        ]
    )
    max_rows: int = Field(default=10_000, ge=1)
    default_limit: int = Field(default=100, ge=1)
    user_access_groups: list[AccessGroup] = Field(default_factory=list)
    tool_access_groups: dict[str, list[str]] | None = Field(
        default=None,
        description=(
            "Optional map ``tool_name -> [group, ...]`` for Vanna ``ToolRegistry`` "
            "access. When unset, group names are taken from ``user_access_groups``."
        ),
    )
    masking_rules: list[MaskingRule] = Field(default_factory=list)
    row_filters: list[RowFilter] = Field(default_factory=list)
    min_group_size: int = Field(default=1, ge=1)
    max_execution_seconds: int = Field(default=30, ge=1)
    allowed_functions: list[str] = Field(default_factory=list)
    blocked_functions: list[str] = Field(default_factory=list)
    blocked_sql_features: list[str] = Field(default_factory=list)

    @field_validator("allowed_operations", "blocked_operations")
    @classmethod
    def _normalise_ops(cls, value: list[str]) -> list[str]:
        return [op.strip().upper() for op in value]

    @model_validator(mode="after")
    def _check_no_overlap(self) -> SecurityPolicy:
        overlap = set(self.allowed_operations) & set(self.blocked_operations)
        if overlap:
            raise ValueError(
                f"operations appear in both allowed and blocked lists: {sorted(overlap)}"
            )
        return self


# ---------------------------------------------------------------------------
# sql_style.yaml
# ---------------------------------------------------------------------------


class SqlStyle(_ProfileBase):
    dialect: str = "tsql"
    use_top: bool = True
    no_select_star: bool = True
    schema_qualified_tables: bool = True
    quote_identifiers: str = Field(
        default="when_needed",
        description="One of 'always', 'never', 'when_needed'.",
    )
    default_ordering: str | None = None
    date_handling: str | None = None
    null_handling: str | None = None
    aggregation_style: str | None = None
    pagination_style: str = "top"


# ---------------------------------------------------------------------------
# tables/<name>.yaml
# ---------------------------------------------------------------------------


class TableProfile(_ProfileBase):
    name: str
    schema_name: str = Field(default="dbo", alias="schema")
    business_name_ar: str | None = None
    business_name_en: str | None = None
    description: str | None = None
    grain: str | None = None
    primary_key: list[str] = Field(default_factory=list)
    important_columns: list[str] = Field(default_factory=list)
    sensitive_columns: list[str] = Field(default_factory=list)
    date_columns: list[str] = Field(default_factory=list)
    status_columns: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    common_filters: list[str] = Field(default_factory=list)
    common_joins: list[str] = Field(default_factory=list)
    common_questions: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.medium


# ---------------------------------------------------------------------------
# Top-level aggregate
# ---------------------------------------------------------------------------


class Profile(_ProfileBase):
    """The complete in-memory representation of a database profile."""

    meta: ProfileMeta
    database_schema: DatabaseSchema
    relationships: RelationshipsDocument = Field(default_factory=RelationshipsDocument)
    business_rules: BusinessRulesDocument = Field(default_factory=BusinessRulesDocument)
    glossary: GlossaryDocument = Field(default_factory=GlossaryDocument)
    metrics: MetricsDocument = Field(default_factory=MetricsDocument)
    examples: ExamplesDocument = Field(default_factory=ExamplesDocument)
    eval_questions: EvalQuestionsDocument = Field(default_factory=EvalQuestionsDocument)
    security_policy: SecurityPolicy = Field(default_factory=SecurityPolicy)
    sql_style: SqlStyle = Field(default_factory=SqlStyle)
    tables: dict[str, TableProfile] = Field(default_factory=dict)
