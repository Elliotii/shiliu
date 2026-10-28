"""Review unattended video source patches."""

from pathlib import Path
from alembic import op

revision = "0014_assistant_source_patch"
down_revision = "0013_assistant_notifications"
branch_labels = None
depends_on = None


def upgrade():
    source = Path(__file__).resolve().parents[1] / "sql" / "0014.sql"
    op.get_bind().connection.driver_connection.execute(
        source.read_text(encoding="utf-8"), prepare=False
    )


def downgrade():
    raise RuntimeError(
        "Irreversible schema/data migration: restore a verified PG and Artifact backup"
    )
