"""Bounded synchronous PG access, owned and injected by the application layer.

No runtime DDL, SQLite fallback, model calls or import-time connections. Callers
passing a connection across stores own the transaction; stores must not commit.
"""
from __future__ import annotations

import time
import os
from contextlib import contextmanager
from dataclasses import dataclass
from tempfile import TemporaryFile
from typing import Any, Callable, Iterator, TypeVar

import psycopg
from pgvector.psycopg import register_vector
from psycopg import Connection, IsolationLevel
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout, TooManyRequests

from shiliu.config import PostgresConfig, LIBPQ_DISABLED_PASSFILE
from shiliu.storage.errors import StorageError, safe_error
from shiliu.storage.scope import ResourceContext

T = TypeVar("T")
DRIVER_ERRORS = (psycopg.Error, PoolClosed, PoolTimeout, TooManyRequests, StorageError)
POSTGRES_VERSION = 180006
VECTOR_VERSION = "0.8.7"
VECTOR_SCHEMA = "shiliu"


class _SafeConnection(Connection):
    @classmethod
    def connect(cls, *args: Any, **kwargs: Any) -> Any:
        # The pool logs connection errors in worker threads. Sanitize before the
        # exception reaches that logger, including URI and keyword conninfo.
        try:
            if any(key.startswith('PG') and value for key,value in os.environ.items()):
                raise StorageError('implicit_libpq_environment_rejected')
            return super().connect(*args, **kwargs)
        except Exception as error:
            raise safe_error(error) from None


@dataclass(frozen=True)
class PoolSettings:
    min_size: int = 1
    max_size: int = 8
    timeout: float = 5.0
    lock_timeout_ms: int = 3000
    statement_timeout_ms: int = 15000
    idle_timeout_ms: int = 30000

    def __post_init__(self) -> None:
        if not (1 <= self.min_size <= self.max_size <= 8):
            raise ValueError("Pool sizes must satisfy 1 <= min <= max <= 8")
        if not (0 < self.timeout <= 5):
            raise ValueError("Pool timeout must be positive and at most 5 seconds")
        for value, limit in ((self.lock_timeout_ms, 3000), (self.statement_timeout_ms, 15000),
                             (self.idle_timeout_ms, 30000)):
            if type(value) is not int or not 0 < value <= limit:
                raise ValueError("Session timeouts must be positive and within runtime limits")


