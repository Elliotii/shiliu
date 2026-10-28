"""Explicit read-only closed candidate audit; writes only a private JSON report.

Never normalizes/backs up SQLite, starts Application, reads config or contacts a
provider. Refuses active handles/nonempty journals before immutable inspection.
"""

from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def stat(path):
    if not path.exists():
        return None
    s = path.stat()
    return dict(
        size=s.st_size, mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns, inode=s.st_ino
    )


def qi(name):
    return '"' + name.replace('"', '""') + '"'


def strings(value, field):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from strings(v, field + "." + k)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v, field + "[]")
    elif isinstance(value, str):
        yield field, value


def audit(source, roots, report, reference_roots=()):
    source = source.absolute()
    if source.is_symlink() or not source.is_file():
        raise ValueError("source must be explicit regular file")
    if report.parent.is_symlink() or not report.parent.is_dir():
        raise ValueError("create private report directory first")
    if (
        report.parent.stat().st_uid != os.getuid()
        or report.parent.stat().st_mode & 0o077
    ):
        raise ValueError("report directory must be owner-only")
    if report.exists():
        raise ValueError("refusing to overwrite evidence")
    roots = [r.resolve(strict=True) for r in roots]
    reference_roots = [r.resolve(strict=True) for r in reference_roots]
    allowed_roots = roots + reference_roots
    paths = [
        source,
        *[source.with_name(source.name + s) for s in ("-wal", "-shm", "-journal")],
    ]
    before = {str(p): stat(p) for p in paths}
    opened = subprocess.run(
        ["/usr/sbin/lsof", "-F", "pn", "--", *[str(p) for p in paths if p.exists()]],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if opened.returncode not in (0, 1) or opened.stdout.strip():
        raise ValueError("candidate open handles; closed audit refused")
    if any(p.exists() and p.stat().st_size for p in (paths[1], paths[3])):
        raise ValueError("nonempty WAL/journal; immutable audit refused")
    digest = sha(source)
    references = []
    tables = {}
    states = {}
    principals = {}
    json_bad = Counter()
    fk = []
    typed_errors = []
    identities = []
    from shiliu.migration.snapshot import mapping
    from shiliu.migration.values import convert, MigrationRejected

    target_contract = mapping()["tables"]
    conn = sqlite3.connect(source.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        fk = [list(r) for r in conn.execute("PRAGMA foreign_key_check")]
        objects = [
            dict(r)
            for r in conn.execute(
                "SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','trigger','index') ORDER BY type,name"
            )
        ]
        for obj in objects:
            if obj["type"] != "table":
                continue
            name = obj["name"]
            columns = [
                dict(r) for r in conn.execute("PRAGMA table_xinfo(" + qi(name) + ")")
            ]
            count = conn.execute("SELECT count(*) FROM " + qi(name)).fetchone()[0]
            tables[name] = {"count": count, "columns": columns}
            names = {c["name"] for c in columns}
            for key in ("status", "lifecycle_status", "kind"):
                if key in names:
                    states[name + "." + key] = dict(
                        conn.execute(
                            "SELECT "
                            + qi(key)
                            + ",count(*) FROM "
                            + qi(name)
                            + " GROUP BY "
                            + qi(key)
                        )
                    )
            if "principal_id" in names:
                principals[name] = dict(
                    conn.execute(
                        "SELECT principal_id,count(*) FROM "
                        + qi(name)
                        + " GROUP BY principal_id"
                    )
                )
            if name.startswith("sqlite_") or "_fts" in name:
                continue
            pks = [c["name"] for c in columns if c["pk"]]
            for row in conn.execute("SELECT * FROM " + qi(name)):
                key = {k: row[k] for k in pks}
                for column, raw in dict(row).items():
                    definition = (
                        target_contract.get(name, {}).get("columns", {}).get(column)
                    )
                    if definition and "source" in definition:
                        try:
                            convert(raw, definition, field=name + "." + column)
                        except MigrationRejected as error:
                            typed_errors.append(
                                {
                                    "table": name,
                                    "key": key,
                                    "field": column,
                                    "category": str(error),
                                }
                            )
                    if not isinstance(raw, str) or not raw:
                        continue
                    value = raw
                    if column.endswith("_json"):
                        try:
                            value = json.loads(raw)
                        except ValueError:
                            json_bad[name + "." + column] += 1
                            continue
                    for field, text in strings(value, column):
                        if field == "source_version" or field.endswith(
                            ".source_version"
                        ):
                            identities.append(
                                {
                                    "table": name,
                                    "key": key,
                                    "field": field,
                                    "source_version": text,
                                }
                            )
                        if "://" in text or "\n" in text or len(text) > 4096:
                            continue
                        # A whole path-valued string, never an embedded sentence.
                        looks_path = (
                            text.startswith("/")
                            or "/" in text
                            or bool(
                                re.search(
                                    r"\.(?:json|txt|md|jpg|png|mp3|m4a|wav|webm|pdf)$",
                                    text,
                                )
                            )
                        )
                        path_field = bool(
                            re.search(
                                r"(?:path|file|snapshot_ref|artifact_ref|export_ref|artifact_dir)(?:\[\])?$",
                                field,
                            )
                        )
                        if not looks_path or not path_field:
                            continue
                        references.append(
                            {"table": name, "key": key, "field": field, "path": text}
                        )
        # Enumerate all allowed content roots as well: old source versions may
        # be addressed solely by hash/segment identity inside historical JSON.
        files = {}
        unsafe = []
        candidates = set()
        for root in roots:
            for directory, dirs, names in os.walk(root, followlinks=False):
                for dirname in list(dirs):
                    p = Path(directory) / dirname
                    if p.is_symlink():
                        unsafe.append(str(p))
                        dirs.remove(dirname)
                for name in names:
                    candidates.add(Path(directory) / name)
        for ref in references:
            p = Path(ref["path"])
            if not p.is_absolute():
                options = [r / p for r in allowed_roots]
                options += [source.parent / p, source.parent.parent / p]
                present = [p for p in options if p.is_file()]
                p = present[0] if len(present) == 1 else p
            ref["resolved"] = str(p)
            if p.is_absolute() and any(
                p.resolve().is_relative_to(r) for r in allowed_roots
            ):
                if p.is_dir():
                    ref["reference_kind"] = "directory"
                else:
                    candidates.add(p)
            else:
                ref["outside_allowed_roots"] = True
        for path in sorted(candidates):
            if path.is_symlink() or any(p.is_symlink() for p in path.parents):
                unsafe.append(str(path))
                continue
            if not path.is_file():
                continue
            first = stat(path)
            h = sha(path)
            if first != stat(path):
                raise ValueError("file changed during hash audit")
            files[str(path)] = {**first, "sha256": h}
        known_hashes = {f["sha256"] for f in files.values()}
        for identity in identities:
            identity["raw_bytes_found"] = (
                identity["source_version"].removeprefix("sha256:") in known_hashes
            )
        for ref in references:
            ref["exists"] = (
                ref.get("reference_kind") == "directory" or ref["resolved"] in files
            )
            if ref["resolved"] in files:
                ref["sha256"] = files[ref["resolved"]]["sha256"]
    finally:
        conn.close()
    after = {str(p): stat(p) for p in paths}
    if before != after or digest != sha(source):
        raise ValueError("candidate changed during audit")
    aggregate = {
        "source_schema": str(version),
        "table_count": len(tables),
        "rows": {n: t["count"] for n, t in tables.items()},
        "fk_anomalies": len(fk),
        "typed_anomalies": len(typed_errors),
        "typed_anomaly_categories": dict(Counter(e["category"] for e in typed_errors)),
        "invalid_json_fields": dict(json_bad),
        "references": len(references),
        "missing_or_outside_references": sum(not r["exists"] for r in references),
        "outside_references": sum(
            r.get("outside_allowed_roots", False) for r in references
        ),
        "raw_identity_references": len(identities),
        "unmatched_raw_identity_references": sum(
            not i["raw_bytes_found"] for i in identities
        ),
        "files_hashed": len(files),
        "bytes_hashed": sum(f["size"] for f in files.values()),
        "symlink_rejections": len(unsafe),
        "source_stable": True,
        "open_handles": 0,
    }
    payload = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "source_sha256": digest,
        "reference_roots": list(map(str, reference_roots)),
        "source_stat_before": before,
        "source_stat_after": after,
        "roots": list(map(str, roots)),
        "aggregate": aggregate,
        "tables": tables,
        "states": states,
        "principals": principals,
        "raw_identities": identities,
        "typed_anomalies": typed_errors,
        "foreign_key_anomalies": fk,
        "references": references,
        "files": files,
        "unsafe_paths": unsafe,
    }
    with report.open("x", encoding="utf-8") as f:
        os.chmod(report, 0o600)
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return aggregate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--content-root", type=Path, action="append", required=True)
    parser.add_argument("--reference-root", type=Path, action="append", default=[])
    parser.add_argument("--private-report", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            audit(
                args.source, args.content_root, args.private_report, args.reference_root
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
