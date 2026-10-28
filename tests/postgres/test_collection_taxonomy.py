from __future__ import annotations
from types import SimpleNamespace
import json
import pytest
from shiliu.domain import FavoriteItem, SummaryResult, EntityItem
from shiliu.artifacts import ArtifactStore
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.corpus import TaxonomyCorpusService


def composition(db, app_paths):
    artifacts = ArtifactStore(app_paths.videos_dir, db=db)
    return SimpleNamespace(
        db=db, artifacts=artifacts, taxonomy_corpus=TaxonomyCorpusService(db, artifacts)
    )


def item(index: int, title: str | None = None) -> FavoriteItem:
    return FavoriteItem(
        bvid=f"BV{index:010d}",
        title=title or f"视频 {index}",
        uploader=f"UP {index}",
        favorite_time=1000 - index,
    )


def save_summary(application: SimpleNamespace, video_id: int, conclusion: str) -> None:
    video = application.db.get_video(video_id)
    assert video is not None
    summary = SummaryResult(
        conclusion=conclusion,
        key_points=["观点一", "观点二", "观点三"],
        detailed_notes=["详细内容"],
        entities=[EntityItem(name="Claude Code", kind="工具")],
    )
    batch = application.artifacts.batch(video_id)
    _, markdown_path = batch.save_summary(
        str(video["source_id"]), summary, revision="refined"
    )
    batch.commit(
        lambda conn: application.db.update_video(
            video_id,
            conn=conn,
            summary_path=str(markdown_path),
            active_revision="refined",
            status="completed",
        )
    )


def build_evidence_fixture(application: SimpleNamespace) -> tuple[int, dict[str, int]]:
    source_id = application.db.create_favorite_source(
        folder_id=101,
        folder_title="人工分类含义很强的收藏夹",
        account_name="测试账号",
        history_policy="all",
    )
    application.db.initialize_source_memberships(
        source_id, [item(1), item(2), item(3), item(4)], authoritative=True
    )
    video_ids: dict[str, int] = {}
    for index, level in ((1, "A"), (2, "B"), (3, "C")):
        video_ids[level] = application.db.materialize_history_membership(
            source_id, item(index).bvid
        )
    application.db.update_video(video_ids["A"], description="有效简介")
    save_summary(application, video_ids["A"], "A 级结论")
    save_summary(application, video_ids["B"], "B 级结论")
    application.db.update_video(video_ids["C"], description="有效简介")
    return source_id, video_ids


def test_preview_grades_cards_and_keeps_d_out_of_discovery(
    app_paths, collection_db
) -> None:
    application = composition(collection_db, app_paths)
    source_id, _ = build_evidence_fixture(application)

    preview = application.taxonomy_corpus.preview([source_id])

    assert preview.membership_count == 4
    assert preview.total_cards == 4
    assert preview.evidence_counts == {"A": 1, "B": 1, "C": 1, "D": 1}
    assert preview.discovery_eligible_count == 3
    assert preview.trial_assignment_only_count == 1
    d_card = next(card for card in preview.cards if card.evidence_level.value == "D")
    assert d_card.video_id is None
    assert d_card.discovery_eligible is False


def test_dash_description_is_not_evidence(app_paths, collection_db) -> None:
    application = composition(collection_db, app_paths)
    source_id = application.db.create_favorite_source(folder_id=1, folder_title="测试")
    application.db.record_source_snapshot(
        source_id, [item(1)], processing_profile="formal"
    )
    video = application.db.get_video_by_source(item(1).bvid)
    assert video is not None
    application.db.update_video(int(video["id"]), description="-")
    card = application.taxonomy_corpus.preview([source_id]).cards[0]
    assert card.evidence_level.value == "D"
    assert card.stored_card.description == ""


def test_duplicate_memberships_merge_and_removed_content_is_excluded(
    app_paths, collection_db
) -> None:
    application = composition(collection_db, app_paths)
    first = application.db.create_favorite_source(folder_id=1, folder_title="第一夹")
    second = application.db.create_favorite_source(folder_id=2, folder_title="第二夹")
    application.db.record_source_snapshot(
        first, [item(1), item(2)], processing_profile="formal"
    )
    application.db.initialize_source_memberships(second, [item(1)], authoritative=True)

    preview = application.taxonomy_corpus.preview([first, second])
    assert preview.membership_count == 3
    assert preview.total_cards == 2
    assert preview.duplicate_memberships_merged == 1
    duplicate = next(
        card
        for card in preview.cards
        if card.content_key.endswith(f"{item(1).bvid}:p1")
    )
    assert duplicate.stored_card.folder_names == ["第一夹", "第二夹"]

    application.db.record_source_snapshot(
        first, [item(1)], processing_profile="formal", authoritative=True
    )
    after_removal = application.taxonomy_corpus.preview([first])
    assert after_removal.total_cards == 1
    assert all(item(2).bvid not in card.content_key for card in after_removal.cards)


