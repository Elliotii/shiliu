from __future__ import annotations
from shiliu.config import LIBPQ_DISABLED_PASSFILE

import os
import uuid
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from shiliu.config import PostgresConfig
from shiliu.storage.postgres import PgDatabase, PoolSettings
from isolation import RUN_USER, TASK_ROOT, guard


@pytest.fixture(scope='session')
def pg_target():
    # No unknown DSN or implicit libpq default, including when tests are selected
    # without this task's service. Missing environment is an explicit test error.
    config = PostgresConfig(os.environ.get('SHILIU_DATABASE_URL', ''),
                            Path(os.environ.get('SHILIU_ARTIFACT_ROOT', '')),
                            os.environ.get('SHILIU_ENV', ''))
    parts = guard(config, admin=True)
    name = 'shiliu_w01_test_' + uuid.uuid4().hex[:12]
    runtime_parts = dict(parts, dbname=name, user=RUN_USER)
    runtime_parts.pop('password', None)
    runtime = replace(config, database_url=make_conninfo(**runtime_parts))
    guard(runtime)
    admin = replace(config, database_url=make_conninfo(**dict(parts, dbname=name)))
    guard(admin, admin=True)
    with psycopg.connect(config.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as control:
        if (control.info.server_version != 180006 or
                control.execute("SHOW data_directory").fetchone()[0] != str(TASK_ROOT / 'data')):
            raise RuntimeError('Refusing unexpected W01 test instance/version')
        roles = control.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                                "FROM pg_roles WHERE rolname=%s", (RUN_USER,)).fetchone()
        if roles != (False, False, False, False, False):
            raise RuntimeError('Refusing privileged W01 runtime role')
        control.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as conn:
            conn.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))
            conn.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
            conn.execute('CREATE SCHEMA shiliu')
            conn.execute("CREATE EXTENSION vector WITH SCHEMA shiliu VERSION '0.8.7'")
            from shiliu.retrieval.bm25 import install_extension, grant_query_access
            install_extension(conn)
            grant_query_access(conn, RUN_USER)
            conn.execute('CREATE TABLE shiliu.probe (id bigint PRIMARY KEY, payload jsonb, '
                         'at timestamptz, day date, flag boolean, embedding shiliu.vector(512))')
            conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(
                sql.Identifier(name), sql.Identifier(RUN_USER)))
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA shiliu TO {}').format(sql.Identifier(RUN_USER)))
            conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA shiliu TO {}')
                         .format(sql.Identifier(RUN_USER)))
        yield runtime, admin
    finally:
        # Revalidate before every cleanup connection and destructive operation.
        guard(config, admin=True)
        guard(admin, admin=True)
        with psycopg.connect(config.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as control:
            control.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest.fixture
def pg(pg_target):
    runtime, admin = pg_target
    guard(admin, admin=True)
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as conn:
        conn.execute('TRUNCATE shiliu.probe')
    guard(runtime)
    with PgDatabase(runtime, settings=PoolSettings(min_size=1, max_size=2, timeout=.5,
                    lock_timeout_ms=100, statement_timeout_ms=300, idle_timeout_ms=1000)) as db:
        yield db

@pytest.fixture
def collection_db():
    from schema_support import formal_target
    from shiliu.db import Database
    from shiliu.storage.scope import personal_context
    config=PostgresConfig(os.environ.get('SHILIU_DATABASE_URL',''),Path(os.environ.get('SHILIU_ARTIFACT_ROOT','')),os.environ.get('SHILIU_ENV',''))
    with formal_target(config) as (runtime,admin):
        with PgDatabase(runtime) as pg:
            yield Database(pg,personal_context())


@pytest.fixture
def retrieval(collection_db, tmp_path):
    from shiliu.artifacts import ArtifactStore
    from shiliu.retrieval.service import RetrievalService
    from shiliu.retrieval.dense import PgExactDenseIndex
    from test_collection_retrieval import FixedProvider
    artifacts = ArtifactStore(tmp_path / "formal", collection_db)
    lexical = RetrievalService(db=collection_db, artifacts=artifacts)
    provider = FixedProvider()
    dense = PgExactDenseIndex(db=collection_db, provider=provider, lexical=lexical)
    return collection_db, artifacts, lexical, dense
