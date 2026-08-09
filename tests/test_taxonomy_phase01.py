from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from eval import freeze_silver_reference
from shiliu.app import Application
from shiliu.db import Database, SCHEMA_VERSION
from shiliu.domain import EntityItem, FavoriteItem, SummaryResult
from shiliu.web import create_web_app


def item(index: int, title: str | None = None) -> FavoriteItem:
    return FavoriteItem(
        bvid=f"BV{index:010d}",
        title=title or f"视频 {index}",
        uploader=f"UP {index}",
        favorite_time=1000 - index,
    )


def save_summary(application: Application, video_id: int, conclusion: str) -> None:
    video = application.db.get_video(video_id)
    assert video is not None
    summary = SummaryResult(
        conclusion=conclusion,
        key_points=["观点一", "观点二", "观点三"],
        detailed_notes=["详细内容"],
        entities=[EntityItem(name="Claude Code", kind="工具")],
    )
    _, markdown_path = application.artifacts.save_summary(
        str(video["source_id"]), summary, revision="refined"
    )
    application.db.update_video(
        video_id,
        summary_path=str(markdown_path),
        active_revision="refined",
        status="completed",
    )


def build_evidence_fixture(application: Application) -> tuple[int, dict[str, int]]:
    source_id = application.db.create_favorite_source(
        folder_id=101,
        folder_title="人工分类含义很强的收藏夹",
        account_name="测试账号",
        history_policy="all",
    )
    application.db.initialize_source_memberships(source_id, [item(1), item(2), item(3), item(4)])
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


def test_schema_v6_adds_only_four_taxonomy_tables(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    with db.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'taxonomy_%'"
            ).fetchall()
        }
    assert SCHEMA_VERSION == 14
    assert tables == {
        "taxonomy_corpus_snapshots",
        "taxonomy_classification_cards",
        "taxonomy_runs",
        "taxonomy_stage_runs",
    }


def test_preview_grades_cards_and_keeps_d_out_of_discovery(app_paths) -> None:
    application = Application(app_paths)
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


def test_dash_description_is_not_evidence(app_paths) -> None:
    application = Application(app_paths)
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


def test_duplicate_memberships_merge_and_removed_content_is_excluded(app_paths) -> None:
    application = Application(app_paths)
    first = application.db.create_favorite_source(folder_id=1, folder_title="第一夹")
    second = application.db.create_favorite_source(folder_id=2, folder_title="第二夹")
    application.db.record_source_snapshot(first, [item(1), item(2)], processing_profile="formal")
    application.db.initialize_source_memberships(second, [item(1)])

    preview = application.taxonomy_corpus.preview([first, second])
    assert preview.membership_count == 3
    assert preview.total_cards == 2
    assert preview.duplicate_memberships_merged == 1
    duplicate = next(card for card in preview.cards if card.content_key.endswith(f"{item(1).bvid}:p1"))
    assert duplicate.stored_card.folder_names == ["第一夹", "第二夹"]

    application.db.record_source_snapshot(first, [item(1)], processing_profile="formal")
    after_removal = application.taxonomy_corpus.preview([first])
    assert after_removal.total_cards == 1
    assert all(item(2).bvid not in card.content_key for card in after_removal.cards)


def test_discovery_view_excludes_folder_and_user_behavior(app_paths) -> None:
    application = Application(app_paths)
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
        "content_id", "title", "uploader", "description", "one_line_summary",
        "key_points", "projects_tools_models", "evidence_level",
    }
    serialized = json.dumps(discovery, ensure_ascii=False)
    for forbidden in (
        "folder_names", "source_ids", "memberships", "reading_state",
        "is_marked", "archived_at", "is_ignored", "人工提出的分类名称",
    ):
        assert forbidden not in serialized


def test_snapshot_is_immutable_hash_reuses_and_changes_create_new_snapshot(app_paths) -> None:
    application = Application(app_paths)
    source_id, video_ids = build_evidence_fixture(application)
    first = application.taxonomy_corpus.freeze([source_id])
    same = application.taxonomy_corpus.freeze([source_id])
    assert same.snapshot_id == first.snapshot_id
    assert same.snapshot_hash == first.snapshot_hash
    assert same.reused is True

    frozen_before = application.taxonomy_corpus.repository.get_snapshot(first.snapshot_id)
    application.db.update_video(video_ids["A"], description="后来修改的简介")
    save_summary(application, video_ids["A"], "后来修改的结论")
    frozen_after = application.taxonomy_corpus.repository.get_snapshot(first.snapshot_id)
    assert frozen_after == frozen_before

    changed = application.taxonomy_corpus.freeze([source_id])
    assert changed.snapshot_id != first.snapshot_id
    assert changed.snapshot_hash != first.snapshot_hash


