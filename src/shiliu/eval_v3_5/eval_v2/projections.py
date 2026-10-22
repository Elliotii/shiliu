from __future__ import annotations

from .contracts import MasterCaseV2


def project_v3_retrieval(case: MasterCaseV2) -> dict[str, object]:
    return {"view_version": "v3-retrieval-view-from-eval-v2",
            "case_identity": case.case_identity.model_dump(mode="json"),
            "corpus_truth": case.corpus_truth.model_dump(mode="json"),
            "retrieval_gold": case.retrieval_gold.model_dump(mode="json"),
            "constraint": "diagnostic_only_no_v3_retuning_authority"}


def project_v3_5_fine_evidence(case: MasterCaseV2) -> dict[str, object]:
    evidence = case.evidence_gold
    return {"view_version": "v3.5-fine-evidence-view-from-eval-v2", "case_id": case.case_identity.case_id,
            "query": case.case_identity.query, "target_video_ids": case.corpus_truth.target_video_ids,
            "acceptable_evidence_groups": [x.model_dump(mode="json") for x in evidence.acceptable_evidence_groups],
            "required_spans": [x.model_dump(mode="json") for x in evidence.required_spans],
            "optional_context_spans": [x.model_dump(mode="json") for x in evidence.optional_context_spans],
            "source_artifact_ids": case.corpus_truth.source_artifact_ids,
            "source_versions": case.corpus_truth.source_versions}


def project_v3_5_sufficiency(case: MasterCaseV2) -> dict[str, object]:
    return {"view_version": "v3.5-sufficiency-view-from-eval-v2", "case_id": case.case_identity.case_id,
            "query": case.case_identity.query,
            "required_aspects": [x.model_dump(mode="json") for x in case.evidence_gold.required_aspects],
            **case.sufficiency_gold.model_dump(mode="json")}

