from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider, parse_json_content
from shiliu.taxonomy.controlled_facets_completion import _tree_hash
from shiliu.taxonomy.controlled_facets import _hash_file, _stable_hash, _utc_now, _write_json
from shiliu.taxonomy.provider_single_flight import ProviderSingleFlight


TAIL_PROMPT_VERSION = "checkpoint312c-tail-completion-v1"
TAIL_REPAIR_PROMPT_VERSION = "checkpoint312c-tail-repair-v1"
DOMAIN_EVIDENCE_CONTRACT_VERSION = "domain-evidence-contract-v2"
DOMAIN_EVIDENCE_ADAPTER_VERSION = "domain-evidence-contract-v2-adapter-v1"
TAIL_IDS = ("nc_037", "nc_038", "nc_039", "nc_040")
TAIL_ACTIONS = (
    "merge_into_existing_domain",
    "downgrade_to_topic",
    "downgrade_to_entity",
    "remove_as_unsupported",
    "unresolved_requires_new_domain",
)


class TailCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_id: str = Field(pattern=r"^nc_0(37|38|39|40)$")
    action: Literal[
        "merge_into_existing_domain",
        "downgrade_to_topic",
        "downgrade_to_entity",
        "remove_as_unsupported",
        "unresolved_requires_new_domain",
    ]
    target_id: str | None = Field(default=None, pattern=r"^d_[a-z0-9_]+$")
    reason: str = Field(min_length=1, max_length=500)
    definition_comparison: str = Field(min_length=1, max_length=500)
    evidence_assessment: str = Field(min_length=1, max_length=500)
    granularity_assessment: str = Field(min_length=1, max_length=500)
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def validate_action_target(self):
        if self.action == "merge_into_existing_domain" and self.target_id is None:
            raise ValueError("merge_into_existing_domain requires target_id")
        if self.action == "unresolved_requires_new_domain" and self.target_id is not None:
            raise ValueError("unresolved_requires_new_domain requires target_id=null")
        return self


class TailCompletionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_decisions: list[TailCandidateDecision] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_exact_coverage(self):
        ids = [item.candidate_id for item in self.candidate_decisions]
        if ids != list(TAIL_IDS):
            raise ValueError(f"candidate IDs must be exactly {TAIL_IDS} in order")
        return self


TAIL_SCHEMA_HINT = (
    '{"candidate_decisions":['
    '{"candidate_id":"nc_037","action":"merge_into_existing_domain|downgrade_to_topic|'
    'downgrade_to_entity|remove_as_unsupported|unresolved_requires_new_domain",'
    '"target_id":"d_01|null","reason":"","definition_comparison":"",'
    '"evidence_assessment":"","granularity_assessment":"",'
    '"confidence":"high|medium|low"}]}'
)


