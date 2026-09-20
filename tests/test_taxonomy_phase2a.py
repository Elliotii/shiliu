from __future__ import annotations

import json

from eval.silver_generator import (
    SilverTaxonomy,
    _compact_card,
    _silver_review_sample,
)
from shiliu.domain import PipelineError
from shiliu.taxonomy.domain import FacetBatchOutput
from shiliu.taxonomy.facets import (
    FACET_PROMPT_VERSION,
    FacetExtractionService,
    build_facet_prompt,
    select_spike_cards,
)


def card(index: int, evidence: str) -> dict[str, object]:
    content_id = f"bilibili:BV{index:010d}:p1"
    return {
        "content_key": content_id,
        "evidence_level": evidence,
        "discovery_eligible": evidence != "D",
        "discovery_view": {
            "content_id": content_id,
            "title": f"视频 {index}",
            "uploader": f"UP {index}",
            "description": f"简介 {index}",
            "one_line_summary": f"结论 {index}",
            "key_points": ["观点"],
            "projects_tools_models": ["Tool"],
            "evidence_level": evidence,
        },
    }


class FakeRepository:
    def __init__(self, cards: list[dict[str, object]]) -> None:
        self.cards = cards

    def get_snapshot(self, snapshot_id: int):
        return {
            "id": snapshot_id,
            "snapshot_hash": "1" * 64,
            "cards": self.cards,
        }


class FakeFacetProvider:
    model = "facet-model"
    thinking_enabled = True
    reasoning_effort = "high"

    def complete_json(self, prompt: str, schema, *, max_tokens: int | None = None):
        assert schema is FacetBatchOutput
        assert max_tokens == 16384
        views = json.loads(prompt.split("内容卡 JSON：\n", 1)[1])
        return FacetBatchOutput.model_validate(
            {
                "facets": [
                    {
                        "content_id": view["content_id"],
                        "main_subject": view["title"],
                        "content_goal": "解释卡片中的主题",
                        "technical_aspects": ["技术"],
                        "usage_context": ["学习"],
                        "candidate_topics": ["阶段性专题"],
                        "candidate_entities": [
                            {"name": "Tool", "entity_type": "tool", "evidence": "卡片实体"}
                        ],
                        "evidence_notes": [view["description"]],
                        "ambiguity_notes": [],
                    }
                    for view in views
                ]
            }
        )


class FlakyFacetProvider(FakeFacetProvider):
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, prompt: str, schema, *, max_tokens: int | None = None):
        self.calls += 1
        if self.calls == 1:
            raise PipelineError("暂时失败", code="provider_retryable", retryable=True)
        return super().complete_json(prompt, schema, max_tokens=max_tokens)


def test_spike_selection_is_seeded_and_balances_eligible_evidence() -> None:
    cards = [card(index, level) for level in ("A", "B", "C", "D") for index in range(10)]
    first = select_spike_cards(cards, limit=12, seed=42)
    second = select_spike_cards(cards, limit=12, seed=42)
    assert [item["content_key"] for item in first] == [item["content_key"] for item in second]
    assert {level: sum(item["evidence_level"] == level for item in first) for level in "ABCD"} == {
        "A": 4,
        "B": 4,
        "C": 4,
        "D": 0,
    }


def test_facet_prompt_forbids_formal_taxonomy_creation() -> None:
    prompt = build_facet_prompt([card(1, "A")["discovery_view"]])
    assert "不得创建、建议或命名正式" in prompt
    assert "不得补充外部知识" in prompt
    assert "uploader 只是来源元数据" in prompt
    assert "没有具体产品证据时标为 concept" in prompt
    assert FACET_PROMPT_VERSION == "facet-extraction-v2"


def test_facet_spike_saves_auditable_structured_outputs(tmp_path) -> None:
    cards = [
        card(index + offset * 100, level)
        for offset, level in enumerate(("A", "B", "C"))
        for index in range(10)
    ]
    service = FacetExtractionService(
        repository=FakeRepository(cards),  # type: ignore[arg-type]
        provider_factory=lambda role: FakeFacetProvider(),  # type: ignore[arg-type]
        output_dir=tmp_path,
    )
    result = service.run_spike(2, limit=12, seed=42, batch_size=4)
    assert result["completed_count"] == 12
    assert result["failed_batch_count"] == 0
    assert result["sample_evidence_counts"] == {"A": 4, "B": 4, "C": 4, "D": 0}
    assert len(result["calls"]) == 3
    manifest = json.loads((tmp_path / result["run_id"] / "manifest.json").read_text())
    assert manifest["snapshot_hash"] == "1" * 64
    assert len(manifest["facets_hash"]) == 64


def test_facet_spike_preserves_each_retry_error(tmp_path) -> None:
    cards = [card(index + level_index * 100, level) for level_index, level in enumerate(("A", "B", "C")) for index in range(10)]
    provider = FlakyFacetProvider()
    service = FacetExtractionService(
        repository=FakeRepository(cards),  # type: ignore[arg-type]
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=tmp_path,
    )
    result = service.run_spike(2, limit=10, seed=7, batch_size=5)
    assert result["calls"][0]["attempt_count"] == 2
    assert result["calls"][0]["attempt_errors"] == [
        {
            "attempt": 1,
            "error_code": "provider_retryable",
            "error_message": "暂时失败",
            "retryable": True,
        }
    ]


def test_silver_protocol_declares_isolation_and_non_accuracy_semantics() -> None:
    text = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "eval" / "protocols" / "silver_eval_protocol_v1.yaml"
    ).read_text(encoding="utf-8")
    assert "discovery_a_output" in text
    assert "silver_reference_taxonomy" in text
    assert "true_accuracy" in text
    assert "not_evaluated" in text


def test_future_silver_review_uses_evidence_compaction_and_bounded_sample() -> None:
    views = [card(index, "A")["discovery_view"] for index in range(60)]
    views[0]["description"] = "A 级不发送的简介"
    views[0]["key_points"] = ["重复", "重复", "二", "三", "四"]
    compact = [_compact_card(view) for view in views]
    assert "description" not in compact[0]
    assert "uploader" not in compact[0]
    assert compact[0]["key_points"] == ["重复", "二", "三"]
    taxonomy = SilverTaxonomy.model_validate(
        {
            "version": "v2",
            "reference_kind": "silver",
            "content_types": [
                {
                    "id": "sct_1",
                    "name": "教程",
                    "definition": "教学内容",
                    "includes": ["教学"],
                    "excludes": ["新闻"],
                    "example_content_ids": [compact[0]["content_id"]],
                }
            ],
            "domains": [
                {
                    "id": "sd_1",
                    "name": "工程",
                    "definition": "工程内容",
                    "includes": ["工程"],
                    "excludes": ["娱乐"],
                    "example_content_ids": [compact[1]["content_id"]],
                    "children": [],
                }
            ],
        }
    )
    sample = _silver_review_sample(compact, taxonomy, limit=48)
    assert len(sample) == 48
    assert compact[0] in sample
    assert compact[1] in sample
