"""Assistant business-result notifications."""
from pathlib import Path
from alembic import op
revision = '0013_assistant_notifications'
down_revision = '0012_collection_chunk_bm25'
branch_labels = None
depends_on = None

def upgrade():
    source = Path(__file__).resolve().parents[1] / 'sql' / '0013.sql'
    op.get_bind().connection.driver_connection.execute(source.read_text(encoding='utf-8'), prepare=False)

def downgrade():
    raise RuntimeError('Irreversible schema/data migration: restore a verified PG and Artifact backup')
