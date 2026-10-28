"""Closed SQLite input, bounded stable-PK readers; never opens a product path.

The caller validates the complete schema and source identity before constructing
these views. Each iterator owns/closes its read-only handle, even on rejection.
"""
from __future__ import annotations
from collections.abc import Sequence
from contextlib import contextmanager
import sqlite3

from shiliu.migration.values import MigrationRejected

BATCH_SIZE = 128


def identifier(name):
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def closed_reader(source):
    # immutable must never silently ignore a committed WAL. These are explicitly
    # closed input snapshots; active candidates use the separate read-only audit.
    if any(p.exists() and p.stat().st_size for p in
           (source.with_name(source.name+'-wal'), source.with_name(source.name+'-journal'))):
        raise MigrationRejected('source_not_closed')
    conn = sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1', uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        yield conn
    finally:
        conn.close()


class SourceRows(Sequence):
    def __init__(self, source, name, pk, count):
        self.source, self.name, self.pk, self.count = source, name, pk, count

    def __len__(self):
        return self.count

    def batches(self, size=BATCH_SIZE):
        if not 1 <= size <= 1000:
            raise ValueError('invalid migration batch size')
        keys = ','.join(map(identifier, self.pk))
        last = None
        with closed_reader(self.source) as conn:
            while True:
                where = '' if last is None else ' WHERE ('+keys+') > ('+','.join('?' for _ in self.pk)+')'
                rows = [dict(r) for r in conn.execute(
                    'SELECT rowid AS __source_rowid,* FROM '+identifier(self.name)+where+
                    ' ORDER BY '+keys+' LIMIT ?', [*(last or ()), size])]
                if not rows:
                    return
                if any(r[k] is None for r in rows for k in self.pk):
                    raise MigrationRejected('null_source_primary_key', table_name=self.name)
                yield rows
                last = tuple(rows[-1][k] for k in self.pk)

    def __iter__(self):
        for batch in self.batches():
            yield from batch

    def __getitem__(self, index):
        # Compatibility for diagnostic callers; import never uses OFFSET.
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            return [self[i] for i in range(start, stop, step)]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        with closed_reader(self.source) as conn:
            return dict(conn.execute('SELECT rowid AS __source_rowid,* FROM '+identifier(self.name)+
                ' ORDER BY '+','.join(map(identifier, self.pk))+' LIMIT 1 OFFSET ?', (index,)).fetchone())

    def only(self, key, value):
        with closed_reader(self.source) as conn:
            rows = conn.execute('SELECT rowid AS __source_rowid,* FROM '+identifier(self.name)+
                ' WHERE '+identifier(key)+' IS ? LIMIT 2', (value,)).fetchall()
        if len(rows) != 1:
            raise MigrationRejected('missing_or_ambiguous_source_parent', table_name=self.name)
        return dict(rows[0])


class BatchSource(dict):
    """Iterate only a current batch; parent lookup stays an indexed source read."""
    def __init__(self, raw, name, batch):
        super().__init__({name: batch})
        self.raw = raw

    def parent(self, table, key, value):
        return self.raw[table].only(key, value)


class ConvertedRows(Sequence):
    def __init__(self, identity, raw, name):
        self.identity, self.raw, self.name = identity, raw, name

    def __len__(self):
        return len(self.raw[self.name])

    def convert(self, batch):
        from shiliu.migration.snapshot import convert_snapshot
        return convert_snapshot(self.identity, BatchSource(self.raw, self.name, batch), artifacts=False)[self.name]

    def batches(self, size=BATCH_SIZE):
        for raw in self.raw[self.name].batches(size):
            yield raw, self.convert(raw)

    def __iter__(self):
        for _, batch in self.batches():
            yield from batch

    def __getitem__(self, index):
        raw = self.raw[self.name][index]
        if isinstance(index, slice):
            return self.convert(raw)
        return self.convert([raw])[0]


class SourceTables(dict):
    pass


def converted_tables(identity, raw):
    from shiliu.migration.snapshot import convert_snapshot
    result = {name: ConvertedRows(identity, raw, name) for name in raw}
    generated = convert_snapshot(dict(identity, synthetic_vectors=[]), {})
    if identity['synthetic_vectors']:
        units = [raw['retrieval_units'].only('unit_id', v['unit_id']) for v in identity['synthetic_vectors']]
        generated.update(convert_snapshot(identity, BatchSource(raw, 'retrieval_units', units)))
        generated.pop('retrieval_units', None)
    result.update(generated)
    return result
