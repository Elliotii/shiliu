"""Preserve candidate boundary versus inner artifact source checkpoint."""
from pathlib import Path
from alembic import op
revision = '0011_research_candidate_boundary'
down_revision = '0010_research_control_lineage'
branch_labels = None
depends_on = None

def upgrade():
    source = Path(__file__).resolve().parents[1] / 'sql' / '0011.sql'
    op.get_bind().connection.driver_connection.execute(source.read_text(encoding='utf-8'), prepare=False)

def downgrade():
    raise RuntimeError('Irreversible schema/data migration: restore a verified PG and Artifact backup')
