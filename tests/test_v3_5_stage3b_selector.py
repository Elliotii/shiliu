from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiliu.evidence import SourceArtifactReference, load_source_artifact
from shiliu.evidence.stage3a import (
    CANDIDATE_GENERATION_POLICY_STAGE3B,
    CandidateBuilderConfig,
    build_within_video_candidates,
    compact_acronym_tokens,
    one_substitution_acronym_matches,
)
from shiliu.evidence.stage3b import (
    STRUCTURED_SELECTOR_CONTRACT_VERSION,
    StructuredSelectorConfig,
    StructuredSelectorError,
    build_structured_selector_prompt,
    reconstruct_structured_bundle,
    select_structured_evidence_bundle,
)
from shiliu.llm import CompletionResponse


def artifact(tmp_path: Path, texts: list[str]):
    directory = tmp_path / "BVSTAGE3B"
    directory.mkdir()
    payload = [
        {"from": index * 5.0, "to": index * 5.0 + 4.0, "content": text}
        for index, text in enumerate(texts)
    ]
    path = directory / "subtitle-raw.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_source_artifact(SourceArtifactReference(
        platform="bilibili", source_id="BVSTAGE3B", part=1, source_type="ai",
        source_language="zh", artifact_path=str(path), source_lineage="ai",
    ))


def builder_config(**changes):
    values = dict(
        config_id="stage3b-test", within_video_max_candidates=8,
        candidate_generation_policy_version=CANDIDATE_GENERATION_POLICY_STAGE3B,
        asr_acronym_anchor_enabled=True,
    )
    values.update(changes)
    return CandidateBuilderConfig(**values)


class FakeProvider:
    name = "fake-openai-compatible"
    model = "fake-structured-model"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def complete_raw(self, prompt: str, *, max_tokens=None):
        self.prompts.append(prompt)
        value = self.outputs.pop(0)
        if isinstance(value, BaseException):
            raise value
        return CompletionResponse(
            content=value, finish_reason="stop", usage={"total_tokens": 12}, response_id="fake",
        )


def candidate_set(tmp_path: Path):
    raw = artifact(tmp_path, [
        "generic introduction", "the AXC protocol begins here", "implementation detail",
        "a separate exact context token", "first complementary fact", "transition one",
        "second section", "second complementary fact", "transition two", "third section",
        "third complementary fact", "transition three", "fourth section", "closing fact",
    ])
    return build_within_video_candidates(
        "How does ABC protocol work?", 7, raw.source_version, raw,
        builder_config(), query_id="QUERY_PUBLIC_ID",
    )


def output(candidate_ids, *, action="select", roles=None, reason=None, **extra):
    value = {
        "schema_version": STRUCTURED_SELECTOR_CONTRACT_VERSION,
        "action": action,
        "selected_candidate_ids": candidate_ids,
        "candidate_roles": roles if roles is not None else [
            {"candidate_id": value, "role": "primary" if index == 0 else "complementary"}
            for index, value in enumerate(candidate_ids)
        ],
        "abstain_reason": reason,
    }
    value.update(extra)
    return json.dumps(value)


def test_acronym_compaction_case_punctuation_and_generic_substitution() -> None:
    config = builder_config()
    assert compact_acronym_tokens("About A.B-C", query_tokens=True) == ("abc",)
    assert one_substitution_acronym_matches("Use ABC", "asr said aBc", config) == ()
    assert one_substitution_acronym_matches("Use ABC", "asr said A.X.C", config) == (("abc", "axc"),)
    assert one_substitution_acronym_matches("Use ABC", "asr said axc", config) == (("abc", "axc"),)
    assert one_substitution_acronym_matches("ordinary", "ordxnary", config) == ()


def test_builder_fuzzy_anchor_is_bounded_and_has_no_dictionary(tmp_path: Path) -> None:
    raw = artifact(tmp_path, [f"segment {index}" for index in range(20)] + ["the AXC protocol"])
    result = build_within_video_candidates("Explain ABC", 7, raw.source_version, raw, builder_config(), query_id="Q")
    assert len(result.candidates) <= 8
    assert sum(value.character_count for value in result.candidates) <= 6000
    assert any(value.score_breakdown["asr_acronym_anchor_score"] == 1 for value in result.candidates)


