"""Stage 3R-PQS-A-R: query-source coverage supplement only.

This module builds a new, query-only packet.  It never invokes retrieval or
opens corpus/video/subtitle/Gold assets; Phase A assets are read only through
the source constants required to preserve their candidate wording.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from shiliu.eval_v3_5.product_query_set_phase_a import HUMAN_QUERY_SOURCES, normalize_for_exact_duplicate


RUNNER_VERSION = "v3.5-product-query-set-phase-a-r-v1"
MAX_CANDIDATE_POOL = 40


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(canonical_json(row) for row in rows) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _line_number(reference: str) -> int:
    value = "".join(char for char in reference if char.isdigit())
    return int(value) if value else 0


def _source(
    raw_query: str, source_file: str, source_reference: str, source_type: str,
    source_excerpt: str, query_family: str, multi_aspect: bool,
    priority: int, priority_label: str, source_order: int,
) -> dict[str, Any]:
    return {
        "raw_query": raw_query, "source_file": source_file, "source_reference": source_reference,
        "source_type": source_type, "source_excerpt": source_excerpt,
        "query_family": query_family, "multi_aspect": multi_aspect,
        "source_priority": priority, "source_priority_label": priority_label,
        "source_order": source_order,
    }


def _phase_a_sources() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(HUMAN_QUERY_SOURCES, start=1):
        # The four retained V3 examples are explicit product search/navigation
        # requirements; the rest are human-authored planning information needs.
        priority = 2 if row["source_type"] == "actual_search_or_navigation_requirement" else 3
        label = "explicit_product_use_need" if priority == 2 else "project_planning_user_information_need"
        rows.append(_source(
            str(row["raw_query"]), str(row["source_file"]), str(row["source_reference"]),
            str(row["source_type"]), str(row["source_excerpt"]), str(row["query_family"]),
            bool(row["multi_aspect"]), priority, label, index,
        ))
    return rows


# These headings are verbatim, approved user-flow requirements in the product
# specification.  They are short source phrases, not Codex rewrites.
SUPPLEMENTAL_SOURCES: tuple[dict[str, Any], ...] = (
    _source("添加公开来源", "docs/specs/2026-07-15-shiliu-v1.md", "line 138", "explicit_product_use_requirement", "Users and Key Flows heading.", "how_to_or_process", False, 2, "explicit_product_use_need", 1),
    _source("立即同步", "docs/specs/2026-07-15-shiliu-v1.md", "line 152", "explicit_product_use_requirement", "Users and Key Flows heading.", "how_to_or_process", False, 2, "explicit_product_use_need", 2),
    _source("定时同步发现新视频或处理历史积压", "docs/specs/2026-07-15-shiliu-v1.md", "line 166", "explicit_product_use_requirement", "Users and Key Flows heading.", "how_to_or_process", False, 2, "explicit_product_use_need", 3),
    _source("精修快速版", "docs/specs/2026-07-15-shiliu-v1.md", "line 179", "explicit_product_use_requirement", "Users and Key Flows heading.", "how_to_or_process", False, 2, "explicit_product_use_need", 4),
)


def source_sort_key(row: Mapping[str, Any]) -> tuple[int, str, int, int]:
    """The protocol's fixed selection order, with no system-result inputs."""
    return (int(row["source_priority"]), str(row["source_file"]), _line_number(str(row["source_reference"])), int(row["source_order"]))


def build_revised_candidates(
    phase_a_sources: Iterable[Mapping[str, Any]] = (), supplemental_sources: Iterable[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], int, int]:
    """Exact-deduplicate, then cap with the prescribed deterministic ordering."""
    source_rows = list(phase_a_sources) + list(supplemental_sources)
    normalized_seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    exact_duplicates = 0
    for row in source_rows:
        if not str(row.get("raw_query", "")).strip() or not row.get("source_file") or not row.get("source_reference"):
            raise ValueError("Every revised candidate must retain a non-empty traceable source.")
        normalized = normalize_for_exact_duplicate(str(row["raw_query"]))
        if normalized in normalized_seen:
            exact_duplicates += 1
            continue
        normalized_seen.add(normalized)
        unique.append(dict(row))
    selected = sorted(unique, key=source_sort_key)[:MAX_CANDIDATE_POOL]
    candidates: list[dict[str, Any]] = []
    for index, source in enumerate(selected, start=1):
        retained = source["source_file"] in {item["source_file"] for item in HUMAN_QUERY_SOURCES}
        candidates.append({
            "candidate_query_id": f"PQS_R_CAND_{index:03d}",
            "raw_query": source["raw_query"], "source_type": source["source_type"],
            "source_file": source["source_file"], "source_reference": source["source_reference"],
            "source_excerpt": source["source_excerpt"], "normalization_notes": "",
            "query_family": source["query_family"], "multi_aspect": source["multi_aspect"],
            "natural_without_video_context": True, "plausibly_asked_in_shiliu": True,
            "possible_semantic_duplicate_group": None, "stress_set_overlap": False,
            "answerability_checked": False, "retrieval_executed": False, "human_decision": None,
            "selection_priority": source["source_priority_label"],
            "retained_from_phase_a": retained,
        })
    return candidates, exact_duplicates, max(0, len(unique) - MAX_CANDIDATE_POOL)


