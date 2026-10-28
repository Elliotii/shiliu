from __future__ import annotations
from shiliu.config import LIBPQ_DISABLED_PASSFILE

from dataclasses import replace
from datetime import date, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import quote

import psycopg
import pytest
from pgvector import Vector
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from shiliu.storage.dto import row_dto
from shiliu.storage.errors import StorageError
from shiliu.storage.postgres import PgDatabase, PoolSettings
from shiliu.storage.scope import personal_context
from isolation import TASK_ROOT, guard


def count(db):
    with db.read() as conn:
        return conn.execute('SELECT count(*) AS n FROM shiliu.probe').fetchone()['n']


def test_commit_rollback_reborrow(pg):
    with pg.transaction() as conn:
        first_pid = conn.info.backend_pid
        assert conn.execute('SHOW transaction_isolation').fetchone()['transaction_isolation'] == 'read committed'
        conn.execute('INSERT INTO shiliu.probe (id) VALUES (%s)', (1,))
    assert count(pg) == 1
    with pytest.raises(RuntimeError, match='caller'):
        with pg.transaction() as conn:
            conn.execute('INSERT INTO shiliu.probe (id) VALUES (2)')
            raise RuntimeError('caller')
    assert count(pg) == 1
    with pg.transaction() as conn:
        assert conn.info.backend_pid == first_pid
        conn.execute('INSERT INTO shiliu.probe (id) VALUES (3)')
    assert count(pg) == 2


def test_read_only_and_snapshot(pg):
    with pytest.raises(StorageError) as caught:
        with pg.read() as conn:
            conn.execute('INSERT INTO shiliu.probe (id) VALUES (1)')
    assert caught.value.category == 'read_only'
    with pg.transaction(read_only=True, isolation='repeatable read') as snapshot:
        assert snapshot.execute('SELECT count(*) AS n FROM shiliu.probe').fetchone()['n'] == 0
        with pg.transaction() as writer:
            assert writer.info.backend_pid != snapshot.info.backend_pid
            writer.execute('INSERT INTO shiliu.probe (id) VALUES (1)')
        assert snapshot.execute('SELECT count(*) AS n FROM shiliu.probe').fetchone()['n'] == 0
    assert count(pg) == 1


def test_session_reset_and_no_idle_transaction(pg, pg_target):
    with pg.transaction(isolation='serializable', read_only=True) as conn:
        conn.execute("SET TIME ZONE 'Asia/Shanghai'")
        conn.execute("SET search_path TO public")
        conn.execute("SELECT pg_advisory_lock(17893)")
    with pg.transaction() as conn:
        assert conn.read_only is False
        assert conn.execute('SHOW TimeZone').fetchone()['TimeZone'] == 'UTC'
        assert conn.execute('SHOW search_path').fetchone()['search_path'] == 'pg_catalog, shiliu'
        assert conn.execute('SHOW transaction_isolation').fetchone()['transaction_isolation'] == 'read committed'
        assert conn.execute("SELECT count(*) AS n FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'").fetchone()['n'] == 0
    runtime, admin = pg_target
    guard(admin, admin=True)
    # Observe from a separate real admin connection; no borrowed pool connection.
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as monitor:
        deadline = time.monotonic() + 1
        while True:
            rows = monitor.execute("SELECT state, query, xact_start FROM pg_stat_activity "
                                   "WHERE application_name='shiliu-pg' AND datname=current_database()").fetchall()
            if rows and all(row[0] == 'idle' for row in rows):
                break
            # Pool growth may still be registering adapters via TypeInfo.fetch's
            # short transaction. A lingering transaction must fail within 1s.
            if time.monotonic() > deadline:
                pytest.fail(f'Pool connections failed to become idle: {rows}')
            time.sleep(.02)


