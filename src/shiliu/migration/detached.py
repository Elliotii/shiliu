"""One detached W16 rebuild attempt. No cutover, retry loop or Job dispatch."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
    with temporary.open("x") as f:
        temporary.chmod(0o600)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


def identity(pid):
    result = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", "lstart="],
        capture_output=True,
        text=True,
        check=False,
    )
    return {"pid": pid, "start_identity": result.stdout.strip()}


def _wait_and_record(attempt, command, metadata):
    """Small wait/exit primitive; controlled process tests do not load a model."""
    attempt = Path(attempt)
    run = dict(
        metadata,
        started_at=now(),
        runner=identity(os.getpid()),
        session_id=os.getsid(0),
        process_group=os.getpgrp(),
    )
    child = None
    try:
        with (
            (attempt / "stdout.log").open("x") as stdout,
            (attempt / "stderr.log").open("x") as stderr,
        ):
            for file in ("stdout.log", "stderr.log"):
                (attempt / file).chmod(0o600)
            env = {
                "PATH": os.defpath,
                "HOME": str(Path.home()),
                "LANG": "en_US.UTF-8",
                "PYTHONUNBUFFERED": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            }
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                env=env,
                close_fds=True,
            )
            run["child"] = identity(child.pid)
            atomic_json(attempt / "run.json", run)
            previous = signal.signal(
                signal.SIGTERM, lambda sig, frame: child.send_signal(sig)
            )
            try:
                code = child.wait()
            finally:
                signal.signal(signal.SIGTERM, previous)
        result = None
        try:
            result = json.loads((attempt / "stdout.log").read_text())
        except (ValueError, OSError):
            pass
        valid = isinstance(result, dict)
        if metadata.get("kind") == "w16_rebuild":
            valid = bool(
                valid
                and result.get("manifest_hash") == metadata["manifest_hash"]
                and result.get("run_id") == metadata["run_id"]
                and result.get("rebuild", {}).get("status") == "ready"
            )
        if valid:
            atomic_json(attempt / "result.json", result)
        record = dict(
            finished_at=now(),
            child_exit_code=code,
            signal=-code if code < 0 else None,
            final_result_valid=valid,
            success=code == 0 and valid,
        )
    except Exception as error:
        record = dict(
            finished_at=now(),
            child_exit_code=None if child is None else child.poll(),
            signal=None,
            final_result_valid=False,
            success=False,
            error_type=type(error).__name__,
        )
    atomic_json(attempt / "exit.json", record)
    return 0 if record["success"] else 1


def launch(source, run_id, manifest_hash, code_commit, model_path, attempt_id):
    from psycopg.conninfo import make_conninfo
    from shiliu.config import PostgresConfig
    from shiliu.migration import deployment as d
    from shiliu.migration.safety import guard, guard_input_target
    from shiliu.retrieval.qwen import (
        verify_qwen_snapshot,
        QWEN_MODEL_PATH,
        QWEN_MODEL_REVISION,
    )
    import re

    config = PostgresConfig(
        make_conninfo(
            host=str(d.ROOT / "socket"), port=55484, dbname="shiliu_w16", user=d.ETL
        ),
        d.ROOT / "artifacts",
        "production",
    )
    guard(config, etl=True)
    guard_input_target(source, config)
    if model_path != QWEN_MODEL_PATH:
        raise ValueError("Refusing different W16 model path")
    verify_qwen_snapshot(model_path)
    if not re.fullmatch(r"[a-z0-9_]{1,64}", attempt_id) or not re.fullmatch(
        r"[0-9a-f]{40}", code_commit
    ):
        raise ValueError("Invalid W16 attempt/code identity")
    if Path(sys.prefix) != d.ROOT / "runtime":
        raise ValueError("W16 runner requires fixed installed runtime")
    d.private(d.ROOT / "runtime-release.json", directory=False)
    release = json.loads((d.ROOT / "runtime-release.json").read_text())
    if release["code_commit"] != code_commit:
        raise ValueError("W16 installed release identity mismatch")
    d.private(d.ROOT / "attempts")
    attempt = d.ROOT / "attempts" / attempt_id
    attempt.mkdir(mode=0o700)
    metadata = {
        "kind": "w16_rebuild",
        "run_id": run_id,
        "manifest_hash": manifest_hash,
        "code_commit": code_commit,
        "model_revision": QWEN_MODEL_REVISION,
        "dimension": 512,
        "target": "shiliu_w16",
        "attempt_id": attempt_id,
    }
    atomic_json(
        attempt / "request.json",
        dict(metadata, source=str(source), model_path=str(model_path)),
    )
    with (attempt / "runner.log").open("x") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-u",
                "-m",
                "shiliu.migration.detached",
                "worker",
                str(attempt),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            cwd=attempt,
            start_new_session=True,
            close_fds=True,
        )
    (attempt / "runner.log").chmod(0o600)
    launched = dict(
        runner=identity(process.pid), launched_at=now(), attempt=str(attempt)
    )
    atomic_json(attempt / "launch.json", launched)
    return launched


def worker(attempt):
    from psycopg.conninfo import make_conninfo
    from shiliu.migration import deployment as d

    d.binding()
    d.private(attempt)
    if attempt.parent != d.ROOT / "attempts" or Path(sys.prefix) != d.ROOT / "runtime":
        raise ValueError("Refusing unbound attempt")
    request = json.loads((attempt / "request.json").read_text())
    if Path("/usr/bin/caffeinate").is_file():
        subprocess.Popen(
            ["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    metadata = {k: v for k, v in request.items() if k not in {"source", "model_path"}}
    command = [
        sys.executable,
        "-I",
        "-u",
        "-m",
        "shiliu.migration",
        "rebuild",
        "--source",
        request["source"],
        "--run-id",
        request["run_id"],
        "--database-url",
        make_conninfo(
            host=str(d.ROOT / "socket"), port=55484, dbname="shiliu_w16", user=d.ETL
        ),
        "--artifact-root",
        str(d.ROOT / "artifacts"),
        "--environment",
        "production",
        "--embedding",
        "qwen",
        "--model-path",
        request["model_path"],
    ]
    return _wait_and_record(attempt, command, metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    work = sub.add_parser("worker")
    work.add_argument("attempt", type=Path)
    start = sub.add_parser("start")
    for key in (
        "source",
        "run-id",
        "manifest-hash",
        "code-commit",
        "model-path",
        "attempt-id",
    ):
        start.add_argument(
            "--" + key,
            required=True,
            type=Path if key in {"source", "model-path"} else str,
        )
    args = vars(parser.parse_args())
    action = args.pop("action")
    if action == "worker":
        return worker(**args)
    print(json.dumps(launch(**args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
