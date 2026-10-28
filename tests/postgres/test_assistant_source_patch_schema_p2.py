"""0013 -> 0014 on real PG, preserving existing merge ownership constraints."""

import psycopg
import pytest
from psycopg.rows import dict_row
from schema_support import formal_target
from seed_rows import SyntheticGraph

from shiliu.config import LIBPQ_DISABLED_PASSFILE, load_postgres_config
from shiliu.migration.schema import HEAD_REVISION, MIGRATIONS, upgrade


def test_0013_to_0014_constraints_and_resources():
    assert HEAD_REVISION == "0014_assistant_source_patch"
    assert (MIGRATIONS / "sql" / "0014.sql").is_file()
    assert (MIGRATIONS / "versions" / "0014_assistant_source_patch.py").is_file()
    with formal_target(
        load_postgres_config(), revisions=("0012_collection_chunk_bm25",)
    ) as (runtime, admin):
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
            upgrade(c, "0013_assistant_notifications")
        with psycopg.connect(
            admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE, row_factory=dict_row
        ) as c:
            c.execute("SET search_path TO shiliu,public")
            graph = SyntheticGraph(c)
            p = graph.ensure("assistant_wiki_proposals")
            c.execute("UPDATE assistant_wiki_proposals SET kind='merge'")
            c.execute(
                "INSERT INTO users(id,display_name) VALUES('other','Synthetic other')"
            )
            c.execute(
                "INSERT INTO workspaces(id,kind,owner_user_id) VALUES('personal:other','personal','other')"
            )
            outsider = SyntheticGraph(
                c,
                workspace="personal:other",
                user="other",
                suffix="_other",
                numeric_id=2,
            ).ensure("assistant_wiki_proposals")
            cross_space = SyntheticGraph(c, suffix="_space3", numeric_id=3).ensure(
                "assistant_wiki_pages"
            )

            before = {
                r["conname"]
                for r in c.execute(
                    "SELECT conname FROM pg_constraint WHERE conrelid='assistant_wiki_proposals'::regclass"
                )
            }
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
            upgrade(c, "head")
        with psycopg.connect(
            runtime.database_url, passfile=LIBPQ_DISABLED_PASSFILE, row_factory=dict_row
        ) as c:
            c.execute("SET search_path TO shiliu,public")
            after = {
                r["conname"]
                for r in c.execute(
                    "SELECT conname FROM pg_constraint WHERE conrelid='assistant_wiki_proposals'::regclass"
                )
            }
            assert before.issubset(after)
            old = c.execute(
                "SELECT * FROM assistant_wiki_proposals WHERE id=%s", (p["id"],)
            ).fetchone()
            assert (
                old["content_version"] == 1
                and old["kind"] == "merge"
                and old["decided_at"] is None
            )
            c.execute(
                "INSERT INTO assistant_wiki_proposals(workspace_id,principal_id,id,space_id,kind,target_page_id,target_version,input_fingerprint,payload_json,status,created_at,updated_at,supersedes_id) SELECT workspace_id,principal_id,'p2',space_id,'source_patch',target_page_id,target_version,'p2','{}','pending',clock_timestamp(),clock_timestamp(),id FROM assistant_wiki_proposals WHERE id=%s",
                (p["id"],),
            )
            assert c.execute(
                "SELECT source_page_id,source_version FROM assistant_wiki_proposals WHERE id='p2'"
            ).fetchone() == {"source_page_id": None, "source_version": None}
            for clause, error in [
                ("content_version=0", psycopg.errors.CheckViolation),
                ("status='invalid'", psycopg.errors.CheckViolation),
                ("supersedes_id='p2'", psycopg.errors.CheckViolation),
                ("supersedes_id='unknown'", psycopg.errors.ForeignKeyViolation),
                (
                    f"supersedes_id='{outsider['id']}'",
                    psycopg.errors.ForeignKeyViolation,
                ),
                (
                    f"target_page_id='{cross_space['id']}'",
                    psycopg.errors.ForeignKeyViolation,
                ),
                ("principal_id='other'", psycopg.errors.ForeignKeyViolation),
                ("space_id=9999", psycopg.errors.ForeignKeyViolation),
                ("source_page_id=target_page_id", psycopg.errors.CheckViolation),
            ]:
                with pytest.raises(error):
                    with c.transaction():
                        c.execute(
                            "UPDATE assistant_wiki_proposals SET "
                            + clause
                            + " WHERE id='p2'"
                        )
            ix = c.execute(
                "SELECT indexdef FROM pg_indexes WHERE indexname='assistant_source_patch_pending'"
            ).fetchone()["indexdef"]
            assert "status = 'pending'" in ix
