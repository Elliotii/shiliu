from shiliu.config import LIBPQ_DISABLED_PASSFILE
import os
"""Formal schema tests use random child databases of the guarded task instance."""
from contextlib import contextmanager
from dataclasses import replace
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from shiliu.migration.schema import grant_roles, upgrade
from isolation import RUN_USER, guard

ETL_USER = 'shiliu_w01_etl'


@contextmanager
def formal_target(control_config, *, revisions=('head',)):
    parts = guard(control_config, admin=True)
    name = 'shiliu_w01_test_' + uuid.uuid4().hex[:12]
    admin = replace(control_config, database_url=make_conninfo(**dict(parts, dbname=name)))
    runtime_parts = dict(parts, dbname=name, user=RUN_USER)
    runtime_parts.pop('password', None)
    runtime = replace(admin, database_url=make_conninfo(**runtime_parts))
    guard(admin, admin=True)
    guard(runtime)
    with psycopg.connect(control_config.database_url,passfile=LIBPQ_DISABLED_PASSFILE, autocommit=True) as c:
        if c.info.server_version != 180006 or c.execute('SHOW data_directory').fetchone()[0] != str(__import__('isolation').TASK_ROOT/'data'):
            raise RuntimeError('Refusing unexpected version')
        if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(ETL_USER,)).fetchone():
            c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(ETL_USER)))
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        from shiliu.retrieval.bm25 import install_extension
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            install_extension(c)
        for revision in revisions:
            guard(admin, admin=True)
            with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
                upgrade(c,revision)
        if revisions and (revisions[-1]=='head' or revisions[-1] in ('0007_collection_profiles','0012_collection_chunk_bm25')):
            guard(admin, admin=True)
            with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
                c.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))
                for user in (RUN_USER,ETL_USER):
                    c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(name),sql.Identifier(user)))
                grant_roles(c,runtime_role=RUN_USER,etl_role=ETL_USER)
        yield runtime,admin
    finally:
        guard(control_config, admin=True)
        with psycopg.connect(control_config.database_url,passfile=LIBPQ_DISABLED_PASSFILE,autocommit=True) as c:
            c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
