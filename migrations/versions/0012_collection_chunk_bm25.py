"""Shared partial BM25 index for Collection transcript chunks."""
from pathlib import Path
from alembic import op
revision = '0012_collection_chunk_bm25'
down_revision = '0011_research_candidate_boundary'
branch_labels = None
depends_on = None

def upgrade():
    source = Path(__file__).resolve().parents[1] / 'sql' / '0012.sql'
    op.get_bind().connection.driver_connection.execute(source.read_text(encoding='utf-8'), prepare=False)

def downgrade():
    raise RuntimeError('Irreversible schema/data migration: restore a verified PG and Artifact backup')
