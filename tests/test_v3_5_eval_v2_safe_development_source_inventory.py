import hashlib
import json
import sqlite3

from shiliu.eval_v3_5.eval_v2.protected_source_projection import ProtectedSourceProjection
from shiliu.eval_v3_5.eval_v2.safe_development_source_inventory import (
    INVENTORY_FIELDS, build_safe_development_source_inventory_v2,
)


def _fixture(tmp_path):
    artifacts = tmp_path / "artifacts"
    raw = artifacts / "safe-video" / "subtitle-raw.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'[{"from":0,"to":1.5,"content":"fixture"}]')
    db = tmp_path / "snapshot.db"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE videos (id INTEGER, platform TEXT, source_id TEXT, part INTEGER, subtitle_source TEXT, subtitle_language TEXT, raw_subtitle_path TEXT, duration_seconds INTEGER)")
    connection.execute("INSERT INTO videos VALUES (1,'fixture','safe-video',1,'human','en',?,2)", (str(raw),))
    connection.execute("INSERT INTO videos VALUES (2,'fixture','missing-video',1,'unknown',NULL,NULL,0)")
    connection.commit(); connection.close()
    raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
    manifest = tmp_path / "artifacts.jsonl"
    manifest.write_text(json.dumps({"artifact_type":"raw_subtitle","video_id":1,"status":"ok","sha256":raw_hash}) + "\n" + json.dumps({"artifact_type":"raw_subtitle","video_id":2,"status":"not_declared"}) + "\n")
    projection = ProtectedSourceProjection(frozenset({"q"}), frozenset(), frozenset(), frozenset(), 5, 2)
    return db, artifacts, manifest, projection


def _build(tmp_path):
    db, artifacts, manifest, projection = _fixture(tmp_path)
    return build_safe_development_source_inventory_v2(
        snapshot_db_path=db, snapshot_db_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),
        artifact_root=artifacts, artifact_manifest_path=manifest,
        artifact_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), protection=projection,
    )


def test_inventory_fields_versions_timeline_and_unavailable(tmp_path):
    records, _, audit = _build(tmp_path)
    assert len(records) == 2
    assert all(set(record) == INVENTORY_FIELDS for record in records)
    available = next(record for record in records if record["source_availability"] == "available")
    missing = next(record for record in records if record["source_availability"] == "missing")
    assert available["segment_count"] == 1 and len(available["timeline_run_ids"]) == 1
    assert missing["export_relative_path"] is None and missing["segment_count"] == 0
    assert audit["candidate_case_count"] == 0 and audit["model_call_count"] == 0


def test_stable_ids_and_bytes(tmp_path):
    first, first_manifest, _ = _build(tmp_path / "one")
    second, second_manifest, _ = _build(tmp_path / "two")
    # Absolute fixture paths affect the authority DB, but logical source IDs and raw bytes do not.
    assert {r["video_id"]: r["source_version"] for r in first} == {
        r["video_id"]: r["source_version"] for r in second
    }
    assert first_manifest["source_count"] == second_manifest["source_count"] == 2


def test_protected_video_is_excluded(tmp_path):
    db, artifacts, manifest, projection = _fixture(tmp_path)
    projection = ProtectedSourceProjection(projection.heldout_query_identities, frozenset(), frozenset({"safe-video"}), frozenset(), 5, 2)
    records, _, audit = build_safe_development_source_inventory_v2(
        snapshot_db_path=db, snapshot_db_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),
        artifact_root=artifacts, artifact_manifest_path=manifest,
        artifact_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), protection=projection,
    )
    assert {record["video_id"] for record in records} == {"missing-video"}
    assert audit["excluded_source_count"] == 1
