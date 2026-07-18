from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from shiliu.cli import build_parser
from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import SubdomainNode, TopLevelDomainDraft, TopLevelDomainNode
from shiliu.taxonomy.controlled_facets import (
    ASSIGNMENT_SCHEMA_VERSION,
    DYNAMIC_FACETING_VERSION,
    ENTITY_MAPPING_VERSION,
    ControlledDomainAssignment,
    ControlledFormAssignment,
    ControlledObjectAssignment,
    ControlledVocabulary,
    HybridControlledAssignment,
    NoveltyProposal,
    SuggestedContextAssignment,
    _build_repair_schema_hint,
    _query,
    build_derived_filter_proposals,
    build_dynamic_faceting,
    build_quality_gate,
    build_reviewer_bundle,
    load_controlled_vocabularies,
    map_entities_to_object_types,
    validate_assignments,
    HybridAssignmentOutput,
)
from shiliu.taxonomy.faceted_metadata import FacetedMetadataService


def domain() -> TopLevelDomainDraft:
    return TopLevelDomainDraft(
        domains=[
            TopLevelDomainNode(
                id="d_01",
                name="软件工程",
                definition="软件工程领域",
                includes=["工程"],
                excludes=["硬件"],
                supporting_ids=["C001", "C002", "C003"],
                representative_ids=["C001"],
                children=[],
            ),
            TopLevelDomainNode(
                id="d_02",
                name="模型工程",
                definition="模型工程领域",
                includes=["模型"],
                excludes=["硬件"],
                supporting_ids=["C004"],
                representative_ids=["C004"],
                children=[
                    SubdomainNode(
                        id="d_02_01",
                        name="模型训练",
                        definition="模型训练子领域",
                        includes=["训练"],
                        excludes=["部署"],
                        supporting_ids=["C004"],
                        representative_ids=["C004"],
                        parent_id="d_02",
                    )
                ],
            ),
        ],
        candidate_decisions=[],
        consolidation_notes=[],
    )


def assignment(
    content_id: str,
    *,
    domain_id: str = "d_01",
    form: str = "PF04",
    object_id: str | None = "OT04",
    context_id: str | None = "UC07",
    entity: str = "Paper A",
) -> HybridControlledAssignment:
    return HybridControlledAssignment(
        content_id=content_id,
        domain=ControlledDomainAssignment(
            primary_path=[domain_id], secondary_paths=[], confidence="high"
        ),
        presentation_form=ControlledFormAssignment(
            primary=form,
            secondary=None,
            confidence="high" if form != "unknown" else "low",
            evidence=["形式证据"] if form != "unknown" else [],
        ),
        object_types=(
            [
                ControlledObjectAssignment(
                    id=object_id,
                    source_entities=[entity],
                    mapping_source="model_assisted",
                    confidence="high",
                    evidence=["对象证据"],
                )
            ]
            if object_id
            else []
        ),
        suggested_use_contexts=(
            [
                SuggestedContextAssignment(
                    id=context_id,
                    confidence="medium",
                    evidence=["场景证据"],
                )
            ]
            if context_id
            else []
        ),
        facet_novelty=[],
        ambiguities=[],
    )


def test_controlled_vocabulary_versions_and_stable_ids() -> None:
    registry = load_controlled_vocabularies()
    assert registry.presentation_form.version == "presentation_form_v1"
    assert registry.focus_object_type.version == "focus_object_type_v1"
    assert registry.suggested_use_context.version == "suggested_use_context_v1"
    assert registry.presentation_form.active_ids == frozenset(
        f"PF{index:02d}" for index in range(1, 12)
    )
    assert registry.focus_object_type.active_ids == frozenset(
        f"OT{index:02d}" for index in range(1, 10)
    )
    assert registry.suggested_use_context.active_ids == frozenset(
        f"UC{index:02d}" for index in range(1, 9)
    )


