"""Safe error boundary: never carry driver messages, SQL, parameters or conninfo."""
from __future__ import annotations

from psycopg import Error, OperationalError
from psycopg_pool import PoolClosed, PoolTimeout, TooManyRequests


class StorageError(RuntimeError):
    def __init__(self, category: str, sqlstate: str | None = None) -> None:
        self.category = category
        self.sqlstate = sqlstate
        super().__init__(f"PostgreSQL {category}" + (f" (SQLSTATE {sqlstate})" if sqlstate else ""))


def safe_error(error: Exception) -> StorageError:
    if isinstance(error, StorageError):
        return error
    state = getattr(error, "sqlstate", None)
    if isinstance(error, PoolTimeout):
        category = "pool_timeout"
    elif isinstance(error, (PoolClosed, TooManyRequests)):
        category = "pool_unavailable"
    elif state in {"40001", "40P01"}:
        category = "transaction_retryable"
    elif state == "23505":
        category = "unique_conflict"
    elif state == "55P03":
        category = "lock_timeout"
    elif state == "57014":
        category = "statement_cancelled"
    elif state == "25006":
        category = "read_only"
    elif isinstance(error, OperationalError) or (state and state.startswith("08")):
        category = "connection_unavailable"
    elif isinstance(error, Error):
        category = "sql_error"
    else:
        category = "configuration_failed"
    return StorageError(category, state)
