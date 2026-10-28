"""Small W16 runner and resource-boundary checks; no production SQL or model."""

import json
import os
import subprocess
import sys
import time

import pytest

from shiliu.config import PostgresConfig
from shiliu.migration.deployment import guard, ROOT, RUNTIME, private


def test_w16_restore_keeps_all_data_and_constraints_with_preinstalled_extensions():
    from shiliu.migration.backup import _preinstalled_vector_toc
    from shiliu.migration.values import MigrationRejected

    archive = "\n".join(
        [
            "; archive",
            "8; 2615 11 SCHEMA - shiliu_search owner",
            "9; 3079 21 EXTENSION - pg_textsearch",
            "1; 2615 10 SCHEMA - shiliu owner",
            "2; 3079 20 EXTENSION - vector",
            "3; 2615 30 SCHEMA - shiliu_migration owner",
            "4; 1259 40 TABLE shiliu videos owner",
            "5; 0 40 TABLE DATA shiliu videos owner",
            "6; 2606 50 FK CONSTRAINT shiliu child parent owner",
            "7; 2620 60 TRIGGER shiliu immutable owner",
        ]
    )
    filtered = _preinstalled_vector_toc(archive)
    assert filtered.count("; 1;") == filtered.count("; 2;") == 1
    for line in archive.splitlines()[5:]:
        assert line in filtered.splitlines()
    with pytest.raises(MigrationRejected):
        _preinstalled_vector_toc(
            archive.replace("SCHEMA - shiliu owner", "SCHEMA - other owner")
        )


@pytest.mark.parametrize(
    "url",
    [
        "host=localhost port=55484 dbname=shiliu_w16 user=shiliu_w16_runtime",
        "host=/tmp port=55484 dbname=shiliu_w16 user=shiliu_w16_runtime",
        f"host='{ROOT}/socket' port=55484 dbname=other user={RUNTIME}",
        f"host='{ROOT}/socket' port=55484 dbname=shiliu_w16 user={RUNTIME} options=PRIVATE",
    ],
)
def test_w16_rejects_unbound_targets_without_database_connection(url):
    with pytest.raises(ValueError, match="Refusing") as error:
        guard(PostgresConfig(url, ROOT / "artifacts", "production"))
    assert "PRIVATE" not in str(error.value)


def test_w16_private_boundary_rejects_symlink_and_public_directory(tmp_path):
    target = tmp_path / "data"
    target.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        private(target)
    target.chmod(0o700)
    private(target)
    link = tmp_path / "linked"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        private(link)


@pytest.mark.parametrize("failure", [False, True])
def test_detached_attempt_survives_launcher_exit_and_records_result(tmp_path, failure):
    # The launcher exits immediately. Its session-independent grandchild owns
    # the wait/exit recording; pytest's process/session does not own the task.
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    command = [
        sys.executable,
        "-c",
        "import time,json,sys; time.sleep(.8); print(json.dumps({'controlled':True}),flush=True); sys.exit("
        + ("7" if failure else "0")
        + ")",
    ]
    worker = (
        "from shiliu.migration.detached import _wait_and_record; import sys; sys.exit(_wait_and_record("
        + repr(str(attempt))
        + ","
        + repr(command)
        + ",{'kind':'controlled_process_test'}))"
    )
    launcher = (
        "import subprocess,sys,json; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c',"
        + repr(worker)
        + "],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,close_fds=True); print(json.dumps({'pid':p.pid,'launcher':__import__('os').getpid()}))"
    )
    launched = subprocess.run(
        [sys.executable, "-c", launcher], capture_output=True, text=True, check=True
    )
    info = json.loads(launched.stdout)
    deadline = time.monotonic() + 15
    while not (attempt / "run.json").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    run = json.loads((attempt / "run.json").read_text())
    assert run["runner"]["pid"] == info["pid"]
    assert run["session_id"] == info["pid"] != os.getsid(0)
    assert not (attempt / "exit.json").exists()
    os.kill(info["pid"], 0)  # Launcher already exited, runner still executing.
    while not (attempt / "exit.json").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    result = json.loads((attempt / "exit.json").read_text())
    assert result["child_exit_code"] == (7 if failure else 0)
    assert result["success"] is (not failure)
    assert result["signal"] is None
    assert json.loads((attempt / "stdout.log").read_text()) == {"controlled": True}
    assert (attempt / "stderr.log").is_file()
    assert not list(attempt.glob("*.tmp"))
