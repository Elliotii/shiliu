"""Keep source AUTOINCREMENT tombstone highwaters; never lower a PG sequence."""

from psycopg import sql
from shiliu.migration.safety import guard_source
from shiliu.migration.stream import closed_reader
from shiliu.migration.values import MigrationRejected


def floors(source, tables):
    with closed_reader(guard_source(source)) as c:
        counters = dict(c.execute("SELECT name,seq FROM sqlite_sequence"))
    result = {}
    for name, t in tables.items():
        if not t["source"] or name not in counters:
            continue
        sequence = counters[name]
        if type(sequence) is not int or sequence < 0:
            raise MigrationRejected("invalid_source_sequence_counter", table_name=name)
        primary = {c["name"] for c in t["source"]["columns"] if c["pk"]}
        for key, column in t["columns"].items():
            if column["identity"] and key in primary:
                result[name, key] = sequence
    return result


def check(conn, source, tables, *, calibrate=False):
    source_floors = floors(source, tables)
    checked = raised = 0
    for name, t in tables.items():
        for key, column in t["columns"].items():
            if not column["identity"]:
                continue
            maximum = (
                conn.execute(
                    sql.SQL("SELECT max({}) AS n FROM shiliu.{}").format(
                        sql.Identifier(key), sql.Identifier(name)
                    )
                ).fetchone()["n"]
                or 0
            )
            floor = max(maximum, source_floors.get((name, key), 0))
            sequence = conn.execute(
                "SELECT pg_get_serial_sequence(%s,%s) AS seq", ("shiliu." + name, key)
            ).fetchone()["seq"]
            if not sequence or len(sequence.split(".")) != 2:
                raise MigrationRejected(
                    "target_identity_sequence_missing", table_name=name
                )
            state = conn.execute(
                sql.SQL("SELECT last_value,is_called FROM {}").format(
                    sql.Identifier(*sequence.split("."))
                )
            ).fetchone()
            following = state["last_value"] + (1 if state["is_called"] else 0)
            if following <= floor:
                if not calibrate:
                    raise MigrationRejected(
                        "identity_sequence_below_source_highwater", table_name=name
                    )
                conn.execute("SELECT setval(%s::regclass,%s,true)", (sequence, floor))
                raised += 1
            checked += 1
    return {
        "identity_sequences_verified": checked,
        "source_autoincrement_counters": len(source_floors),
    }, raised