class PgDatabase:
    def __init__(self, config: PostgresConfig, *, settings: PoolSettings | None = None) -> None:
        if any(key.startswith('PG') and value for key,value in os.environ.items()):
            raise StorageError('implicit_libpq_environment_rejected')
        self.config = config
        self.settings = settings or PoolSettings()
        self._configure_failure: StorageError | None = None
        self._pool = ConnectionPool(
            config.database_url, connection_class=_SafeConnection,
            kwargs={"autocommit": True, "row_factory": dict_row,
                    "connect_timeout": max(1, int(self.settings.timeout)),
                    "application_name": "shiliu-pg", "prepare_threshold": None,"passfile": LIBPQ_DISABLED_PASSFILE,
                    "options": "-c search_path=pg_catalog,shiliu -c timezone=UTC"},
            min_size=self.settings.min_size, max_size=self.settings.max_size,
            timeout=self.settings.timeout, max_waiting=32,
            reconnect_timeout=self.settings.timeout,
            configure=self._configure, reset=self._reset,
            check=ConnectionPool.check_connection, open=False, name="shiliu-pg",
        )

    def _baseline(self, conn: Connection) -> None:
        conn.autocommit = True
        conn.isolation_level = None
        conn.read_only = None
        conn.deferrable = None
        conn.row_factory = dict_row
        conn.execute("SET search_path TO pg_catalog, shiliu")
        conn.execute("SET default_text_search_config TO 'pg_catalog.simple'")
        conn.execute("SET TIME ZONE 'UTC'")
        for name, value in (("lock_timeout", self.settings.lock_timeout_ms),
                            ("statement_timeout", self.settings.statement_timeout_ms),
                            ("idle_in_transaction_session_timeout", self.settings.idle_timeout_ms)):
            conn.execute("SELECT pg_catalog.set_config(%s, %s, false)", (name, f"{value}ms"))

    def _check_versions(self, conn: Connection) -> None:
        if conn.info.server_version != POSTGRES_VERSION:
            raise StorageError("server_version_mismatch")
        row = conn.execute(
            "SELECT e.extversion, n.nspname FROM pg_catalog.pg_extension e "
            "JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'"
        ).fetchone()
        if row != {"extversion": VECTOR_VERSION, "nspname": VECTOR_SCHEMA}:
            raise StorageError("vector_version_or_schema_mismatch")

        from shiliu.retrieval.bm25 import check_extension
        check_extension(conn)

    def _configure(self, conn: Connection) -> None:
        try:
            self._baseline(conn)
            self._check_versions(conn)
            # Controlled search_path above, validated extension namespace, and no
            # runtime CREATE privilege: type lookup cannot follow a caller path.
            try:
                register_vector(conn)
            except Exception:
                raise StorageError("vector_adapter_registration_failed") from None
        except Exception as error:
            self._configure_failure = safe_error(error)
            raise self._configure_failure from None

    def _reset(self, conn: Connection) -> None:
        try:
            if conn.info.transaction_status != TransactionStatus.IDLE:
                conn.rollback()
            conn.autocommit = True
            # DISCARD removes SQL SET/ROLE, temp tables, advisory locks and LISTEN.
            # Prepared statements are disabled so client/server caches stay aligned.
            conn.execute("DISCARD ALL")
            self._baseline(conn)
        except Exception as error:
            conn.close()
            raise safe_error(error) from None

    def open(self) -> PgDatabase:
        try:
            self._configure_failure = None
            self._pool.open(wait=True, timeout=self.settings.timeout)
        except DRIVER_ERRORS as error:
            self.close()
            failure = self._configure_failure or (StorageError("connection_unavailable")
                if isinstance(error, PoolTimeout) else safe_error(error))
            raise failure from None
        return self

    def close(self) -> None:
        self._pool.close(timeout=self.settings.timeout)

    def __enter__(self) -> PgDatabase:
        return self.open()

    def __exit__(self, *args: Any) -> None:
        self.close()

    @contextmanager
    def transaction(self, *, read_only: bool = False,
                    isolation: str = "read committed") -> Iterator[Connection]:
        levels = {"read committed": IsolationLevel.READ_COMMITTED,
                  "repeatable read": IsolationLevel.REPEATABLE_READ,
                  "serializable": IsolationLevel.SERIALIZABLE}
        if isolation not in levels:
            raise ValueError("Unsupported transaction isolation")
        try:
            with self._pool.connection(timeout=self.settings.timeout) as conn:
                conn.isolation_level = levels[isolation]
                conn.read_only = read_only
                with conn.transaction():
                    yield conn
        except DRIVER_ERRORS as error:
            raise safe_error(error) from None

    @contextmanager
    def read(self) -> Iterator[Connection]:
        # A short read-only transaction makes write protection explicit. Callers
        # requiring a stable multi-statement snapshot opt into repeatable read.
        with self.transaction(read_only=True) as conn:
            yield conn

    def replay_pure_db(self, operation: Callable[[Connection], T]) -> T:
        """Explicit opt-in: at most 3 attempts, only SQLSTATE 40001/40P01.

        operation MUST contain replayable DB work only: no files, network,
        model/ASR calls, or mutations to external/process state. Never wrap an
        arbitrary caller context or use this for artifact publication.
        """
        for attempt in range(3):
            try:
                with self.transaction() as conn:
                    result = operation(conn)
                return result
            except StorageError as error:
                if error.sqlstate not in {"40001", "40P01"} or attempt == 2:
                    raise
                time.sleep(0.02 * (attempt + 1))
        raise AssertionError("unreachable")

    def validate_startup(self, *, revision: str, context: ResourceContext) -> None:
        """Validate an explicit W02 contract; no defaults, skips or automatic DDL.

        W02 supplies revision and real scope seeds. W13 calls this before workers.
        Test-only control objects do not constitute the formal schema/revision.
        """
        if not revision:
            raise ValueError("An expected Alembic revision is required")
        try:
            # Root must already exist. Probe only this explicit root, never mkdir.
            with TemporaryFile(dir=self.config.artifact_root) as probe:
                probe.write(b"shiliu startup probe")
                probe.seek(0)
                if probe.read() != b"shiliu startup probe":
                    raise OSError()
        except OSError:
            raise StorageError("artifact_root_unavailable") from None

        with self.read() as conn:
            self._check_versions(conn)
            versions = conn.execute("SELECT version_num FROM shiliu.alembic_version").fetchall()
            if versions != [{"version_num": revision}]:
                raise StorageError("revision_mismatch")
            from shiliu.retrieval.bm25 import check_index
            check_index(conn)
            owner = conn.execute(
                "SELECT w.id FROM shiliu.workspaces w JOIN shiliu.users u "
                "ON u.id=w.owner_user_id WHERE w.id=%s AND u.id=%s AND w.kind='personal'",
                (context.workspace_id, context.user_id),
            ).fetchone()
            if owner is None:
                raise StorageError("default_ownership_mismatch")
