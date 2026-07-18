from __future__ import annotations

import pytest
from pydantic import ValidationError

from shiliu.cli import build_parser
from shiliu.taxonomy.candidates import (
    CompactContentTypeCandidate,
    CompactContentTypeTable,
    TopLevelDomainDraft,
    TopLevelDomainNode,
)
from shiliu.taxonomy.faceted_metadata import (
    ASSIGNMENT_SCHEMA_VERSION,
    DECOMPOSITION_SCHEMA_VERSION,
    FACETED_PROTOCOL_VERSION,
    VOCABULARY_SCHEMA_VERSION,
    AssignmentEvidence,
    CandidateDecomposition,
    CandidateDecompositionOutput,
    DomainFacetAssignment,
    FacetComponent,
    FacetLabelAssignment,
    FacetVocabularyNode,
    FacetedAssignment,
    FacetedVocabularyOutput,
    PresentationFormAssignment,
    build_quality_gate,
    build_reviewer_bundle,
    apply_vocabulary_support_policy,
    simulate_filters,
    validate_decomposition,
    validate_vocabulary,
)


def component(name: str) -> FacetComponent:
    return FacetComponent(
        canonical_name=name,
        definition=f"{name} 的边界定义",
        evidence=[f"{name} 的来源证据"],
    )


def decomposition(
    *, source_name: str = "复合来源", compound: bool = True,
    form_name: str | None = "步骤演示",
) -> CandidateDecomposition:
    return CandidateDecomposition(
        source_candidate_id="nct_001",
        source_name=source_name,
        presentation_form_component=component(form_name) if form_name else None,
        focus_object_type_components=[component("软件工具")],
        use_context_components=[component("求职准备")],
        domain_component=component("软件工程"),
        entity_components=["ExampleKit"],
        is_compound=compound,
        decomposition_reason="来源同时包含形式、对象、情境和领域，分别保留。",
        supporting_evidence=["来源定义", "代表内容"],
        confidence="high",
        unresolved_parts=[],
    )


def table() -> CompactContentTypeTable:
    return CompactContentTypeTable(
        content_types=[
            CompactContentTypeCandidate(
                candidate_id="nct_001",
                name="复合来源",
                definition="复合定义",
                includes=[],
                excludes=[],
                support_count=2,
                batch_count=1,
                supporting_ids=["C001", "C002"],
                representative_ids=["C001"],
            )
        ],
        source_batch_count=1,
    )


def node(
    node_id: str, facet: str, name: str, *, status: str = "stable",
    supporting: list[str] | None = None,
) -> FacetVocabularyNode:
    return FacetVocabularyNode(
        temporary_id=node_id,
        facet=facet,
        canonical_name=name,
        definition=f"{name} 的定义",
        includes=["包含边界"],
        excludes=["排除边界"],
        aliases=[],
        supporting_candidate_ids=["nct_001"],
        supporting_content_ids=supporting or ["C001", "C002"],
        status=status,
        rejection_reason="不属于该分面" if status == "rejected" else None,
    )


def vocabulary(*, object_name: str = "软件工具") -> FacetedVocabularyOutput:
    return FacetedVocabularyOutput(
        presentation_forms=[node("pf_01", "presentation_form", "步骤演示")],
        focus_object_types=[node("fo_01", "focus_object_type", object_name)],
        use_contexts=[node("uc_01", "use_context", "求职准备", status="draft")],
    )


def domain() -> TopLevelDomainDraft:
    return TopLevelDomainDraft(
        domains=[
            TopLevelDomainNode(
                id="d_01",
                name="软件工程",
                definition="软件系统工程实践",
                includes=["工程"],
                excludes=["硬件"],
                supporting_ids=["C001", "C002"],
                representative_ids=["C001"],
                children=[],
            )
        ],
        candidate_decisions=[],
        consolidation_notes=[],
    )


def assignment(
    content_id: str, *, form: str | None = "pf_01",
    objects: list[str] | None = None, contexts: list[str] | None = None,
) -> FacetedAssignment:
    objects = ["fo_01"] if objects is None else objects
    contexts = [] if contexts is None else contexts
    return FacetedAssignment(
        content_id=content_id,
        domain=DomainFacetAssignment(
            primary_path=["d_01"], secondary_paths=[], confidence="high"
        ),
        presentation_form=PresentationFormAssignment(
            status="assigned" if form else "unknown",
            primary=form,
            secondary=None,
            alternatives=[],
            confidence="high" if form else "low",
        ),
        focus_object_types=[
            FacetLabelAssignment(node_id=value, confidence="high", evidence="对象证据")
            for value in objects
        ],
        use_contexts=[
            FacetLabelAssignment(node_id=value, confidence="medium", evidence="场景证据")
            for value in contexts
        ],
        entities=["ExampleKit"],
        ambiguities=[],
        evidence=AssignmentEvidence(
            domain=["领域证据"],
            presentation_form=["形式证据"] if form else [],
            focus_object_types=["对象证据"] if objects else [],
            use_contexts=["场景证据"] if contexts else [],
        ),
    )