def test_valid_selection_and_deterministic_raw_reconstruction(tmp_path: Path) -> None:
    values = candidate_set(tmp_path)
    chosen = [values.candidates[1].candidate_id, values.candidates[0].candidate_id]
    result = select_structured_evidence_bundle(values.original_query, values, FakeProvider([output(chosen)]))
    assert result.bundle is not None
    by_id = {value.candidate_id: value for value in values.candidates}
    assert result.bundle.source_texts == tuple(by_id[value].source_text for value in result.bundle.candidate_ids)
    assert result.bundle.normalized_spans[0]["start_time"] == by_id[result.bundle.candidate_ids[0]].start_time
    assert reconstruct_structured_bundle(result.output, values).bundle_id == result.bundle.bundle_id


@pytest.mark.parametrize("bad,code", [
    ("not json", "repair_attempt_exhausted"),
    (json.dumps({"action": "wrong"}), "repair_attempt_exhausted"),
])
def test_invalid_json_and_schema_are_not_silently_accepted(tmp_path: Path, bad: str, code: str) -> None:
    values = candidate_set(tmp_path)
    with pytest.raises(StructuredSelectorError) as error:
        select_structured_evidence_bundle(values.original_query, values, FakeProvider([bad, bad]))
    assert error.value.code == code


def test_unknown_duplicate_extra_field_and_invalid_action(tmp_path: Path) -> None:
    values = candidate_set(tmp_path)
    known = values.candidates[0].candidate_id
    bad_values = [
        output(["candidate_missing"]),
        output([known, known]),
        output([known], quote="forbidden"),
        output([], action="other", roles=[]),
    ]
    for bad in bad_values:
        with pytest.raises(StructuredSelectorError, match="invalid after one repair"):
            select_structured_evidence_bundle(values.original_query, values, FakeProvider([bad, bad]))


def test_abstain_contract_and_count_limit(tmp_path: Path) -> None:
    values = candidate_set(tmp_path)
    valid = output([], action="abstain", roles=[], reason="no_relevant_candidate")
    result = select_structured_evidence_bundle(values.original_query, values, FakeProvider([valid]))
    assert result.bundle is None
    bad = output([], action="select", roles=[])
    with pytest.raises(StructuredSelectorError):
        select_structured_evidence_bundle(values.original_query, values, FakeProvider([bad, bad]))
    ids = [value.candidate_id for value in values.candidates[:2]]
    with pytest.raises(StructuredSelectorError):
        select_structured_evidence_bundle(
            values.original_query, values, FakeProvider([output(ids), output(ids)]),
            StructuredSelectorConfig(max_selected_candidates=1),
        )


def test_one_repair_success_uses_same_query_candidates_and_no_case_id(tmp_path: Path) -> None:
    values = candidate_set(tmp_path)
    known = values.candidates[0].candidate_id
    provider = FakeProvider([output(["candidate_missing"]), output([known])])
    result = select_structured_evidence_bundle(values.original_query, values, provider)
    assert result.metrics["repair_used"] is True and result.metrics["attempt_count"] == 2
    assert values.original_query in provider.prompts[0] and values.original_query in provider.prompts[1]
    assert "CASE_" not in provider.prompts[0]
    for candidate in values.candidates:
        assert candidate.candidate_id in provider.prompts[0] and candidate.candidate_id in provider.prompts[1]


def test_timeout_and_provider_failure_are_typed(tmp_path: Path) -> None:
    values = candidate_set(tmp_path)
    with pytest.raises(StructuredSelectorError) as timeout:
        select_structured_evidence_bundle(values.original_query, values, FakeProvider([TimeoutError("late")]))
    assert timeout.value.code == "provider_timeout"
    with pytest.raises(StructuredSelectorError) as failure:
        select_structured_evidence_bundle(values.original_query, values, FakeProvider([RuntimeError("down")]))
    assert failure.value.code == "provider_failure"


def test_prompt_serializes_only_allowed_candidate_fields(tmp_path: Path) -> None:
    values = candidate_set(tmp_path)
    prompt = build_structured_selector_prompt(values.original_query, values.candidates, StructuredSelectorConfig())
    assert "segment_ids" not in prompt and "gold_" not in prompt and "required_aspects" not in prompt
    assert "QUERY_PUBLIC_ID" not in prompt and "CASE_" not in prompt
