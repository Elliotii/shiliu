"""Native backfill: held scheduling, atomic provenance and guarded rollback.

Port the effective tests/test_metadata_backfill.py contracts. SQLite backup
fixtures are replaced with a PG target fingerprint; no backup drill is run.
"""

from datetime import datetime, timezone
import pytest
from psycopg.types.json import Jsonb
from shiliu.metadata_backfill import MetadataBackfillService
from shiliu.assistant.pg_store import PgAssistantRunStore
from shiliu.artifacts import ArtifactStore
from shiliu.domain import FavoriteItem


def candidate(vid, bvid="BV1234567890"):
    return dict(
        video_id=vid,
        bvid=bvid,
        platform="bilibili",
        part=1,
        source_field="info.pubdate",
        raw_pubdate=1600000000,
        published_at=1600000000,
        metadata_observed_at=datetime.fromtimestamp(
            1700000000, timezone.utc
        ).isoformat(),
        source="synthetic",
    )


def fixture(db, tmp_path, count=1, *, source=False, year=False):
    sid = db.create_favorite_source(
        folder_id=321, folder_title="synthetic", account_id=32958899
    )
    items = [
        FavoriteItem(bvid=f"BV123456789{i}", title=f"fixture {i}", favorite_time=100)
        for i in range(count)
    ]
    db.record_source_snapshot(sid, items, processing_profile="formal")
    vids = [db.get_video_by_source(i.bvid)["id"] for i in items]
    store = PgAssistantRunStore(db)
    space = store.create_space(
        name="backfill", source_ids=[sid], maintenance_mode="automatic"
    )
    artifacts = ArtifactStore(tmp_path / "backfill", db)
    service = MetadataBackfillService(db, artifacts)
    captured = []
    if source:
        for vid in vids:
            value = service.sources.snapshots.capture(vid)
            captured.append(value)
            card = dict(
                title="fixture",
                uploader="",
                published_at=None,
                memberships=value.snapshot["memberships"],
                coverage="metadata_only",
                material_kind="metadata_only",
                summary="Safe summary.",
                key_points=[],
                topics=["fixture"],
                limitations=[],
            )
            service.wiki._commit_source_card(
                value,
                input_hash=service.wiki._card_input_hash(value.snapshot),
                card=card,
            )
        refs = [v.revision for v in captured]
        blocks = [
            dict(
                stable_id="block",
                heading="fixture",
                markdown="In 2024 needs review." if year else "Stable statement.",
                applicability="fixture",
                assessment="source_reported",
                speaker="",
                source_refs=refs,
            )
        ]
        with db.connect(guard=True) as c:
            c.execute(
                "INSERT INTO assistant_wiki_pages(workspace_id,id,principal_id,space_id,normalized_title,title,aliases_json,page_type,summary,blocks_json,version,status,scope_version,created_at,updated_at) VALUES(%s,'backfill-page',%s,%s,'fixture','fixture','[]','topic','Safe summary.',%s,1,'active',1,clock_timestamp(),clock_timestamp())",
                (db.workspace_id, db.context.user_id, space["id"], Jsonb(blocks)),
            )
            for vid, value in zip(vids, captured):
                c.execute(
                    "INSERT INTO assistant_wiki_dependencies(workspace_id,page_id,block_id,source_revision,video_id,dependency_kind,created_at) VALUES(%s,'backfill-page','block',%s,%s,'source',clock_timestamp())",
                    (db.workspace_id, value.revision, vid),
                )
                c.execute(
                    "INSERT INTO assistant_wiki_materials(workspace_id,page_id,video_id,source_revision,relation,status,created_at,updated_at) VALUES(%s,'backfill-page',%s,%s,'supports_block','integrated',clock_timestamp(),clock_timestamp())",
                    (db.workspace_id, vid, value.revision),
                )
    return service, [candidate(v, i.bvid) for v, i in zip(vids, items)], captured


