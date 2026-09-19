from __future__ import annotations

import pytest
from pydantic import ValidationError

from shiliu.cli import build_parser
from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import TopLevelDomainDraft, TopLevelDomainNode
from shiliu.taxonomy.controlled_facets import (
    ControlledDomainAssignment,
    ControlledFormAssignment,
    ControlledObjectAssignment,
    HybridAssignmentOutput,
    HybridControlledAssignment,
    SuggestedContextAssignment,
    build_dynamic_faceting,
    load_controlled_vocabularies,
    map_entities_to_object_types,
)
from shiliu.taxonomy.controlled_facets_completion import (
    MODEL_SCHEMA_VERSION,
    ModelFacetAssignment,
    ModelFacetOutput,
    ModelObjectAssignment,
    adapt_historical_batch,
    build_completion_derived_filters,
    build_completion_dynamic_faceting,
    build_completion_metrics,
    build_completion_quality_gate,
    build_completion_repair_hint,
    combine_frozen_domain,
    normalize_model_assignment,
)


def domain_draft() -> TopLevelDomainDraft:
    return TopLevelDomainDraft(
        domains=[
            TopLevelDomainNode(
                id="d_01",
                name="软件工程",
                definition="软件工程领域",
                includes=["工程"],
                excludes=["硬件"],
                supporting_ids=["C001"],
                representative_ids=["C001"],
                children=[],
            )
        ]
    )


def model_assignment(
    content_id: str = "C001",
    *,
    objects: list[ModelObjectAssignment] | None = None,
    context: str | None = "UC07",
) -> ModelFacetAssignment:
    return ModelFacetAssignment(
        content_id=content_id,
        presentation_form=ControlledFormAssignment(
            primary="PF04",
            secondary=None,
            confidence="high",
            evidence=["解释原理"],
        ),
        object_types=objects or [],
        suggested_use_contexts=(
            [
                SuggestedContextAssignment(
                    id=context, confidence="medium", evidence=["学习使用"]
                )
            ]
            if context
            else []
        ),
        facet_novelty=[],
        ambiguities=[],
    )


def object_item(
    entity: str,
    *,
    object_id: str = "OT07",
    confidence: str = "medium",
    evidence: list[str] | None = None,
) -> ModelObjectAssignment:
    return ModelObjectAssignment(
        id=object_id,
        source_entities=[entity],
        mapping_source="model_assisted",
        confidence=confidence,
        evidence=evidence or [entity],
    )


def full_assignment(content_id: str = "C001") -> HybridControlledAssignment:
    return combine_frozen_domain(
        model_assignment(
            content_id,
            objects=[object_item("Company A")],
        ),
        ControlledDomainAssignment(
            primary_path=["d_01"], secondary_paths=[], confidence="high"
        ),
    )


def test_duplicate_object_type_is_merged_with_auditable_max_confidence() -> None:
    value = model_assignment(
        objects=[
            object_item("Company A", confidence="medium", evidence=["A", "shared"]),
            object_item("Organization B", confidence="high", evidence=["shared", "B"]),
        ]
    )
    normalized, events = normalize_model_assignment(
        value,
        allowed_entities={"Company A", "Organization B"},
        timestamp="2026-01-01T00:00:00Z",
    )
    assert len(normalized.object_types) == 1
    merged = normalized.object_types[0]
    assert merged.id == "OT07"
    assert merged.source_entities == ["Company A", "Organization B"]
    assert merged.evidence == ["A", "shared", "B"]
    assert merged.confidence == "high"
    assert events[0]["original_confidences"] == ["medium", "high"]
    assert events[0]["operation"] == "merge_duplicate_object_type_v1"
    assert events[0]["original_item_count"] == 2


def test_duplicate_entities_and_evidence_keep_first_seen_order() -> None:
    item1 = ModelObjectAssignment(
        id="OT07",
        source_entities=["A", "B"],
        mapping_source="model_assisted",
        confidence="medium",
        evidence=["one", "two"],
    )
    item2 = ModelObjectAssignment(
        id="OT07",
        source_entities=["B", "C"],
        mapping_source="model_assisted",
        confidence="medium",
        evidence=["two", "three"],
    )
    normalized, _ = normalize_model_assignment(
        model_assignment(objects=[item1, item2]),
        allowed_entities={"A", "B", "C"},
        timestamp="fixed",
    )
    assert normalized.object_types[0].source_entities == ["A", "B", "C"]
    assert normalized.object_types[0].evidence == ["one", "two", "three"]


def test_different_object_type_ids_are_not_merged() -> None:
    normalized, events = normalize_model_assignment(
        model_assignment(
            objects=[object_item("A", object_id="OT07"), object_item("B", object_id="OT01")]
        ),
        allowed_entities={"A", "B"},
        timestamp="fixed",
    )
    assert [value.id for value in normalized.object_types] == ["OT07", "OT01"]
    assert events == []


def test_object_normalization_rejects_entity_outside_card_whitelist() -> None:
    with pytest.raises(PipelineError, match="白名单"):
        normalize_model_assignment(
            model_assignment(objects=[object_item("unknown")]),
            allowed_entities={"known"},
            timestamp="fixed",
        )


