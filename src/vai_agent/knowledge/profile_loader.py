"""Load a :class:`Profile` from disk.

Mandatory files (the loader raises :class:`ProfileFileError` if missing):

* ``profile.yaml``
* ``schema.generated.yaml``

Optional files (loader returns an empty default document if absent):

* ``relationships.yaml``
* ``business_rules.yaml``
* ``glossary.yaml``
* ``metrics.yaml``
* ``examples.yaml``
* ``security_policy.yaml`` (default = restrictive policy from
  :class:`SecurityPolicy`)
* ``sql_style.yaml``
* ``tables.yaml`` — optional unified file with a top-level ``tables:`` map
  of table name → table profile document; if absent, ``tables/*.yaml`` is
  used (one file per table).

This is intentionally narrow: no I/O happens outside ``load()``, no
mutation of disk, and the loader is stateless so unit tests can build it
against a temporary directory.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from vai_agent.knowledge.profile_models import (
    BusinessRulesDocument,
    DatabaseSchema,
    EvalQuestionsDocument,
    ExamplesDocument,
    GlossaryDocument,
    MetricsDocument,
    Profile,
    ProfileMeta,
    RelationshipsDocument,
    SecurityPolicy,
    SqlStyle,
    TableProfile,
)

logger = logging.getLogger(__name__)


class ProfileError(Exception):
    """Base class for profile loading errors."""


class ProfileNotFoundError(ProfileError):
    """Raised when the profile directory does not exist."""


class ProfileFileError(ProfileError):
    """Raised when a profile file is missing (when mandatory) or malformed."""


_MANDATORY_FILES: tuple[str, ...] = ("profile.yaml", "schema.generated.yaml")


def _read_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileFileError(f"cannot read {path}: {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProfileFileError(f"invalid YAML in {path}: {exc}") from exc


def _parse_model(model_cls: type, path: Path, data: Any) -> Any:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ProfileFileError(
            f"{path}: expected a YAML mapping at top level, got {type(data).__name__}"
        )
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise ProfileFileError(f"{path}: {exc}") from exc


class ProfileLoader:
    """Load profiles from a directory tree rooted at ``profiles_root``."""

    def __init__(self, profiles_root: Path | str) -> None:
        self.profiles_root = Path(profiles_root)

    def profile_dir(self, profile_id: str) -> Path:
        return self.profiles_root / profile_id

    def load(self, profile_id: str) -> Profile:
        """Load and return the profile identified by ``profile_id``."""

        directory = self.profile_dir(profile_id)
        if not directory.is_dir():
            raise ProfileNotFoundError(
                f"profile {profile_id!r} not found at {directory}"
            )

        for required in _MANDATORY_FILES:
            if not (directory / required).is_file():
                raise ProfileFileError(
                    f"profile {profile_id!r} is missing mandatory file {required}"
                )

        logger.info(
            "loading profile",
            extra={"profile_id": profile_id, "path": str(directory)},
        )

        meta = _parse_model(ProfileMeta, directory / "profile.yaml",
                            _read_yaml(directory / "profile.yaml"))
        database_schema = _parse_model(
            DatabaseSchema,
            directory / "schema.generated.yaml",
            _read_yaml(directory / "schema.generated.yaml"),
        )

        relationships = self._optional(directory, "relationships.yaml", RelationshipsDocument)
        business_rules = self._optional(directory, "business_rules.yaml", BusinessRulesDocument)
        glossary = self._optional(directory, "glossary.yaml", GlossaryDocument)
        metrics = self._optional(directory, "metrics.yaml", MetricsDocument)
        examples = self._optional(directory, "examples.yaml", ExamplesDocument)
        eval_questions = self._optional(
            directory, "eval_questions.yaml", EvalQuestionsDocument
        )
        security_policy = self._optional(directory, "security_policy.yaml", SecurityPolicy)
        sql_style = self._optional(directory, "sql_style.yaml", SqlStyle)
        tables = self._load_tables(directory)

        return Profile(
            meta=meta,
            database_schema=database_schema,
            relationships=relationships,
            business_rules=business_rules,
            glossary=glossary,
            metrics=metrics,
            examples=examples,
            eval_questions=eval_questions,
            security_policy=security_policy,
            sql_style=sql_style,
            tables=tables,
        )

    def _optional(self, directory: Path, filename: str, model_cls: type) -> Any:
        path = directory / filename
        if not path.is_file():
            return model_cls()
        return _parse_model(model_cls, path, _read_yaml(path))

    def _load_tables(self, profile_dir: Path) -> dict[str, TableProfile]:
        """Load table profiles from ``tables.yaml`` or legacy ``tables/*.yaml``."""

        unified = profile_dir / "tables.yaml"
        if unified.is_file():
            return self._load_tables_unified(unified)
        return self._load_tables_individual(profile_dir / "tables")

    def _load_tables_unified(self, path: Path) -> dict[str, TableProfile]:
        data = _read_yaml(path)
        if not isinstance(data, dict):
            raise ProfileFileError(
                f"{path}: expected a YAML mapping at top level, got {type(data).__name__}"
            )
        raw_tables = data.get("tables")
        tables: dict[str, TableProfile] = {}

        if isinstance(raw_tables, dict):
            for _key, table_data in raw_tables.items():
                if not isinstance(table_data, dict):
                    raise ProfileFileError(
                        f"{path}: table entry {_key!r} must be a mapping, got {type(table_data).__name__}"
                    )
                tp = TableProfile.model_validate(table_data)
                if tp.name in tables:
                    raise ProfileFileError(
                        f"duplicate table profile for {tp.name!r} in {path.name}"
                    )
                tables[tp.name] = tp
            return tables

        if isinstance(raw_tables, list):
            for i, table_data in enumerate(raw_tables):
                if not isinstance(table_data, dict):
                    raise ProfileFileError(
                        f"{path}: tables[{i}] must be a mapping, got {type(table_data).__name__}"
                    )
                tp = TableProfile.model_validate(table_data)
                if tp.name in tables:
                    raise ProfileFileError(
                        f"duplicate table profile for {tp.name!r} in {path.name}"
                    )
                tables[tp.name] = tp
            return tables

        raise ProfileFileError(
            f"{path}: 'tables' must be a mapping or a list of table documents, got {type(raw_tables).__name__}"
        )

    def _load_tables_individual(self, tables_dir: Path) -> dict[str, TableProfile]:
        if not tables_dir.is_dir():
            return {}
        result: dict[str, TableProfile] = {}
        for path in self._iter_yaml_files(tables_dir):
            tp = _parse_model(TableProfile, path, _read_yaml(path))
            if tp.name in result:
                raise ProfileFileError(
                    f"duplicate table profile for {tp.name!r} "
                    f"(seen in {path.name})"
                )
            result[tp.name] = tp
        return result

    @staticmethod
    def _iter_yaml_files(directory: Path) -> Iterable[Path]:
        return sorted(p for p in directory.iterdir() if p.suffix in {".yaml", ".yml"})
