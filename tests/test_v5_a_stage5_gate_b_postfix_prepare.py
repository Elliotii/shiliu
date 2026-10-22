from __future__ import annotations

from pathlib import Path
import sqlite3
import stat

from scripts.v5_a_gate_b_postfix_prepare import (
    WRITE_BITS,
    _copy_schema_snapshot_for_migration,
    _rebind_eval_artifact_paths,
)
from scripts.v5_a_gate_b_postfix_validate import (
    _completion_create_command,
    _completion_task_id,
    _run_envelope,
)


def test_postfix_prepare_only_makes_eval_working_copy_owner_writable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.schema9.db"
    source.write_bytes(b"immutable-schema-9-fixture")
    source.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    root = tmp_path / "new-root"
    root.mkdir()

    snapshot, working = _copy_schema_snapshot_for_migration(source, root)

    assert source.read_bytes() == snapshot.read_bytes() == working.read_bytes()
    assert source.stat().st_mode & WRITE_BITS == 0
    assert snapshot.stat().st_mode & WRITE_BITS == 0
    assert working.stat().st_mode & stat.S_IWUSR
    assert working.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0


def test_completion_run_envelope_and_task_identity_are_run_wide() -> None:
    envelope = _run_envelope(completion=True)
    assert envelope == {
        "authorized_cases": ("GB-PC-G-01", "GB-PC-H-01"),
        "max_logical_calls": 10,
        "max_http_attempts": 20,
        "max_input_tokens": 80_000,
        "max_output_tokens": 17_792,
        "max_wall_seconds": 22 * 60,
        "reserve_stop_usd": envelope["reserve_stop_usd"],
        "absolute_max_cost_usd": envelope["absolute_max_cost_usd"],
    }
    assert str(envelope["reserve_stop_usd"]) == "0.20"
    assert str(envelope["absolute_max_cost_usd"]) == "0.25"
    run_id = "GB-PC-test"
    assert _completion_task_id(run_id, "GB-PC-G-01") != _completion_task_id(
        run_id, "GB-PC-H-01"
    )
    assert _completion_create_command(run_id, "GB-PC-G-01").endswith(
        ":GB-PC-G-01:create"
    )


def test_grounded_completion_smoke_envelope_is_exactly_one_bounded_case() -> None:
    envelope = _run_envelope(completion_g_only=True)

    assert envelope["authorized_cases"] == ("GB-PC-G-01",)
    assert envelope["max_logical_calls"] == 5
    assert envelope["max_http_attempts"] == 10
    assert envelope["max_input_tokens"] == 40_000
    assert envelope["max_output_tokens"] == 8_896
    assert envelope["max_wall_seconds"] == 12 * 60
    assert str(envelope["reserve_stop_usd"]) == "0.08"
    assert str(envelope["absolute_max_cost_usd"]) == "0.10"


def test_completion_eval_database_rebinds_only_to_isolated_artifact_copy(
    tmp_path: Path,
) -> None:
    database = tmp_path / "eval.db"
    artifact_root = tmp_path / "artifacts"
    destination = artifact_root / "videos" / "BV-fixture"
    destination.mkdir(parents=True)
    for name in ("cover.jpg", "subtitle-raw.txt", "transcript.txt", "summary.md"):
        (destination / name).write_text(name, encoding="utf-8")
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE videos (id INTEGER PRIMARY KEY, source_id TEXT, "
            "artifact_dir TEXT, cover_path TEXT, raw_subtitle_path TEXT, "
            "transcript_path TEXT, summary_path TEXT)"
        )
        connection.execute(
            "INSERT INTO videos VALUES (1, 'BV-fixture', '/live/BV-fixture', "
            "'/live/BV-fixture/cover.jpg', '/live/BV-fixture/subtitle-raw.txt', "
            "'/live/BV-fixture/transcript.txt', '/live/BV-fixture/summary.md')"
        )
        connection.commit()
    finally:
        connection.close()

    assert _rebind_eval_artifact_paths(database, artifact_root) == 1

    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT artifact_dir, cover_path, raw_subtitle_path, transcript_path, "
            "summary_path FROM videos WHERE id=1"
        ).fetchone()
    finally:
        connection.close()
    assert row == (
        str(destination),
        str(destination / "cover.jpg"),
        str(destination / "subtitle-raw.txt"),
        str(destination / "transcript.txt"),
        str(destination / "summary.md"),
    )
