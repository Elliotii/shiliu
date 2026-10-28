"""Explicit reviewed PostgreSQL DDL; source mapping in contracts/schema26_target.json."""
from pathlib import Path
from alembic import op

revision = '0003_retrieval_artifacts'
down_revision = '0002_agent_domains'
branch_labels = None
depends_on = None


def upgrade():
    source = Path(__file__).resolve().parents[1] / 'sql' / '0003.sql'
    # Execute fixed DDL without an empty parameter tuple: SQL LIKE '%' must
    # remain literal, and a revision may contain several statements/functions.
    op.get_bind().connection.driver_connection.execute(source.read_text(encoding='utf-8'), prepare=False)


def downgrade():
    raise RuntimeError('Irreversible schema/data migration: restore a verified PG and Artifact backup')
