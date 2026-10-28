"""W14 full-table and multi-batch contracts on the real isolated server."""

from shiliu.config import LIBPQ_DISABLED_PASSFILE, load_postgres_config
from shiliu.migration.etl import import_snapshot
from shiliu.migration.snapshot import inspect_snapshot, mapping
from shiliu.migration.values import MigrationRejected
from full_source import make_full_source
from schema_support import formal_target
from test_etl import target_etl
import psycopg
import pytest


def test_all_formal_tables_and_bounded_batches_resume():
    source = make_full_source()
    identity, raw = inspect_snapshot(source)
    assert set(raw) == {n for n, t in mapping()["tables"].items() if t["source"]}
    assert len(raw["events"]) == 1105
    sizes = [len(batch) for batch in raw["events"].batches()]
    assert sizes == [128] * 8 + [81]
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        with pytest.raises(MigrationRejected, match="injected_import_interruption"):
            import_snapshot(source, target, "w04_full", _fault_after_batches=12)
        report = import_snapshot(source, target, "w04_full")
        assert report["counts"]["events"] == 1105
        assert import_snapshot(source, target, "w04_full") == report
        with psycopg.connect(
            admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE
        ) as conn:
            assert conn.execute(
                "SELECT count(*),max(input_rows),sum(input_rows) FROM shiliu.migration_batches WHERE table_name='events'"
            ).fetchone() == (9, 128, 1105)


def test_explicit_second_owner_keeps_closed_graph_and_artifact_namespace():
    import json
    import sqlite3
    from poc_source import make_source
    from test_etl import clone_source

    source = clone_source(make_source())
    # Construct a second-owner synthetic input. Preserve/reinstall its frozen
    # triggers; the importer never disables either source or target protection.
    with sqlite3.connect(source) as conn:
        triggers = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        for name, _ in triggers:
            conn.execute('DROP TRIGGER "' + name + '"')
        for name, t in mapping()["tables"].items():
            if t["source"] and any(
                c["name"] == "principal_id" for c in t["source"]["columns"]
            ):
                conn.execute(
                    'UPDATE "' + name + '" SET principal_id=?', ("second_owner",)
                )
        for _, ddl in triggers:
            conn.execute(ddl)
    (source.parent / "ownership.json").write_text(
        json.dumps(
            {
                "default_principal": "second_owner",
                "principals": {"second_owner": "personal:second_owner"},
            }
        )
    )
    artifacts = json.loads((source.parent / "artifacts.json").read_text())
    for artifact in artifacts:
        artifact["relative_key"] = artifact["relative_key"].replace(
            "personal:local_operator/", "personal:second_owner/"
        )
    (source.parent / "artifacts.json").write_text(json.dumps(artifacts))
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        report = import_snapshot(source, target, "w04_second_owner")
        assert report["counts"]["assistant_memories"] == 4
        with psycopg.connect(
            admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE
        ) as conn:
            assert conn.execute(
                "SELECT DISTINCT workspace_id,principal_id FROM shiliu.assistant_memories"
            ).fetchall() == [("personal:second_owner", "second_owner")]
            assert conn.execute(
                "SELECT DISTINCT workspace_id FROM shiliu.artifact_objects"
            ).fetchall() == [("personal:second_owner",)]
            assert conn.execute(
                "SELECT membership_highwater FROM shiliu.workspace_guards WHERE workspace_id='personal:second_owner'"
            ).fetchone() == (20,)