def test_json_time_date_bool_bigint_and_all_connection_vectors(pg):
    corpus = json.loads(Path('tests/fixtures/postgres_migration/roundtrip_cases.json').read_text())
    vector = Vector([1.] + [0.] * 511)
    timestamps = [datetime.fromisoformat(value) for value in corpus['timestamps']]
    with pg.transaction() as first, pg.transaction() as second:
        assert first.info.backend_pid != second.info.backend_pid
        for conn in (first, second):
            value = conn.execute('SELECT %s::shiliu.vector AS v', (vector,)).fetchone()['v']
            assert value.to_list() == vector.to_list()
        first.execute('INSERT INTO shiliu.probe VALUES (%s,%s,%s,%s,%s,%s)',
                      (2**53+1, Jsonb({'中文': [3, 1, 2], 'null': None}), timestamps[0], date(2026,10,23), True, vector))
    with pg.read() as conn:
        row = conn.execute('SELECT * FROM shiliu.probe').fetchone()
        assert isinstance(row, dict)
        assert row['at'] == timestamps[1]
        result = row_dto(row, timestamps=('at', 'absent'), dates=('day',))
        assert result['at'] == '2026-10-23T00:01:02+00:00'
        assert result['day'] == '2026-10-23' and result['payload'] == {'中文':[3,1,2], 'null':None}
        assert result['embedding'].to_list() == vector.to_list()
        assert type(result['flag']) is bool and result['flag'] is True
        assert type(result['id']) is int and result['id'] == 2**53+1
        assert 'absent' not in result and 'absent' not in result['payload']
        for document in corpus['json_documents']:
            obj = json.loads(document)
            row = conn.execute('SELECT %s::jsonb AS value, %s::jsonb IS NULL AS sql_null',
                               (Jsonb(obj), Jsonb(obj))).fetchone()
            assert row == {'value': obj, 'sql_null': False}
        assert conn.execute('SELECT %s::jsonb AS value, %s::jsonb IS NULL AS sql_null',
                            (None, None)).fetchone() == {'value': None, 'sql_null': True}


def test_pool_exhaustion_bounded_and_reusable(pg):
    with pg.transaction(), pg.transaction():
        start = time.monotonic()
        with pytest.raises(StorageError) as caught:
            with pg.read():
                pytest.fail('pool over-allocated')
        elapsed = time.monotonic() - start
    assert caught.value.category == 'pool_timeout' and .4 <= elapsed < 2
    assert count(pg) == 0


def test_sql_errors_timeouts_and_reuse(pg):
    with pytest.raises(StorageError) as caught:
        with pg.transaction() as conn:
            conn.execute('INSERT INTO shiliu.probe (id) VALUES (1)')
            conn.execute('SELECT 1/0')
    assert caught.value.sqlstate == '22012' and count(pg) == 0
    with pytest.raises(StorageError) as caught:
        with pg.transaction() as conn:
            conn.execute('SELECT pg_sleep(2)')
    assert caught.value.category == 'statement_cancelled' and count(pg) == 0
    with pg.transaction() as conn:
        conn.execute('INSERT INTO shiliu.probe (id) VALUES (1)')
    with pg.transaction() as locker:
        locker.execute('SELECT id FROM shiliu.probe WHERE id=1 FOR UPDATE')
        with pytest.raises(StorageError) as caught:
            with pg.transaction() as blocked:
                blocked.execute('UPDATE shiliu.probe SET flag=true WHERE id=1')
        assert caught.value.category == 'lock_timeout'
    assert count(pg) == 1
    with pytest.raises(StorageError) as caught:
        with pg.transaction() as conn:
            conn.execute('INSERT INTO shiliu.probe (id, payload) VALUES (1,%s)', (Jsonb('PRIVATE'),))
    assert caught.value.category == 'unique_conflict' and 'PRIVATE' not in str(caught.value)
    assert caught.value.__cause__ is None
    assert count(pg) == 1


