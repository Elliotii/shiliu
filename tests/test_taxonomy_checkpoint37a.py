from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from shiliu.domain import PipelineError
from shiliu.cli import build_parser
from shiliu.llm import CompletionResponse
from shiliu.taxonomy.profiles import (
    ClassificationProfile,
    ClassificationProfileBatch,
    ClassificationProfileService,
    build_profile_prompt,
    compression_metrics,
    profile_is_polluted,
    select_profile_rows,
    validate_profile_batch,
)


def card(index: int, evidence: str) -> dict:
    content_key = f"bilibili:synthetic-{index}:p1"
    return {
        "content_key": content_key,
        "evidence_level": evidence,
        "discovery_eligible": evidence != "D",
        "discovery_view": {
            "content_id": content_key,
            "title": f"合成标题 {index}",
            "description": f"C级冻结简介 {index} " + "简介内容" * 60,
            "one_line_summary": f"合成结论 {index} " + "较长结论" * 30,
            "key_points": ["核心观点" * 20, "第二观点" * 20, "第三观点" * 20],
            "projects_tools_models": ["SyntheticTool"],
        },
    }


def profile(content_id: str, level: str = "A") -> ClassificationProfile:
    return ClassificationProfile.model_validate(
        {
            "content_id": content_id,
            "main_subject": "合成主题",
            "content_goal": "说明目标",
            "key_concepts": ["概念"],
            "usage_contexts": ["学习"],
            "entities": ["SyntheticTool"],
            "unknown_terms": [],
            "source_evidence_level": level,
        }
    )


def test_profile_input_projection_preserves_c_description_and_excludes_d() -> None:
    cards = [card(1, "A"), card(2, "B"), card(3, "C"), card(4, "D")]
    rows, _ = select_profile_rows(cards, limit=3, seed=73)
    by_level = {row[1]: row for row in rows}

    assert len(by_level["A"]) == 6
    assert len(by_level["B"]) == 6
    assert len(by_level["C"]) == 4
    assert "C级冻结简介" in by_level["C"][3]
    assert len(by_level["C"][3]) <= 300
    assert "D" not in by_level


def test_profile_cli_defaults_match_checkpoint37a_contract() -> None:
    arguments = build_parser().parse_args(
        ["taxonomy", "profile-spike", "--snapshot-id", "2"]
    )
    assert arguments.limit == 48
    assert arguments.seed == 73
    assert arguments.batch_size == 12


def test_profile_prompt_requires_nonempty_scalar_fields() -> None:
    prompt = build_profile_prompt([["C001", "C", "合成标题", "合成简介"]])

    assert "main_subject 和 content_goal 必须是非空字符串" in prompt
    assert "无法从证据判断 content_goal 时写“信息不足”" in prompt
    assert '"content_goal":"信息不足"' in prompt


def test_profile_schema_caps_bounded_fields_and_forbids_domain_key() -> None:
    value = ClassificationProfile.model_validate(
        {
            "content_id": "C001",
            "main_subject": "主" * 100,
            "content_goal": "目" * 150,
            "key_concepts": ["概" * 80, *[f"概念{index}" for index in range(6)]],
            "usage_contexts": [f"情境{index}" for index in range(5)],
            "entities": [f"实体{index}" for index in range(7)],
            "unknown_terms": [f"词{index}" for index in range(5)],
            "source_evidence_level": "A",
        }
    )
    assert len(value.main_subject) == 80
    assert len(value.content_goal) == 120
    assert len(value.key_concepts) == 5
    assert len(value.key_concepts[0]) == 60
    assert len(value.usage_contexts) == 3
    assert len(value.entities) == 5
    assert len(value.unknown_terms) == 3

    payload = value.model_dump(mode="json")
    payload["domain"] = "禁止字段"
    with pytest.raises(ValidationError):
        ClassificationProfile.model_validate(payload)


def test_profile_validation_rejects_id_level_and_classification_pollution() -> None:
    clean = profile("C001")
    validate_profile_batch(
        ClassificationProfileBatch(profiles=[clean]), {"C001": "A"}
    )

    with pytest.raises(PipelineError) as wrong_level:
        validate_profile_batch(
            ClassificationProfileBatch(profiles=[clean]), {"C001": "B"}
        )
    assert wrong_level.value.code == "profile_evidence_level_mismatch"

    polluted = clean.model_copy(update={"content_goal": "建议归入某个一级领域"})
    assert profile_is_polluted(polluted) is True
    with pytest.raises(PipelineError) as pollution:
        validate_profile_batch(
            ClassificationProfileBatch(profiles=[polluted]), {"C001": "A"}
        )
    assert pollution.value.code == "profile_domain_pollution"


