"""Alembic runs only on a caller-injected migration connection.

No environment DSN lookup, application import, automatic runtime upgrade or DDL
on an implicit target. The migration command owns credentials and transaction.
"""
from alembic import context

connection = context.config.attributes.get('connection')
if connection is None:
    raise RuntimeError('An explicit managed migration connection is required')
connection.exec_driver_sql('CREATE SCHEMA IF NOT EXISTS shiliu')
context.configure(connection=connection, version_table='alembic_version',
                  version_table_schema='shiliu', transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