@pytest.mark.parametrize('state', ['40001', '40P01'])
def test_opt_in_pure_db_retry_is_bounded_and_rolls_back(pg, state):
    calls = []
    def operation(conn):
        calls.append(1)  # Test instrumentation, no business side effect.
        conn.execute('INSERT INTO shiliu.probe (id) VALUES (1)')
        if len(calls) < 3:
            conn.execute("DO $$ BEGIN RAISE EXCEPTION 'synthetic' USING ERRCODE = '" + state + "'; END $$")
        return 17
    assert pg.replay_pure_db(operation) == 17
    assert len(calls) == 3 and count(pg) == 1
    calls.clear()
    def always_fails(conn):
        calls.append(1)
        conn.execute("DO $$ BEGIN RAISE EXCEPTION 'synthetic' USING ERRCODE = '" + state + "'; END $$")
    with pytest.raises(StorageError):
        pg.replay_pure_db(always_fails)
    assert len(calls) == 3


def test_nonretry_errors_and_caller_exceptions_not_replayed(pg):
    calls = []
    def operation(conn):
        calls.append(1)
        conn.execute('SELECT 1/0')
    with pytest.raises(StorageError):
        pg.replay_pure_db(operation)
    assert len(calls) == 1
    calls.clear()
    def caller(conn):
        calls.append(1)
        raise RuntimeError('caller error')
    with pytest.raises(RuntimeError):
        pg.replay_pure_db(caller)
    assert len(calls) == 1


def test_runtime_cannot_ddl_install_or_disable_triggers(pg, pg_target):
    for statement in ('CREATE TABLE shiliu.forbidden (id int)', 'ALTER TABLE shiliu.probe DISABLE TRIGGER ALL',
                      "SET session_replication_role = 'replica'", 'CREATE SCHEMA forbidden'):
        with pytest.raises(StorageError) as caught:
            with pg.transaction() as conn:
                conn.execute(statement)
        assert caught.value.sqlstate == '42501'
    runtime, admin = pg_target
    guard(admin, admin=True)
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as conn:
        conn.execute('DROP EXTENSION plpgsql')
    try:
        with pytest.raises(StorageError) as caught:
            with pg.transaction() as conn:
                conn.execute('CREATE EXTENSION plpgsql')
        assert caught.value.sqlstate == '42501'
    finally:
        guard(admin, admin=True)
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as conn:
            conn.execute('CREATE EXTENSION plpgsql')
    assert count(pg) == 0


def test_close_repeated_close_and_subprocess_exit(pg_target):
    runtime, _ = pg_target
    db = PgDatabase(runtime, settings=PoolSettings(timeout=.5))
    db.open()
    db.close()
    db.close()
    with pytest.raises(StorageError) as caught:
        with db.read():
            pytest.fail('closed pool borrowed')
    assert caught.value.category == 'pool_unavailable'
    result = subprocess.run([sys.executable, '-c', '''
import os
from shiliu.config import load_postgres_config
from shiliu.storage.postgres import PgDatabase
try:
    with PgDatabase(load_postgres_config()) as db:
        with db.transaction() as conn:
            conn.execute('SELECT 1')
            raise RuntimeError('synthetic exit')
except RuntimeError:
    pass
'''], timeout=10, capture_output=True, text=True,
        env=dict(os.environ, SHILIU_DATABASE_URL=runtime.database_url,
                 SHILIU_ARTIFACT_ROOT=str(runtime.artifact_root), SHILIU_ENV='test'))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('uri', [False, True])
def test_connection_failure_redacts_pool_worker_logs(pg_target, caplog, uri):
    runtime, _ = pg_target
    name = 'shiliu_w01_test_missing_private'
    if uri:
        dsn = f'postgresql://shiliu_w01_runtime:PRIVATE@/{name}?host={quote(str(TASK_ROOT / "socket"), safe="")}&port=55483'
    else:
        dsn = f"host={TASK_ROOT}/socket port=55483 dbname={name} user=shiliu_w01_runtime password=PRIVATE"
    cfg = replace(runtime, database_url=dsn)
    guard(cfg)
    start = time.monotonic()
    db = PgDatabase(cfg, settings=PoolSettings(timeout=.25))
    with pytest.raises(StorageError) as caught:
        db.open()
    db.close()
    assert time.monotonic() - start < 2
    assert 'PRIVATE' not in str(caught.value) + caplog.text + repr(cfg) + repr(db)
    assert dsn not in caplog.text and name not in caplog.text


