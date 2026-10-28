"""Fail-closed local test target guard. Must precede connect, DDL and cleanup."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict

from shiliu.config import PostgresConfig

TASK_ROOT = Path("/tmp/shiliu-w01-20261023").resolve()
TEST_PREFIX = "shiliu_w01_test_"
ADMIN_USER = "shiliu_w01_admin"
RUN_USER = "shiliu_w01_runtime"
ETL_USER = "shiliu_w01_etl"


def guard(
    config: PostgresConfig, *, admin: bool = False, etl: bool = False
) -> dict[str, str]:
    """Only task-owned Unix sockets, exact names and owner-only resource root.

    Not a production safety boundary. No remote host / arbitrary local service /
    database name merely containing 'test' is accepted. Does not perform I/O on
    any database. The marker is created only after explicit task bootstrap.
    """
    if config.environment == "production":
        from shiliu.migration.deployment import guard as production_guard

        return production_guard(config, admin=admin, etl=etl)
    invalid = ValueError("Refusing non-isolated W01 PostgreSQL test target")
    try:
        if any(key.startswith("PG") and value for key, value in os.environ.items()):
            raise invalid
        if config.environment != "test":
            raise invalid
        root_stat = TASK_ROOT.stat()
        if root_stat.st_uid != os.getuid() or root_stat.st_mode & 0o077:
            raise invalid
        marker = TASK_ROOT / "instance.json"
        if marker.is_symlink() or marker.stat().st_uid != os.getuid():
            raise invalid
        if json.loads(marker.read_text()) != {
            "task": "shiliu-w01-20261023",
            "port": 55483,
        }:
            raise invalid
        parts = conninfo_to_dict(config.database_url)
        allowed = {"host", "port", "dbname", "user", "password"}
        if set(parts) - allowed:
            raise invalid
        if (
            parts.get("host") != str(TASK_ROOT / "socket")
            or parts.get("port") != "55483"
        ):
            raise invalid
        socket_root = TASK_ROOT / "socket"
        if socket_root.is_symlink() or socket_root.stat().st_mode & 0o077:
            raise invalid
        if not re.fullmatch(r"shiliu_w01_test_[a-z0-9_]+", parts.get("dbname", "")):
            raise invalid
        if admin and etl:
            raise invalid
        expected_user = ADMIN_USER if admin else ETL_USER if etl else RUN_USER
        if parts.get("user") != expected_user:
            raise invalid
        root = config.artifact_root
        base = TASK_ROOT / "artifacts"
        if root.is_symlink() or not root.is_dir():
            raise invalid
        if root.resolve() != base:
            if root.parent.resolve() != base or not re.fullmatch(
                r"w(?:04|14)_[a-z0-9_]+", root.name
            ):
                raise invalid
            if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
                raise invalid
        return parts
    except Exception:
        raise invalid from None


def guard_source(path: Path) -> Path:
    """Only private task packages, synthetic or explicitly approved historical."""
    invalid = ValueError("Refusing unknown W04 source snapshot")
    try:
        source = path.resolve(strict=True)
        parent = source.parent
        if path.is_symlink() or parent.is_symlink() or source.name != "source.sqlite3":
            raise invalid
        from shiliu.migration.deployment import ROOT, package_root, private

        if parent.parent == ROOT / "sources":
            package_root(parent)
            private(parent)
        elif parent.parent != TASK_ROOT / "sources" or not re.fullmatch(
            r"w(?:04|14)_[a-z0-9_]+", parent.name
        ):
            raise invalid
        if parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077:
            raise invalid
        if source.stat().st_uid != os.getuid() or not source.is_file():
            raise invalid
        source_kind(source)
        return source
    except Exception:
        raise invalid from None


def source_kind(source):
    synthetic = source.parent / "synthetic.json"
    historical = source.parent / "historical.json"
    if synthetic.exists() == historical.exists():
        raise ValueError("ambiguous or missing source provenance")
    marker = synthetic if synthetic.exists() else historical
    if marker.is_symlink() or marker.stat().st_uid != os.getuid():
        raise ValueError("unsafe source provenance")
    value = json.loads(marker.read_text())
    from shiliu.migration.deployment import ROOT, TASK

    task = TASK if source.parent.parent == ROOT / "sources" else "shiliu-w01-20261023"
    if synthetic.exists():
        if task == TASK:
            raise ValueError("synthetic source forbidden for W16 production")
        if value != {"task": "shiliu-w01-20261023", "synthetic_only": True}:
            raise ValueError("invalid synthetic provenance")
        return {"synthetic_only": True}
    if (
        set(value) != {"task", "source_kind", "approval_reference", "database_sha256"}
        or value["task"] != task
        or value["source_kind"] != "historical"
        or not isinstance(value["approval_reference"], str)
        or not value["approval_reference"].strip()
        or not re.fullmatch("[0-9a-f]{64}", value["database_sha256"])
    ):
        raise ValueError("approved historical source provenance required")
    return dict(value, synthetic_only=False)


def resource_root(config):
    if config.environment == "production":
        from shiliu.migration.deployment import binding

        return binding()
    return TASK_ROOT


def new_package_root(destination):
    from shiliu.migration.deployment import ROOT, package_root

    if destination.parent == ROOT / "sources":
        return package_root(destination)
    return TASK_ROOT


def guard_input_target(source, config):
    source = guard_source(source)
    if source.parent.parent != resource_root(config) / "sources":
        raise ValueError("Refusing source and target resource mismatch")
