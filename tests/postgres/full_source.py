"""Full-table synthetic input, distinct from the frozen W04 semantic closure."""

from __future__ import annotations
from datetime import date, datetime
from contextlib import closing
import json
import hashlib
from pathlib import Path
import sqlite3
import uuid

import psycopg
from psycopg import sql

from shiliu.config import LIBPQ_DISABLED_PASSFILE, load_postgres_config
from shiliu.migration.safety import TASK_ROOT
from seed_rows import SyntheticGraph, MAPPING
from schema_support import formal_target


def make_full_source(*, event_count=1105, package_locators=False):
    root = TASK_ROOT / "sources" / ("w04_" + uuid.uuid4().hex[:12])
    root.mkdir(mode=0o700, parents=True)
    (root / "files").mkdir(mode=0o700)
    (root / "synthetic.json").write_text(
        json.dumps({"task": "shiliu-w01-20261023", "synthetic_only": True})
    )
    artifacts = []
    schema = json.loads(
        Path("tests/fixtures/postgres_migration/schema26.json").read_text()
    )["databases"]["main"]
    path = root / "source.sqlite3"
    with formal_target(load_postgres_config()) as (_, admin):
        with (
            psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as pg,
            closing(sqlite3.connect(path)) as source,
        ):
            from psycopg.rows import dict_row

            pg.row_factory = dict_row
            graph = SyntheticGraph(
                pg, overrides={"research_results": {"attempt_id": "required-closure"}}
            )
            for name, t in MAPPING["tables"].items():
                if t["source"]:
                    graph.ensure(name)
            from shiliu.assistant.snapshots import _json_hash
            from shiliu.evidence.source import (
                make_source_artifact_id,
                make_segment_id,
                make_timeline_run_id,
            )
            from shiliu.evidence.contracts import SourceArtifactReference

            raw_bytes = b'[{"from":0,"to":1,"content":"synthetic full-table evidence"}]'
            raw_version = hashlib.sha256(raw_bytes).hexdigest()
            old_revision = graph.rows["assistant_source_revisions"]["revision"]
            metadata = {"id": 1, "title": graph.rows["videos"]["title"]}
            metadata_hash = _json_hash(metadata)
            content_hash = _json_hash(
                {
                    "material_hashes": {"subtitle": raw_version},
                    "notes": [],
                    "active_revision": graph.rows["videos"]["active_revision"],
                }
            )
            membership_hash = _json_hash([{"source_id": 1}])
            revision = _json_hash(
                {
                    "metadata_hash": metadata_hash,
                    "content_hash": content_hash,
                    "membership_hash": membership_hash,
                    "extractor_version": "assistant-source-v1",
                }
            )
            snapshot = {
                "schema": "assistant-source-snapshot-v1",
                "revision": revision,
                "metadata": metadata,
                "metadata_hash": metadata_hash,
                "content_hash": content_hash,
                "membership_hash": membership_hash,
                "coverage": "subtitle",
                "memberships": [],
                "materials": {"subtitle": "synthetic full-table evidence"},
                "material_hashes": {"subtitle": raw_version},
                "notes": [],
            }
            artifact_id = make_source_artifact_id(
                SourceArtifactReference(
                    graph.rows["videos"]["platform"],
                    graph.rows["videos"]["source_id"],
                    graph.rows["videos"]["part"],
                    "human",
                    "zh",
                    "synthetic",
                )
            )

            def file(payload, logical, version, reference=None):
                digest = hashlib.sha256(payload).hexdigest()
                name = "files/" + digest + ".json"
                (root / name).write_bytes(payload)
                value = dict(
                    source_file=name,
                    sha256=digest,
                    byte_size=len(payload),
                    relative_key="personal:local_operator/objects/" + digest,
                    media_type="application/json",
                    version_id="synthetic_full_" + str(len(artifacts)),
                    video_id=1,
                    logical_key=logical,
                    source_version=version,
                    is_head=True,
                    created_at="2026-10-23T00:00:00+00:00",
                )
                if reference:
                    value["source_reference"] = reference
                artifacts.append(value)
                return name

            raw_file = file(raw_bytes, "video:1:subtitle-raw.json", raw_version)
            snapshot_file = file(
                json.dumps(
                    snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode(),
                "source_snapshot:" + revision,
                revision,
            )
            export_reference = graph.rows["research_knowledge_exports"]["relative_path"]
            taxonomy_bytes = b'{"synthetic_taxonomy":true}'
            taxonomy_file = file(
                taxonomy_bytes,
                "synthetic-taxonomy-output",
                hashlib.sha256(taxonomy_bytes).hexdigest(),
            )
            export_file = file(
                b"synthetic knowledge export",
                "research-export:"
                + graph.rows["research_knowledge_exports"]["export_id"],
                "synthetic-export-v1",
                export_reference,
            )
            for obj in schema:
                if (
                    obj["type"] == "table"
                    and obj.get("table_kind") != "shadow"
                    and obj["name"] != "sqlite_sequence"
                ):
                    source.execute(obj["sql"])
            for name, t in MAPPING["tables"].items():
                if not t["source"]:
                    continue
                source_columns = {c["name"] for c in t["source"]["columns"]}
                for row in pg.execute(
                    sql.SQL("SELECT * FROM shiliu.{}").format(sql.Identifier(name))
                ):
                    data = {k: v for k, v in row.items() if k in source_columns}
                    for key, value in data.items():
                        if isinstance(value, str) and value == old_revision:
                            data[key] = revision
                    if name in {"assistant_source_heads", "assistant_source_revisions"}:
                        data.update(
                            metadata_hash=metadata_hash,
                            content_hash=content_hash,
                            membership_hash=membership_hash,
                        )
                    if name == "videos":
                        data.update(
                            raw_subtitle_path=raw_file,
                            subtitle_source="human",
                            subtitle_language="zh",
                        )
                    if name == "assistant_source_revisions":
                        data["snapshot_ref"] = snapshot_file
                    if name == "taxonomy_stage_runs":
                        data.update(
                            output_path=taxonomy_file,
                            output_hash=hashlib.sha256(taxonomy_bytes).hexdigest(),
                        )
                    if name == "research_knowledge_exports" and package_locators:
                        data["relative_path"] = str(root / export_file)
                    if name == "research_evidence_identities":
                        data["source_version"] = raw_version
                    if name == "research_evidence_identities":
                        data.update(
                            source_artifact_id=artifact_id,
                            timeline_run_id=make_timeline_run_id(raw_version, 0),
                            segment_ids_json=[
                                make_segment_id(artifact_id, raw_version, 0)
                            ],
                            segment_ordinals_json=[0],
                        )
                    for k, v in data.items():
                        if t["columns"][k]["type"] == "jsonb":
                            data[k] = (
                                None if v is None else json.dumps(v, ensure_ascii=False)
                            )
                        elif isinstance(v, (date, datetime)):
                            data[k] = v.isoformat()
                        elif isinstance(v, bool):
                            data[k] = int(v)
                    source.execute(
                        'INSERT INTO "'
                        + name
                        + '" ('
                        + ",".join('"' + k + '"' for k in data)
                        + ") VALUES ("
                        + ",".join("?" for _ in data)
                        + ")",
                        list(data.values()),
                    )
            source.row_factory = sqlite3.Row
            event = dict(source.execute("SELECT * FROM events LIMIT 1").fetchone())
            for i in range(2, event_count + 1):
                data = dict(event, id=i)
                source.execute(
                    "INSERT INTO events ("
                    + ",".join('"' + k + '"' for k in data)
                    + ") VALUES ("
                    + ",".join("?" for _ in data)
                    + ")",
                    list(data.values()),
                )
            source.execute(
                "INSERT INTO schema_meta(key,value) VALUES ('schema_version','26')"
            )
            for obj in schema:
                if obj["type"] in {"index", "trigger"} and obj["sql"]:
                    source.execute(obj["sql"])
            assert not source.execute("PRAGMA foreign_key_check").fetchall()
            source.commit()
    (root / "artifacts.json").write_text(
        json.dumps(artifacts, ensure_ascii=False, indent=2)
    )
    return path
