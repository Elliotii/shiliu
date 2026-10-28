"""Exact, opt-in W16 resource binding. Never an arbitrary production DSN gate."""

from __future__ import annotations
import json
import os
from pathlib import Path
import re

from psycopg.conninfo import conninfo_to_dict

ROOT = (Path.home() / "Library/Application Support/Shiliu-Postgres-20261025")
TASK = "shiliu-w16-20261025"
ADMIN = "shiliu_w16_admin"
ETL = "shiliu_w16_etl"
RUNTIME = "shiliu_w16_runtime"
DATABASES = {"shiliu_w16": "artifacts", "shiliu_w16_restore": "restore-artifacts"}
BINDING = {
    "format": "shiliu-exact-w16-binding-v1",
    "task": TASK,
    "root": str(ROOT),
    "port": 55484,
    "databases": DATABASES,
    "roles": {"admin": ADMIN, "etl": ETL, "runtime": RUNTIME},
    "exception_approval_sha256": "89c8d48036c22b5266fbaffa26d5c1990eb914d93e034aa705416c184e608f84",
}


def private(path, *, directory=True):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Refusing symlink W16 resource")
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError("Refusing non-private W16 resource")
    if directory != path.is_dir() or (not directory and not path.is_file()):
        raise ValueError("Refusing wrong W16 resource type")


def binding():
    private(ROOT)
    marker = ROOT / "resource-binding.json"
    private(marker, directory=False)
    if json.loads(marker.read_text()) != BINDING:
        raise ValueError("Refusing unrecognized W16 binding")
    return ROOT


def guard(config, *, admin=False, etl=False):
    invalid = ValueError("Refusing non-bound W16 PostgreSQL target")
    try:
        if config.environment != "production" or (admin and etl):
            raise invalid
        if any(k.startswith("PG") and v for k, v in os.environ.items()):
            raise invalid
        p = conninfo_to_dict(config.database_url)
        role = ADMIN if admin else ETL if etl else RUNTIME
        if (
            set(p) != {"host", "port", "dbname", "user"}
            or p["host"] != str(ROOT / "socket")
            or p["port"] != "55484"
            or p["dbname"] not in DATABASES
            or p["user"] != role
            or config.artifact_root != ROOT / DATABASES[p["dbname"]]
        ):
            raise invalid
        binding()
        private(ROOT / "socket")
        private(config.artifact_root)
        return p
    except Exception:
        raise invalid from None


def package_root(path):
    """Exact persistent package parent, including before a new copy exists."""
    binding()
    path = Path(path)
    private(ROOT / "sources")
    if path.parent != ROOT / "sources" or not re.fullmatch(
        r"w14_[a-z0-9_]+", path.name
    ):
        raise ValueError("Refusing non-bound W16 source package")
    if path.is_symlink():
        raise ValueError("Refusing symlink W16 source package")
    return ROOT


def check_server(conn):
    def setting(name):
        row = conn.execute("SHOW " + name).fetchone()
        return row[name] if isinstance(row, dict) else row[0]

    if (
        conn.info.server_version != 180006
        or setting("data_directory") != str(ROOT / "pgdata")
        or setting("listen_addresses") != ""
    ):
        raise ValueError("Refusing unexpected W16 server identity")