def _family_counts(candidates: Iterable[Mapping[str, Any]]) -> Counter[str]:
    return Counter(str(row["query_family"]) for row in candidates)


def _audit(candidates: list[dict[str, Any]], exact_duplicates: int, capped: int) -> str:
    source_counts = Counter(row["source_file"] for row in candidates)
    family_counts = _family_counts(candidates)
    retained = sum(row["retained_from_phase_a"] for row in candidates)
    added = len(candidates) - retained
    return "\n".join([
        "# Product Query Set v1 — Revised Query Source Audit", "",
        "## Read-only expanded source audit", "",
        "Newly audited paths:", "",
        "- `01_V3_SESSION_OPERATING_CONTRACT.md` (main/version-session contract; no eligible standalone user query retained)",
        "- `V3_CURRENT_STATE.md` and `V3_5_CURRENT_STATE.md` (version-state context; no candidate extracted)",
        "- `reports/V3_TAXONOMY_CLOSEOUT_AND_PRODUCT_REFRAME_HANDOFF_2026-07-19.md` (handoff; no candidate extracted)",
        "- `docs/specs/2026-07-15-shiliu-v1.md` (approved product user flows; four verbatim requirements retained)",
        "- `README.md` and `tests/test_product_search_api.py` (product/fixture audit; no candidate outranked the capped pool)", "",
        "No video title, transcript/subtitle, Gold, retrieval result, Builder/Selector result, or performance result was used as a candidate source.",
        "", "## Deterministic cap", "",
        "After exact deduplication, candidates were ordered by: source priority (real user wording → explicit product use need → project-planning information need → test fixture), then source path, source location, and original order. The first 40 were retained. No retrieval-success, answerability, label-balance, or Query Family criterion affected selection.",
        "", "## Counts", "",
        f"- Original Phase A candidates retained: {retained}/39",
        f"- Newly added-source candidates retained: {added}",
        f"- Exact duplicates removed: {exact_duplicates}",
        "- Possible semantic duplicates marked: 0 (none semantically deleted)",
        f"- Candidates excluded only by the 40-item cap: {capped}",
        f"- Final revised candidate pool: {len(candidates)}", "",
        "### Source contribution in revised pool", "",
        *(f"- `{path}`: {count}" for path, count in sorted(source_counts.items())),
        "", "### Query family distribution", "",
        *(f"- `{family}`: {count}" for family, count in sorted(family_counts.items())),
        "", "## Remaining coverage note", "",
        "The revised source pool remains visibly thin for `purpose_or_use_case` (zero retained). This is a source-coverage observation only: no Query was generated, revised, or selected to close it. The source breadth now includes an approved product specification in addition to the two Phase A sources.",
        "",
    ])


def _review_packet(candidates: Iterable[Mapping[str, Any]]) -> str:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in candidates:
        groups.setdefault(str(row["query_family"]), []).append(row)
    lines = ["# Product Query Set v1 — Revised Query-only Review Packet", "", "This packet contains query wording and traceable human-source information only. It intentionally omits answerability, target video, subtitle, Gold, search output, and expected system performance.", ""]
    for family in sorted(groups):
        lines.extend([f"## {family}", ""])
        for row in groups[family]:
            lines.extend([
                f"### {row['candidate_query_id']}", "", f"- Raw Query: {row['raw_query']}",
                f"- Source Type: {row['source_type']}", f"- Source Reference: `{row['source_file']}`, {row['source_reference']}",
                f"- Query Family: {row['query_family']}", f"- Multi-aspect: {str(row['multi_aspect']).lower()}",
                "- Possible Duplicate: None marked", "- Stress-set Overlap: false", "",
            ])
    return "\n".join(lines)


