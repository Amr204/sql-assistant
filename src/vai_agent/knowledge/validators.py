"""Cross-file semantic validation for a loaded :class:`Profile`.

Pydantic models in ``profile_models`` enforce the *shape* of each file;
this module enforces *consistency between files* — relationships pointing
to real tables, examples referencing real columns, per-table profiles
that match the schema, etc.

A validator returns a :class:`ValidationReport` rather than raising, so
the CLI and future API can surface every issue at once instead of one
exception per run.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from vai_agent.knowledge.profile_models import Profile

# A relaxed first-keyword check. Full SQL parsing happens in the secure
# SQL tool (later phase) with sqlglot; here we only block the obvious
# write statements so an example like ``DELETE FROM x`` never lands in
# memory.
_SELECT_START_RE = re.compile(r"^\s*(?:WITH\b.+?\bSELECT\b|SELECT\b)", re.IGNORECASE | re.DOTALL)
_FORBIDDEN_FIRST_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "MERGE",
    "DROP", "ALTER", "TRUNCATE", "EXEC", "EXECUTE", "CREATE",
)


class Severity(StrEnum):
    """Severity."""
    error = "error"
    warning = "warning"


class ValidationIssue(BaseModel):
    """ValidationIssue."""
    code: str
    severity: Severity
    location: str
    message: str


class ValidationReport(BaseModel):
    """ValidationReport."""
    profile_id: str
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Errors."""
        return [i for i in self.issues if i.severity is Severity.error]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Warnings."""
        return [i for i in self.issues if i.severity is Severity.warning]

    @property
    def ok(self) -> bool:
        """Ok."""
        return not self.errors


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_relationships(profile: Profile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    schema = profile.database_schema
    for rel in profile.relationships.relationships:
        loc = f"relationships[{rel.id}]"
        if not schema.has_table(rel.from_table):
            issues.append(ValidationIssue(
                code="REL001", severity=Severity.error, location=loc,
                message=f"from_table {rel.from_table!r} does not exist in schema",
            ))
        else:
            for col in rel.from_columns:
                if not schema.has_column(rel.from_table, col):
                    issues.append(ValidationIssue(
                        code="REL002", severity=Severity.error, location=loc,
                        message=(
                            f"from_column {col!r} does not exist on table "
                            f"{rel.from_table!r}"
                        ),
                    ))
        if not schema.has_table(rel.to_table):
            issues.append(ValidationIssue(
                code="REL003", severity=Severity.error, location=loc,
                message=f"to_table {rel.to_table!r} does not exist in schema",
            ))
        else:
            for col in rel.to_columns:
                if not schema.has_column(rel.to_table, col):
                    issues.append(ValidationIssue(
                        code="REL004", severity=Severity.error, location=loc,
                        message=(
                            f"to_column {col!r} does not exist on table "
                            f"{rel.to_table!r}"
                        ),
                    ))
    return issues


def _check_examples(profile: Profile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    schema = profile.database_schema
    seen_ids: set[str] = set()
    for ex in profile.examples.examples:
        loc = f"examples[{ex.id}]"
        if ex.id in seen_ids:
            issues.append(ValidationIssue(
                code="EX001", severity=Severity.error, location=loc,
                message=f"duplicate example id {ex.id!r}",
            ))
        seen_ids.add(ex.id)

        sql = ex.sql.strip()
        first_token = sql.split(None, 1)[0].upper() if sql else ""
        if ex.difficulty.value == "rejected":
            continue
        if first_token in _FORBIDDEN_FIRST_KEYWORDS:
            issues.append(ValidationIssue(
                code="EX002", severity=Severity.error, location=loc,
                message=(
                    f"example sql starts with forbidden keyword {first_token!r}; "
                    f"only SELECT/WITH statements are allowed in examples"
                ),
            ))
        elif not _SELECT_START_RE.match(sql):
            issues.append(ValidationIssue(
                code="EX003", severity=Severity.warning, location=loc,
                message="example sql does not start with SELECT or WITH ... SELECT",
            ))

        for table in ex.required_tables:
            if not schema.has_table(table):
                issues.append(ValidationIssue(
                    code="EX004", severity=Severity.warning, location=loc,
                    message=f"required_table {table!r} not found in schema",
                ))
    return issues


def _check_security_policy(profile: Profile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    sp = profile.security_policy
    overlap = set(sp.allowed_schemas) & set(sp.blocked_schemas)
    if overlap:
        issues.append(ValidationIssue(
            code="SEC001", severity=Severity.error, location="security_policy",
            message=f"schemas appear in both allowed and blocked: {sorted(overlap)}",
        ))

    overlap_tables = set(sp.allowed_tables) & set(sp.blocked_tables)
    if overlap_tables:
        issues.append(ValidationIssue(
            code="SEC002", severity=Severity.error, location="security_policy",
            message=f"tables appear in both allowed and blocked: {sorted(overlap_tables)}",
        ))

    if "SELECT" not in sp.allowed_operations:
        issues.append(ValidationIssue(
            code="SEC003", severity=Severity.warning, location="security_policy",
            message="SELECT is not in allowed_operations; the assistant cannot run queries",
        ))

    if sp.default_limit > sp.max_rows:
        issues.append(ValidationIssue(
            code="SEC004", severity=Severity.error, location="security_policy",
            message=(
                f"default_limit ({sp.default_limit}) exceeds max_rows ({sp.max_rows})"
            ),
        ))
    return issues


def _check_per_table_profiles(profile: Profile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    schema = profile.database_schema
    for name, tp in profile.tables.items():
        loc = f"tables[{name}]"
        if name != tp.name:
            issues.append(ValidationIssue(
                code="TP001", severity=Severity.error, location=loc,
                message=(
                    f"file key {name!r} does not match TableProfile.name {tp.name!r}"
                ),
            ))
        table = schema.table(tp.name)
        if table is None:
            issues.append(ValidationIssue(
                code="TP002", severity=Severity.error, location=loc,
                message=f"table {tp.name!r} not found in schema",
            ))
            continue
        column_names = {c.name for c in table.columns}
        important_names = [ic.name for ic in tp.important_columns]
        for group, code in (
            (tp.primary_key, "TP003"),
            (important_names, "TP004"),
            (tp.sensitive_columns, "TP005"),
            (tp.date_columns, "TP006"),
            (tp.status_columns, "TP007"),
        ):
            for col in group:
                if col not in column_names:
                    issues.append(ValidationIssue(
                        code=code, severity=Severity.warning, location=loc,
                        message=f"column {col!r} not found on table {tp.name!r}",
                    ))
    return issues


def _check_metrics(profile: Profile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    schema = profile.database_schema
    for metric in profile.metrics.metrics:
        loc = f"metrics[{metric.id}]"
        for table in metric.required_tables:
            if not schema.has_table(table):
                issues.append(ValidationIssue(
                    code="MET001", severity=Severity.warning, location=loc,
                    message=f"required_table {table!r} not found in schema",
                ))
    return issues


def _check_glossary(profile: Profile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    schema = profile.database_schema
    for term in profile.glossary.terms:
        loc = f"glossary[{term.canonical}]"
        for table in term.maps_to.tables:
            if not schema.has_table(table):
                issues.append(ValidationIssue(
                    code="GLO001", severity=Severity.warning, location=loc,
                    message=f"maps_to.tables references unknown table {table!r}",
                ))
    return issues


def _check_business_rules(profile: Profile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    schema = profile.database_schema
    for meaning in (
        *profile.business_rules.status_meanings,
        *profile.business_rules.type_meanings,
    ):
        loc = f"business_rules[{meaning.table}.{meaning.column}]"
        if not schema.has_column(meaning.table, meaning.column):
            issues.append(ValidationIssue(
                code="BR001", severity=Severity.warning, location=loc,
                message=(
                    f"code meaning references unknown column "
                    f"{meaning.table!r}.{meaning.column!r}"
                ),
            ))
    return issues


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def validate_profile(profile: Profile) -> ValidationReport:
    """Run all semantic checks against ``profile`` and return a report."""

    issues: list[ValidationIssue] = []
    issues.extend(_check_relationships(profile))
    issues.extend(_check_examples(profile))
    issues.extend(_check_security_policy(profile))
    issues.extend(_check_per_table_profiles(profile))
    issues.extend(_check_metrics(profile))
    issues.extend(_check_glossary(profile))
    issues.extend(_check_business_rules(profile))
    return ValidationReport(profile_id=profile.meta.profile_id, issues=issues)