def test_unmapped_owner_and_artifact_workspace_are_rejected_before_target():
    import json
    from poc_source import make_source
    from test_etl import clone_source
    from shiliu.migration.snapshot import plan_snapshot

    source = clone_source(make_source())
    (source.parent / "ownership.json").write_text(
        json.dumps(
            {
                "default_principal": "second_owner",
                "principals": {"second_owner": "personal:second_owner"},
            }
        )
    )
    artifacts = json.loads((source.parent / "artifacts.json").read_text())
    for artifact in artifacts:
        artifact["relative_key"] = artifact["relative_key"].replace(
            "personal:local_operator/", "personal:second_owner/"
        )
    (source.parent / "artifacts.json").write_text(json.dumps(artifacts))
    with pytest.raises(MigrationRejected, match="explicit_principal_mapping_required"):
        plan_snapshot(source)
    # Source principals remain local_operator, while file manifest claims a
    # second owner's physical namespace: reject, never move it by inference.
    (source.parent / "ownership.json").unlink()
    artifacts = json.loads((source.parent / "artifacts.json").read_text())
    artifacts[0]["relative_key"] = artifacts[0]["relative_key"].replace(
        "personal:local_operator/", "personal:second_owner/"
    )
    (source.parent / "artifacts.json").write_text(json.dumps(artifacts))
    with pytest.raises(MigrationRejected, match="artifact_workspace_key_mismatch"):
        plan_snapshot(source)


def test_immutable_parent_in_later_pk_batch_is_imported_first():
    import sqlite3
    from poc_source import make_source

    source = make_source()
    with sqlite3.connect(source) as conn:
        conn.row_factory = sqlite3.Row
        base = dict(
            conn.execute("SELECT * FROM research_fact_revisions LIMIT 1").fetchone()
        )
        # All children sort before their shared parent, which is in batch two.
        # They are immutable; importing NULL then UPDATE is not an option.
        parent = dict(
            base,
            fact_revision_id="zz_synthetic_parent",
            revision=1000,
            parent_revision_id=None,
            supersedes_revision_id=None,
        )

        def put(row):
            conn.execute(
                "INSERT INTO research_fact_revisions ("
                + ",".join('"' + k + '"' for k in row)
                + ") VALUES ("
                + ",".join("?" for _ in row)
                + ")",
                list(row.values()),
            )

        put(parent)
        for i in range(130):
            put(
                dict(
                    base,
                    fact_revision_id=f"aa_synthetic_child_{i:03}",
                    revision=1001 + i,
                    parent_revision_id=parent["fact_revision_id"],
                    supersedes_revision_id=None,
                )
            )
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        result = import_snapshot(source, target, "w04_parent_order")
        assert result["counts"]["research_fact_revisions"] == 133
        with psycopg.connect(
            admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE
        ) as conn:
            assert conn.execute(
                "SELECT count(*) FROM shiliu.research_fact_revisions WHERE parent_revision_id='zz_synthetic_parent'"
            ).fetchone() == (130,)
            assert conn.execute(
                "SELECT count(*) FROM shiliu.migration_batches WHERE table_name='research_fact_revisions'"
            ).fetchone() == (2,)


@pytest.mark.parametrize("version", [24, 25])
def test_old_schema_normalization_only_writes_a_new_synthetic_package(version):
    import json
    import sqlite3
    import uuid
    from poc_source import make_source
    from shiliu.migration.normalize import normalize_package
    from shiliu.migration.safety import TASK_ROOT
    from shiliu.migration.snapshot import sha

    source = make_source()
    with sqlite3.connect(source) as c:
        c.execute("ALTER TABLE assistant_threads DROP COLUMN context_state_json")
        c.execute("ALTER TABLE assistant_task_notes DROP COLUMN checkpoint_json")
        if version == 24:
            c.execute("DROP TABLE assistant_wiki_materials")
        c.execute(
            "UPDATE schema_meta SET value=? WHERE key='schema_version'", (str(version),)
        )
    before = sha(source)
    destination = TASK_ROOT / "sources" / ("w14_normalized_" + uuid.uuid4().hex[:10])
    normalized, evidence = normalize_package(source, destination)
    assert (
        sha(source) == before
        and evidence["source_schema"] == version
        and evidence["synthetic_only"]
    )
    with sqlite3.connect(normalized) as c:
        assert c.execute(
            "SELECT context_state_json FROM assistant_threads"
        ).fetchone() == ("{}",)
        assert c.execute(
            "SELECT checkpoint_json FROM assistant_task_notes"
        ).fetchone() == ("{}",)
        assert (
            c.execute("SELECT count(*) FROM assistant_wiki_materials").fetchone()[0]
            >= 1
        )
    with formal_target(load_postgres_config()) as (runtime, admin):
        report = import_snapshot(normalized, target_etl(runtime), "w14_normalized")
        assert report["counts"]["assistant_messages"] == 2
    assert json.loads((destination / "normalization.json").read_text()) == evidence


