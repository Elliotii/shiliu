from __future__ import annotations

from datetime import datetime, timezone
import json
import hashlib

import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.wiki import WikiService
from shiliu.db import Database, utc_now
import shiliu.metadata_backfill as backfill
from shiliu.metadata_backfill import apply, dry_run, rollback, stage


def _candidate(video_id: int, bvid: str = "BV1234567890", published_at: int = 1_600_000_000):
    return {
        "video_id": video_id,
        "bvid": bvid,
        "platform": "bilibili",
        "part": 1,
        "source_field": "info.pubdate",
        "raw_pubdate": published_at,
        "published_at": published_at,
        "metadata_observed_at": datetime.fromtimestamp(
            1_700_000_000, timezone.utc
        ).isoformat(timespec="seconds"),
        "source": "bilibili.get_info",
    }


def _db(tmp_path, *, automatic: bool = False):
    db = Database(tmp_path / "isolated.db")
    db.initialize()
    now = utc_now()
    with db.connect() as connection:
        source_id = connection.execute(
            """INSERT INTO favorite_sources(account_id,folder_id,created_at,updated_at)
               VALUES(32958899,123,?,?)""", (now, now)
        ).lastrowid
        video_id = connection.execute(
            """INSERT INTO videos(platform,source_id,part,title,video_url,status,discovered_at,updated_at)
               VALUES('bilibili','BV1234567890',1,'title','https://example.invalid','completed',?,?)""",
            (now, now),
        ).lastrowid
        connection.execute(
            """INSERT INTO video_source_memberships(source_id,bvid,video_id,first_observed_at,last_observed_at)
               VALUES(?,?,?,?,?)""", (source_id, "BV1234567890", video_id, now, now)
        )
        if automatic:
            connection.execute(
                """INSERT INTO assistant_spaces(principal_id,name,source_ids_json,maintenance_mode,created_at,updated_at)
                   VALUES('local_operator','auto',?,'automatic',?,?)""",
                (f"[{source_id}]", now, now),
            )
    return db, int(video_id)


def test_backfill_stage_apply_resume_and_rollback(tmp_path):
    db, video_id = _db(tmp_path)
    candidates = [_candidate(video_id)]
    assert dry_run(db.path, candidates)["states"][0]["state"] == "ready"
    stage(db.path, "test-run", candidates)
    assert apply(db.path, "test-run")["counts"] == {"applied": 1}
    assert apply(db.path, "test-run")["counts"] == {"already_applied": 1}
    with db.connect() as connection:
        row = connection.execute("SELECT published_at FROM videos WHERE id=?", (video_id,)).fetchone()
    assert row["published_at"] == 1_600_000_000
    assert rollback(db.path, "test-run")["counts"] == {"rolled_back": 1}
    with db.connect() as connection:
        row = connection.execute("SELECT published_at FROM videos WHERE id=?", (video_id,)).fetchone()
    assert row["published_at"] is None


def test_backfill_holds_generated_jobs_after_worker_resume(tmp_path):
    db, video_id = _db(tmp_path, automatic=True)
    store = AssistantRunStore(db)
    candidates = [_candidate(video_id)]
    stage(db.path, "hold-run", candidates)
    assert apply(db.path, "hold-run")["counts"] == {"applied": 1}
    assert store.claim_job(owner="test-worker", allow_model_jobs=True) is None
    with db.connect() as connection:
        held = connection.execute("SELECT count(*) AS n FROM metadata_backfill_job_holds").fetchone()["n"]
        queued = connection.execute("SELECT count(*) AS n FROM assistant_jobs WHERE kind='source_reconcile' AND status='queued'").fetchone()["n"]
    assert held == queued == 1


def test_candidate_identity_and_future_time_are_rejected(tmp_path):
    db, video_id = _db(tmp_path)
    invalid_identity = _candidate(video_id, "BV0000000000")
    assert dry_run(db.path, [invalid_identity])["states"][0]["state"] == "identity_or_scope_mismatch"
    future = _candidate(video_id, published_at=1_900_000_000)
    from shiliu.metadata_backfill import validate_candidate
    try:
        validate_candidate(future)
    except ValueError as exc:
        assert str(exc) == "publication_after_observation"
    else:
        raise AssertionError("future publish timestamp was accepted")


