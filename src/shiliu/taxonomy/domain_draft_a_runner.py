from __future__ import annotations

import argparse
import json
from pathlib import Path

from shiliu.app import Application
from shiliu.taxonomy.controlled_facets import (
    _stable_hash,
    _utc_now,
    _write_json,
    _write_json_once,
)
from shiliu.taxonomy.domain_draft_a import (
    DOMAIN_DRAFT_A_PROMPT_VERSION,
    DOMAIN_DRAFT_A_SCHEMA_HINT,
    DomainDraftA,
    evaluate_domain_draft_a,
    validate_domain_draft_a,
)
from shiliu.taxonomy.model_calls import _write_repair_semantic_diff
from shiliu.taxonomy.workflow import _combined_audit


def _recover_existing_repair(
    *, app: Application, run_id: int, call_dir: Path,
    clusters: dict[str, object],
) -> DomainDraftA | None:
    repair_raw_path = call_dir / "repair-raw-response.txt"
    audit_path = call_dir / "audit.json"
    repair_audit_path = call_dir / "repair-audit.json"
    validation_path = call_dir / "validation-error.txt"
    if not all(path.is_file() for path in (
        repair_raw_path, audit_path, repair_audit_path, validation_path,
    )):
        return None
    result = DomainDraftA.model_validate_json(
        repair_raw_path.read_text(encoding="utf-8")
    )
    validate_domain_draft_a(result, final_clusters=clusters)  # type: ignore[arg-type]
    output = result.model_dump(mode="json")
    _write_json(call_dir / "parsed-output.json", output)
    _write_repair_semantic_diff(
        call_dir=call_dir,
        original_raw=(call_dir / "raw-response.txt").read_text(encoding="utf-8"),
        repaired_value=output,
        validation_error=validation_path.read_text(encoding="utf-8"),
        stage_id=DOMAIN_DRAFT_A_PROMPT_VERSION,
        attempt_id="existing-repair-local-validator-correction",
    )
    repair_audit = json.loads(repair_audit_path.read_text(encoding="utf-8"))
    successful_attempts = [
        attempt for attempt in repair_audit.get("attempt_history") or []
        if attempt.get("raw_response_path") == repair_raw_path.name
    ]
    repair_audit.update({
        "status": "completed_by_local_validator_rule_correction",
        "usage": None,
        "raw_response_path": repair_raw_path.name,
        "abandoned_request_without_response_count": 1,
        "local_recovery": {
            "provider_call_count": 0,
            "source_path": repair_raw_path.name,
            "source_hash": _stable_hash(json.loads(repair_raw_path.read_text(encoding="utf-8"))),
            "result_hash": _stable_hash(output),
            "reason": "原 Gate 误把父子节点共享来源 Cluster 视为跨分支重复；"
            "修正 Gate 后原 Repair 响应无需语义改写即可通过。",
        },
        "finished_at": _utc_now(),
    })
    if successful_attempts:
        repair_audit["accepted_attempt"] = successful_attempts[-1]
    _write_json(repair_audit_path, repair_audit)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.update({
        "status": "completed",
        "repair": repair_audit,
        "local_recovery": repair_audit["local_recovery"],
        "finished_at": _utc_now(),
    })
    _write_json(audit_path, audit)
    app.taxonomy_run_repository.complete_stage(
        run_id,
        "domain_draft_a_synthesis",
        "main",
        output_path=str(call_dir / "parsed-output.json"),
        output_hash=_stable_hash(output),
        audit=_combined_audit(audit),
    )
    return result


def run(run_id: int) -> dict[str, object]:
    app = Application()
    run_dir = (
        app.paths.content_dir / "taxonomy" / "runtime" / "runs" / f"run-{run_id:06d}"
    )
    clusters = json.loads(
        (run_dir / "m3-final-clusters.json").read_text(encoding="utf-8")
    )
    prompt_path = (
        run_dir / "domain_draft_a_synthesis" / "main" / "attempt-01" / "prompt.txt"
    )
    if not prompt_path.is_file():
        raise FileNotFoundError(
            "Draft A Runner 只恢复已通过预算预检并冻结 Prompt 的 Stage"
        )
    prompt = prompt_path.read_text(encoding="utf-8")
    call_dir = prompt_path.parent
    result = _recover_existing_repair(
        app=app, run_id=run_id, call_dir=call_dir, clusters=clusters,
    )
    if result is None:
        result = app.taxonomy_workflow._model_stage(
            run_id=run_id,
            run_dir=run_dir,
            stage_name="domain_draft_a_synthesis",
            unit_key="main",
            role="taxonomy_global",
            prompt=prompt,
            prompt_version=DOMAIN_DRAFT_A_PROMPT_VERSION,
            schema=DomainDraftA,
            schema_hint=DOMAIN_DRAFT_A_SCHEMA_HINT,
            max_tokens=24576,
            input_ids=[
                cluster["cluster_id"]
                for cluster in clusters["clusters"]
                if cluster.get("domain_disposition") in {"domain_candidate", "uncertain"}
            ],
            validator=lambda value: validate_domain_draft_a(
                value, final_clusters=clusters,
            ),
        )
    payload = result.model_dump(mode="json")
    _write_json_once(run_dir / "domain-draft-a.provider-draft.json", payload)
    evaluation = evaluate_domain_draft_a(result)
    _write_json_once(
        run_dir / "domain-draft-a-complexity-metrics.json", evaluation["metrics"]
    )
    _write_json_once(
        run_dir / "domain-draft-a-hierarchy-risks.json",
        evaluation["hierarchy_risks"],
    )
    app.taxonomy_run_repository.set_run_status(
        run_id,
        "waiting_for_review",
        current_stage="domain_draft_a_hierarchy_review",
        error_code=None,
        error_message=None,
    )
    return {
        "run_id": run_id,
        "node_count": len(result.nodes),
        "excluded_cluster_count": len(result.excluded_cluster_ids),
        "deterministic_gate_passed": evaluation["passed"],
        "blocking_count": len(evaluation["hierarchy_risks"]["blocking"]),
        "concern_count": len(evaluation["hierarchy_risks"]["concerns"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume frozen Run #24 Draft A synthesis")
    parser.add_argument("run_id", type=int)
    args = parser.parse_args()
    print(json.dumps(run(args.run_id), ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
