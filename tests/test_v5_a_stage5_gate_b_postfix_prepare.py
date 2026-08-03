from __future__ import annotations

from pathlib import Path
import stat

from scripts.v5_a_gate_b_postfix_prepare import (
    WRITE_BITS,
    _copy_schema_snapshot_for_migration,
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