def test_production_stage_requires_verified_pre_migration_backup(tmp_path, monkeypatch):
    db, video_id = _db(tmp_path)
    monkeypatch.setattr(backfill, "PRODUCTION_DATABASE", db.path)
    with pytest.raises(ValueError, match="production_backup_manifest_required"):
        stage(db.path, "gated-run", [_candidate(video_id)])
    with db.connect() as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='metadata_backfill_runs'"
        ).fetchone() is None
    backup = tmp_path / "before-migration.db"
    source = backfill._connect(db.path)
    destination = backfill._connect(backup)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    manifest_path = tmp_path / "backup-manifest.json"
    manifest = {
        "source_database": str(db.path), "snapshot_database": str(backup),
        "service_stop": "isolated_fixture", "checkpoint": [0, 0, 0],
        "migration_applied": False,
        "db_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest))
    assert stage(db.path, "gated-run", [_candidate(video_id)],
                 production_backup_manifest=manifest_path)["count"] == 1
    manifest["db_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="production_backup_hash_mismatch"):
        apply(db.path, "gated-run", production_backup_manifest=manifest_path)


def test_rollback_skips_rows_changed_after_apply_and_refresh_preserves_known_date(tmp_path):
    db, video_id = _db(tmp_path)
    stage(db.path, "conflict-run", [_candidate(video_id)])
    apply(db.path, "conflict-run")
    db.update_video(video_id, title="changed after backfill", published_at=None)
    with db.connect() as connection:
        connection.execute("UPDATE videos SET updated_at='2099-01-01T00:00:00+00:00' WHERE id=?", (video_id,))
        row = connection.execute("SELECT published_at FROM videos WHERE id=?", (video_id,)).fetchone()
    assert row["published_at"] == 1_600_000_000
    assert rollback(db.path, "conflict-run")["counts"] == {"rollback_conflict": 1}
    with db.connect() as connection:
        row = connection.execute("SELECT published_at,title FROM videos WHERE id=?", (video_id,)).fetchone()
    assert row["published_at"] == 1_600_000_000
    assert row["title"] == "changed after backfill"


def _source_fixture(tmp_path, count: int = 1, *, wiki_year: bool = False):
    db = Database(tmp_path / "fixture.db")
    db.initialize()
    now = utc_now()
    with db.connect() as connection:
        source_id = connection.execute(
            """INSERT INTO favorite_sources(account_id,folder_id,created_at,updated_at)
               VALUES(32958899,321,?,?)""", (now, now)
        ).lastrowid
        video_ids = []
        for index in range(count):
            bvid = "BV1234567890" if index == 0 else f"BV123456789{index}"
            video_id = connection.execute(
                """INSERT INTO videos(platform,source_id,part,title,description,video_url,status,discovered_at,updated_at)
                   VALUES('bilibili',?,1,?,'description','https://example.invalid','completed',?,?)""",
                (bvid, f"fixture {index}", now, now),
            ).lastrowid
            connection.execute(
                """INSERT INTO video_source_memberships(source_id,bvid,video_id,first_observed_at,last_observed_at)
                   VALUES(?,?,?,?,?)""", (source_id, bvid, video_id, now, now)
            )
            video_ids.append((int(video_id), bvid))
    artifacts = ArtifactStore(tmp_path / "content/videos")
    object_root = tmp_path / "content/assistant"
    snapshots = SourceSnapshotStore(db, artifacts, object_root)
    sources = CollectionSourceService(db=db, artifacts=artifacts, snapshots=snapshots)
    store = AssistantRunStore(db)
    wiki = WikiService(db=db, store=store, sources=sources)
    captured = []
    for video_id, _bvid in video_ids:
        value = snapshots.capture(video_id)
        captured.append(value)
        card = {
            "title": "fixture", "uploader": "uploader", "published_at": None,
            "memberships": value.snapshot["memberships"], "coverage": "metadata_only",
            "material_kind": "metadata_only", "summary": "Safe card summary.",
            "key_points": [], "topics": ["Fixture topic"], "limitations": [],
        }
        wiki._commit_source_card(value, input_hash=wiki._card_input_hash(value.snapshot), card=card)
    space = store.create_space(name="backfill fixture", source_ids=[int(source_id)], maintenance_mode="automatic")
    page_id = "fixture-wiki-page"
    source_refs = [item.revision for item in captured]
    body = "This statement remains stable."
    if wiki_year:
        body = "This statement refers to 2024 and needs review."
    blocks = [{"stable_id": "fixture-block", "heading": "Fixture heading", "markdown": body,
               "applicability": "Fixture applicability", "assessment": "source_reported",
               "speaker": "", "source_refs": list(source_refs)}]
    with db.connect() as connection:
        connection.execute(
            """INSERT INTO assistant_wiki_pages(
               id,principal_id,space_id,normalized_title,title,aliases_json,page_type,summary,
               blocks_json,version,status,scope_version,created_at,updated_at)
               VALUES(?, 'local_operator', ?, 'fixture-topic', 'Fixture topic', '[]', 'topic', ?, ?, 1, 'active', 1, ?, ?)""",
            (page_id, int(space["id"]), "Contains a year." if wiki_year else "Safe page summary.",
             json.dumps(blocks, ensure_ascii=False), now, now),
        )
        page_row = connection.execute("SELECT * FROM assistant_wiki_pages WHERE id=?", (page_id,)).fetchone()
        wiki._fts_replace(connection, wiki._decode_page(dict(page_row)))
        for (video_id, _bvid), source in zip(video_ids, captured):
            connection.execute(
                """INSERT INTO assistant_wiki_dependencies(page_id,block_id,source_revision,video_id,dependency_kind,created_at)
                   VALUES(?,?,?,?,'source',?)""", (page_id, "fixture-block", source.revision, video_id, now)
            )
            connection.execute(
                """INSERT INTO assistant_wiki_materials(page_id,video_id,source_revision,relation,status,created_at,updated_at)
                   VALUES(?,?,?,'supports_block','integrated',?,?)""",
                (page_id, video_id, source.revision, now, now),
            )
    candidates = [
        _candidate(video_id, bvid, 1_600_000_000 + index * 1000)
        for index, (video_id, bvid) in enumerate(video_ids)
    ]
    return db, video_ids, candidates, object_root, artifacts.videos_dir, page_id, captured


def test_wiki_rebind_job_is_held_before_expiry_and_retry(tmp_path, monkeypatch):
    db, video_ids, candidates, object_root, videos_dir, _page_id, _captured = _source_fixture(tmp_path)
    run_id = "held-wiki-job"
    stage(db.path, run_id, candidates)

    def fail_before_rebind(*_args, **_kwargs):
        raise RuntimeError("injected_before_wiki_commit")

    monkeypatch.setattr(backfill, "_rebind_with_backfill_intent", fail_before_rebind)
    result = apply(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)
    assert result["counts"] == {"applied": 1}
    with db.connect() as connection:
        job = connection.execute("SELECT id,status FROM assistant_jobs WHERE kind='wiki_integrate' AND id LIKE 'metadata-backfill-wiki-%'").fetchone()
        assert job is not None and job["status"] == "queued"
        hold = connection.execute("SELECT run_id FROM metadata_backfill_job_holds WHERE job_id=?", (job["id"],)).fetchone()
        assert hold["run_id"] == run_id
        connection.execute("UPDATE assistant_jobs SET status='running',lease_until='2000-01-01T00:00:00+00:00' WHERE id=?", (job["id"],))
    assert AssistantRunStore(db).claim_job(owner="after-restart", allow_model_jobs=True) is None
    with db.connect() as connection:
        assert connection.execute("SELECT status FROM assistant_jobs WHERE id=?", (job["id"],)).fetchone()["status"] == "queued"
        assert connection.execute("SELECT 1 FROM metadata_backfill_job_holds WHERE job_id=?", (job["id"],)).fetchone()


def test_rebind_commit_before_operation_summary_resumes_and_rolls_back(tmp_path, monkeypatch):
    db, video_ids, candidates, object_root, videos_dir, page_id, captured = _source_fixture(tmp_path)
    run_id = "rebind-cut"
    stage(db.path, run_id, candidates)
    original_persist = backfill._persist_operation_maintenance
    failed = False

    def fail_after_wiki_commit(connection, current_run, video_id, maintenance):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("injected_after_page_commit_before_run_summary")
        return original_persist(connection, current_run, video_id, maintenance)

    monkeypatch.setattr(backfill, "_persist_operation_maintenance", fail_after_wiki_commit)
    with pytest.raises(RuntimeError, match="before_run_summary"):
        apply(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)
    with db.connect() as connection:
        operation = connection.execute("SELECT state,maintenance_json FROM metadata_backfill_operations WHERE run_id=?", (run_id,)).fetchone()
        intent = connection.execute("SELECT state,after_version FROM metadata_backfill_wiki_intents WHERE run_id=?", (run_id,)).fetchone()
        dependency = connection.execute("SELECT source_revision FROM assistant_wiki_dependencies WHERE page_id=? AND video_id=?", (page_id, video_ids[0][0])).fetchone()
    assert operation["state"] == "applied" and operation["maintenance_json"] == "{}"
    assert intent["state"] == "rebound" and intent["after_version"] == 2
    assert dependency["source_revision"] != captured[0].revision

    monkeypatch.setattr(backfill, "_persist_operation_maintenance", original_persist)
    assert apply(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)["counts"] == {"already_applied": 1}
    with db.connect() as connection:
        operation = connection.execute("SELECT maintenance_json FROM metadata_backfill_operations WHERE run_id=?", (run_id,)).fetchone()
        intent_id = int(connection.execute("SELECT id FROM metadata_backfill_wiki_intents WHERE run_id=?", (run_id,)).fetchone()["id"])
    assert json.loads(operation["maintenance_json"])["wiki_rebound_pages"][0]["intent_id"] == intent_id
    assert rollback(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)["counts"] == {"rolled_back": 1}
    with db.connect() as connection:
        assert connection.execute("SELECT published_at FROM videos WHERE id=?", (video_ids[0][0],)).fetchone()["published_at"] is None
        assert connection.execute("SELECT source_revision FROM assistant_wiki_dependencies WHERE page_id=? AND video_id=?", (page_id, video_ids[0][0])).fetchone()["source_revision"] == captured[0].revision


def test_shared_page_rolls_back_video_rebinds_in_reverse_order(tmp_path):
    db, video_ids, candidates, object_root, videos_dir, page_id, captured = _source_fixture(tmp_path, count=2)
    run_id = "shared-page-lifo"
    stage(db.path, run_id, candidates)
    assert apply(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)["counts"] == {"applied": 2}
    with db.connect() as connection:
        assert connection.execute("SELECT version FROM assistant_wiki_pages WHERE id=?", (page_id,)).fetchone()["version"] == 3
    assert rollback(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)["counts"] == {"rolled_back": 2}
    with db.connect() as connection:
        page_version = connection.execute("SELECT version FROM assistant_wiki_pages WHERE id=?", (page_id,)).fetchone()["version"]
        deps = {int(row["video_id"]): str(row["source_revision"]) for row in connection.execute("SELECT video_id,source_revision FROM assistant_wiki_materials WHERE page_id=?", (page_id,))}
        holds = connection.execute("SELECT count(*) n FROM metadata_backfill_job_holds").fetchone()["n"]
    assert page_version == 5
    assert deps == {video_ids[i][0]: captured[i].revision for i in range(2)}
    assert holds == 0


def test_rollback_resumes_after_reverse_wiki_commit(tmp_path, monkeypatch):
    db, video_ids, candidates, object_root, videos_dir, page_id, _captured = _source_fixture(tmp_path)
    run_id = "rollback-rebind-cut"
    stage(db.path, run_id, candidates)
    assert apply(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)["counts"] == {"applied": 1}
    original_maintain = backfill._maintain_existing_source
    failed = False

    def fail_after_reverse_commit(database, current_run, video_id, old_revision, **kwargs):
        nonlocal failed
        result = original_maintain(database, current_run, video_id, old_revision, **kwargs)
        if kwargs.get("job_tag") == run_id + "-rollback" and not failed:
            failed = True
            raise RuntimeError("injected_after_reverse_page_commit")
        return result

    monkeypatch.setattr(backfill, "_maintain_existing_source", fail_after_reverse_commit)
    with pytest.raises(RuntimeError, match="after_reverse_page_commit"):
        rollback(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)
    with db.connect() as connection:
        operation = connection.execute("SELECT state FROM metadata_backfill_operations WHERE run_id=?", (run_id,)).fetchone()
        page_version = connection.execute("SELECT version FROM assistant_wiki_pages WHERE id=?", (page_id,)).fetchone()["version"]
    assert operation["state"] == "rollback_pending"
    assert page_version == 3

    monkeypatch.setattr(backfill, "_maintain_existing_source", original_maintain)
    assert rollback(db.path, run_id, assistant_objects_root=object_root, videos_dir=videos_dir)["counts"] == {"rolled_back": 1}
    with db.connect() as connection:
        assert connection.execute("SELECT state FROM metadata_backfill_operations WHERE run_id=?", (run_id,)).fetchone()["state"] == "rolled_back"
        assert connection.execute("SELECT count(*) n FROM metadata_backfill_job_holds").fetchone()["n"] == 0


def test_year_bearing_wiki_stays_deferred_without_model_work(tmp_path, monkeypatch):
    db, video_ids, candidates, object_root, videos_dir, page_id, captured = _source_fixture(tmp_path, wiki_year=True)
    stage(db.path, "year-page", candidates)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("year-bearing page must not be rebound or sent to a model")

    monkeypatch.setattr(backfill, "_rebind_with_backfill_intent", forbidden)
    result = apply(db.path, "year-page", assistant_objects_root=object_root, videos_dir=videos_dir)
    assert result["counts"] == {"applied": 1}
    with db.connect() as connection:
        operation = connection.execute("SELECT maintenance_json FROM metadata_backfill_operations WHERE run_id='year-page'").fetchone()
        dep = connection.execute("SELECT source_revision FROM assistant_wiki_dependencies WHERE page_id=? AND video_id=?", (page_id, video_ids[0][0])).fetchone()
        models = connection.execute("SELECT count(*) n FROM assistant_jobs WHERE kind IN ('source_extract','wiki_integrate') AND status IN ('queued','running')").fetchone()["n"]
    evidence = json.loads(operation["maintenance_json"])
    assert evidence["wiki_deferred_pages"] == [page_id]
    assert dep["source_revision"] == captured[0].revision
    assert models == 0