def test_stage_apply_resume_hold_and_rollback(collection_db, tmp_path):
    service, cs, _ = fixture(collection_db, tmp_path)
    assert service.dry_run(cs)["states"][0]["state"] == "ready"
    service.stage("basic", cs)
    assert service.apply("basic")["counts"] == {"applied": 1}
    assert service.apply("basic")["counts"] == {"already_applied": 1}
    assert service.store.claim_job(owner="normal", allow_model_jobs=True) is None
    with collection_db.connect(read_only=True) as c:
        assert (
            c.execute("SELECT count(*) n FROM metadata_backfill_job_holds").fetchone()[
                "n"
            ]
            == 1
        )
    assert service.rollback("basic")["counts"] == {"rolled_back": 1}
    assert collection_db.get_video(cs[0]["video_id"])["published_at"] is None


def test_atomic_apply_failure_and_later_edit_blocks_rollback(collection_db, tmp_path):
    service, cs, _ = fixture(collection_db, tmp_path)
    service.stage("failure", cs)

    def fail(point):
        if point == "after_metadata_update":
            raise RuntimeError("synthetic cut")

    service.fault_injector = fail
    with pytest.raises(RuntimeError):
        service.apply("failure")
    assert collection_db.get_video(cs[0]["video_id"])["published_at"] is None
    with collection_db.connect(read_only=True) as c:
        assert (
            c.execute("SELECT count(*) n FROM metadata_backfill_job_holds").fetchone()[
                "n"
            ]
            == 0
        )
    service.fault_injector = lambda point: None
    service.apply("failure")
    collection_db.update_video(cs[0]["video_id"], title="later edit", published_at=None)
    with collection_db.connect(guard=True) as c:
        c.execute(
            "UPDATE videos SET updated_at='2099-01-01' WHERE id=%s",
            (cs[0]["video_id"],),
        )
    assert service.rollback("failure")["counts"] == {"rollback_conflict": 1}
    assert collection_db.get_video(cs[0]["video_id"])["published_at"] == 1600000000


def test_wiki_commit_cut_reentry_and_shared_page_lifo(collection_db, tmp_path):
    service, cs, old = fixture(collection_db, tmp_path, 2, source=True)
    service.stage("wiki", cs)

    def fail(point):
        if point == "after_wiki_commit_before_operation_summary":
            raise RuntimeError("after page commit")

    service.fault_injector = fail
    with pytest.raises(RuntimeError, match="after page commit"):
        service.apply("wiki")
    with collection_db.connect(read_only=True) as c:
        op = c.execute(
            "SELECT * FROM metadata_backfill_operations WHERE video_id=%s",
            (cs[0]["video_id"],),
        ).fetchone()
        assert op["state"] == "applied" and op["maintenance_json"] == {}
        assert (
            c.execute(
                "SELECT version FROM assistant_wiki_pages WHERE id='backfill-page'"
            ).fetchone()["version"]
            == 2
        )
        assert (
            c.execute("SELECT state FROM metadata_backfill_wiki_intents").fetchone()[
                "state"
            ]
            == "rebound"
        )
    service.fault_injector = lambda point: None
    assert service.apply("wiki")["counts"] == {"already_applied": 1, "applied": 1}
    assert service.rollback("wiki")["counts"] == {"rolled_back": 2}
    with collection_db.connect(read_only=True) as c:
        assert (
            c.execute(
                "SELECT version FROM assistant_wiki_pages WHERE id='backfill-page'"
            ).fetchone()["version"]
            == 5
        )
        assert (
            c.execute("SELECT count(*) n FROM metadata_backfill_job_holds").fetchone()[
                "n"
            ]
            == 0
        )
        assert {
            r["source_revision"]
            for r in c.execute("SELECT source_revision FROM assistant_wiki_materials")
        } == {s.revision for s in old}


