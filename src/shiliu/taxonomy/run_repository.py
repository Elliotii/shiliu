from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from shiliu.db import Database, utc_now, collection_dto
from psycopg.types.json import Jsonb


class TaxonomyRunRepository:
    """Persistence boundary for resumable corpus-level taxonomy work."""

    def __init__(self, db: Database, artifacts, output_root: Path) -> None:
        self.db = db
        self.artifacts = artifacts
        self.output_root = Path(output_root).absolute()
        self.output_root.mkdir(parents=True, exist_ok=True)

    def _stage_dto(self, row):
        value = collection_dto(row)
        if value.get("output_path"):
            ref = value["output_path"]
            if not ref.startswith("artifact:"):
                raise ValueError("taxonomy_output_manifest_required")
            value["output_ref"] = ref
            value["output_path"] = str(self.artifacts.managed_file(ref))
        return value

    def _output_bytes(self, value):
        if value.startswith("artifact:"):
            return self.artifacts.read_bytes(value)
        path = Path(value).absolute()
        if (
            not path.is_relative_to(self.output_root)
            or path.is_symlink()
            or path.resolve() != path
            or not path.is_file()
        ):
            raise ValueError("taxonomy_output_outside_preparation_root")
        return path.read_bytes()

    def complete_stage(
        self, run_id, stage_name, unit_key, *, output_path, output_hash, audit=None
    ):
        raw = self._output_bytes(output_path)

        def publish(conn, descriptor):
            stage = conn.execute(
                "SELECT * FROM shiliu.taxonomy_stage_runs WHERE workspace_id=%s AND run_id=%s AND stage_name=%s AND unit_key=%s FOR UPDATE",
                (self.db.workspace_id, run_id, stage_name, unit_key),
            ).fetchone()
            if stage is None:
                raise KeyError((run_id, stage_name, unit_key))
            ref = self.artifacts.objects.publish(
                conn,
                f"taxonomy:{run_id}:{stage_name}:{unit_key}:output",
                descriptor.sha256,
                descriptor,
            )
            self._complete_stage(
                run_id,
                stage_name,
                unit_key,
                output_path=ref,
                output_hash=output_hash,
                audit=audit,
                conn=conn,
            )

        self.artifacts.objects.publish_bytes(raw, "taxonomy", output_hash, publish)

    def create_run(
        self,
        *,
        snapshot_id: int,
        run_kind: str,
        engine: str,
        engine_version: str,
        parameters: dict[str, Any],
    ) -> int:
        now = utc_now()
        with self.db.connect(guard=True) as connection:
            cursor = connection.execute(
                """
                INSERT INTO taxonomy_runs(
                    workspace_id, run_kind, status, current_stage, corpus_snapshot_id,
                    engine, engine_version, parameters_json, search_enabled,
                    created_at, updated_at
                ) VALUES(%s, %s, 'pending', NULL, %s, %s, %s, %s, false, %s, %s) RETURNING id
                """,
                (
                    self.db.workspace_id,
                    run_kind,
                    snapshot_id,
                    engine,
                    engine_version,
                    _compact_json(parameters),
                    now,
                    now,
                ),
            )
        return int(cursor.fetchone()["id"])

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self.db.connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT * FROM taxonomy_runs WHERE workspace_id=%s AND id=%s",
                (
                    self.db.workspace_id,
                    run_id,
                ),
            ).fetchone()
        if row is None:
            return None
        value = collection_dto(row)
        value["parameters"] = value.pop("parameters_json")
        return value

    def ensure_stage(
        self,
        run_id: int,
        stage_name: str,
        unit_key: str,
        *,
        input_hash: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.db.connect(guard=True) as connection:
            connection.execute(
                """
                INSERT INTO taxonomy_stage_runs(
                    workspace_id, run_id, stage_name, unit_key, status, input_hash, updated_at
                ) VALUES(%s, %s, %s, %s, 'pending', %s, %s)
                ON CONFLICT(run_id, stage_name, unit_key) DO NOTHING
                """,
                (self.db.workspace_id, run_id, stage_name, unit_key, input_hash, now),
            )
            row = connection.execute(
                """
                SELECT * FROM taxonomy_stage_runs
                WHERE workspace_id=%s AND run_id=%s AND stage_name=%s AND unit_key=%s
                """,
                (self.db.workspace_id, run_id, stage_name, unit_key),
            ).fetchone()
        assert row is not None
        value = self._stage_dto(row)
        if input_hash and value.get("input_hash") not in {None, input_hash}:
            raise ValueError("Stage input hash changed; refusing unsafe resume")
        return value

    def list_stages(self, run_id: int) -> list[dict[str, Any]]:
        with self.db.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT * FROM taxonomy_stage_runs
                WHERE workspace_id=%s AND run_id=%s ORDER BY id
                """,
                (
                    self.db.workspace_id,
                    run_id,
                ),
            ).fetchall()
        return [self._stage_dto(row) for row in rows]

    def start_stage(
        self,
        run_id: int,
        stage_name: str,
        unit_key: str,
        *,
        input_hash: str,
        model: str | None,
        prompt_version: str | None,
        thinking_enabled: bool | None,
        reasoning_effort: str | None,
        force_new_attempt: bool = False,
        expected_attempt_count: int | None = None,
    ) -> dict[str, Any]:
        stage = self.ensure_stage(run_id, stage_name, unit_key, input_hash=input_hash)
        now = utc_now()
        with self.db.connect(guard=True) as connection:
            current = connection.execute(
                "SELECT * FROM taxonomy_stage_runs WHERE workspace_id=%s AND id=%s FOR UPDATE",
                (
                    self.db.workspace_id,
                    stage["id"],
                ),
            ).fetchone()
            assert current is not None
            if current["status"] != "completed":
                recovery_already_advanced = (
                    force_new_attempt
                    and expected_attempt_count is not None
                    and int(current["attempt_count"] or 0) > expected_attempt_count
                )
                resume_existing = (
                    not force_new_attempt
                    and current["status"] in {"processing", "retry_wait"}
                    and int(current["attempt_count"] or 0) > 0
                )
                attempt_increment = (
                    0 if resume_existing or recovery_already_advanced else 1
                )
                connection.execute(
                    """
                    UPDATE taxonomy_stage_runs
                    SET status='processing', attempt_count=attempt_count+%s,
                        input_hash=%s, model=%s, prompt_version=%s,
                        thinking_enabled=%s, reasoning_effort=%s, started_at=%s,
                        completed_at=NULL, last_error_code=NULL,
                        last_error_message=NULL, next_retry_at=NULL, updated_at=%s
                    WHERE workspace_id=%s AND id=%s
                    """,
                    (
                        attempt_increment,
                        input_hash,
                        model,
                        prompt_version,
                        bool(thinking_enabled)
                        if thinking_enabled is not None
                        else None,
                        reasoning_effort,
                        now,
                        now,
                        self.db.workspace_id,
                        stage["id"],
                    ),
                )
                connection.execute(
                    """
                    UPDATE taxonomy_runs
                    SET status='running', current_stage=%s,
                        started_at=COALESCE(started_at, %s), updated_at=%s,
                        last_error_code=NULL, last_error_message=NULL
                    WHERE workspace_id=%s AND id=%s
                    """,
                    (stage_name, now, now, self.db.workspace_id, run_id),
                )
        return self.ensure_stage(run_id, stage_name, unit_key)

    def _complete_stage(
        self,
        run_id: int,
        stage_name: str,
        unit_key: str,
        *,
        output_path: str,
        output_hash: str,
        audit: dict[str, Any] | None = None,
        conn,
    ) -> None:
        now = utc_now()
        usage = (audit or {}).get("usage") or {}
        reasoning_tokens = (
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            if isinstance(usage.get("completion_tokens_details"), dict)
            else None
        )
        with self.db.connect(conn, guard=True) as connection:
            connection.execute(
                """
                UPDATE taxonomy_stage_runs
                SET status='completed', output_path=%s, output_hash=%s,
                    input_tokens=%s, output_tokens=%s, reasoning_tokens=%s,
                    elapsed_seconds=%s, completed_at=%s, next_retry_at=NULL,
                    last_error_code=NULL, last_error_message=NULL, updated_at=%s
                WHERE workspace_id=%s AND run_id=%s AND stage_name=%s AND unit_key=%s
                """,
                (
                    output_path,
                    output_hash,
                    _optional_int(usage.get("prompt_tokens")),
                    _optional_int(usage.get("completion_tokens")),
                    _optional_int(reasoning_tokens),
                    (audit or {}).get("elapsed_seconds"),
                    now,
                    now,
                    self.db.workspace_id,
                    run_id,
                    stage_name,
                    unit_key,
                ),
            )

    def record_reused_stage(
        self,
        run_id: int,
        stage_name: str,
        unit_key: str,
        *,
        input_hash: str,
        output_path: str,
        output_hash: str,
        model: str | None,
        prompt_version: str,
        thinking_enabled: bool | None,
        reasoning_effort: str | None,
    ) -> None:
        """Record a verified cross-Run artifact without pretending it was called again."""

        raw = self._output_bytes(output_path)
        now = utc_now()

        def publish(conn, descriptor):
            conn.execute(
                "INSERT INTO shiliu.taxonomy_stage_runs(workspace_id,run_id,stage_name,unit_key,status,input_hash,updated_at) VALUES(%s,%s,%s,%s,'pending',%s,%s) ON CONFLICT(run_id,stage_name,unit_key) DO NOTHING",
                (self.db.workspace_id, run_id, stage_name, unit_key, input_hash, now),
            )
            stage = conn.execute(
                "SELECT * FROM shiliu.taxonomy_stage_runs WHERE workspace_id=%s AND run_id=%s AND stage_name=%s AND unit_key=%s FOR UPDATE",
                (self.db.workspace_id, run_id, stage_name, unit_key),
            ).fetchone()
            if stage["status"] not in {"pending", "completed"}:
                raise ValueError(
                    "Only pending or already reused stages can be recorded"
                )
            if stage["input_hash"] not in {None, input_hash}:
                raise ValueError("Reused stage lineage changed")
            if stage["status"] == "completed":
                manifest = self.artifacts.objects.manifest(
                    version_id=stage["output_path"], conn=conn
                )
                if (
                    stage["output_hash"] != output_hash
                    or manifest["object_sha256"] != descriptor.sha256
                ):
                    raise ValueError("Reused stage lineage changed")
                return
            ref = self.artifacts.objects.publish(
                conn,
                f"taxonomy:{run_id}:{stage_name}:{unit_key}:output",
                descriptor.sha256,
                descriptor,
            )
            conn.execute(
                "UPDATE shiliu.taxonomy_stage_runs SET status='completed',attempt_count=0,input_hash=%s,output_path=%s,output_hash=%s,model=%s,prompt_version=%s,thinking_enabled=%s,reasoning_effort=%s,input_tokens=NULL,output_tokens=NULL,reasoning_tokens=NULL,elapsed_seconds=0,started_at=%s,completed_at=%s,updated_at=%s WHERE workspace_id=%s AND id=%s",
                (
                    input_hash,
                    ref,
                    output_hash,
                    model,
                    prompt_version,
                    thinking_enabled,
                    reasoning_effort,
                    now,
                    now,
                    now,
                    self.db.workspace_id,
                    stage["id"],
                ),
            )

        self.artifacts.objects.publish_bytes(raw, "taxonomy", output_hash, publish)

    def fail_stage(
        self,
        run_id: int,
        stage_name: str,
        unit_key: str,
        *,
        error_code: str,
        error_message: str,
        retryable: bool,
        next_retry_at: str | None = None,
    ) -> None:
        now = utc_now()
        stage_status = "retry_wait" if retryable else "failed"
        with self.db.connect(guard=True) as connection:
            connection.execute(
                """
                UPDATE taxonomy_stage_runs
                SET status=%s, next_retry_at=%s, last_error_code=%s,
                    last_error_message=%s, updated_at=%s
                WHERE workspace_id=%s AND run_id=%s AND stage_name=%s AND unit_key=%s
                """,
                (
                    stage_status,
                    next_retry_at,
                    error_code,
                    error_message,
                    now,
                    self.db.workspace_id,
                    run_id,
                    stage_name,
                    unit_key,
                ),
            )
            connection.execute(
                """
                UPDATE taxonomy_runs
                SET status=%s, current_stage=%s, last_error_code=%s,
                    last_error_message=%s, updated_at=%s WHERE workspace_id=%s AND id=%s
                """,
                (
                    stage_status,
                    stage_name,
                    error_code,
                    error_message,
                    now,
                    self.db.workspace_id,
                    run_id,
                ),
            )

    def set_run_status(
        self,
        run_id: int,
        status: str,
        *,
        current_stage: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = utc_now()
        completed_at = now if status in {"completed", "quality_failed"} else None
        with self.db.connect(guard=True) as connection:
            connection.execute(
                """
                UPDATE taxonomy_runs
                SET status=%s, current_stage=%s, last_error_code=%s,
                    last_error_message=%s, completed_at=%s, updated_at=%s
                WHERE workspace_id=%s AND id=%s
                """,
                (
                    status,
                    current_stage,
                    error_code,
                    error_message,
                    completed_at,
                    now,
                    self.db.workspace_id,
                    run_id,
                ),
            )

    def reset_stages(self, run_id: int, stage_names: list[str]) -> None:
        """Reset selected/downstream stages while preserving completed upstream batches."""

        if not stage_names:
            return
        placeholders = ",".join("%s" for _ in stage_names)
        now = utc_now()
        with self.db.connect(guard=True) as connection:
            connection.execute(
                f"""
                UPDATE taxonomy_stage_runs
                SET status='pending', input_hash=NULL, output_path=NULL,
                    output_hash=NULL, next_retry_at=NULL,
                    last_error_code=NULL, last_error_message=NULL,
                    started_at=NULL, completed_at=NULL, updated_at=%s
                WHERE workspace_id=%s AND run_id=%s AND stage_name IN ({placeholders})
                """,
                (now, self.db.workspace_id, run_id, *stage_names),
            )
            connection.execute(
                """
                UPDATE taxonomy_runs
                SET status='pending', current_stage=NULL, completed_at=NULL,
                    last_error_code=NULL, last_error_message=NULL, updated_at=%s
                WHERE workspace_id=%s AND id=%s
                """,
                (now, self.db.workspace_id, run_id),
            )


def _compact_json(value: Any) -> Jsonb:
    return Jsonb(value)


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None
