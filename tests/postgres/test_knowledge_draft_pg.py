"""Retain current Draft -> Research -> confirmed knowledge contracts on PG."""

import pytest
from shiliu.knowledge_draft import KnowledgeDraftService
from test_research_knowledge_pg import knowledge_core  # noqa: F401
from test_research_outer_pg import outer_core  # noqa: F401


@pytest.fixture
def draft_core(knowledge_core, monkeypatch):  # noqa: F811
    import test_v5_6_goal2b_knowledge_draft as original

    core = knowledge_core
    core.knowledge_drafts = KnowledgeDraftService(
        db=core.db, product=core.research_product, knowledge=core.research_knowledge
    )
    monkeypatch.setattr(original, "_fixture_core", lambda paths: core)

    def drift(core):
        from shiliu.domain import SubtitleSegment

        video = core.db.get_video_by_source("BV0000000002")
        batch = core.artifacts.batch(video["id"])
        _, ref = batch.save_raw_subtitle(
            video["source_id"],
            [
                SubtitleSegment.model_validate(
                    {
                        "from": 0,
                        "to": 4,
                        "content": "底层字幕已变化，旧 Research Evidence 不再 current。",
                    }
                )
            ],
        )
        batch.commit(
            lambda conn: core.db.update_video(
                video["id"], raw_subtitle_path=ref, conn=conn
            )
        )

    monkeypatch.setattr(original, "_replace_fixture_source", drift)
    return core


@pytest.mark.parametrize(
    "contract",
    [
        "test_valid_research_draft_binds_exact_server_lineage_and_replay_fails_closed",
        "test_research_source_drift_blocks_confirm_before_publication",
        "test_unchanged_valid_research_draft_promotes_only_after_confirmation",
    ],
)
def test_original_research_draft_contract_on_pg(draft_core, app_paths, contract):
    import test_v5_6_goal2b_knowledge_draft as original

    getattr(original, contract)(app_paths)


def test_draft_native_json_immutable_and_parallel_command(draft_core):
    from concurrent.futures import ThreadPoolExecutor
    from test_v5_b_stage1_knowledge_workspace import _terminal_task
    from shiliu.knowledge_draft import (
        SaveKnowledgeDraftRequest,
        DraftCommandRequest,
        KnowledgeDraftError,
    )
    from shiliu.storage.errors import StorageError

    core = draft_core
    task = _terminal_task(core, "parallel-draft")
    request = SaveKnowledgeDraftRequest(
        source_kind="research_task", source_id=task, command_id="save-parallel"
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: core.knowledge_drafts.save(request), range(2))
        )
    assert results[0]["draft_revision_id"] == results[1]["draft_revision_id"]
    saved = results[0]
    with pytest.raises(StorageError) as error:
        with core.db.connect(guard=True) as c:
            c.execute(
                "UPDATE knowledge_draft_revisions SET status='failed' WHERE workspace_id=%s AND draft_id=%s",
                (core.db.workspace_id, saved["draft_id"]),
            )
    assert error.value.sqlstate == "23514"
    command = DraftCommandRequest(command_id="cancel-parallel", expected_version=1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: core.knowledge_drafts.cancel(saved["draft_id"], command),
                range(2),
            )
        )
    assert results[0]["draft_revision_id"] == results[1]["draft_revision_id"]
    assert [
        r["status"] for r in core.knowledge_drafts.get(saved["draft_id"])["history"]
    ] == ["saved", "cancelled"]
    with pytest.raises(KnowledgeDraftError, match="trusted context"):
        core.knowledge_drafts.confirm_promotion(
            saved["draft_id"], command, principal_id="other"
        )