def test_year_page_deferred_held_and_no_dispatch(collection_db, tmp_path):
    service, cs, old = fixture(collection_db, tmp_path, source=True, year=True)
    service.stage("year", cs)
    service.apply("year")
    with collection_db.connect(read_only=True) as c:
        op = c.execute(
            "SELECT maintenance_json FROM metadata_backfill_operations"
        ).fetchone()["maintenance_json"]
        assert op["wiki_deferred_pages"] == ["backfill-page"]
        assert (
            c.execute(
                "SELECT source_revision FROM assistant_wiki_dependencies"
            ).fetchone()["source_revision"]
            == old[0].revision
        )
        assert (
            c.execute("SELECT count(*) n FROM model_dispatch_receipts").fetchone()["n"]
            == 0
        )
    assert service.store.claim_job(owner="normal", allow_model_jobs=True) is None


def test_shared_model_lane_defers_rebind_and_rollback_resumes_commit_cut(
    collection_db, tmp_path
):
    service, cs, old = fixture(collection_db, tmp_path, source=True)
    service.stage("lane", cs)
    with collection_db.connect(guard=True) as c:
        other = service.store.enqueue_job(
            c, kind="wiki_integrate", dedupe_key="other-lane-owner", payload={}
        )
    claimed = service.store.claim_job(
        owner="other-owner", allow_model_jobs=True, kinds=["wiki_integrate"]
    )
    assert claimed["id"] == other
    service.apply("lane")
    with collection_db.connect(read_only=True) as c:
        assert (
            c.execute(
                "SELECT version FROM assistant_wiki_pages WHERE id='backfill-page'"
            ).fetchone()["version"]
            == 1
        )
        assert (
            c.execute("SELECT state FROM metadata_backfill_wiki_intents").fetchone()[
                "state"
            ]
            == "pending"
        )
    service.store.finish_job(
        other, owner="other-owner", lease_epoch=claimed["lease_epoch"]
    )
    service.apply("lane")

    def cut(point):
        if point == "after_wiki_commit_before_operation_summary":
            raise RuntimeError("reverse page committed")

    service.fault_injector = cut
    with pytest.raises(RuntimeError, match="reverse page committed"):
        service.rollback("lane")
    with collection_db.connect(read_only=True) as c:
        assert (
            c.execute("SELECT state FROM metadata_backfill_operations").fetchone()[
                "state"
            ]
            == "rollback_pending"
        )
        assert (
            c.execute(
                "SELECT version FROM assistant_wiki_pages WHERE id='backfill-page'"
            ).fetchone()["version"]
            == 3
        )
    service.fault_injector = lambda point: None
    assert service.rollback("lane")["counts"] == {"rolled_back": 1}
    with collection_db.connect(read_only=True) as c:
        assert (
            c.execute("SELECT count(*) n FROM metadata_backfill_job_holds").fetchone()[
                "n"
            ]
            == 0
        )
        assert (
            c.execute(
                "SELECT source_revision FROM assistant_wiki_materials"
            ).fetchone()["source_revision"]
            == old[0].revision
        )


def test_production_gate_verifies_explicit_pg_target_manifest(
    collection_db, tmp_path, monkeypatch
):
    from dataclasses import replace
    from psycopg.conninfo import conninfo_to_dict
    import hashlib, json
    from shiliu.metadata_backfill import _candidate_hash

    service, cs, _ = fixture(collection_db, tmp_path)
    monkeypatch.setattr(
        collection_db.pg,
        "config",
        replace(collection_db.pg.config, environment="production"),
    )
    with pytest.raises(ValueError, match="production_backup_manifest_required"):
        service.stage("gated", cs)
    target = conninfo_to_dict(collection_db.pg.config.database_url)
    identity = {key: target.get(key) for key in ("host", "port", "dbname", "user")}
    identity["workspace_id"] = collection_db.workspace_id
    manifest = {
        "service_stop": "synthetic-contract-only",
        "target_fingerprint": _candidate_hash(identity),
    }
    for name in ("postgres_backup", "artifact_manifest"):
        path = tmp_path / name
        path.write_bytes(b"synthetic gate fixture; no backup or restore exercise")
        manifest[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    assert service.stage("gated", cs, production_backup_manifest=path)["count"] == 1
    manifest["postgres_backup"]["sha256"] = "0" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="production_backup_hash_mismatch"):
        service.apply("gated", production_backup_manifest=path)
