"""Separate Wiki privacy fences from ordinary Memory corrections."""

from pathlib import Path
from alembic import op

revision = "0015_wiki_source_suppression"
down_revision = "0014_assistant_source_patch"
branch_labels = None
depends_on = None


def upgrade():
    source = Path(__file__).resolve().parents[1] / "sql" / "0015.sql"
    op.get_bind().connection.driver_connection.execute(
        source.read_text(encoding="utf-8"), prepare=False
    )


def downgrade():
    raise RuntimeError(
        "Irreversible schema/data migration: restore a verified PG and Artifact backup"
    )
