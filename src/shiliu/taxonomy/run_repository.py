from __future__ import annotations

import json
from typing import Any

from shiliu.db import Database, utc_now


class TaxonomyRunRepository:
    """Persistence boundary for resumable corpus-level taxonomy work."""

    def __init__(self, db: Database) -> None:
        self.db = db

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
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO taxonomy_runs(
                    run_kind, status, current_stage, corpus_snapshot_id,
                    engine, engine_version, parameters_json, search_enabled,
                    created_at, updated_at
                ) VALUES(?, 'pending', NULL, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    run_kind,
                    snapshot_id,
                    engine,
                    engine_version,
                    _compact_json(parameters),
                    now,
                    now,
                ),
            )
        return int(cursor.lastrowid)

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM taxonomy_runs WHERE id=?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["parameters"] = json.loads(value.pop("parameters_json"))
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
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO taxonomy_stage_runs(
                    run_id, stage_name, unit_key, status, input_hash, updated_at
                ) VALUES(?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(run_id, stage_name, unit_key) DO NOTHING
                """,
                (run_id, stage_name, unit_key, input_hash, now),
            )
            row = connection.execute(
                """
                SELECT * FROM taxonomy_stage_runs
                WHERE run_id=? AND stage_name=? AND unit_key=?
                """,
                (run_id, stage_name, unit_key),
            ).fetchone()
        assert row is not None
        value = dict(row)
        if input_hash and value.get("input_hash") not in {None, input_hash}:
            raise ValueError("Stage input hash changed; refusing unsafe resume")
        return value

    def list_stages(self, run_id: int) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM taxonomy_stage_runs
                WHERE run_id=? ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

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
    ) -> dict[str, Any]:
        stage = self.ensure_stage(
            run_id, stage_name, unit_key, input_hash=input_hash
        )
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE taxonomy_stage_runs
                SET status='processing', attempt_count=attempt_count+1,
                    input_hash=?, model=?, prompt_version=?,
                    thinking_enabled=?, reasoning_effort=?, started_at=?,
                    completed_at=NULL, last_error_code=NULL,
                    last_error_message=NULL, next_retry_at=NULL, updated_at=?
                WHERE id=?
                """,
                (
                    input_hash,
                    model,
                    prompt_version,
                    int(thinking_enabled) if thinking_enabled is not None else None,
                    reasoning_effort,
                    now,
                    now,
                    stage["id"],
                ),
            )
            connection.execute(
                """
                UPDATE taxonomy_runs
                SET status='running', current_stage=?,
                    started_at=COALESCE(started_at, ?), updated_at=?,
                    last_error_code=NULL, last_error_message=NULL
                WHERE id=?
                """,
                (stage_name, now, now, run_id),
            )
        return self.ensure_stage(run_id, stage_name, unit_key)

    def complete_stage(
        self,
        run_id: int,
        stage_name: str,
        unit_key: str,
        *,
        output_path: str,
        output_hash: str,
        audit: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        usage = (audit or {}).get("usage") or {}
        reasoning_tokens = (
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            if isinstance(usage.get("completion_tokens_details"), dict)
            else None
        )
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE taxonomy_stage_runs
                SET status='completed', output_path=?, output_hash=?,
                    input_tokens=?, output_tokens=?, reasoning_tokens=?,
                    elapsed_seconds=?, completed_at=?, next_retry_at=NULL,
                    last_error_code=NULL, last_error_message=NULL, updated_at=?
                WHERE run_id=? AND stage_name=? AND unit_key=?
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

        stage = self.ensure_stage(
            run_id, stage_name, unit_key, input_hash=input_hash
        )
        if stage["status"] not in {"pending", "completed"}:
            raise ValueError("Only pending or already reused stages can be recorded")
        if stage["status"] == "completed":
            if (
                stage.get("input_hash") != input_hash
                or stage.get("output_hash") != output_hash
                or stage.get("output_path") != output_path
            ):
                raise ValueError("Reused stage lineage changed")
            return
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE taxonomy_stage_runs
                SET status='completed', attempt_count=0, input_hash=?,
                    output_path=?, output_hash=?, model=?, prompt_version=?,
                    thinking_enabled=?, reasoning_effort=?, input_tokens=NULL,
                    output_tokens=NULL, reasoning_tokens=NULL,
                    elapsed_seconds=0, started_at=?, completed_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    input_hash,
                    output_path,
                    output_hash,
                    model,
                    prompt_version,
                    int(thinking_enabled) if thinking_enabled is not None else None,
                    reasoning_effort,
                    now,
                    now,
                    now,
                    stage["id"],
                ),
            )

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
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE taxonomy_stage_runs
                SET status=?, next_retry_at=?, last_error_code=?,
                    last_error_message=?, updated_at=?
                WHERE run_id=? AND stage_name=? AND unit_key=?
                """,
                (
                    stage_status,
                    next_retry_at,
                    error_code,
                    error_message,
                    now,
                    run_id,
                    stage_name,
                    unit_key,
                ),
            )
            connection.execute(
                """
                UPDATE taxonomy_runs
                SET status=?, current_stage=?, last_error_code=?,
                    last_error_message=?, updated_at=? WHERE id=?
                """,
                (
                    stage_status,
                    stage_name,
                    error_code,
                    error_message,
                    now,
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
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE taxonomy_runs
                SET status=?, current_stage=?, last_error_code=?,
                    last_error_message=?, completed_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    status,
                    current_stage,
                    error_code,
                    error_message,
                    completed_at,
                    now,
                    run_id,
                ),
            )

    def reset_stages(self, run_id: int, stage_names: list[str]) -> None:
        """Reset selected/downstream stages while preserving completed upstream batches."""

        if not stage_names:
            return
        placeholders = ",".join("?" for _ in stage_names)
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute(
                f"""
                UPDATE taxonomy_stage_runs
                SET status='pending', input_hash=NULL, output_path=NULL,
                    output_hash=NULL, next_retry_at=NULL,
                    last_error_code=NULL, last_error_message=NULL,
                    started_at=NULL, completed_at=NULL, updated_at=?
                WHERE run_id=? AND stage_name IN ({placeholders})
                """,
                (now, run_id, *stage_names),
            )
            connection.execute(
                """
                UPDATE taxonomy_runs
                SET status='pending', current_stage=NULL, completed_at=NULL,
                    last_error_code=NULL, last_error_message=NULL, updated_at=?
                WHERE id=?
                """,
                (now, run_id),
            )


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None