def test_imported_current_ref_reads_exact_historical_citation_bytes():
    import json
    import sqlite3
    from poc_source import make_source
    from shiliu.artifacts import ArtifactStore
    from shiliu.db import Database
    from shiliu.storage.postgres import PgDatabase
    from shiliu.storage.scope import personal_context
    from shiliu.storage.artifacts import artifact_version_id
    from shiliu.evidence.source import load_source_artifact
    from shiliu.evidence.contracts import SourceArtifactReference
    from shiliu.assistant.snapshots import SourceSnapshotStore

    source = make_source()
    artifacts = json.loads((source.parent / "artifacts.json").read_text())
    for item in list(artifacts):
        if item["logical_key"] == "subtitle:1":
            logical = "video:1:subtitle-raw.json"
            artifacts.append(
                dict(
                    item,
                    logical_key=logical,
                    version_id=artifact_version_id(
                        "personal:local_operator", logical, item["source_version"]
                    ),
                )
            )
    current = next(
        a
        for a in artifacts
        if a["logical_key"] == "video:1:subtitle-raw.json" and a["is_head"]
    )
    old = next(
        a
        for a in artifacts
        if a["logical_key"] == "video:1:subtitle-raw.json" and not a["is_head"]
    )
    (source.parent / "artifacts.json").write_text(json.dumps(artifacts))
    with sqlite3.connect(source) as c:
        c.execute(
            "UPDATE videos SET raw_subtitle_path=?,subtitle_source='human',subtitle_language='zh' WHERE id=1",
            (current["source_file"],),
        )
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        report = import_snapshot(source, target, "w14_raw_history")
        assert report["artifacts_verified"] == 5
        with PgDatabase(runtime) as pg:
            db = Database(pg, personal_context())
            store = ArtifactStore(target.artifact_root, db)
            video = db.get_video(1)
            assert video["raw_subtitle_path"].startswith("artifact:")
            reference = SourceArtifactReference(
                video["platform"],
                video["source_id"],
                video["part"],
                "human",
                "zh",
                video["raw_subtitle_path"],
            )
            parsed = load_source_artifact(
                reference,
                artifacts=store,
                expected_source_version=old["source_version"],
            )
            assert parsed.source_version == old["source_version"]
            assert (
                store.raw_bytes(
                    video["raw_subtitle_path"],
                    expected_source_version=old["source_version"],
                )
                == (source.parent / old["source_file"]).read_bytes()
            )
            assert (
                store.raw_bytes(video["raw_subtitle_path"])
                == (source.parent / current["source_file"]).read_bytes()
            )
            snapshot = next(
                a for a in artifacts if a["logical_key"].startswith("source_snapshot:")
            )
            captured = SourceSnapshotStore(db, store).load(
                1, snapshot["source_version"]
            )
            assert captured.snapshot["revision"] == snapshot["source_version"]


def test_missing_referenced_raw_version_is_rejected_before_import():
    import json
    from poc_source import make_source

    source = make_source()
    artifacts = json.loads((source.parent / "artifacts.json").read_text())
    (source.parent / "artifacts.json").write_text(
        json.dumps([a for a in artifacts if a["is_head"]])
    )
    with pytest.raises(
        MigrationRejected, match="historical_source_version_bytes_missing"
    ):
        inspect_snapshot(source)