def test_missing_startup_contract_and_test_only_controls(pg, pg_target):
    with pytest.raises(StorageError) as caught:
        pg.validate_startup(revision='w01_test_only', context=personal_context())
    assert caught.value.sqlstate == '42P01'
    runtime, admin = pg_target
    guard(admin, admin=True)
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as conn:
        conn.execute('CREATE TABLE shiliu.alembic_version (version_num text)')
        conn.execute('CREATE TABLE shiliu.users (id text)')
        conn.execute('CREATE TABLE shiliu.workspaces (id text, owner_user_id text, kind text)')
        conn.execute("INSERT INTO shiliu.alembic_version VALUES ('w01_test_only')")
        conn.execute("INSERT INTO shiliu.users VALUES ('local_operator')")
        conn.execute("INSERT INTO shiliu.workspaces VALUES ('personal:local_operator','local_operator','personal')")
        conn.execute('GRANT SELECT ON ALL TABLES IN SCHEMA shiliu TO shiliu_w01_runtime')
    try:
        pg.validate_startup(revision='w01_test_only', context=personal_context())
        with pytest.raises(StorageError, match='revision_mismatch'):
            pg.validate_startup(revision='wrong', context=personal_context())
        with pytest.raises(StorageError, match='default_ownership_mismatch'):
            pg.validate_startup(revision='w01_test_only', context=replace(personal_context(), user_id='client'))
        other = PgDatabase(replace(runtime, artifact_root=TASK_ROOT / 'missing-artifacts'))
        try:
            # Artifact probe fails before any connection is opened/borrowed.
            with pytest.raises(StorageError, match='artifact_root_unavailable'):
                other.validate_startup(revision='w01_test_only', context=personal_context())
        finally:
            other.close()
        assert not (TASK_ROOT / 'missing-artifacts').exists()
    finally:
        guard(admin, admin=True)
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as conn:
            conn.execute('DROP TABLE shiliu.alembic_version, shiliu.users, shiliu.workspaces')


def test_extension_schema_is_checked_and_failure_is_bounded(pg_target):
    runtime, admin = pg_target
    guard(admin, admin=True)
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as conn:
        conn.execute('CREATE SCHEMA wrong_vector')
        conn.execute('ALTER EXTENSION vector SET SCHEMA wrong_vector')
    try:
        start = time.monotonic()
        with pytest.raises(StorageError, match='vector_version_or_schema_mismatch'):
            PgDatabase(runtime, settings=PoolSettings(timeout=.3)).open()
        assert time.monotonic() - start < 2
    finally:
        guard(admin, admin=True)
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as conn:
            conn.execute('ALTER EXTENSION vector SET SCHEMA shiliu')
            conn.execute('DROP SCHEMA wrong_vector')


def test_pg_module_import_and_constructor_open_no_connections(pg_target):
    runtime, _ = pg_target
    result = subprocess.run([sys.executable, '-c', '''
import sys
sys.addaudithook(lambda event, args: (_ for _ in ()).throw(AssertionError(event))
                if event in {'socket.__new__', 'socket.connect'} else None)
import psycopg
psycopg.Connection.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError('connect'))
from shiliu.config import load_postgres_config
from shiliu.storage.postgres import PgDatabase
PgDatabase(load_postgres_config()).close()
'''], timeout=10, capture_output=True, text=True,
        env=dict(os.environ, SHILIU_DATABASE_URL=runtime.database_url,
                 SHILIU_ARTIFACT_ROOT=str(runtime.artifact_root), SHILIU_ENV='test'))
    assert result.returncode == 0, result.stderr