def test_versions_do_not_reuse_deprecated_content_type_semantics() -> None:
    assert DECOMPOSITION_SCHEMA_VERSION == "faceted-candidate-decomposition-v1"
    assert VOCABULARY_SCHEMA_VERSION == "faceted-controlled-vocabulary-v1"
    assert ASSIGNMENT_SCHEMA_VERSION == "faceted-assignment-v1"
    assert FACETED_PROTOCOL_VERSION == "checkpoint310-faceted-metadata-v1"


def test_compound_candidate_can_route_to_four_facets_and_entity() -> None:
    value = decomposition()
    assert value.presentation_form_component.canonical_name == "步骤演示"
    assert value.focus_object_type_components[0].canonical_name == "软件工具"
    assert value.use_context_components[0].canonical_name == "求职准备"
    assert value.domain_component.canonical_name == "软件工程"
    assert value.entity_components == ["ExampleKit"]


def test_decomposition_requires_exact_source_coverage() -> None:
    output = CandidateDecompositionOutput(decisions=[decomposition()], discarded_parts=[])
    validate_decomposition(output, candidates=table())
    changed = output.model_copy(
        update={"decisions": [decomposition(source_name="被改写的来源")]}
    )
    with pytest.raises(Exception, match="来源名称"):
        validate_decomposition(changed, candidates=table())


def test_object_and_context_budgets_fail_without_truncation() -> None:
    payload = assignment("C001").model_dump(mode="json")
    payload["focus_object_types"] = [
        {"node_id": "fo_01", "confidence": "high", "evidence": "证据"},
        {"node_id": "fo_02", "confidence": "high", "evidence": "证据"},
        {"node_id": "fo_03", "confidence": "high", "evidence": "证据"},
    ]
    with pytest.raises(ValidationError):
        FacetedAssignment.model_validate(payload)
    assert len(payload["focus_object_types"]) == 3


def test_presentation_secondary_budget_is_structurally_single() -> None:
    fields = PresentationFormAssignment.model_fields
    assert "secondary" in fields
    assert "secondaries" not in fields


def test_use_context_can_be_empty() -> None:
    assert assignment("C001", contexts=[]).use_contexts == []


def test_assigned_facets_require_evidence() -> None:
    payload = assignment("C001").model_dump(mode="json")
    payload["evidence"]["presentation_form"] = []
    with pytest.raises(ValidationError, match="requires evidence"):
        FacetedAssignment.model_validate(payload)


def test_vocabulary_requires_rejection_reason_only_for_rejected() -> None:
    with pytest.raises(ValidationError):
        node("pf_01", "presentation_form", "步骤演示").model_copy(
            update={"rejection_reason": "不应出现"}
        ).model_validate(
            {
                **node("pf_01", "presentation_form", "步骤演示").model_dump(),
                "rejection_reason": "不应出现",
            }
        )


def test_vocabulary_capacity_is_derived_from_source_not_hidden_top_k() -> None:
    forms = [
        node(f"pf_{index:02d}", "presentation_form", f"形式{index}")
        for index in range(1, 29)
    ]
    value = FacetedVocabularyOutput(
        presentation_forms=forms,
        focus_object_types=[node("fo_01", "focus_object_type", "对象")],
        use_contexts=[node("uc_01", "use_context", "场景")],
    )
    assert len(value.presentation_forms) == 28
    payload = value.model_dump(mode="json")
    payload["presentation_forms"] += [
        node(f"pf_{index:02d}", "presentation_form", f"形式{index}").model_dump(mode="json")
        for index in range(29, 33)
    ]
    with pytest.raises(ValidationError):
        FacetedVocabularyOutput.model_validate(payload)


def test_single_content_stable_is_audited_and_downgraded_to_draft() -> None:
    output = vocabulary()
    output.presentation_forms[0] = node(
        "pf_01", "presentation_form", "步骤演示", supporting=["C001"]
    )
    decomp = CandidateDecompositionOutput(decisions=[decomposition()], discarded_parts=[])
    validate_vocabulary(
        output,
        decomposition=decomp,
        valid_content_ids={"C001", "C002"},
    )
    normalized, events = apply_vocabulary_support_policy(output)
    assert normalized.presentation_forms[0].status == "draft"
    assert events == [
        {
            "field_path": "presentation_forms[0].status",
            "node_id": "pf_01",
            "original_value": "stable",
            "normalized_value": "draft",
            "reason": "stable requires at least two supporting content IDs",
            "support_count": 1,
        }
    ]


