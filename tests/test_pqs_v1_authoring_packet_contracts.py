from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.export_pqs_v1_authoring_packet import build_content_map, load_navigation_metadata


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/product_query_set_v1/authoring_packet"


def _audit() -> dict:
    return json.loads((OUT / "pqs_v1_authoring_packet_execution.audit.json").read_text(encoding="utf-8"))


def _rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (OUT / name).read_text(encoding="utf-8").splitlines() if line]


def test_authoring_packet_does_not_run_retrieval() -> None:
    assert _audit()["retrieval_calls"] == _audit()["product_search_calls"] == 0


def test_authoring_packet_does_not_call_embedding() -> None:
    assert _audit()["embedding_calls"] == 0


def test_authoring_packet_does_not_call_builder_or_selector() -> None:
    assert _audit()["candidate_builder_calls"] == _audit()["selector_calls"] == 0


def test_authoring_packet_does_not_access_heldout() -> None:
    assert _audit()["heldout_accessed"] is False


def test_authoring_packet_does_not_read_raw_transcript_or_gold() -> None:
    assert _audit()["raw_transcript_read_for_authoring"] is False and _audit()["gold_read_for_authoring"] is False


def test_authoring_packet_does_not_use_stress_results() -> None:
    assert _audit()["stress_results_read_for_topic_prioritization"] is False


@pytest.mark.external_artifact
def test_neutral_content_map_is_grounded_and_has_private_provenance() -> None:
    topics, provenance = build_content_map(load_navigation_metadata())
    assert topics and provenance and all(row["share_with_independent_webgpt"] is False for row in provenance)


def test_neutral_content_map_excludes_video_ids_bvs_timestamps_and_title_lists() -> None:
    text = (OUT / "PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md").read_text(encoding="utf-8")
    assert "video_id" not in text and not re.search(r"BV[0-9A-Za-z]{6,}", text) and not re.search(r"\b\d{1,2}:\d{2}\b", text)
    assert "video_title" not in text


def test_neutral_content_map_does_not_claim_answerability() -> None:
    text = (OUT / "PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md").read_text(encoding="utf-8")
    assert "可以回答" not in text and "充分证据" not in text and "正确答案" in text


def test_legacy_packet_preserves_all_revised_candidates_and_raw_wording() -> None:
    revised = [json.loads(line) for line in (ROOT / "research/v3_5/product_query_set_v1/phase_a_r/product_query_candidates.revised.jsonl").read_text(encoding="utf-8").splitlines() if line]
    legacy = _rows("pqs_v1_legacy_candidates.jsonl")
    assert len(legacy) == len(revised) == 40
    assert [row["raw_query"] for row in legacy] == [row["raw_query"] for row in revised]


def test_legacy_review_template_is_blank_and_performance_free() -> None:
    assert all(row["legacy_action"] == row["proposed_revision"] == row["reason"] == "" and row["related_independent_draft_ids"] == [] for row in _rows("legacy_candidate_review.template.jsonl"))
    assert "系统表现" not in (OUT / "PQS_V1_LEGACY_CANDIDATE_PACKET.md").read_text(encoding="utf-8")


def test_independent_and_user_templates_are_blank() -> None:
    assert all(row["proposed_query"] == "" and row["user_validated_as_plausible"] is None for row in _rows("independent_query_draft.template.jsonl"))
    assert all(row["draft_query_id"] == row["final_user_query"] == row["user_action"] == row["decision_reason"] == "" and row["authoring_origin"] == [] and row["user_validated_as_plausible"] is None for row in _rows("product_query_user_validation.template.jsonl"))


def test_handoff_requires_pass1_before_legacy_pass2_and_starts_nothing() -> None:
    handoff = (OUT / "PQS_V1_INDEPENDENT_WEBGPT_HANDOFF.md").read_text(encoding="utf-8")
    assert handoff.index("Pass 1") < handoff.index("Pass 2") and "not frozen" in handoff
    manifest = json.loads((OUT / "pqs_v1_authoring_packet_manifest.json").read_text(encoding="utf-8"))
    assert not manifest["dev_eval_split_started"] and not manifest["product_baseline_started"] and not manifest["f1a_started"] and not manifest["f1b_started"]
