"""``generate_profile_from_schema`` CLI implementation.

Reads a SQL Server DDL script, extracts structural information, and
writes the four Phase-3 YAML facets (``profile.yaml``,
``schema.generated.yaml``, ``relationships.yaml``, ``tables/*.yaml``) into
``<profiles_root>/<profile_id>/``.

Exit codes:

* ``0`` — profile written successfully
* ``1`` — output directory already contains a profile and ``--force``
  was not passed
* ``2`` — input schema file is missing or could not be decoded
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from vai_agent.db.schema_extractor import parse_schema_sql
from vai_agent.knowledge.profile_generator import (
    generate_profile,
    read_schema_file,
    write_profile_to_disk,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_profile_from_schema",
        description=(
            "Parse a SQL Server DDL file and generate the base profile YAML "
            "files (profile / schema.generated / relationships / tables)."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to the SQL DDL file (e.g. data/input/Schema.sql).",
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="Profile id; output is written to <profiles-root>/<profile>/.",
    )
    parser.add_argument(
        "--profiles-root",
        default=Path("profiles"),
        type=Path,
        help="Root directory for profiles (default: ./profiles).",
    )
    parser.add_argument(
        "--database-name",
        default=None,
        help="Logical database name to record in profile.yaml. "
             "Defaults to the profile id.",
    )
    parser.add_argument(
        "--default-schema",
        default="dbo",
        help="Default SQL schema/namespace for the database (default: dbo).",
    )
    parser.add_argument(
        "--timezone",
        default="UTC",
        help="Timezone string to record in profile.yaml (default: UTC).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing profile.yaml at the target location.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Main."""
    out = stdout or sys.stdout
    err = stderr or sys.stderr

    args = _build_parser().parse_args(argv)

    schema_path: Path = args.input
    if not schema_path.is_file():
        print(f"input schema file not found: {schema_path}", file=err)
        return 2

    try:
        text = read_schema_file(schema_path)
    except UnicodeDecodeError as exc:
        print(f"could not decode {schema_path}: {exc}", file=err)
        return 2

    extracted = parse_schema_sql(text)

    profile = generate_profile(
        extracted=extracted,
        profile_id=args.profile,
        database_name=args.database_name or args.profile,
        source_path=schema_path,
        default_schema=args.default_schema,
        timezone=args.timezone,
    )

    output_dir = args.profiles_root / args.profile
    try:
        written = write_profile_to_disk(profile, output_dir, force=args.force)
    except FileExistsError as exc:
        print(f"refusing to overwrite: {exc}", file=err)
        return 1

    print(f"profile: {args.profile}", file=out)
    print(f"  tables:         {len(profile.database_schema.tables)}", file=out)
    print(f"  views:          {len(profile.database_schema.views)}", file=out)
    print(f"  procedures:     {len(profile.database_schema.stored_procedures)}", file=out)
    print(f"  relationships:  {len(profile.relationships.relationships)}", file=out)
    print(f"  files written:  {len(written)}", file=out)
    print(f"  output:         {output_dir}", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
