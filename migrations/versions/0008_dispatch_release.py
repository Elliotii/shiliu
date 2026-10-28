"""Allow a proven-not-sent model dispatch reservation to be released."""
from pathlib import Path
from alembic import op

revision = '0008_dispatch_release'
down_revision = '0007_collection_profiles'
branch_labels = None
depends_on = None


def upgrade():
    source = Path(__file__).resolve().parents[1] / 'sql' / '0008.sql'
    op.get_bind().connection.driver_connection.execute(source.read_text(encoding='utf-8'), prepare=False)


def downgrade():
    raise RuntimeError('Irreversible schema/data migration: restore a verified PG and Artifact backup')
