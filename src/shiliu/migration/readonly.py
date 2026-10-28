"""Explicit closed historical SQLite reader; no default paths or creation.

Runtime modules do not import historical readers. Never ignore a committed WAL
by requesting immutable on an active input; closed inputs reject journals first.
"""
from pathlib import Path
import sqlite3
from shiliu.migration.values import MigrationRejected


class _ClosedSnapshot(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()


def connect_snapshot(source):
    path=Path(source).absolute()
    if path.is_symlink() or not path.is_file():raise MigrationRejected('historical_snapshot_missing_or_symlink')
    for suffix in ('-wal','-journal'):
        sidecar=path.with_name(path.name+suffix)
        if sidecar.is_symlink() or (sidecar.exists() and sidecar.stat().st_size):
            raise MigrationRejected('historical_snapshot_not_closed')
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True,factory=_ClosedSnapshot)
    conn.execute('PRAGMA query_only=ON')
    return conn
