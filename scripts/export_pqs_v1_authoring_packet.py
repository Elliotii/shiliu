"""Export the neutral, two-pass Product Query Set v1 authoring packet.

Only navigation metadata is read from the local Product database.  This script
does not import retrieval services and never opens subtitle, transcript, Gold,
or evaluation-result assets.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping


RUNNER_VERSION = "v3.5-product-query-set-authoring-packet-v1"
PRODUCT_DB = Path("/Users/elliot/Library/Application Support/Shiliu/shiliu.db")


CLUSTERS = (
    ("PQS_TOPIC_001", "Agent 评测与质量保障", "收藏内容涉及 Agent 能力评测、测试、回归与质量保障方法。", ("eval", "evaluation", "benchmark", "评测", "评估", "测试", "回归", "质量")),
    ("PQS_TOPIC_002", "RAG、检索与向量系统", "收藏内容涉及 RAG、检索增强、向量、索引与相关工程实践。", ("rag", "retrieval", "检索", "向量", "embedding", "faiss", "索引")),
    ("PQS_TOPIC_003", "训练、微调与数据", "收藏内容涉及模型训练、微调、数据格式与训练技巧。", ("sft", "lora", "finetune", "fine-tune", "训练", "微调", "预训练", "post-train", "dataset", "数据集")),
    ("PQS_TOPIC_004", "上下文、记忆与提示", "收藏内容涉及上下文管理、记忆、提示与长文本相关实践。", ("memory", "context", "上下文", "记忆", "prompt", "提示词", "token")),
    ("PQS_TOPIC_005", "产品规格与需求流程", "收藏内容涉及产品需求、规格、规划与需求变更流程。", ("prd", "spec", "需求", "产品", "openspec", "规划")),
    ("PQS_TOPIC_006", "Coding Agent 与 AI 辅助开发", "收藏内容涉及编程 Agent、代码工具与 AI 辅助软件开发。", ("claude", "cursor", "codex", "coding", "vibe", "code", "编程", "开发")),
    ("PQS_TOPIC_007", "Agent 工作流、工具与自动化", "收藏内容涉及 Agent 工作流、工具调用、Harness、Skill 与自动化。", ("agent", "智能体", "workflow", "工作流", "harness", "skill", "mcp", "openclaw", "automation", "自动化")),
    ("PQS_TOPIC_008", "部署、工程化与运行基础设施", "收藏内容涉及部署、云环境、工程化、运行与基础设施。", ("deploy", "deployment", "部署", "cloud", "docker", "k8s", "infra", "rollback", "工程")),
    ("PQS_TOPIC_009", "Python 与编程基础", "收藏内容涉及 Python、常见编程概念与基础实践。", ("python", "pandas", "numpy", "leetcode", "算法", "数据结构")),
    ("PQS_TOPIC_010", "模型、研究与 AI 生态", "收藏内容涉及语言模型、研究进展与 AI 工具生态。", ("llm", "gpt", "gemini", "deepseek", "deepmind", "model", "模型", "ai")),
    ("PQS_TOPIC_011", "其他软件工具与实践", "收藏内容涉及未归入上述主题的软件工具、实践经验和技术内容。", ()),
)

SHAPE_CUES = (
    ("definition", ("是什么", "what is", "概念", "原理", "介绍", "基础")),
    ("process", ("如何", "流程", "实践", "步骤", "搭建", "实现", "workflow", "教程")),
    ("comparison", ("对比", "区别", "vs", "比较", "还是")),
    ("limitation", ("限制", "风险", "问题", "陷阱", "失败", "不足")),
    ("reported_result", ("结果", "提升", "减少", "节省", "案例", "实践")),
    ("evaluation", ("eval", "evaluation", "benchmark", "评测", "评估", "测试", "回归", "质量")),
)


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


def load_navigation_metadata(database: Path = PRODUCT_DB) -> list[dict[str, Any]]:
    """Read only title/description and subtitle metadata; never content files."""
    if not database.is_file():
        raise FileNotFoundError(f"Product metadata database unavailable: {database}")
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT id, title, uploader, description, subtitle_language, subtitle_source,
                      summary_path, artifact_dir
                 FROM videos WHERE status = 'completed' ORDER BY id"""
        ).fetchall()
    return [dict(row) for row in rows]


def _cluster_for(text: str) -> tuple[str, str, str]:
    lowered = text.casefold()
    for cluster_id, label, description, terms in CLUSTERS:
        if any(term.casefold() in lowered for term in terms):
            return cluster_id, label, description
    cluster_id, label, description, _ = CLUSTERS[-1]
    return cluster_id, label, description


def _shapes_for(text: str) -> list[str]:
    lowered = text.casefold()
    return [shape for shape, terms in SHAPE_CUES if any(term.casefold() in lowered for term in terms)]