def test_task_service_restart_recovers_without_replay(pg, pg_target):
    # Only the hardcoded, marker-verified task instance; never an unknown service.
    runtime, _ = pg_target
    guard(runtime)
    script = Path('scripts/postgres_w01_local.py').resolve()
    subprocess.run([sys.executable, str(script), 'stop'], check=True, capture_output=True, timeout=15)
    try:
        with pytest.raises(StorageError) as caught:
            with pg.read():
                pytest.fail('stopped instance borrowed')
        assert caught.value.category in {'pool_timeout', 'connection_unavailable'}
    finally:
        subprocess.run([sys.executable, str(script), 'start'], check=True, capture_output=True, timeout=15)
    # The failed read is not transparently replayed. A new explicit operation
    # succeeds after a replacement connection has been configured by the pool.
    deadline = time.monotonic() + 3
    while True:
        try:
            assert count(pg) == 0
            break
        except StorageError:
            if time.monotonic() > deadline:
                raise


def test_adapter_failure_is_redacted_and_pool_closes(pg_target, monkeypatch, caplog):
    runtime, _ = pg_target
    import shiliu.storage.postgres as module
    def fail(conn):
        raise RuntimeError('PRIVATE adapter failure')
    monkeypatch.setattr(module, 'register_vector', fail)
    db = PgDatabase(runtime, settings=PoolSettings(timeout=.25))
    with pytest.raises(StorageError, match='vector_adapter_registration_failed'):
        db.open()
    db.close()
    assert 'PRIVATE' not in caplog.text


def test_product_default_timeouts_and_connection_state(pg_target):
    runtime, _ = pg_target
    with PgDatabase(runtime) as db:
        assert db.settings == PoolSettings(min_size=1, max_size=8, timeout=5,
                lock_timeout_ms=3000, statement_timeout_ms=15000, idle_timeout_ms=30000)
        with db.transaction() as conn:
            assert conn.execute('SHOW lock_timeout').fetchone()['lock_timeout'] == '3s'
            assert conn.execute('SHOW statement_timeout').fetchone()['statement_timeout'] == '15s'
            assert conn.execute('SHOW idle_in_transaction_session_timeout').fetchone()['idle_in_transaction_session_timeout'] == '30s'
        # Transaction context has committed before release; reset may run in a
        # pool worker, so force a borrow to wait for its completion.
        with db.read() as conn:
            assert conn.info.transaction_status == TransactionStatus.INTRANS


def test_terminated_connection_rolls_back_and_replacement_is_adapted(pg, pg_target):
    runtime, admin = pg_target
    guard(admin, admin=True)
    with pytest.raises(StorageError) as caught:
        with pg.transaction() as victim:
            pid = victim.info.backend_pid
            victim.execute('INSERT INTO shiliu.probe (id) VALUES (91)')
            with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as killer:
                row = killer.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                                     "WHERE pid=%s AND datname=current_database() "
                                     "AND application_name='shiliu-pg'", (pid,)).fetchone()
                assert row == (True,)
            victim.execute('SELECT 1')
    assert caught.value.category == 'connection_unavailable'
    assert count(pg) == 0
    with pg.read() as conn:
        assert conn.info.backend_pid != pid
        assert conn.execute('SELECT %s::shiliu.vector AS v',
                            (Vector([1.] + [0.] * 511),)).fetchone()['v'].to_list()[0] == 1


def test_wrong_server_pin_fails_closed(pg_target, monkeypatch):
    runtime, _ = pg_target
    import shiliu.storage.postgres as module
    monkeypatch.setattr(module, 'POSTGRES_VERSION', 180005)
    with pytest.raises(StorageError, match='server_version_mismatch'):
        PgDatabase(runtime, settings=PoolSettings(timeout=.25)).open()


def test_explicit_pool_disables_default_passfile_and_ambient_pg_override(pg_target,monkeypatch):
    runtime,_=pg_target
    with PgDatabase(runtime) as db:
        with db.read() as conn:
            assert conn.info.get_parameters().get('passfile')==LIBPQ_DISABLED_PASSFILE
    monkeypatch.setenv('PGHOSTADDR','127.0.0.1')
    with pytest.raises(StorageError,match='implicit_libpq_environment_rejected'):
        PgDatabase(runtime)