def test_controlled_vocabulary_terms_are_runtime_immutable() -> None:
    registry = load_controlled_vocabularies()
    with pytest.raises(ValidationError):
        registry.presentation_form.terms[0].canonical_name = "运行时改名"
    assert isinstance(registry.presentation_form.terms, tuple)


def test_only_active_and_deprecated_statuses_are_allowed() -> None:
    registry = load_controlled_vocabularies()
    payload = registry.presentation_form.model_dump(mode="json")
    payload["terms"][0]["status"] = "draft"
    with pytest.raises(ValidationError):
        ControlledVocabulary.model_validate(payload)


def test_historical_open_vocabulary_builder_is_disabled_by_default() -> None:
    service = object.__new__(FacetedMetadataService)
    with pytest.raises(PipelineError) as error:
        service.create_spike(sample_profile_run_id="historical")
    assert error.value.code == "open_facet_vocabulary_builder_disabled"


def test_incomplete_historical_open_run_cannot_resume() -> None:
    class Repository:
        def get_run(self, run_id):
            return {
                "id": run_id,
                "run_kind": "faceted_metadata_spike",
                "engine_version": "faceted-metadata-spike-v1",
                "status": "retry_wait",
            }

    service = object.__new__(FacetedMetadataService)
    service.run_repository = Repository()
    with pytest.raises(PipelineError) as error:
        service.execute(16, resume=True)
    assert error.value.code == "open_facet_historical_run_read_only"


def test_entity_type_mapping_is_deterministic_and_traceable() -> None:
    registry = load_controlled_vocabularies()
    values = map_entities_to_object_types(
        [
            {"name": "ExampleLib", "type": "library"},
            {"name": "ExamplePaper", "type": "paper"},
            "UntypedThing",
        ],
        registry,
    )
    assert values[0].object_type_id == "OT01"
    assert values[1].object_type_id == "OT04"
    assert values[2].mapping_status == "untyped"
    assert values[0].rule_version == ENTITY_MAPPING_VERSION


def test_object_type_can_be_empty_when_no_entity_evidence() -> None:
    value = assignment("C001", object_id=None, context_id=None)
    assert value.object_types == []
    assert value.suggested_use_contexts == []


def test_form_must_use_controlled_id_or_unknown() -> None:
    with pytest.raises(ValidationError):
        ControlledFormAssignment(
            primary="自创新形式",
            secondary=None,
            confidence="high",
            evidence=["证据"],
        )
    unknown = ControlledFormAssignment(
        primary="unknown", secondary=None, confidence="low", evidence=[]
    )
    assert unknown.primary == "unknown"


def test_novelty_remains_proposal_and_cannot_be_assignment_id() -> None:
    value = NoveltyProposal(
        facet="presentation_form",
        proposed_name="新形式",
        definition="与已有形式存在明确差异。",
        closest_existing_ids=["PF03"],
        difference="不是快速概览。",
        supporting_content_ids=["C001"],
        evidence=["内容证据"],
        confidence="medium",
    )
    assert value.proposed_name == "新形式"
    with pytest.raises(ValidationError):
        ControlledFormAssignment(
            primary="新形式", secondary=None, confidence="medium", evidence=["证据"]
        )


def test_assignment_rejects_uncontrolled_ids_and_preserves_empty_context() -> None:
    registry = load_controlled_vocabularies()
    output = HybridAssignmentOutput(
        assignments=[assignment("C001", context_id=None)]
    )
    mappings = map_entities_to_object_types(["Paper A"], registry)
    validate_assignments(
        output,
        expected_ids={"C001"},
        domain_draft=domain(),
        registry=registry,
        entity_mappings={"C001": mappings},
    )
    payload = output.model_dump(mode="json")
    payload["assignments"][0]["presentation_form"]["primary"] = "PF99"
    invalid = HybridAssignmentOutput.model_validate(payload)
    with pytest.raises(PipelineError, match="non active|非 active|Form"):
        validate_assignments(
            invalid,
            expected_ids={"C001"},
            domain_draft=domain(),
            registry=registry,
            entity_mappings={"C001": mappings},
        )


