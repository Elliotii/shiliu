from __future__ import annotations

import json

from .agreement import compare_reviews
from .canary import render_human_review_packet, scan_artifacts_for_secrets
from .contracts import AnnotationReviewV2
from .finalize_stage2r_b1_b import _packet, _path_result, _read
from .query_grounding import validate_query_grounding
from .reviewer_draft import ReviewerDraft
from .run_stage2r_b1_b import OUTPUT_ROOT, _specs, _write_json


def main() -> None:
    specs = {spec.case_id: spec for spec in _specs()}
    summaries = _read(OUTPUT_ROOT / "canary_summary.json")
    summary_by_case = {item["case_id"]: item for item in summaries}
    audit: list[dict[str, object]] = []
    for root in sorted(OUTPUT_ROOT.glob("B1B_*")):
        identity = _read(root / "review_run.json")
        case_id = str(identity["case_id"])
        packet = _packet(root / "primary/reviewer_packet.json")
        path_results = {}
        reviews = {}
        for role in ("primary", "secondary"):
            role_root = root / role
            draft_path = role_root / "reviewer_draft.repair.json"
            if not draft_path.exists():
                draft_path = role_root / "reviewer_draft.initial.json"
            draft = ReviewerDraft.model_validate(_read(draft_path))
            grounding = validate_query_grounding(draft, packet)
            validation = _read(role_root / "reviewer_validation.json")
            previous = validation.get("query_grounding_status")
            validation["query_grounding_status"] = grounding.status
            validation["query_grounding_errors"] = list(grounding.errors)
            _write_json(role_root / "reviewer_validation.json", validation)
            review = AnnotationReviewV2.model_validate(_read(role_root / "canonical_review.json"))
            reviews[role] = review
            path_results[role] = _path_result(review, validation)
            identity[f"{role}_query_grounding"] = grounding.status
            summary_by_case[case_id][f"{role}_query_grounding"] = grounding.status
            audit.append(
                {
                    "case_id": case_id,
                    "role": role,
                    "draft": draft_path.relative_to(OUTPUT_ROOT).as_posix(),
                    "previous_status": previous,
                    "current_status": grounding.status,
                    "findings": list(grounding.errors),
                    "label_changed": False,
                }
            )
        agreement = compare_reviews(
            reviews["primary"], reviews["secondary"], cross_language=False, asr_error=False
        )
        _write_json(root / "review_run.json", identity)
        (root / "human_review_packet.md").write_text(
            render_human_review_packet(
                spec=specs[case_id],
                packet=packet,
                primary=path_results["primary"],
                secondary=path_results["secondary"],
                agreement=agreement,
                review_run_id=root.name,
            ),
            encoding="utf-8",
        )
    _write_json(OUTPUT_ROOT / "canary_summary.json", summaries)
    _write_json(
        OUTPUT_ROOT / "query_grounding_revalidation.audit.json",
        {
            "validator_policy": "exact anchors plus conservative CLI/command-line lexical association",
            "reviews": audit,
            "labels_changed": False,
            "provider_resampled": False,
        },
    )
    _write_json(
        OUTPUT_ROOT / "secret_scan.audit.json",
        scan_artifacts_for_secrets(OUTPUT_ROOT, secrets=()),
    )


if __name__ == "__main__":
    main()