def _coverage_signal(count: int) -> str:
    return "dense" if count >= 16 else "medium" if count >= 6 else "light"


def build_content_map(metadata: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    descriptions: dict[str, tuple[str, str]] = {}
    for item in metadata:
        text = f"{item['title']}\n{item['description']}"
        cluster_id, label, description = _cluster_for(text)
        grouped[cluster_id].append(item)
        descriptions[cluster_id] = (label, description)
    map_rows: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for cluster_id, label, default_description, _terms in CLUSTERS:
        items = grouped.get(cluster_id, [])
        if not items:
            continue
        shapes = sorted({shape for item in items for shape in _shapes_for(f"{item['title']}\n{item['description']}")})
        languages = sorted({str(item['subtitle_language'] or "unknown") for item in items})
        sources = sorted({str(item['subtitle_source'] or "unknown") for item in items})
        label, description = descriptions[cluster_id]
        map_rows.append({
            "topic_cluster_id": cluster_id, "neutral_topic_label": label,
            "neutral_topic_description": description, "approximate_item_count": len(items),
            "coverage_signal": _coverage_signal(len(items)), "content_shapes": shapes,
            "single_or_multi_item_potential": "both" if len(items) > 1 else "single",
            "source_languages": languages, "subtitle_source_types": sources,
            "navigation_sources_used": ["metadata", "title", "description", "subtitle_metadata"],
            "authoring_notes": "只说明导航材料中出现的内容形态，不说明可回答性或系统表现。",
        })
        for item in items:
            provenance.append({
                "topic_cluster_id": cluster_id, "internal_video_id": item["id"],
                "video_title": item["title"], "uploader": item["uploader"],
                "metadata_database": str(PRODUCT_DB), "summary_asset_present": bool(item["summary_path"]),
                "navigation_assets_used": ["metadata", "title", "description", "subtitle_metadata"],
                "share_with_independent_webgpt": False,
            })
    return map_rows, provenance


def load_legacy_candidates(repository_root: Path) -> list[dict[str, Any]]:
    path = repository_root / "research/v3_5/product_query_set_v1/phase_a_r/product_query_candidates.revised.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 40:
        raise ValueError(f"Expected the preserved Phase A-R legacy pool of 40, found {len(rows)}.")
    return rows


def scenario_brief() -> str:
    return """# Product Query Set v1 — Product Scenario Brief

## 产品背景

拾流管理和检索用户保存的 Bilibili 视频资料。用户希望在不重新逐个观看视频的情况下，找到相关视频、定位原字幕证据，并判断收藏夹是否足以回答问题。

## 自然信息任务

独立出题时可参考这些自然信息任务维度：概念或术语解释、技术或工具的作用、实施流程或操作步骤、两个方法或工具的比较、方案选择时机、限制/风险/前置条件、视频是否报告实际效果、评测/测试/质量保障方法、多个视频的互补信息，以及收藏夹可能缺少足够信息的情况。这些是 Authoring Dimensions，不是配额。

## 当前产品边界

- 原字幕与 ASR 是后续证据权威；标题、描述、AI Summary 和章节仅用于 Query Authoring Navigation，不构成后续 Evidence Gold。
- V3.5 关注 Evidence Resolution 与 Sufficiency；本阶段不要求生成答案、Target Video 或 Evidence Gold。
- Product Query 应像普通用户搜索，而不是专门为某个标签或某条视频标题编写。

## 自然性标准

```yaml
standalone_understandable: true
plausible_for_shiliu: true
natural_user_wording: true
not_written_to_match_exact_video_title: true
not_written_to_force_a_known_label: true
```

允许简单单意图、自然双方面/少量多方面、单视频或多视频综合，以及少量可能无答案的问题。避免让集合被证据审计式、项目规划式、过长复合式或面试大纲式问题主导。
"""


def content_map_markdown(rows: Iterable[Mapping[str, Any]]) -> str:
    lines = ["# Product Query Set v1 — Neutral Library Content Map", "", "此地图只用于独立 Query Authoring Navigation。它不表示任何问题可被回答，也不表示某个视频是正确答案。AI Summary、标题和章节若被使用，也不构成后续 Evidence Gold。", ""]
    for row in rows:
        lines.extend([f"## {row['topic_cluster_id']} — {row['neutral_topic_label']}", "", row["neutral_topic_description"], "",
                      f"- Approximate items: {row['approximate_item_count']}", f"- Coverage signal: {row['coverage_signal']}",
                      f"- Content shapes observed in navigation material: {', '.join(row['content_shapes']) or 'not classified'}",
                      f"- Single/multi-item potential: {row['single_or_multi_item_potential']}",
                      f"- Source languages: {', '.join(row['source_languages'])}",
                      f"- Subtitle source types: {', '.join(row['subtitle_source_types'])}",
                      f"- Navigation sources: {', '.join(row['navigation_sources_used'])}", f"- Note: {row['authoring_notes']}", ""])
    return "\n".join(lines)


def independent_guide() -> str:
    return """# Product Query Set v1 — Independent Authoring Guide

## Pass 1 only

Only use the Product Scenario Brief and Neutral Library Content Map. Do **not** read the Legacy Candidate Packet before completing this pass.

Independently draft 24–30 natural Product Query candidates. Do not create a question for every Topic Cluster or force Query Family quotas. Prefer standalone, plausible wording; a few multi-video synthesis or potentially no-answer questions are allowed. Do not write answers, Target Videos, Gold, or predicted retrieval outcomes. Mark drafts that need user discussion.

`user_validated_as_plausible` must remain `null`; only the user can validate it later.
"""


def legacy_packet(candidates: Iterable[Mapping[str, Any]]) -> str:
    lines = ["# Product Query Set v1 — Legacy Candidate Packet", "", "以下问题是从历史项目文档中提取的 Legacy Candidate，仅作为第二阶段参考材料。它们不是经过批准的 Product Query，也不代表真实搜索日志。", "", "Only provide this packet after Pass 1 independent drafting is complete.", ""]
    for row in candidates:
        lines.extend([f"## {row['legacy_candidate_id']}", "", f"- Raw Query: {row['raw_query']}",
                      f"- Source Type: {row['source_type']}", f"- Source Reference: `{row['source_file']}`, {row['source_reference']}",
                      f"- Existing Query Family: {row['query_family']}", f"- Multi-aspect: {str(row['multi_aspect']).lower()}", ""])
    return "\n".join(lines)


def handoff() -> str:
    return """# Product Query Set v1 — Independent WebGPT Handoff

## Pass 1 — Independent Authoring

Provide only these files first:

- `PQS_V1_PRODUCT_SCENARIO_BRIEF.md`
- `PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md`
- `PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md`
- `independent_query_draft.template.jsonl`

Ask WebGPT to draft 24–30 independent natural Product Queries and complete the blank template. Do not provide Legacy materials during this pass. The internal `pqs_v1_content_map_provenance.jsonl` is private and must not be shared.

## Pass 2 — Legacy Candidate Reconciliation

Only after Pass 1 is complete, provide:

- `PQS_V1_LEGACY_CANDIDATE_PACKET.md`
- `legacy_candidate_review.template.jsonl`

Ask WebGPT to record `absorb`, `revise`, `merge`, `exclude`, or `reserve`, compare Legacy wording with independent drafts, and identify issues for user discussion. It must not validate queries on the user's behalf.

## Final user discussion

WebGPT may present a unified candidate pool, discuss and merge wording, and recommend 20–24 candidates. The user alone records `user_validated_as_plausible: true`. Product Query Set v1 is not frozen here; no Dev/Frozen Eval split, Product Baseline, F1A, or F1B is started.
"""


def report(topic_rows: list[dict[str, Any]], legacy_count: int) -> str:
    counts = {row["topic_cluster_id"]: row["approximate_item_count"] for row in topic_rows}
    return f"""# V3.5 Product Query Set v1 — Authoring Packet Report

## Positioning

1. Product Query Set is **not** defined as a historical search-log dataset.
2. It is a scenario-grounded, independently authored, and user-validated Product Query Set.
3. Codex exports neutral materials; independent WebGPT authors/reconciles drafts; the user alone validates plausibility.

## Product Scenario Brief

4. Product requirements used: `00_V3_RETRIEVAL_VERSION_BRIEF.md`, `docs/specs/2026-07-15-shiliu-v1.md`, `V3_CURRENT_STATE.md`, and the Stage 5 product interaction description.
5. It includes real product information tasks: yes.
6. It includes system performance or Stress results: no.
7. New Product Queries generated by Codex: 0.

## Content Map

8. Topic clusters: {len(topic_rows)}.
9. Approximate item counts: {counts}.
10. Navigation sources: metadata, title, description, subtitle language/source metadata.
11. Raw transcript body read: no.
12. Gold viewed: no.
13. Video ID / BV / timestamp exposed to independent WebGPT: no.
14. Every cluster has internal Provenance: yes.
15. Answerability promise made: no.

## Legacy Pool

16. Legacy Candidates: {legacy_count}.
17. Raw wording preserved: yes.
18. Codex automatic rewrites: 0.
19. System performance information included: no.
20. Separated from Pass 1: yes.

## Handoff

21. Pass 1 independent authoring is explicit: yes.
22. Pass 2 Legacy Reconciliation is explicit: yes.
23. Blank independent draft template generated: yes.
24. Blank Legacy Review Template generated: yes.
25. Blank User Validation Template generated: yes.
26. Ready for independent WebGPT: yes.
27. Product Query frozen: no.
28. Dev / Eval split: no.
29. Product Baseline started: no.
30. F1A / F1B started: no.
"""


def build_authoring_packet(repository_root: Path, database: Path = PRODUCT_DB) -> dict[str, Any]:
    output = repository_root / "research/v3_5/product_query_set_v1/authoring_packet"
    for name in ("protocol", "product_scenarios", "library_content_map", "provenance", "independent_authoring", "legacy_candidates", "user_validation", "isolation", "tests"):
        directory = output / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "README.md").write_text(f"# {name}\n\nSee the top-level authoring-packet exports.\n", encoding="utf-8")
    metadata = load_navigation_metadata(database)
    topic_rows, provenance_rows = build_content_map(metadata)
    legacy = load_legacy_candidates(repository_root)
    (output / "PQS_V1_PRODUCT_SCENARIO_BRIEF.md").write_text(scenario_brief(), encoding="utf-8")
    (output / "PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md").write_text(content_map_markdown(topic_rows), encoding="utf-8")
    write_jsonl(output / "pqs_v1_neutral_library_content_map.jsonl", topic_rows)
    write_jsonl(output / "pqs_v1_content_map_provenance.jsonl", provenance_rows)
    (output / "PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md").write_text(independent_guide(), encoding="utf-8")
    write_jsonl(output / "independent_query_draft.template.jsonl", ({"independent_draft_id": f"PQS_IND_{index:03d}", "proposed_query": "", "topic_cluster_ids": [], "query_family": "", "complexity": "", "single_or_multi_item_intent": "", "authoring_rationale": "", "needs_user_discussion": False, "user_validated_as_plausible": None} for index in range(1, 31)))
    legacy_rows = [{"legacy_candidate_id": row["candidate_query_id"], "raw_query": row["raw_query"], "source_type": row["source_type"], "source_file": row["source_file"], "source_reference": row["source_reference"], "query_family": row["query_family"], "multi_aspect": row["multi_aspect"]} for row in legacy]
    write_jsonl(output / "pqs_v1_legacy_candidates.jsonl", legacy_rows)
    (output / "PQS_V1_LEGACY_CANDIDATE_PACKET.md").write_text(legacy_packet(legacy_rows), encoding="utf-8")
    write_jsonl(output / "legacy_candidate_review.template.jsonl", ({"legacy_candidate_id": row["legacy_candidate_id"], "legacy_action": "", "related_independent_draft_ids": [], "proposed_revision": "", "reason": ""} for row in legacy_rows))
    write_jsonl(output / "product_query_user_validation.template.jsonl", ({"draft_query_id": "", "final_user_query": "", "authoring_origin": [], "user_action": "", "user_validated_as_plausible": None, "decision_reason": ""} for _ in range(30)))
    (output / "PQS_V1_INDEPENDENT_WEBGPT_HANDOFF.md").write_text(handoff(), encoding="utf-8")
    audit = {"runner_version": RUNNER_VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "retrieval_calls": 0, "product_search_calls": 0, "embedding_calls": 0, "candidate_builder_calls": 0, "selector_calls": 0, "sufficiency_judge_calls": 0, "final_answer_calls": 0, "raw_transcript_read_for_authoring": False, "gold_read_for_authoring": False, "stress_results_read_for_topic_prioritization": False, "system_performance_used": False, "heldout_accessed": False, "new_product_queries_generated_by_codex": 0, "legacy_queries_rewritten_by_codex": 0, "human_decisions_filled": 0, "navigation_material_types": ["metadata", "title", "description", "subtitle_language", "subtitle_source"]}
    write_json(output / "pqs_v1_authoring_packet_execution.audit.json", audit)
    manifest = {"runner_version": RUNNER_VERSION, "status": "Stage 3R-PQS-B0 Complete", "topic_cluster_count": len(topic_rows), "navigation_item_count": len(metadata), "legacy_candidate_count": len(legacy_rows), "content_map_provenance_private": True, "product_query_set_frozen": False, "dev_eval_split_started": False, "product_baseline_started": False, "f1a_started": False, "f1b_started": False}
    write_json(output / "pqs_v1_authoring_packet_manifest.json", manifest)
    (output / "V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md").write_text(report(topic_rows, len(legacy_rows)), encoding="utf-8")
    tracked = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "pqs_v1_authoring_packet_file_hash_manifest.jsonl")
    write_jsonl(output / "pqs_v1_authoring_packet_file_hash_manifest.jsonl", ({"path": str(path.relative_to(output)), "sha256": file_sha256(path)} for path in tracked))
    return manifest


if __name__ == "__main__":
    print(json.dumps(build_authoring_packet(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2, sort_keys=True))