def test_compression_metrics_use_same_order_and_clear_25_percent_gate() -> None:
    cards = [card(1, "A"), card(2, "B"), card(3, "C")]
    rows, _ = select_profile_rows(cards, limit=3, seed=73)
    profiles = [profile(str(row[0]), str(row[1])) for row in rows]

    metrics = compression_metrics(rows, profiles)

    assert metrics["profile_characters"] < metrics["compact_characters"]
    assert metrics["estimated_token_reduction"] >= 0.25
    assert metrics["compression_gate_passed"] is True


class SnapshotRepository:
    def __init__(self, cards: list[dict]) -> None:
        self.cards = cards

    def get_snapshot(self, snapshot_id: int):
        return {
            "id": snapshot_id,
            "snapshot_hash": "c" * 64,
            "cards": self.cards,
        }


class ProfileProvider:
    model = "fake-profile"
    thinking_enabled = False
    reasoning_effort = None

    def __init__(self) -> None:
        self.calls = 0

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        self.calls += 1
        rows = [
            json.loads(line)
            for line in prompt.split("输入行：\n", 1)[1].splitlines()
            if line.strip()
        ]
        output = {
            "profiles": [
                {
                    "content_id": row[0],
                    "main_subject": "合成主题",
                    "content_goal": "说明目标",
                    "key_concepts": ["概念"],
                    "usage_contexts": ["学习"],
                    "entities": row[5][:1] if row[1] in {"A", "B"} else [],
                    "unknown_terms": [],
                    "source_evidence_level": row[1],
                }
                for row in rows
            ]
        }
        return CompletionResponse(
            json.dumps(output, ensure_ascii=False),
            "stop",
            {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "prompt_tokens_details": {"cached_tokens": 10},
            },
            f"profile-{self.calls}",
        )


def test_profile_spike_is_private_batched_audited_and_resumable(tmp_path) -> None:
    cards = [card(1, "A"), card(2, "B"), card(3, "C"), card(4, "A"), card(5, "D")]
    provider = ProfileProvider()
    service = ClassificationProfileService(
        repository=SnapshotRepository(cards),  # type: ignore[arg-type]
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=tmp_path / "profile_spikes",
    )

    result = service.run_spike(2, limit=4, seed=73, batch_size=2)

    assert result["status"] == "completed"
    assert result["production_stage"] is False
    assert result["completed_count"] == 4
    assert result["repair_count"] == 0
    assert result["missing_field_count"] == 0
    assert result["pollution_count"] == 0
    assert result["raw_pollution_error_count"] == 0
    assert result["raw_schema_success_rate"] == 1.0
    assert result["usage"]["total_tokens"] == 300
    assert result["usage"]["cached_tokens"] == 20
    assert result["gates"]["schema_success_100_percent"] is True
    assert result["gates"]["estimated_token_reduction_at_least_25_percent"] is True
    run_dir = tmp_path / "profile_spikes" / result["run_id"]
    assert (run_dir / "profiles.jsonl").is_file()
    assert (run_dir / "profile-discovery-view.jsonl").is_file()
    assert len(list((run_dir / "batch-001" / "responses" / "primary").glob(
        "response-*.txt"
    ))) == 1
    calls_before = provider.calls

    resumed = service.resume_spike(result["run_id"])

    assert resumed["profiles_hash"] == result["profiles_hash"]
    assert provider.calls == calls_before


def test_profile_corpus_reuses_accepted_rows_and_generates_only_missing(tmp_path) -> None:
    cards = [card(index, "A" if index < 5 else "C") for index in range(1, 6)]
    output_dir = tmp_path / "profile_spikes"
    source_dir = output_dir / "accepted-source"
    source_dir.mkdir(parents=True)
    source_profiles = [profile("C001"), profile("C002")]
    (source_dir / "profiles.jsonl").write_text(
        "".join(item.model_dump_json() + "\n" for item in source_profiles),
        encoding="utf-8",
    )
    (source_dir / "manifest.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "snapshot_hash": "c" * 64,
                "prompt_version": "classification-profile-generation-v2",
                "profiles_hash": "source-hash",
                "gates": {"schema": True, "repair": True},
            }
        ),
        encoding="utf-8",
    )
    provider = ProfileProvider()
    service = ClassificationProfileService(
        repository=SnapshotRepository(cards),  # type: ignore[arg-type]
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=output_dir,
    )

    result = service.materialize_snapshot(
        2, reuse_run_id="accepted-source", batch_size=2
    )

    assert result["status"] == "completed"
    assert result["completed_count"] == 5
    assert result["reused_count"] == 2
    assert result["generated_count"] == 3
    assert provider.calls == 2
    assert result["repair_count"] == 0