def test_model_output_schema_rejects_domain_and_unknown_fields() -> None:
    payload = {
        "version": MODEL_SCHEMA_VERSION,
        "assignments": [
            {
                **model_assignment().model_dump(mode="json"),
                "domain": {"primary_path": ["d_01"]},
            }
        ],
    }
    with pytest.raises(ValidationError):
        ModelFacetOutput.model_validate(payload)


def test_frozen_domain_is_combined_locally_without_changing_facets() -> None:
    model = model_assignment(objects=[object_item("Company A")])
    domain = ControlledDomainAssignment(
        primary_path=["d_01"], secondary_paths=[], confidence="high"
    )
    combined = combine_frozen_domain(model, domain)
    assert combined.domain == domain
    assert combined.presentation_form == model.presentation_form
    assert [value.model_dump(mode="json") for value in combined.object_types] == [
        value.model_dump(mode="json") for value in model.object_types
    ]


def test_historical_adapter_removes_only_domain_and_records_no_provider_call() -> None:
    legacy = full_assignment()
    mappings = map_entities_to_object_types(
        ["Company A"], load_controlled_vocabularies()
    )
    adapted, audit = adapt_historical_batch(
        HybridAssignmentOutput(assignments=[legacy]),
        expected_ids=["C001"],
        entity_mappings={"C001": mappings},
        timestamp="fixed",
    )
    assert adapted == [legacy]
    assert audit["semantic_fields_changed"] is False
    assert audit["operations"][0]["operation"] == "remove_legacy_model_domain_v1"


def test_repair_hint_has_entity_whitelist_and_forbids_domain() -> None:
    registry = load_controlled_vocabularies()
    hint = build_completion_repair_hint(
        expected_ids=["C001"],
        entity_mappings={
            "C001": map_entities_to_object_types(["Company A"], registry)
        },
        registry=registry,
    )
    assert '"forbidden_fields":["domain"]' in hint
    assert '"C001":["Company A"]' in hint
    assert "do not redo semantic assignment" in hint


def test_derived_filters_include_form_object_and_form_context_expressions() -> None:
    registry = load_controlled_vocabularies()
    values = [full_assignment(f"C{index:03d}") for index in range(1, 4)]
    proposals = build_completion_derived_filters(values, registry)
    expressions = [value["expression"] for value in proposals]
    assert {
        "presentation_form": ["PF04"],
        "focus_object_type": ["OT07"],
    } in expressions
    assert {
        "presentation_form": ["PF04"],
        "suggested_use_context": ["UC07"],
    } in expressions
    assert all(value["status"] == "report_only" for value in proposals)


def test_completion_metrics_separate_untyped_and_model_assisted_counts() -> None:
    registry = load_controlled_vocabularies()
    values = [full_assignment()]
    mappings = map_entities_to_object_types(["Company A", "Unused"], registry)
    metrics = build_completion_metrics(
        assignments=values,
        entity_mappings={"C001": mappings},
        dynamic=build_dynamic_faceting(values, registry),
        normalization_events=[],
    )
    objects = metrics["focus_object_type"]
    assert objects["deterministic_entity_mapping_count"] == 0
    assert objects["model_assisted_object_assignment_count"] == 1
    assert objects["untyped_entity_count"] == 2
    assert objects["untyped_entity_with_no_object_count"] == 1


def test_completion_gate_blocks_incomplete_results_and_forced_context() -> None:
    registry = load_controlled_vocabularies()
    values = [full_assignment(f"C{index:03d}") for index in range(1, 4)]
    quality = build_completion_quality_gate(
        assignments=values,
        registry=registry,
        dynamic=build_dynamic_faceting(values, registry),
        source_domain_hash="same",
        current_domain_hash="same",
        source_vocabulary_hashes=registry.hashes,
        current_vocabulary_hashes=registry.hashes,
        manifest_inputs=["controlled vocabulary v1"],
        historical_tree_hashes={"run-20": "same"},
        current_historical_tree_hashes={"run-20": "same"},
        model_output_forbidden_field_count=0,
    )
    codes = {value["code"] for value in quality.blocking_issues}
    assert "completion_assignment_incomplete" in codes
    assert "suggested_context_forced_filled" in codes


def test_dynamic_faceting_still_exposes_no_zero_support_options() -> None:
    registry = load_controlled_vocabularies()
    result = build_completion_dynamic_faceting(
        [full_assignment(f"C{index:03d}") for index in range(1, 4)],
        registry,
        domain_draft(),
    )
    assert result["metrics"]["exposed_zero_option_count"] == 0
    paths = result["click_path_simulation"]
    assert any(
        "focus_object_type" in item["selections"] for item in paths["second_steps"]
    )
    assert any(
        "suggested_use_context" in item["selections"]
        for item in paths["third_steps"]
    )


def test_cli_exposes_completion_creation_command() -> None:
    args = build_parser().parse_args(
        [
            "taxonomy",
            "create-controlled-facets-completion",
            "--source-run-id",
            "20",
        ]
    )
    assert args.source_run_id == 20