def _report(candidates: list[dict[str, Any]], exact_duplicates: int, capped: int) -> str:
    retained = sum(row["retained_from_phase_a"] for row in candidates)
    family_counts = dict(sorted(_family_counts(candidates).items()))
    return f"""# V3.5 Product Query Set v1 — Phase A-R Report

## Source coverage supplement

- Newly searched source paths are recorded in `PQS_V1_QUERY_SOURCE_AUDIT_REVISED.md`.
- Revised-pool source contributions: `00_V3_RETRIEVAL_VERSION_BRIEF.md` 4; `拾流_Shiliu_完整项目上下文与当前行动.md` {retained - 4}; `docs/specs/2026-07-15-shiliu-v1.md` {len(candidates) - retained}.
- Original Phase A candidates retained: {retained}/39.
- Newly added candidates: {len(candidates) - retained}.
- Exact duplicates removed: {exact_duplicates}; possible semantic duplicates marked: 0.
- Cap-only exclusions: {capped}.
- Final pool: {len(candidates)}; Query Family distribution: {family_counts}.
- Remaining visible source/type gap: `purpose_or_use_case` has no retained candidate. No query was generated or rewritten to fill it.

## Query-only isolation

- Retrieval calls: 0; embedding calls: 0.
- Video or transcript viewed: false.
- Answerability checked: false.
- System results used: false.
- Codex-generated queries: 0.
- Human decisions filled: 0.

## Handoff

The revised packet and blank revised template are suitable to hand to an independent WebGPT Query-only Review. This stage did not run Retrieval and did not select the final Product Query Set.
"""


def build_phase_a_r(repository_root: Path) -> dict[str, Any]:
    output = repository_root / "research/v3_5/product_query_set_v1/phase_a_r"
    output.mkdir(parents=True, exist_ok=True)
    candidates, exact_duplicates, capped = build_revised_candidates(_phase_a_sources(), SUPPLEMENTAL_SOURCES)
    write_jsonl(output / "product_query_candidates.revised.jsonl", candidates)
    write_jsonl(output / "product_query_decisions.revised.template.jsonl", (
        {"candidate_query_id": row["candidate_query_id"], "human_action": "", "approved_user_query": "", "decision_reason": "", "preferred_split": ""}
        for row in candidates
    ))
    (output / "PQS_V1_QUERY_SOURCE_AUDIT_REVISED.md").write_text(_audit(candidates, exact_duplicates, capped), encoding="utf-8")
    (output / "PQS_V1_QUERY_ONLY_REVIEW_PACKET_REVISED.md").write_text(_review_packet(candidates), encoding="utf-8")
    (output / "V3_5_PRODUCT_QUERY_SET_V1_PHASE_A_R_REPORT.md").write_text(_report(candidates, exact_duplicates, capped), encoding="utf-8")
    isolation = {
        "runner_version": RUNNER_VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retrieval_calls": 0, "embedding_calls": 0, "video_or_transcript_viewed": False,
        "answerability_checked": False, "system_results_used": False, "codex_generated_queries": 0,
        "human_decisions_filled": 0, "candidate_builder_calls": 0, "selector_calls": 0,
        "sufficiency_judge_calls": 0, "external_llm_calls": 0, "external_network_calls": 0,
        "heldout_accessed": False,
    }
    write_json(output / "product_query_set_phase_a_r_execution.audit.json", isolation)
    manifest = {
        "runner_version": RUNNER_VERSION, "candidate_count": len(candidates), "phase_a_candidates_retained": sum(row["retained_from_phase_a"] for row in candidates),
        "supplemental_candidates_added": sum(not row["retained_from_phase_a"] for row in candidates),
        "exact_duplicates_removed": exact_duplicates, "possible_semantic_duplicates": 0,
        "cap_exclusions": capped, "status": "Stage 3R-PQS-A-R Complete",
    }
    write_json(output / "product_query_set_phase_a_r_manifest.json", manifest)
    tracked = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "product_query_set_phase_a_r_file_hash_manifest.jsonl")
    write_jsonl(output / "product_query_set_phase_a_r_file_hash_manifest.jsonl", ({"path": str(path.relative_to(output)), "sha256": file_sha256(path)} for path in tracked))
    return manifest
