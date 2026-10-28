"""Normalize a guarded source package into a NEW package; never edit its source.

Only reviewed Schema24/25 additive history is supported. This module is not a
runtime initializer. Real copying/normalization requires prior user approval,
recorded in the guarded input's historical.json, never a synthetic marker.
"""

from __future__ import annotations
from datetime import datetime, timezone
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3

from shiliu.migration.safety import (
    guard_source,
    source_kind,
    new_package_root,
)
from shiliu.migration.readonly import connect_snapshot
from shiliu.migration.snapshot import sha
from shiliu.migration.values import MigrationRejected


def normalize_package(source: Path, destination: Path):
    source = guard_source(source)
    provenance = source_kind(source)
    before = sha(source)
    if not provenance["synthetic_only"] and provenance["database_sha256"] != before:
        raise MigrationRejected("approved_source_identity_mismatch")
    if (
        destination.parent.resolve() != new_package_root(destination) / "sources"
        or source.parent.parent != destination.parent
        or destination.exists()
        or destination.is_symlink()
    ):
        raise MigrationRejected("normalization_requires_new_private_package")
    import re

    if not re.fullmatch(r"w14_[a-z0-9_]+", destination.name):
        raise MigrationRejected("invalid_normalized_package_name")
    with connect_snapshot(source) as c:
        version = int(
            c.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
        )
        if version not in {24, 25}:
            raise MigrationRejected("normalization_supports_24_25_only")
        destination.mkdir(mode=0o700)
        target = destination / "source.sqlite3"
        with closing(sqlite3.connect(target)) as writer:
            c.backup(writer)
    # All mutation is on the new copy. The original frozen DDL source remains
    # byte-identical in legacy_schema and is imported only inside this function.
    from shiliu.migration.legacy_schema.assistant import (
        initialize_assistant_context_schema,
        initialize_assistant_wiki_schema,
    )

    with closing(sqlite3.connect(target)) as c, c:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        if version == 24:
            initialize_assistant_wiki_schema(c)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            c.execute(
                "INSERT OR IGNORE INTO assistant_wiki_materials(page_id,video_id,source_revision,relation,status,created_at,updated_at) SELECT DISTINCT page_id,video_id,source_revision,'supports_block','integrated',?,? FROM assistant_wiki_dependencies",
                (now, now),
            )
        initialize_assistant_context_schema(c)
        c.execute("UPDATE schema_meta SET value='26' WHERE key='schema_version'")
        if c.execute("PRAGMA foreign_key_check").fetchone():
            raise MigrationRejected("normalized_source_fk_orphan")
    if before != sha(source):
        raise MigrationRejected("normalization_source_changed")
    for name in ("files", "artifacts.json", "ownership.json", "synthetic_vectors.json"):
        original = source.parent / name
        if not original.exists():
            continue
        if original.is_symlink():
            raise MigrationRejected("unsafe_source_package_member")
        if original.is_dir():
            shutil.copytree(original, destination / name, symlinks=True)
        else:
            shutil.copyfile(original, destination / name)
    if provenance["synthetic_only"]:
        (destination / "synthetic.json").write_text(
            json.dumps({"task": "shiliu-w01-20261023", "synthetic_only": True})
        )
    else:
        marker = {k: v for k, v in provenance.items() if k != "synthetic_only"}
        marker["database_sha256"] = sha(target)
        (destination / "historical.json").write_text(json.dumps(marker))
    evidence = {
        "source_schema": version,
        "target_schema": 26,
        "source_sha256": before,
        "normalized_sha256": sha(target),
        "normalization": "reviewed-additive-24-25-to-26-v1",
        "synthetic_only": provenance["synthetic_only"],
    }
    (destination / "normalization.json").write_text(json.dumps(evidence, indent=2))
    return target, evidence


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        _, evidence = normalize_package(args.source, args.destination)
        print(json.dumps(evidence, sort_keys=True))
    except (MigrationRejected, ValueError, OSError, sqlite3.Error) as error:
        category = (
            str(error)
            if isinstance(error, MigrationRejected)
            else "normalization_input_or_copy_failure"
        )
        parser.exit(1, json.dumps({"error": category}) + "\n")


if __name__ == "__main__":
    main()