def test_empty_snapshot_is_rejected(app_paths) -> None:
    application = Application(app_paths)
    source_id = application.db.create_favorite_source(folder_id=1, folder_title="空收藏夹")
    with pytest.raises(ValueError, match="空快照"):
        application.taxonomy_corpus.freeze([source_id])


def test_paused_source_can_freeze_without_resuming_sync(app_paths) -> None:
    application = Application(app_paths)
    source_id = application.db.create_favorite_source(folder_id=1, folder_title="暂停来源")
    application.db.initialize_source_memberships(source_id, [item(1)])
    application.db.set_source_status(source_id, "paused")

    assert [source["id"] for source in application.taxonomy_corpus.repository.selectable_sources()] == [source_id]
    snapshot = application.taxonomy_corpus.freeze([source_id])
    assert snapshot.total_cards == 1
    assert application.db.get_source(source_id)["status"] == "paused"


def test_taxonomy_web_preview_freeze_and_candidate_export_make_no_model_call(app_paths) -> None:
    application = Application(app_paths)
    source_id, _ = build_evidence_fixture(application)
    client = TestClient(create_web_app(application))

    page = client.get("/taxonomy")
    assert page.status_code == 200
    assert "分类实验" in page.text
    assert 'type="checkbox"' in page.text
    assert 'checked' not in page.text

    with patch("shiliu.llm.OpenAICompatibleProvider._generate") as generate:
        preview = client.post(
            "/api/taxonomy/snapshots/preview", json={"source_ids": [source_id]}
        )
        created = client.post(
            "/api/taxonomy/snapshots", json={"source_ids": [source_id]}
        )
    generate.assert_not_called()
    assert preview.status_code == 200
    assert preview.json()["preview"]["evidence_counts"] == {"A": 1, "B": 1, "C": 1, "D": 1}
    assert created.status_code == 201
    snapshot_id = created.json()["snapshot"]["snapshot_id"]
    candidates = client.get(
        f"/api/taxonomy/snapshots/{snapshot_id}/reference-candidates"
    )
    assert candidates.status_code == 200
    assert len(candidates.text.strip().splitlines()) == 4


def test_runtime_package_has_no_eval_dependency() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "shiliu" / "taxonomy"
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from eval" not in source
        assert "import eval" not in source
        assert "private_reference" not in source


def test_silver_reference_freeze_is_hashed_and_append_only(tmp_path, monkeypatch) -> None:
    private = tmp_path / "private"
    monkeypatch.setattr(freeze_silver_reference, "PRIVATE_DIR", private)
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(
        json.dumps(
            {
                "version": "v1",
                "reference_kind": "silver",
                "content_types": [{"name": "独立评测类型"}],
                "domains": [],
            }
        ),
        encoding="utf-8",
    )
    eval_set = tmp_path / "silver.jsonl"
    eval_set.write_text(
        "\n".join(
            json.dumps(
                {
                    "content_key": f"bilibili:BV{index:010d}:p1",
                    "selection_bucket": "high_evidence_clear",
                    "selection_reason": "独立评测选择",
                    "silver_agreement": "agreed",
                }
            )
            for index in range(40)
        ) + "\n",
        encoding="utf-8",
    )
    disagreements = tmp_path / "disagreements.jsonl"
    disagreements.write_text("", encoding="utf-8")
    calls = tmp_path / "calls.jsonl"
    calls.write_text(
        "\n".join(
            json.dumps(
                {
                    "evaluator_role": role,
                    "status": "completed",
                    "model": "model",
                    "prompt_version": "v1",
                    "parameters": {},
                    "input_hash": "a" * 64,
                    "output_hash": "b" * 64,
                    "output_path": f"{role}.json",
                }
            )
            for role in ("evaluator_a", "evaluator_b", "evaluator_c")
        ) + "\n",
        encoding="utf-8",
    )
    arguments = {
        "taxonomy": taxonomy,
        "eval_set": eval_set,
        "disagreements": disagreements,
        "calls": calls,
        "version": "v1",
        "snapshot_id": 2,
        "snapshot_hash": "1" * 64,
    }
    manifest = freeze_silver_reference.freeze(**arguments)
    assert manifest["reference_kind"] == "silver"
    assert manifest["evaluation_semantics"]["true_accuracy"] == "not_claimed"
    assert len(manifest["artifacts"]["silver_reference_taxonomy"]["sha256"]) == 64
    with pytest.raises(FileExistsError):
        freeze_silver_reference.freeze(**arguments)