def test_specific_entity_in_object_type_blocks_gate() -> None:
    decomp = CandidateDecompositionOutput(decisions=[decomposition()], discarded_parts=[])
    values = [assignment("C001"), assignment("C002")]
    filters = simulate_filters(values)
    quality = build_quality_gate(
        table=table(),
        decomposition=decomp,
        vocabulary=vocabulary(object_name="ExampleKit"),
        assignments=values,
        filter_result=filters,
        source_domain_hash="same",
        current_domain_hash="same",
        runtime_inputs=["Snapshot #2"],
        domain_draft=domain(),
    )
    assert not quality.passed
    assert "entity_in_focus_object_type" in {
        item["code"] for item in quality.blocking_issues
    }


def test_compound_source_name_copied_to_form_blocks_gate() -> None:
    copied = decomposition(source_name="复合来源", form_name="复合来源")
    decomp = CandidateDecompositionOutput(decisions=[copied], discarded_parts=[])
    values = [assignment("C001"), assignment("C002")]
    quality = build_quality_gate(
        table=table(), decomposition=decomp, vocabulary=vocabulary(),
        assignments=values, filter_result=simulate_filters(values),
        source_domain_hash="same", current_domain_hash="same",
        runtime_inputs=["Snapshot #2"], domain_draft=domain(),
    )
    assert "compound_candidate_copied_to_form" in {
        item["code"] for item in quality.blocking_issues
    }


def test_filter_uses_or_within_facet_and_and_across_facets() -> None:
    first = assignment("C001", contexts=["uc_01"])
    second = assignment("C002", contexts=[])
    result = simulate_filters([first, second])
    assert result["semantics"] == {
        "within_facet": "OR",
        "across_facets": "AND",
        "unselected_facet": "ignored",
    }
    combo = next(
        item for item in result["two_facet_combinations"]
        if item["facets"] == ["presentation_form", "use_context"]
        and item["labels"] == ["pf_01", "uc_01"]
    )
    assert combo["content_ids"] == ["C001"]


def test_domain_hash_change_blocks_gate() -> None:
    values = [assignment("C001"), assignment("C002")]
    quality = build_quality_gate(
        table=table(),
        decomposition=CandidateDecompositionOutput(
            decisions=[decomposition()], discarded_parts=[]
        ),
        vocabulary=vocabulary(), assignments=values,
        filter_result=simulate_filters(values), source_domain_hash="before",
        current_domain_hash="after", runtime_inputs=["Snapshot #2"],
        domain_draft=domain(),
    )
    assert "frozen_domain_draft_modified" in {
        item["code"] for item in quality.blocking_issues
    }


def test_runtime_silver_reference_is_blocked() -> None:
    values = [assignment("C001"), assignment("C002")]
    quality = build_quality_gate(
        table=table(),
        decomposition=CandidateDecompositionOutput(
            decisions=[decomposition()], discarded_parts=[]
        ),
        vocabulary=vocabulary(), assignments=values,
        filter_result=simulate_filters(values), source_domain_hash="same",
        current_domain_hash="same", runtime_inputs=["Silver Reference"],
        domain_draft=domain(),
    )
    assert "silver_reference_runtime_leak" in {
        item["code"] for item in quality.blocking_issues
    }


def test_reviewer_bundle_excludes_candidate_decision_correctness_and_silver() -> None:
    values = [assignment("C001"), assignment("C002")]
    decomp = CandidateDecompositionOutput(decisions=[decomposition()], discarded_parts=[])
    quality = build_quality_gate(
        table=table(), decomposition=decomp, vocabulary=vocabulary(),
        assignments=values, filter_result=simulate_filters(values),
        source_domain_hash="same", current_domain_hash="same",
        runtime_inputs=["Snapshot #2"], domain_draft=domain(),
    )
    bundle = build_reviewer_bundle(
        protocol={
            "protocol_version": FACETED_PROTOCOL_VERSION,
            "snapshot_hash": "hash",
            "domain_run_id": 12,
            "candidate_run_id": 14,
            "sample_profile_run_id": "profile",
            "source_artifact_hashes": {},
        },
        decomposition=decomp,
        vocabulary=vocabulary(),
        assignments=values,
        filter_result=simulate_filters(values),
        quality=quality,
    )
    assert "candidate_decisions" not in bundle
    assert "Silver Reference" in bundle["excluded"]


def test_cli_exposes_checkpoint310_creation() -> None:
    parsed = build_parser().parse_args(
        [
            "taxonomy",
            "create-faceted-spike",
            "--sample-profile-run-id",
            "profile-spike-accepted",
        ]
    )
    assert parsed.domain_run_id == 12
    assert parsed.candidate_run_id == 14