def extract_complete_array(raw: str, key: str) -> list[dict[str, Any]]:
    marker = f'"{key}"'
    start = raw.find(marker)
    if start < 0:
        raise ValueError(f"missing key: {key}")
    start = raw.find("[", start + len(marker))
    if start < 0:
        raise ValueError(f"missing array: {key}")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(raw)):
        char = raw[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                value = json.loads(raw[start : index + 1])
                if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                    raise ValueError(f"{key} is not an object array")
                return value
    raise ValueError(f"unterminated array: {key}")


def extract_complete_objects_from_partial_array(raw: str, key: str) -> list[dict[str, Any]]:
    marker = f'"{key}"'
    start = raw.find(marker)
    start = raw.find("[", start + len(marker)) if start >= 0 else -1
    if start < 0:
        raise ValueError(f"missing array: {key}")
    decoder = json.JSONDecoder()
    cursor = start + 1
    result: list[dict[str, Any]] = []
    while cursor < len(raw):
        while cursor < len(raw) and raw[cursor] in " \t\r\n,":
            cursor += 1
        if cursor >= len(raw) or raw[cursor] == "]":
            break
        try:
            value, end = decoder.raw_decode(raw, cursor)
        except json.JSONDecodeError:
            break
        if not isinstance(value, dict):
            raise ValueError(f"{key} contains non-object")
        result.append(value)
        cursor = end
    return result


def build_tail_prompt(
    *,
    candidates: list[dict[str, Any]],
    domains: list[dict[str, Any]],
    prior_decisions: list[dict[str, Any]],
    representative_evidence: dict[str, dict[str, Any]],
) -> str:
    if [item["candidate_id"] for item in candidates] != list(TAIL_IDS):
        raise ValueError("tail candidates are not exact")
    frozen_domains = [
        {
            "node_id": item["id"],
            "name": item["name"],
            "definition": item["definition"],
            "includes": item.get("includes") or [],
            "excludes": item.get("excludes") or [],
            "parent_id": item.get("parent_id"),
        }
        for item in flatten_domains(domains)
    ]
    prior_summary = [
        {
            "candidate_id": item["candidate_id"],
            "action": item["action"],
            "target_id": item.get("target_id"),
        }
        for item in prior_decisions
    ]
    tail = []
    for item in candidates:
        tail.append(
            {
                **item,
                "representative_evidence": [
                    representative_evidence[value]
                    for value in item.get("representative_ids") or item.get("supporting_ids") or []
                    if value in representative_evidence
                ],
            }
        )
    payload = {
        "missing_candidates": tail,
        "frozen_domains": frozen_domains,
        "prior_candidate_decision_summary": prior_summary,
    }
    return (
        "你只补全四条缺失的 Candidate Decision。9 个 Domain 与前 36 条 Decision 已冻结，"
        "不得修改、重命名、增删或重排；不得创建新正式 Domain。每个候选只能按定义、"
        "includes/excludes、证据和粒度选择允许动作。若现有节点都不合适且候选可能是稳定领域，"
        "必须使用 unresolved_requires_new_domain，不得强迫合并。downgrade_to_topic 的 target_id"
        "仅是归属参考，不是正式 Assignment。只输出 JSON，不输出 Markdown 或说明。\n"
        f"严格 Schema：{TAIL_SCHEMA_HINT}\n"
        f"冻结输入：{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )


def validate_tail_output(value: TailCompletionOutput, domain_ids: set[str]) -> None:
    for item in value.candidate_decisions:
        if item.target_id is not None and item.target_id not in domain_ids:
            raise PipelineError("Tail target_id 非法", code="tail_target_invalid", retryable=False)


def precheck_finish_reason(finish_reason: str | None, *, stage: str) -> None:
    if finish_reason == "length":
        raise PipelineError(
            f"{stage} 因 length 截断",
            code="tail_completion_length" if stage == "Tail Completion" else "tail_repair_length",
            retryable=False,
        )


def merge_candidate_decisions(
    original: list[dict[str, Any]],
    tail: TailCompletionOutput,
    *,
    original_response_hash: str,
    tail_response_hash: str,
    repaired: bool,
) -> list[dict[str, Any]]:
    if [item.get("candidate_id") for item in original] != [f"nc_{i:03d}" for i in range(1, 37)]:
        raise ValueError("original decisions must be nc_001..nc_036")
    result = [
        {
            **item,
            "decision_source": "original_consolidation",
            "source_attempt": "consolidation-attempt-01",
            "source_response_hash": original_response_hash,
        }
        for item in original
    ]
    attempt = "tail-repair-01" if repaired else "tail-attempt-01"
    result.extend(
        {
            **item.model_dump(mode="json"),
            "decision_source": "tail_completion",
            "source_attempt": attempt,
            "source_response_hash": tail_response_hash,
        }
        for item in tail.candidate_decisions
    )
    if [item["candidate_id"] for item in result] != [f"nc_{i:03d}" for i in range(1, 41)]:
        raise ValueError("merged decisions do not cover nc_001..nc_040")
    return result


def flatten_domains(domains: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for domain in domains:
        parent = {**domain, "parent_id": None}
        children = list(parent.pop("children", []) or [])
        result.append(parent)
        for child in children:
            result.append({**child, "parent_id": domain["id"]})
    return result


def adapt_domain_contract(
    *,
    source_run_id: int,
    domains: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_by_id = {item["candidate_id"]: item for item in candidates}
    sources: dict[str, list[str]] = defaultdict(list)
    for decision in decisions:
        action = decision.get("action")
        target = decision.get("target_id")
        if target and action in {"kept", "merged_into", "renamed", "merge_into_existing_domain"}:
            sources[str(target)].append(str(decision["candidate_id"]))
    flattened = flatten_domains(domains)
    parent_by_id = {item["id"]: item.get("parent_id") for item in flattened}
    for target, candidate_ids in list(sources.items()):
        parent_id = parent_by_id.get(target)
        if parent_id:
            sources[parent_id].extend(candidate_ids)
    nodes = []
    for node in flattened:
        source_ids = list(dict.fromkeys(sources.get(node["id"], [])))
        model_ids = list(dict.fromkeys(node.get("supporting_ids") or []))
        pool: list[str] = []
        batch_ids: list[str] = []
        candidate_representatives: list[str] = []
        for candidate_id in source_ids:
            candidate = candidate_by_id.get(candidate_id)
            if candidate is None:
                raise ValueError(f"missing source candidate: {candidate_id}")
            for value in candidate.get("supporting_ids") or []:
                if value not in pool:
                    pool.append(value)
            for value in candidate.get("representative_ids") or []:
                if value not in candidate_representatives:
                    candidate_representatives.append(value)
            for value in candidate.get("source_batch_ids") or candidate.get("batch_ids") or []:
                if value not in batch_ids:
                    batch_ids.append(value)
        for value in model_ids:
            if value not in pool:
                pool.append(value)
        representatives: list[str] = []
        for sequence in (
            node.get("representative_ids") or [],
            candidate_representatives,
            model_ids,
            pool,
        ):
            for value in sequence:
                if value not in representatives:
                    representatives.append(value)
                if len(representatives) == 5:
                    break
            if len(representatives) == 5:
                break
        canonical_includes = list(node.get("includes") or [])
        canonical_excludes = list(node.get("excludes") or [])
        nodes.append(
            {
                "contract_version": DOMAIN_EVIDENCE_CONTRACT_VERSION,
                "node_id": node["id"],
                "name": node["name"],
                "definition": node["definition"],
                "canonical_includes": canonical_includes,
                "canonical_excludes": canonical_excludes,
                "display_includes": canonical_includes[:5],
                "display_excludes": canonical_excludes[:5],
                "parent_id": node.get("parent_id"),
                "source_candidate_ids": source_ids,
                "source_batch_ids": batch_ids,
                "source_run_id": source_run_id,
                "model_selected_evidence_ids": model_ids,
                "evidence_pool_ids": pool,
                "representative_ids": representatives,
                "evidence_stats": {
                    "source_candidate_count": len(source_ids),
                    "source_batch_count": len(batch_ids),
                    "model_selected_evidence_count": len(model_ids),
                    "evidence_pool_count": len(pool),
                    "representative_count": len(representatives),
                },
            }
        )
    contract = {
        "version": DOMAIN_EVIDENCE_CONTRACT_VERSION,
        "adapter_version": DOMAIN_EVIDENCE_ADAPTER_VERSION,
        "source_run_id": source_run_id,
        **(lineage or {}),
        "nodes": nodes,
    }
    contract["derived_output_hash"] = _stable_hash(contract)
    return contract


def validate_hierarchy_v2(contract: dict[str, Any]) -> dict[str, Any]:
    nodes = contract["nodes"]
    by_id = {item["node_id"]: item for item in nodes}
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if len(by_id) != len(nodes):
        blocking.append({"code": "duplicate_node_id", "details": []})
    for node in nodes:
        parent_id = node.get("parent_id")
        if not node.get("source_candidate_ids"):
            blocking.append({"code": "domain_without_source", "details": [node["node_id"]]})
        if not node.get("model_selected_evidence_ids"):
            blocking.append({"code": "domain_without_discovery_evidence", "details": [node["node_id"]]})
        if parent_id is None:
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            blocking.append({"code": "invalid_parent", "details": [node["node_id"], parent_id]})
            continue
        if parent_id == node["node_id"]:
            blocking.append({"code": "self_parent", "details": [node["node_id"]]})
        if parent.get("parent_id") is not None:
            blocking.append({"code": "depth_exceeds_two", "details": [node["node_id"]]})
        if _normalized(node["name"]) == _normalized(parent["name"]):
            blocking.append({"code": "same_normalized_name", "details": [parent_id, node["node_id"]]})
        child_text = _normalized(node["name"] + " " + node["definition"])
        excluded = [value for value in parent["canonical_excludes"] if _normalized(value) in child_text]
        if excluded:
            blocking.append({"code": "parent_excludes_child", "details": [parent_id, node["node_id"], excluded]})
        overlap = set(parent["evidence_pool_ids"]) & set(node["evidence_pool_ids"])
        if not overlap:
            warnings.append({"code": "parent_child_evidence_zero_overlap", "details": [parent_id, node["node_id"]]})
        if not set(node["model_selected_evidence_ids"]) & set(parent["model_selected_evidence_ids"]):
            warnings.append({"code": "child_not_in_parent_model_evidence", "details": [parent_id, node["node_id"]]})
    for node in nodes:
        seen: set[str] = set()
        cursor = node
        while cursor.get("parent_id") is not None:
            if cursor["node_id"] in seen:
                blocking.append({"code": "cycle", "details": [node["node_id"]]})
                break
            seen.add(cursor["node_id"])
            cursor = by_id.get(cursor["parent_id"], {})
            if not cursor:
                break
    return {"version": "parent-child-gate-v2", "blocking": blocking, "warnings": warnings}


def build_quality_gate(
    *, tail_audit: dict[str, Any], complete_decisions: list[dict[str, Any]],
    run_a: dict[str, Any], run_b: dict[str, Any], hierarchy_a: dict[str, Any],
    hierarchy_b: dict[str, Any], historical_tree_unchanged: bool,
) -> dict[str, Any]:
    blocking: list[dict[str, Any]] = []
    warnings = list(hierarchy_b["warnings"])
    if [item["candidate_id"] for item in complete_decisions] != [f"nc_{i:03d}" for i in range(1, 41)]:
        blocking.append({"code": "candidate_decision_incomplete", "details": []})
    if not historical_tree_unchanged:
        blocking.append({"code": "historical_run_changed", "details": []})
    if (
        run_a.get("version") != DOMAIN_EVIDENCE_CONTRACT_VERSION
        or run_b.get("version") != DOMAIN_EVIDENCE_CONTRACT_VERSION
        or run_a.get("adapter_version") != DOMAIN_EVIDENCE_ADAPTER_VERSION
        or run_b.get("adapter_version") != DOMAIN_EVIDENCE_ADAPTER_VERSION
        or run_a.get("adapter_version") != run_b.get("adapter_version")
    ):
        blocking.append({"code": "adapter_version_mismatch", "details": []})
    required_lineage = {
        "source_stage_id", "source_attempt", "raw_response_hash",
        "candidate_table_hash", "adapter_version", "derived_output_hash",
    }
    for label, contract in (("A", run_a), ("B", run_b)):
        missing = sorted(required_lineage - contract.keys())
        if missing:
            blocking.append({"code": "contract_lineage_missing", "details": [label, missing]})
        expected_hash = contract.get("derived_output_hash")
        unhashed = {key: value for key, value in contract.items() if key != "derived_output_hash"}
        if expected_hash != _stable_hash(unhashed):
            blocking.append({"code": "derived_output_hash_mismatch", "details": [label]})
        bad_nodes = []
        for item in contract.get("nodes", []):
            expected_stats = {
                "source_candidate_count": len(item.get("source_candidate_ids") or []),
                "source_batch_count": len(item.get("source_batch_ids") or []),
                "model_selected_evidence_count": len(item.get("model_selected_evidence_ids") or []),
                "evidence_pool_count": len(item.get("evidence_pool_ids") or []),
                "representative_count": len(item.get("representative_ids") or []),
            }
            if (
                item.get("contract_version") != DOMAIN_EVIDENCE_CONTRACT_VERSION
                or item.get("evidence_stats") != expected_stats
            ):
                bad_nodes.append(item.get("node_id"))
        if bad_nodes:
            blocking.append({"code": "node_contract_fields_missing", "details": [label, bad_nodes]})
    blocking.extend(hierarchy_a["blocking"])
    blocking.extend(hierarchy_b["blocking"])
    unresolved = [item["candidate_id"] for item in complete_decisions if item.get("action") == "unresolved_requires_new_domain"]
    if tail_audit.get("repair_count"):
        warnings.append({"code": "tail_repair_used", "details": [tail_audit["repair_count"]]})
    if tail_audit.get("repair_semantic_changes"):
        warnings.append({"code": "tail_semantic_repair", "details": tail_audit["repair_semantic_changes"]})
    if unresolved:
        warnings.append({"code": "unresolved_requires_new_domain", "details": unresolved})
    warnings.extend([
        {"code": "historical_consolidation_length", "details": ["finish_reason=length"]},
        {"code": "historical_reasoning_tokens_high", "details": [13261]},
        {"code": "historical_consolidation_payload_heavy", "details": ["domain tree + 40 decisions"]},
    ])
    status = "FAIL" if blocking else ("PASS_WITH_CHANGES" if unresolved or tail_audit.get("repair_semantic_changes") else "PASS")
    return {"version": "checkpoint312c-run-b-gate-v1", "status": status, "blocking": blocking, "warnings": warnings}


class Checkpoint312CService:
    def __init__(self, *, runs_dir: Path, output_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.output_dir = output_dir

    def prepare(self) -> dict[str, Any]:
        run22 = self.runs_dir / "run-000022"
        run12 = self.runs_dir / "run-000012"
        candidate_table = json.loads((run22 / "candidate-normalization/compact-candidates.json").read_text())
        candidates = candidate_table["domains"]
        raw_path = run22 / "domain_consolidation/main/attempt-01/raw-response.txt"
        repair_path = run22 / "domain_consolidation/main/attempt-01/repair-raw-response.txt"
        raw = raw_path.read_text()
        domains = extract_complete_array(raw, "domains")
        repair = json.loads(repair_path.read_text())
        prior = repair["candidate_decisions"]
        main_prior = extract_complete_objects_from_partial_array(raw, "candidate_decisions")
        if main_prior != prior:
            raise PipelineError(
                "Run #22 主响应前 36 条与 Repair 决策不一致",
                code="run22_decision_lineage_mismatch",
                retryable=False,
            )
        if len(domains) != 9 or [x["candidate_id"] for x in prior] != [f"nc_{i:03d}" for i in range(1, 37)]:
            raise PipelineError("Run #22 冻结输入不符合预期", code="run22_frozen_input_invalid", retryable=False)
        tail = [x for x in candidates if x["candidate_id"] in TAIL_IDS]
        evidence = self._representative_evidence(run12, tail)
        prompt = build_tail_prompt(candidates=tail, domains=domains, prior_decisions=prior, representative_evidence=evidence)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        frozen = {
            "run22_tree_hash_current_algorithm": _tree_hash(run22),
            "run22_file_count": len([x for x in run22.rglob("*") if x.is_file()]),
            "run22_historical_report_hash": "361e2e3ff8657865570d51db04da5ca81d9a56bc2197ced5bb991ba1104ff17b",
            "run22_key_hashes": {str(x.relative_to(run22)): _hash_file(x) for x in (raw_path, repair_path, run22 / "candidate-normalization/compact-candidates.json", run22 / "run-manifest.json")},
        }
        _write_json(self.output_dir / "frozen-input-manifest.json", frozen)
        (self.output_dir / "tail-completion-prompt.txt").write_text(prompt, encoding="utf-8")
        _write_json(self.output_dir / "tail-completion-input.json", {"candidates": tail, "domains": domains, "prior_decisions": prior, "representative_evidence": evidence})
        return {"prompt": prompt, "domains": domains, "prior": prior, "candidates": candidates, "frozen": frozen}

    def call(self, *, provider: OpenAICompatibleProvider, repair_provider: OpenAICompatibleProvider) -> dict[str, Any]:
        prepared = self.prepare()
        call_dir = self.output_dir / "tail-completion"
        if call_dir.exists():
            audit_path = call_dir / "audit.json"
            existing = json.loads(audit_path.read_text()) if audit_path.is_file() else {}
            if existing.get("status") == "completed" or (call_dir / "raw-response.txt").exists():
                raise FileExistsError(call_dir)
        else:
            call_dir.mkdir(parents=True)
        prompt = prepared["prompt"]
        audit_path = call_dir / "audit.json"
        audit: dict[str, Any] = (
            json.loads(audit_path.read_text())
            if audit_path.is_file()
            else {
                "status": "prepared",
                "prompt_version": TAIL_PROMPT_VERSION,
                "model": provider.model,
                "parameters": {
                    "thinking_enabled": provider.thinking_enabled,
                    "reasoning_effort": provider.reasoning_effort,
                    "max_tokens": 5000,
                },
                "prompt_hash": _hash_text(prompt),
                "started_at": _utc_now(),
                "repair_count": 0,
                "transport_request_attempt_count": 1,
            }
        )
        if not audit_path.is_file():
            _write_json(audit_path, audit)
        single_flight = ProviderSingleFlight(call_dir=call_dir)
        primary = single_flight.invoke(
            provider_call=lambda: provider.complete_raw(prompt, max_tokens=5000),
            request_kind="primary",
            prompt_hash=_hash_text(prompt),
            schema_hash=_hash_text(TAIL_SCHEMA_HINT),
        )
        response = primary.response
        audit.update(
            status="raw_received",
            finish_reason=response.finish_reason,
            usage=response.usage,
            elapsed_seconds=primary.elapsed_seconds,
            raw_response_chars=len(response.content),
            raw_response_path=str(primary.raw_path.relative_to(call_dir)),
            raw_response_sha256=primary.raw_sha256,
            response_id=response.response_id,
        )
        _write_json(call_dir / "audit.json", audit)
        precheck_finish_reason(response.finish_reason, stage="Tail Completion")
        repaired = False
        semantic_changes: list[str] = []
        try:
            output = parse_json_content(response.content, TailCompletionOutput)
            validate_tail_output(output, {x["id"] for x in flatten_domains(prepared["domains"])})
        except PipelineError as exc:
            repaired = True
            single_flight.mark_validation_failed(primary)
            repair_prompt = "你是结构化 JSON Repair。只修正语法、字段、顺序和覆盖；不得改变已合法语义，不读取原任务证据。只输出 JSON。\n" + f"Schema:{TAIL_SCHEMA_HINT}\nExpected:{list(TAIL_IDS)}\nDomain IDs:{[x['id'] for x in flatten_domains(prepared['domains'])]}\nValidation:{str(exc)[:2500]}\nRaw:{response.content}"
            (call_dir / "repair-prompt.txt").write_text(repair_prompt, encoding="utf-8")
            repair_invocation = single_flight.invoke(
                provider_call=lambda: repair_provider.complete_raw(
                    repair_prompt, max_tokens=5000
                ),
                request_kind="json_repair",
                prompt_hash=_hash_text(repair_prompt),
                schema_hash=_hash_text(TAIL_SCHEMA_HINT),
            )
            repair_response = repair_invocation.response
            try:
                precheck_finish_reason(
                    repair_response.finish_reason, stage="Tail Repair"
                )
                output = parse_json_content(
                    repair_response.content, TailCompletionOutput
                )
                validate_tail_output(
                    output, {x["id"] for x in flatten_domains(prepared["domains"])}
                )
            except PipelineError:
                single_flight.mark_validation_failed(repair_invocation)
                raise
            single_flight.accept(repair_invocation)
            before = _partial_decisions(response.content)
            after = {x.candidate_id: x.model_dump(mode="json") for x in output.candidate_decisions}
            semantic_changes = [key for key in TAIL_IDS if key not in before or before[key] != after[key]]
            audit.update(
                repair_count=1,
                repair_usage=repair_response.usage,
                repair_finish_reason=repair_response.finish_reason,
                repair_raw_response_path=str(
                    repair_invocation.raw_path.relative_to(call_dir)
                ),
                repair_raw_response_sha256=repair_invocation.raw_sha256,
            )
            response_hash = _hash_text(repair_response.content)
        else:
            single_flight.accept(primary)
            response_hash = _hash_text(response.content)
        _write_json(call_dir / "parsed-output.json", output.model_dump(mode="json"))
        tail_audit = {"provider_request_hash": _hash_text(prompt), "provider_response_hash": _hash_text(response.content), "finish_reason": response.finish_reason, "candidate_ids": [x.candidate_id for x in output.candidate_decisions], "decision_hashes": {x.candidate_id: _stable_hash(x.model_dump(mode="json")) for x in output.candidate_decisions}, "repair_count": int(repaired), "repair_semantic_changes": semantic_changes, "frozen_domain_hash": _stable_hash(prepared["domains"]), "candidate_table_hash": _stable_hash(prepared["candidates"])}
        _write_json(self.output_dir / "tail-completion-audit.json", tail_audit)
        complete = merge_candidate_decisions(prepared["prior"], output, original_response_hash=_hash_file(self.runs_dir / "run-000022/domain_consolidation/main/attempt-01/raw-response.txt"), tail_response_hash=response_hash, repaired=repaired)
        _write_json(self.output_dir / "candidate-decisions-complete-v1.json", {"candidate_decisions": complete})
        audit.update(status="completed", repair_semantic_changes=semantic_changes, finished_at=_utc_now())
        _write_json(call_dir / "audit.json", audit)
        return {**prepared, "tail": output, "tail_audit": tail_audit, "complete": complete}

    def derive(self, result: dict[str, Any]) -> dict[str, Any]:
        run12 = self.runs_dir / "run-000012"
        run22 = self.runs_dir / "run-000022"
        table_a = json.loads((run12 / "candidate-normalization/compact-candidates.json").read_text())
        _attach_source_batches(table_a["domains"], json.loads((run12 / "local-candidates.json").read_text()))
        _attach_source_batches(result["candidates"], json.loads((run22 / "domain-local-candidates.json").read_text()))
        draft_a = json.loads((run12 / "taxonomy-draft.json").read_text())
        contract_a = adapt_domain_contract(
            source_run_id=12, domains=draft_a["domains"],
            decisions=draft_a["candidate_decisions"], candidates=table_a["domains"],
            lineage={
                "source_stage_id": "run-000012:consolidation:main",
                "source_attempt": "attempt-01",
                "raw_response_hash": _hash_file(run12 / "consolidation/main/attempt-01/raw-response.txt"),
                "candidate_table_hash": _hash_file(run12 / "candidate-normalization/compact-candidates.json"),
            },
        )
        contract_b = adapt_domain_contract(
            source_run_id=22, domains=result["domains"], decisions=result["complete"],
            candidates=result["candidates"],
            lineage={
                "source_stage_id": "run-000022:domain_consolidation:main",
                "source_attempt": "attempt-01+tail-attempt-01",
                "raw_response_hash": _hash_file(run22 / "domain_consolidation/main/attempt-01/raw-response.txt"),
                "candidate_table_hash": _hash_file(run22 / "candidate-normalization/compact-candidates.json"),
            },
        )
        _write_json(self.output_dir / "run-a-domain-contract-v2.json", contract_a)
        _write_json(self.output_dir / "run-b-domain-contract-v2.json", contract_b)
        hierarchy_a = validate_hierarchy_v2(contract_a)
        hierarchy_b = validate_hierarchy_v2(contract_b)
        _write_json(self.output_dir / "hierarchy-risk-findings.json", {"run_a": hierarchy_a, "run_b": hierarchy_b})
        frozen = json.loads((self.output_dir / "frozen-input-manifest.json").read_text())
        unchanged = _tree_hash(run22) == frozen["run22_tree_hash_current_algorithm"] and len([x for x in run22.rglob("*") if x.is_file()]) == frozen["run22_file_count"]
        gate = build_quality_gate(tail_audit=result["tail_audit"], complete_decisions=result["complete"], run_a=contract_a, run_b=contract_b, hierarchy_a=hierarchy_a, hierarchy_b=hierarchy_b, historical_tree_unchanged=unchanged)
        _write_json(self.output_dir / "run-b-quality-gate.json", gate)
        return {"run_a": contract_a, "run_b": contract_b, "hierarchy": {"run_a": hierarchy_a, "run_b": hierarchy_b}, "gate": gate}

    def _representative_evidence(self, run12: Path, candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        compact = json.loads((run12 / "compact-corpus.json").read_text())
        rows = compact.get("cards") or compact.get("items") or compact.get("rows") or compact
        if isinstance(rows, dict):
            rows = list(rows.values())
        wanted = {value for item in candidates for value in item.get("representative_ids") or item.get("supporting_ids") or []}
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            if isinstance(row, list):
                short_id, evidence, title = row[:3]
                value = {"short_id": short_id, "evidence_level": evidence, "title": title}
                if len(row) > 3:
                    value["one_line_summary_or_description"] = row[3]
            else:
                short_id = str(row.get("short_id") or row.get("id"))
                value = {key: row.get(key) for key in ("short_id", "title", "main_subject", "content_goal", "evidence_level") if row.get(key) is not None}
            if str(short_id) in wanted:
                result[str(short_id)] = value
        return result


def _partial_decisions(raw: str) -> dict[str, dict[str, Any]]:
    try:
        values = extract_complete_array(raw, "candidate_decisions")
    except ValueError:
        return {}
    return {str(item.get("candidate_id")): item for item in values}


def _attach_source_batches(candidates: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> None:
    batches: dict[str, list[str]] = defaultdict(list)
    for index, output in enumerate(outputs, start=1):
        for item in output.get("domains") or []:
            batches[_normalized(str(item.get("name") or ""))].append(f"batch-{index:03d}")
    for candidate in candidates:
        candidate["source_batch_ids"] = list(dict.fromkeys(batches.get(_normalized(candidate["name"]), [])))


def _normalized(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
