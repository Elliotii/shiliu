from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from shiliu.eval.snapshot import create_corpus_snapshot, sha256_file, validate_snapshot


def _database(path: Path, artifact: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE videos(
              id INTEGER PRIMARY KEY, source_id TEXT, raw_subtitle_path TEXT,
              summary_path TEXT, artifact_dir TEXT, transcript_path TEXT,
              cover_path TEXT, active_revision TEXT
            );
            CREATE TABLE retrieval_units(
              unit_id TEXT PRIMARY KEY, unit_type TEXT, video_id INTEGER REFERENCES videos(id)
            );
            CREATE VIRTUAL TABLE retrieval_units_fts USING fts5(unit_id UNINDEXED, search_text);
            CREATE TABLE retrieval_dense_vectors(unit_id TEXT PRIMARY KEY REFERENCES retrieval_units(unit_id));
            """
        )
        connection.execute(
            "INSERT INTO videos VALUES(1,'BV1234567890',?,?,?,?,?,?)",
            (
                str(artifact / "subtitle-raw.json"), str(artifact / "summary.refined.json"),
                str(artifact), str(artifact / "transcript.json"),
                str(artifact / "cover.jpg"), "refined",
            ),
        )
        connection.execute("INSERT INTO retrieval_units VALUES('u1','video',1)")
        connection.execute("INSERT INTO retrieval_units_fts VALUES('u1','hello')")
        connection.execute("INSERT INTO retrieval_dense_vectors VALUES('u1')")


def test_backup_artifacts_and_rebinding_only_touch_snapshot(tmp_path: Path) -> None:
    live_artifact = tmp_path / "live" / "BV1234567890"
    live_artifact.mkdir(parents=True)
    (live_artifact / "subtitle-raw.json").write_text(
        json.dumps([{"from": 1, "to": 2, "content": "hello"}]), encoding="utf-8"
    )
    (live_artifact / "summary.refined.json").write_text(
        json.dumps({"important_chapters": []}), encoding="utf-8"
    )
    (live_artifact / "metadata.json").write_text("{}", encoding="utf-8")
    live = tmp_path / "live.db"
    _database(live, live_artifact)
    before = sha256_file(live)
    snapshot = tmp_path / "snapshot" / "shiliu_eval.db"
    result = create_corpus_snapshot(live, snapshot, tmp_path / "snapshot" / "artifacts")
    assert sha256_file(live) == before
    assert result.counts["retrieval_units"] == 1
    assert validate_snapshot(snapshot)["integrity_check"] == "ok"
    with sqlite3.connect(snapshot) as connection:
        raw, transcript, cover = connection.execute(
            "SELECT raw_subtitle_path,transcript_path,cover_path FROM videos"
        ).fetchone()
    assert str(tmp_path / "snapshot" / "artifacts") in raw
    assert transcript is None and cover is None
    assert all(row["status"] == "ok" for row in result.artifact_records)


def test_snapshot_rejects_misaligned_indexes(tmp_path: Path) -> None:
    artifact = tmp_path / "a"
    artifact.mkdir()
    database = tmp_path / "bad.db"
    _database(database, artifact)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM retrieval_dense_vectors")
    try:
        validate_snapshot(database)
    except ValueError as exc:
        assert "aligned=False" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("misaligned snapshot accepted")
