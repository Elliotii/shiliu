from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Iterable


PROTECTED_TABLES = (
    "videos",
    "video_notes",
    "favorite_sources",
    "video_source_memberships",
    "events",
    "retrieval_units",
    "retrieval_units_fts",
    "retrieval_dense_vectors",
    "retrieval_dense_index_meta",
    "retrieval_sync_state",
)


@dataclass(frozen=True)
class SnapshotResult:
    database_path: Path
    artifact_root: Path
    artifact_records: tuple[dict[str, Any], ...]
    counts: dict[str, int]


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup_sqlite(source: Path, destination: Path) -> None:
    """Create a transactionally consistent SQLite snapshot via Backup API."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    source_uri = f"file:{source.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)


def create_corpus_snapshot(
    source_database: Path,
    snapshot_database: Path,
    artifact_root: Path,
) -> SnapshotResult:
    backup_sqlite(source_database, snapshot_database)
    artifact_root.mkdir(parents=True, exist_ok=True)
    records = _copy_and_rebind_artifacts(snapshot_database, artifact_root)
    validation = validate_snapshot(snapshot_database)
    return SnapshotResult(
        database_path=snapshot_database,
        artifact_root=artifact_root,
        artifact_records=tuple(records),
        counts=validation["counts"],
    )


def validate_snapshot(database: Path) -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = [dict(row) for row in connection.execute("PRAGMA foreign_key_check")]
        counts = {
            name: int(connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0])
            for name in (
                "videos",
                "retrieval_units",
                "retrieval_units_fts",
                "retrieval_dense_vectors",
            )
        }
        counts["video_units"] = int(
            connection.execute(
                "SELECT count(*) FROM retrieval_units WHERE unit_type='video'"
            ).fetchone()[0]
        )
        counts["transcript_chunks"] = int(
            connection.execute(
                "SELECT count(*) FROM retrieval_units WHERE unit_type='transcript_chunk'"
            ).fetchone()[0]
        )
        counts["indexed_videos"] = int(
            connection.execute("SELECT count(DISTINCT video_id) FROM retrieval_units").fetchone()[0]
        )
    aligned = (
        counts["retrieval_units"]
        == counts["retrieval_units_fts"]
        == counts["retrieval_dense_vectors"]
    )
    if integrity != "ok" or foreign_keys or not aligned:
        raise ValueError(
            f"invalid snapshot: integrity={integrity}, foreign_keys={len(foreign_keys)}, "
            f"aligned={aligned}"
        )
    return {
        "integrity_check": integrity,
        "foreign_key_violations": foreign_keys,
        "counts": counts,
    }


def table_hash(database: Path, table: str) -> tuple[int, str]:
    if table not in PROTECTED_TABLES:
        raise ValueError(f"unsupported protected table: {table}")
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]
        order = ",".join(f'"{name}"' for name in columns)
        rows = connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}')
        digest = sha256()
        count = 0
        for row in rows:
            payload = {key: _json_value(row[key]) for key in row.keys()}
            digest.update(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            )
            digest.update(b"\n")
            count += 1
    return count, digest.hexdigest()


def protected_table_hashes(database: Path) -> dict[str, dict[str, Any]]:
    return {
        table: {"row_count": values[0], "sha256": values[1]}
        for table in PROTECTED_TABLES
        for values in (table_hash(database, table),)
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _copy_and_rebind_artifacts(database: Path, artifact_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        videos = connection.execute(
            """
            SELECT v.* FROM videos v
            WHERE EXISTS (SELECT 1 FROM retrieval_units u WHERE u.video_id=v.id)
            ORDER BY v.id
            """
        ).fetchall()
        for row in videos:
            video_id = int(row["id"])
            bvid = str(row["source_id"])
            target_dir = artifact_root / bvid
            target_dir.mkdir(parents=True, exist_ok=True)
            raw_source = _raw_source(row["raw_subtitle_path"])
            raw_record = _copy_artifact(video_id, bvid, "raw_subtitle", raw_source, target_dir)
            records.append(raw_record)
            summary_source = _summary_source(row)
            summary_record = _copy_artifact(video_id, bvid, "active_summary", summary_source, target_dir)
            records.append(summary_record)
            metadata_source = _metadata_source(row)
            records.append(
                _copy_artifact(video_id, bvid, "metadata", metadata_source, target_dir)
            )
            connection.execute(
                """
                UPDATE videos
                SET artifact_dir=?, raw_subtitle_path=?, summary_path=?,
                    transcript_path=NULL, cover_path=NULL
                WHERE id=?
                """,
                (
                    str(target_dir),
                    raw_record["snapshot_path"] if raw_record["status"] == "ok" else None,
                    summary_record["snapshot_path"] if summary_record["status"] == "ok" else None,
                    video_id,
                ),
            )
        # Non-indexed Product rows are not part of the Eval artifact corpus,
        # but the snapshot must not retain mutable absolute Live paths either.
        connection.execute(
            """
            UPDATE videos
            SET artifact_dir=NULL, raw_subtitle_path=NULL, summary_path=NULL,
                transcript_path=NULL, cover_path=NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM retrieval_units u WHERE u.video_id=videos.id
            )
            """
        )
    return records


def _raw_source(value: object) -> Path | None:
    if not value:
        return None
    return Path(str(value)).with_name("subtitle-raw.json")


def _summary_source(row: sqlite3.Row) -> Path | None:
    value = row["summary_path"]
    if not value:
        return None
    directory = Path(str(value)).parent
    revision = str(row["active_revision"] or "refined")
    candidates = (directory / f"summary.{revision}.json", directory / "summary.json")
    return next((path for path in candidates if path.is_file()), candidates[0])


def _metadata_source(row: sqlite3.Row) -> Path | None:
    if row["artifact_dir"]:
        return Path(str(row["artifact_dir"])) / "metadata.json"
    if row["raw_subtitle_path"]:
        return Path(str(row["raw_subtitle_path"])).parent / "metadata.json"
    return None


def _copy_artifact(
    video_id: int,
    bvid: str,
    artifact_type: str,
    source: Path | None,
    target_dir: Path,
) -> dict[str, Any]:
    base = {
        "video_id": video_id,
        "bvid": bvid,
        "artifact_type": artifact_type,
        "live_path": str(source) if source else "",
        "snapshot_path": "",
        "sha256": "",
        "size": 0,
    }
    if source is None:
        return {**base, "status": "not_declared"}
    if not source.is_file():
        return {**base, "status": "missing"}
    target = target_dir / source.name
    shutil.copy2(source, target)
    status = "ok"
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        expected = list if artifact_type == "raw_subtitle" else dict
        if not isinstance(payload, expected):
            status = "malformed"
    except (OSError, UnicodeError, json.JSONDecodeError):
        status = "malformed"
    return {
        **base,
        "snapshot_path": str(target),
        "sha256": sha256_file(target),
        "size": target.stat().st_size,
        "status": status,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"blob_sha256": sha256(value).hexdigest(), "size": len(value)}
    return value