def test_label_budgets_fail_without_silent_truncation() -> None:
    payload = assignment("C001").model_dump(mode="json")
    payload["object_types"] = [
        {
            "id": f"OT{index:02d}",
            "source_entities": [f"E{index}"],
            "mapping_source": "model_assisted",
            "confidence": "medium",
            "evidence": ["证据"],
        }
        for index in range(1, 4)
    ]
    with pytest.raises(ValidationError):
        HybridControlledAssignment.model_validate(payload)
    assert len(payload["object_types"]) == 3


def test_secondary_domain_shorthand_is_canonicalized_without_new_label() -> None:
    registry = load_controlled_vocabularies()
    payload = assignment("C001").model_dump(mode="json")
    payload["domain"]["secondary_paths"] = ["d_02_01"]
    output = HybridAssignmentOutput(
        assignments=[HybridControlledAssignment.model_validate(payload)]
    )
    mappings = map_entities_to_object_types(["Paper A"], registry)
    validate_assignments(
        output,
        expected_ids={"C001"},
        domain_draft=domain(),
        registry=registry,
        entity_mappings={"C001": mappings},
    )
    assert output.assignments[0].domain.secondary_paths == [["d_02", "d_02_01"]]


def test_repair_hint_limits_object_sources_to_each_cards_frozen_entities() -> None:
    registry = load_controlled_vocabularies()
    hint = _build_repair_schema_hint(
        {
            "C001": map_entities_to_object_types(["Paper A"], registry),
            "C002": [],
        }
    )
    assert '"C001":["Paper A"]' in hint
    assert '"C002":[]' in hint
    assert "object_types must be []" in hint


def test_dynamic_faceting_only_exposes_nonzero_options() -> None:
    registry = load_controlled_vocabularies()
    values = [
        assignment("C001"),
        assignment("C002"),
        assignment("C003", form="PF01", object_id="OT01", context_id="UC02"),
        assignment("C004", domain_id="d_02", form="PF03", object_id=None, context_id=None),
    ]
    result = build_dynamic_faceting(values, registry)
    assert result["version"] == DYNAMIC_FACETING_VERSION
    assert result["metrics"]["exposed_zero_option_count"] == 0
    assert all(
        count > 0
        for steps in (result["first_steps"], result["second_steps"], result["third_steps"])
        for step in steps
        for options in step["available_options"].values()
        for count in options.values()
    )


def test_query_is_or_within_facet_and_and_across_facets() -> None:
    values = [
        assignment("C001"),
        assignment("C002", form="PF01", object_id="OT01", context_id="UC02"),
        assignment("C003", form="PF03", object_id="OT01", context_id="UC02"),
    ]
    from shiliu.taxonomy.controlled_facets import _facet_records

    records = _facet_records(values)
    assert _query(records, {"presentation_form": {"PF01", "PF04"}}) == {
        "C001",
        "C002",
    }
    assert _query(
        records,
        {"presentation_form": {"PF01", "PF04"}, "focus_object_type": {"OT01"}},
    ) == {"C002"}


def test_cross_facet_redundancy_requires_support_three_and_both_probabilities() -> None:
    registry = load_controlled_vocabularies()
    values = [assignment(f"C{index:03d}") for index in range(1, 4)]
    result = build_dynamic_faceting(values, registry)
    pairs = result["near_duplicate_cross_facet"]
    assert any(
        item["left"] == "presentation_form:PF04"
        and item["right"] == "focus_object_type:OT04"
        for item in pairs
    )


