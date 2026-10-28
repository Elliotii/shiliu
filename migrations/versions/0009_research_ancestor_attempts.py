"""Retain validated read-only ancestor checkpoint branch/replay lineage."""
from pathlib import Path
from alembic import op

revision = '0009_research_ancestor_attempts'
down_revision = '0008_dispatch_release'
branch_labels = None
depends_on = None


def upgrade():
    source = Path(__file__).resolve().parents[1] / 'sql' / '0009.sql'
    op.get_bind().connection.driver_connection.execute(source.read_text(encoding='utf-8'), prepare=False)


def downgrade():
    raise RuntimeError('Irreversible schema/data migration: restore a verified PG and Artifact backup')