def test_discovery_view_excludes_folder_and_user_behavior(
    app_paths, collection_db
) -> None:
    application = composition(collection_db, app_paths)
    source_id, video_ids = build_evidence_fixture(application)
    video_id = video_ids["A"]
    application.db.set_reading_state(video_id, "read")
    application.db.set_marked(video_id, True)
    application.db.set_archived(video_id, True)
    application.db.set_ignored(video_id, True)
    application.db.create_note(video_id, "人工提出的分类名称")

    card = application.taxonomy_corpus.preview([source_id]).cards[0]
    stored = card.stored_card.model_dump(mode="json")
    discovery = card.discovery_view.model_dump(mode="json")
    assert stored["folder_names"] == ["人工分类含义很强的收藏夹"]
    assert set(discovery) == {
        "content_id",
        "title",
        "uploader",
        "description",
        "one_line_summary",
        "key_points",
        "projects_tools_models",
        "evidence_level",
    }
    serialized = json.dumps(discovery, ensure_ascii=False)
    for forbidden in (
        "folder_names",
        "source_ids",
        "memberships",
        "reading_state",
        "is_marked",
        "archived_at",
        "is_ignored",
        "人工提出的分类名称",
    ):
        assert forbidden not in serialized


def test_taxonomy_pg_run_history_resume_and_scope(collection_db, app_paths):
    app = composition(collection_db, app_paths)
    sid, _ = build_evidence_fixture(app)
    frozen = app.taxonomy_corpus.freeze([sid])
    assert app.taxonomy_corpus.freeze([sid]).reused
    repository = TaxonomyRepository(collection_db)
    old = repository.get_snapshot(frozen.snapshot_id)
    assert len(old["cards"]) == 4 and isinstance(old["cards"][0]["stored_card"], dict)
    runs = TaxonomyRunRepository(
        collection_db, app.artifacts, app_paths.videos_dir / "taxonomy-preparation"
    )
    rid = runs.create_run(
        snapshot_id=frozen.snapshot_id,
        run_kind="production",
        engine="fake",
        engine_version="test",
        parameters={"nested": [None, "中文"]},
    )
    assert runs.get_run(rid)["parameters"] == {"nested": [None, "中文"]}
    stage = runs.start_stage(
        rid,
        "fake_model",
        "main",
        input_hash="abc",
        model="fake",
        prompt_version="v1",
        thinking_enabled=True,
        reasoning_effort="high",
    )
    assert stage["attempt_count"] == 1
    runs.fail_stage(
        rid,
        "fake_model",
        "main",
        error_code="transient",
        error_message="synthetic",
        retryable=True,
    )
    stage = runs.start_stage(
        rid,
        "fake_model",
        "main",
        input_hash="abc",
        model="fake",
        prompt_version="v1",
        thinking_enabled=True,
        reasoning_effort="high",
    )
    assert stage["attempt_count"] == 1
    with pytest.raises(ValueError):
        runs.ensure_stage(rid, "fake_model", "main", input_hash="different")
    output = app_paths.videos_dir / "taxonomy-preparation" / "output.json"
    output.write_text('{"synthetic":true}')
    runs.complete_stage(
        rid,
        "fake_model",
        "main",
        output_path=str(output),
        output_hash="def",
        audit={
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            "elapsed_seconds": 0.1,
        },
    )
    assert runs.list_stages(rid)[0]["input_tokens"] == 11
    runs.set_run_status(rid, "completed")
    assert runs.get_run(rid)["status"] == "completed"
    runs.reset_stages(rid, ["fake_model"])
    assert runs.list_stages(rid)[0]["status"] == "pending"
    from shiliu.db import Database
    from shiliu.storage.scope import ResourceContext

    foreign = TaxonomyRunRepository(
        Database(collection_db.pg, ResourceContext("personal:other", "other")),
        app.artifacts,
        app_paths.videos_dir / "taxonomy-preparation",
    )
    assert foreign.get_run(rid) is None and foreign.list_stages(rid) == []