def test_derived_filter_is_report_only_and_keeps_expression() -> None:
    registry = load_controlled_vocabularies()
    values = [assignment(f"C{index:03d}") for index in range(1, 4)]
    proposals = build_derived_filter_proposals(values, registry)
    assert proposals == [
        {
            "id": "DF_PF04_OT04",
            "display_name": "原理解析 · paper_or_research_artifact",
            "expression": {
                "presentation_form": ["PF04"],
                "focus_object_type": ["OT04"],
            },
            "support_count": 3,
            "supporting_content_ids": ["C001", "C002", "C003"],
            "status": "report_only",
        }
    ]


def test_gate_blocks_domain_history_and_forbidden_runtime_inputs() -> None:
    registry = load_controlled_vocabularies()
    values = [assignment(f"C{index:03d}", context_id=None) for index in range(1, 4)]
    dynamic = build_dynamic_faceting(values, registry)
    quality = build_quality_gate(
        assignments=values,
        registry=registry,
        dynamic=dynamic,
        source_domain_hash="before",
        current_domain_hash="after",
        source_vocabulary_hashes=registry.hashes,
        current_vocabulary_hashes=registry.hashes,
        manifest_inputs=["Run #17 open vocabulary"],
        historical_manifest_hashes={"run-17": "old"},
        current_historical_hashes={"run-17": "changed"},
    )
    codes = {item["code"] for item in quality.blocking_issues}
    assert {
        "frozen_domain_modified",
        "historical_run_modified",
        "forbidden_runtime_input",
    } <= codes


def test_context_empty_rate_is_warning_only_not_blocking() -> None:
    registry = load_controlled_vocabularies()
    values = [
        assignment(f"C{index:03d}", context_id=None) for index in range(1, 5)
    ]
    quality = build_quality_gate(
        assignments=values,
        registry=registry,
        dynamic=build_dynamic_faceting(values, registry),
        source_domain_hash="same",
        current_domain_hash="same",
        source_vocabulary_hashes=registry.hashes,
        current_vocabulary_hashes=registry.hashes,
        manifest_inputs=["controlled vocabulary v1"],
        historical_manifest_hashes={"run-17": "same"},
        current_historical_hashes={"run-17": "same"},
    )
    assert quality.passed
    assert "high_suggested_context_empty_rate" in {
        item["code"] for item in quality.warnings
    }


def test_reviewer_bundle_excludes_open_vocabulary_and_private_eval() -> None:
    registry = load_controlled_vocabularies()
    values = [assignment(f"C{index:03d}") for index in range(1, 4)]
    dynamic = build_dynamic_faceting(values, registry)
    quality = build_quality_gate(
        assignments=values,
        registry=registry,
        dynamic=dynamic,
        source_domain_hash="same",
        current_domain_hash="same",
        source_vocabulary_hashes=registry.hashes,
        current_vocabulary_hashes=registry.hashes,
        manifest_inputs=["controlled vocabulary v1"],
        historical_manifest_hashes={"run-17": "same"},
        current_historical_hashes={"run-17": "same"},
    )
    bundle = build_reviewer_bundle(
        protocol={
            "snapshot_hash": "snapshot",
            "domain_run_id": 12,
            "sample_profile_run_id": "profile",
            "vocabulary_hashes": registry.hashes,
            "historical_manifest_hashes": {"run-17": "same"},
        },
        registry=registry,
        entity_mappings={value.content_id: [] for value in values},
        assignments=values,
        dynamic=dynamic,
        proposals=[],
        derived=build_derived_filter_proposals(values, registry),
        quality=quality,
    )
    assert "Run #17 open vocabulary" in bundle["excluded"]
    assert "Silver Reference" in bundle["excluded"]
    assert "candidate_decisions" not in bundle


def test_cli_exposes_hybrid_spike_creation() -> None:
    parsed = build_parser().parse_args(
        [
            "taxonomy",
            "create-hybrid-facets-spike",
            "--sample-profile-run-id",
            "accepted-profile",
        ]
    )
    assert parsed.snapshot_id == 2
    assert parsed.domain_run_id == 12
    assert ASSIGNMENT_SCHEMA_VERSION == "controlled-facet-assignment-v1"
