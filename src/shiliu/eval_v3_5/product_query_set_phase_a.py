"""Query-only preparation for Product Query Set v1.

This module deliberately has no retrieval, embedding, video, subtitle, Gold,
candidate-builder, selector, or judge dependency.  The source rows below are a
small, explicit allowlist of pre-existing human-authored project questions.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping
import unicodedata


RUNNER_VERSION = "v3.5-product-query-set-phase-a-v1"
MAX_CANDIDATE_POOL = 40
MINIMUM_FINAL_QUERIES = 20
TARGET_FINAL_QUERIES = 24


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


def normalize_for_exact_duplicate(query: str) -> str:
    """Only Unicode/whitespace normalization; never semantic normalization."""
    return " ".join(unicodedata.normalize("NFC", query).strip().split())


def _source(
    raw_query: str, source_file: str, source_reference: str, source_type: str,
    source_excerpt: str, query_family: str, multi_aspect: bool = False,
) -> dict[str, Any]:
    return {
        "raw_query": raw_query,
        "source_file": source_file,
        "source_reference": source_reference,
        "source_type": source_type,
        "source_excerpt": source_excerpt,
        "query_family": query_family,
        "multi_aspect": multi_aspect,
    }


# These are transcription-only records from human-authored notes.  They are not
# inferred from the corpus, video titles, Gold, or system results.
HUMAN_QUERY_SOURCES: tuple[dict[str, Any], ...] = (
    _source("找出我收藏过的 Harness 相关内容。", "00_V3_RETRIEVAL_VERSION_BRIEF.md", "lines 74-76", "actual_search_or_navigation_requirement", "V3 典型用户检索示例。", "decision_or_troubleshooting"),
    _source("哪些视频讨论了 Agent Memory 的上下文压缩？", "00_V3_RETRIEVAL_VERSION_BRIEF.md", "lines 78-79", "actual_search_or_navigation_requirement", "V3 典型用户检索示例。", "definition"),
    _source("最近收藏但还没看的 LangGraph 视频有哪些？", "00_V3_RETRIEVAL_VERSION_BRIEF.md", "lines 80-81", "actual_search_or_navigation_requirement", "V3 典型用户检索示例。", "decision_or_troubleshooting"),
    _source("哪条视频在什么时间点提到了某个 GitHub 项目？", "00_V3_RETRIEVAL_VERSION_BRIEF.md", "lines 82-83", "actual_search_or_navigation_requirement", "V3 典型用户检索示例。", "how_to_or_process"),
    _source("这条内容是否值得完整处理？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 614", "human_authored_project_note", "未来 Agent 决策问题。", "decision_or_troubleshooting"),
    _source("应该做简短摘要还是深度分析？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 615", "human_authored_project_note", "未来 Agent 决策问题。", "comparison_or_tradeoff"),
    _source("教程、访谈、新闻、项目演示分别调用什么流程？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 616", "human_authored_project_note", "未来 Agent 决策问题。", "how_to_or_process"),
    _source("字幕不足时是否需要抽关键帧？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 617", "human_authored_project_note", "未来 Agent 决策问题。", "decision_or_troubleshooting"),
    _source("视频提到 GitHub 项目时是否读取 README？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 618", "human_authored_project_note", "未来 Agent 决策问题。", "decision_or_troubleshooting"),
    _source("内容与已有知识库是否重复或冲突？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 619", "human_authored_project_note", "未来 Agent 决策问题。", "evaluation_or_quality"),
    _source("应该生成 Markdown、对比表、知识卡片还是视频？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 620", "human_authored_project_note", "未来 Agent 决策问题。", "comparison_or_tradeoff"),
    _source("失败后应该换哪个 Provider，还是请求人工处理？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 621", "human_authored_project_note", "未来 Agent 决策问题。", "decision_or_troubleshooting"),
    _source("bilibili-cli 是否足以承担拾流的 B 站 Source Adapter？哪些能力可以直接借用，哪些必须由拾流自己实现？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1210", "human_authored_project_note", "近期依赖评估的核心问题。", "natural_multi_aspect", True),
    _source("Source Adapter 怎么定义？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1512", "human_authored_project_note", "框架设计前需要回答的问题。", "definition"),
    _source("Content Item 最小 Schema 是什么？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1513", "human_authored_project_note", "框架设计前需要回答的问题。", "definition"),
    _source("如何识别新增？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1514", "human_authored_project_note", "框架设计前需要回答的问题。", "how_to_or_process"),
    _source("处理状态需要多复杂？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1515", "human_authored_project_note", "框架设计前需要回答的问题。", "comparison_or_tradeoff"),
    _source("字幕 Provider 如何降级？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1516", "human_authored_project_note", "框架设计前需要回答的问题。", "how_to_or_process"),
    _source("摘要输出格式是什么？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1517", "human_authored_project_note", "框架设计前需要回答的问题。", "definition"),
    _source("文件与数据库如何分工？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1518", "human_authored_project_note", "框架设计前需要回答的问题。", "comparison_or_tradeoff"),
    _source("失败如何保留证据？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1519", "human_authored_project_note", "框架设计前需要回答的问题。", "how_to_or_process"),
    _source("拾流 V0 只监控一个收藏夹，还是支持多个收藏夹？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1563", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "comparison_or_tradeoff"),
    _source("“新增”以首次扫描时间、收藏时间还是本地差集定义？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1564", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "comparison_or_tradeoff"),
    _source("是否处理收藏夹已有历史视频，还是只处理启用后的新增？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1565", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "comparison_or_tradeoff"),
    _source("第一版摘要需要什么固定结构？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1566", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "how_to_or_process"),
    _source("是否保存完整字幕和时间戳？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1567", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "decision_or_troubleshooting"),
    _source("长视频采用何种分段策略？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1568", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "how_to_or_process"),
    _source("没有字幕时是否立即 ASR，还是进入待处理列表？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1569", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "comparison_or_tradeoff"),
    _source("第一版是否需要 SQLite，还是先用轻量状态文件？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1570", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "comparison_or_tradeoff"),
    _source("文件目录如何组织？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1571", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "how_to_or_process"),
    _source("是否需要保留原始 API 响应作为证据？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1572", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "evaluation_or_quality"),
    _source("第一版是否必须完全自动运行？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1573", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "decision_or_troubleshooting"),
    _source("是否需要本地查看页，还是 Markdown 足够？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1574", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "comparison_or_tradeoff"),
    _source("哪些失败应自动重试，哪些应停止？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1575", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "decision_or_troubleshooting"),
    _source("是否需要维护摘要版本和 Prompt 版本？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1576", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "decision_or_troubleshooting"),
    _source("后续多平台统一 Schema 应预留到什么程度？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1577", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "decision_or_troubleshooting"),
    _source("什么时候引入 MCP、飞书或 Hermes？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1578", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "decision_or_troubleshooting"),
    _source("项目是只服务个人使用，还是同时准备求职展示？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1579", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "comparison_or_tradeoff"),
    _source("哪些功能体现真实工程能力，哪些应直接复用？", "拾流_Shiliu_完整项目上下文与当前行动.md", "line 1580", "human_authored_project_note", "待与用户逐项讨论的开放问题。", "comparison_or_tradeoff"),
)

# The allowed anonymized stress-query reference is used mechanically for overlap
# marking only; it never provides candidates or selection input.
STRESS_QUERY_REFERENCE = frozenset(normalize_for_exact_duplicate(value) for value in (
    "MSE 和交叉熵分别适合什么任务，遇到异常值或类别不平衡时该怎么选？",
    "终端、命令行和命令有什么区别，初学者运行命令时怎样避免误删文件？",
    "AI 自动导入 Godot 精灵动画相比手工导入节省多少时间，错误率如何？",
    "在已有项目中使用 OpenSpec 后，是否实际减少了需求返工，视频给出了什么使用结果？",
    "Home Rail 当前适合什么任务、使用前有哪些限制，又计划向什么方向发展？",
    "Python 的数字类型有哪些，它们之间应怎样进行安全的类型转换？",
    "如何把一个应用从原型推进到云部署，并建立自动化测试和回滚机制？",
    "SFT 中 completion-only 和 NEFTune 各有什么作用，选择与调参时有哪些风险？",
    "一个高质量 Skill 在上线前应该怎样设计评测、触发边界、正文和目录结构？",
    "RAG 上生产前需要补齐哪些工程能力，又该怎样设计离线与在线质量评测？",
))


def build_candidates(sources: Iterable[Mapping[str, Any]] = HUMAN_QUERY_SOURCES) -> tuple[list[dict[str, Any]], int]:
    """Assign stable ids and remove only exact normalized duplicates."""
    candidates: list[dict[str, Any]] = []
    exact_duplicates = 0
    seen: dict[str, int] = {}
    for source in sources:
        raw_query = str(source["raw_query"])
        if not raw_query.strip() or not source.get("source_file") or not source.get("source_reference"):
            raise ValueError("Every Product Query candidate needs a non-empty traceable source.")
        normalized = normalize_for_exact_duplicate(raw_query)
        if normalized in seen:
            exact_duplicates += 1
            candidates[seen[normalized]]["additional_source_references"].append({
                "source_file": source["source_file"], "source_reference": source["source_reference"],
            })
            continue
        row = {
            "candidate_query_id": f"PQS_CAND_{len(candidates) + 1:03d}",
            "raw_query": raw_query,
            "source_type": source["source_type"],
            "source_file": source["source_file"],
            "source_reference": source["source_reference"],
            "source_excerpt": source["source_excerpt"],
            "normalization_notes": "", "query_family": source["query_family"],
            "multi_aspect": bool(source["multi_aspect"]),
            "natural_without_video_context": True,
            "plausibly_asked_in_shiliu": True,
            "possible_semantic_duplicate_group": None,
            "stress_set_overlap": normalized in STRESS_QUERY_REFERENCE,
            "answerability_checked": False, "retrieval_executed": False,
            "human_decision": None, "additional_source_references": [],
        }
        seen[normalized] = len(candidates)
        candidates.append(row)
    if len(candidates) > MAX_CANDIDATE_POOL:
        raise ValueError(f"Candidate pool exceeds cap of {MAX_CANDIDATE_POOL}.")
    return candidates, exact_duplicates


def family_gaps(candidates: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    minimums = {
        "definition": 3, "purpose_or_use_case": 3, "how_to_or_process": 3,
        "comparison_or_tradeoff": 3, "evaluation_or_quality": 2,
        "decision_or_troubleshooting": 2, "natural_multi_aspect": 1,
    }
    counts = Counter(str(row["query_family"]) for row in candidates)
    return {family: {"observed": counts[family], "soft_minimum": minimum, "shortfall": max(0, minimum - counts[family])}
            for family, minimum in minimums.items()}


def _protocol_markdown() -> str:
    return """# Product Query Set v1 — Lightweight Protocol

## Eval role

Product Query Set ≠ Evidence Sufficiency Stress Set.

Product Query Set evaluates natural, standalone user questions on Product Default Auto: ordinary retrieval, regular evidence resolution, product latency, empty results, and layered failure attribution. The Evidence Sufficiency Stress Set remains for complex multi-aspect evidence, long-span claims, boundaries, partial support, insufficiency/unverifiability, and stress testing.

## Scope and split

The final set has a minimum of 20, target of 24, and maximum of 24 approved queries. This phase permits a 28–36 preferred candidate pool and caps it at 40. After humans approve 20–24 queries and before Retrieval, 24 queries will split as 14 development / 10 frozen evaluation; 20–23 queries will use approximately 60% development and 8–10 frozen evaluation. This phase creates only a human preference field, not a split.

## Gold and review policy

Later Gold needs at least one confirmed minimally sufficient evidence group; it does not require exhaustive acceptable-video or Gold-group annotation. Ordinary cases receive initial annotation plus one independent review. No-answer, partially answerable, multi-video, cross-language, severe-ASR-error, and disputed cases escalate to a second reviewer or human adjudication.

## Stop rules

- Maximum final queries: 24
- Maximum query-selection rounds: 1
- Maximum schema-revision rounds: 1
- Full dual review: false
- Expand for label balance: false
- Exhaustive relevant-video annotation: false
- New annotation platform: false
"""


def _audit_markdown(candidates: list[dict[str, Any]], raw_source_count: int, exact_duplicates: int, gaps: Mapping[str, Mapping[str, int]]) -> str:
    source_counts = Counter(row["source_type"] for row in candidates)
    family_counts = Counter(row["query_family"] for row in candidates)
    lines = ["# Product Query Set v1 — Query Source Audit", "", "## Search scope", "",
             "Searched only the explicit human-authored source allowlist:", "",
             "- `00_V3_RETRIEVAL_VERSION_BRIEF.md` (actual search/navigation requirements)",
             "- `拾流_Shiliu_完整项目上下文与当前行动.md` (human-authored project notes and open requirements)", "",
             "The Stress Track was not used as a candidate source. Its separately published anonymized query reference was used only for exact-overlap marking.",
             "", "## Counts", "", f"- Traceable raw human questions found: {raw_source_count}",
             f"- Traceable candidate queries: {len(candidates)}", f"- Exact duplicates removed: {exact_duplicates}",
             "- Possible semantic duplicates marked: 0 (none automatically inferred or deleted)",
             f"- Exact stress-reference overlaps: {sum(row['stress_set_overlap'] for row in candidates)}", "",
             "### Source types", ""]
    lines.extend(f"- `{kind}`: {count}" for kind, count in sorted(source_counts.items()))
    lines.extend(["", "### Query families", ""])
    lines.extend(f"- `{kind}`: {count}" for kind, count in sorted(family_counts.items()))
    lines.extend(["", "## Soft-coverage gaps", ""])
    for family, detail in gaps.items():
        state = "gap" if detail["shortfall"] else "covered"
        lines.append(f"- `{family}`: {detail['observed']} observed / soft minimum {detail['soft_minimum']} — {state}")
    lines.extend(["", "## Result", "", f"The pool has {len(candidates)} candidates and therefore meets the at-least-20 threshold. No model-authored filler was added; human review may exclude unsuitable candidates. The visible gaps are `purpose_or_use_case` and any family reported above as short.", ""])
    return "\n".join(lines)


def _review_packet(candidates: Iterable[Mapping[str, Any]]) -> str:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in candidates:
        groups.setdefault(str(row["query_family"]), []).append(row)
    lines = ["# Product Query Set v1 — Query-only Human Review Packet", "", "Review only the candidate wording and its traceable human source. Do not make answerability, target-video, Gold, or expected-system-performance judgments in this phase.", ""]
    for family in sorted(groups):
        lines.extend([f"## {family}", ""])
        for row in groups[family]:
            duplicate = row["possible_semantic_duplicate_group"] or "None marked"
            lines.extend([f"### {row['candidate_query_id']}", "", f"- Raw Query: {row['raw_query']}",
                          f"- Source Type: {row['source_type']}", f"- Source Reference: `{row['source_file']}`, {row['source_reference']}",
                          f"- Query Family: {row['query_family']}", f"- Multi-aspect: {str(row['multi_aspect']).lower()}",
                          f"- Possible Duplicate: {duplicate}", f"- Stress-set Overlap: {str(row['stress_set_overlap']).lower()}", ""])
    return "\n".join(lines)


def _report(candidates: list[dict[str, Any]], raw_source_count: int, exact_duplicates: int, gaps: Mapping[str, Mapping[str, int]]) -> str:
    family_counts = Counter(row["query_family"] for row in candidates)
    gap_names = [name for name, detail in gaps.items() if detail["shortfall"]]
    return f"""# V3.5 Product Query Set v1 — Phase A Report

## Protocol

1. Product Set and Stress Set roles are separated: **yes**.
2. Final target: minimum 20, target 24, maximum 24.
3. Later split target: 14 development / 10 frozen evaluation at 24; approximately 60% development and 8–10 frozen evaluation at 20–23.
4. Minimum Gold policy: one confirmed minimally sufficient evidence group.
5. Review policy: initial annotation plus one independent review; high-risk/disputed cases escalate.
6. Stop rules are frozen in `PQS_V1_PROTOCOL.md`.

## Source audit

7. Searched paths: `00_V3_RETRIEVAL_VERSION_BRIEF.md` and `拾流_Shiliu_完整项目上下文与当前行动.md`.
8. Raw human questions found: {raw_source_count}.
9. Traceable candidates: {len(candidates)}.
10. Exact duplicates removed: {exact_duplicates}.
11. Possible semantic duplicates marked: 0 (no semantic deletion performed).
12. Stress-reference overlaps: {sum(row['stress_set_overlap'] for row in candidates)}.
13. Query families: {dict(sorted(family_counts.items()))}.
14. Visible soft-coverage gaps: {', '.join(gap_names) or 'none'}.

## Query-only isolation

15. Retrieval run: no.
16. Videos or subtitles viewed: no.
17. Answerability inspected: no.
18. System results used for selection: no.
19. Codex-generated filler queries: no.
20. Human decisions blank: yes.

## Outputs and status

21. Candidate pool: {len(candidates)}.
22. Review packet: `research/v3_5/product_query_set_v1/phase_a/PQS_V1_QUERY_ONLY_REVIEW_PACKET.md`.
23. Decision template: `research/v3_5/product_query_set_v1/phase_a/product_query_decisions.template.jsonl`.
24. Human authoring required: no; family gaps should be considered during the one human selection round.
25. Ready for Human Query-only Review: yes.
26. Product Query Set Baseline started: no.
27. F1A/F1B started: no.
28. Current Codex session should close after handoff: yes.

## Completion

Stage 3R-PQS-A Complete

Lightweight Product-query Protocol Frozen
Traceable Human-authored Query Sources Audited
Query-only Candidate Pool Prepared
No Retrieval or Answerability Inspection Performed
Human Decision Template Generated
Ready for Human Query-only Review
"""


def _human_authoring_gaps(candidates: list[dict[str, Any]], gaps: Mapping[str, Mapping[str, int]]) -> str:
    missing = max(0, MINIMUM_FINAL_QUERIES - len(candidates))
    families = [family for family, detail in gaps.items() if detail["shortfall"]]
    slots = []
    for index in range(1, missing + 1):
        slots.extend([f"## Slot {index:02d}", "", "- User query:", "- Where did this need arise?", "- Query family:", ""])
    return "\n".join([
        "# Product Query Set v1 — Human Authoring Gaps", "",
        f"- current_candidate_count: {len(candidates)}",
        f"- minimum_missing_count: {missing}",
        f"- missing_query_families: {', '.join(families) or 'none'}", "",
        "Add only real user needs and their traceable origin. Do not derive questions from video titles, Gold, subtitles, or system outcomes.",
        "", *slots,
    ])


def build_phase_a(repository_root: Path, sources: Iterable[Mapping[str, Any]] = HUMAN_QUERY_SOURCES) -> dict[str, Any]:
    output = repository_root / "research/v3_5/product_query_set_v1/phase_a"
    source_rows = list(sources)
    candidates, exact_duplicates = build_candidates(source_rows)
    gaps = family_gaps(candidates)
    directory_notes = {
        "protocol": "Contains the top-level lightweight protocol document.",
        "source_audit": "Contains the top-level traceable-source audit.",
        "candidate_pool": "Contains the top-level query-only candidate JSONL.",
        "query_only_review": "Contains the top-level human query-only review packet.",
        "human_decisions": "Contains the top-level blank human decision template.",
        "isolation": "Contains the top-level query-only execution audit.",
        "tests": "Phase-A contracts are implemented in tests/test_product_query_set_phase_a_contracts.py.",
    }
    for relative, note in directory_notes.items():
        directory = output / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "README.md").write_text(f"# {relative}\n\n{note}\n", encoding="utf-8")

    candidate_path = output / "product_query_candidates.discovered.jsonl"
    decision_path = output / "product_query_decisions.template.jsonl"
    write_jsonl(candidate_path, candidates)
    write_jsonl(decision_path, ({"candidate_query_id": row["candidate_query_id"], "human_action": "", "approved_user_query": "", "decision_reason": "", "preferred_split": ""} for row in candidates))
    (output / "PQS_V1_PROTOCOL.md").write_text(_protocol_markdown(), encoding="utf-8")
    (output / "PQS_V1_QUERY_SOURCE_AUDIT.md").write_text(_audit_markdown(candidates, len(source_rows), exact_duplicates, gaps), encoding="utf-8")
    (output / "PQS_V1_QUERY_ONLY_REVIEW_PACKET.md").write_text(_review_packet(candidates), encoding="utf-8")
    (output / "V3_5_PRODUCT_QUERY_SET_V1_PHASE_A_REPORT.md").write_text(_report(candidates, len(source_rows), exact_duplicates, gaps), encoding="utf-8")
    authoring_gaps_path = output / "PQS_V1_HUMAN_AUTHORING_GAPS.md"
    if len(candidates) < MINIMUM_FINAL_QUERIES:
        authoring_gaps_path.write_text(_human_authoring_gaps(candidates, gaps), encoding="utf-8")
    elif authoring_gaps_path.exists():
        authoring_gaps_path.unlink()

    audit = {
        "runner_version": RUNNER_VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retrieval_calls": 0, "product_search_calls": 0, "embedding_calls": 0,
        "candidate_builder_calls": 0, "selector_calls": 0, "sufficiency_judge_calls": 0,
        "final_answer_calls": 0, "external_llm_calls": 0, "external_network_calls": 0,
        "heldout_accessed": False, "video_titles_used_to_generate_queries": False,
        "gold_used_to_generate_queries": False, "system_results_used_to_select_queries": False,
        "videos_or_subtitles_viewed": False, "answerability_checked": False,
        "f1a_started": False, "f1b_started": False,
        "stress_set_reference_role": "exact_overlap_marking_only; not a candidate source",
    }
    write_json(output / "product_query_set_phase_a_execution.audit.json", audit)
    manifest = {"runner_version": RUNNER_VERSION, "candidate_count": len(candidates), "exact_duplicates_removed": exact_duplicates,
                "possible_semantic_duplicates": 0, "stress_set_overlaps": sum(row["stress_set_overlap"] for row in candidates),
                "family_gaps": gaps, "source_allowlist": sorted({row["source_file"] for row in source_rows}),
                "status": "Stage 3R-PQS-A Complete", "human_authoring_required": len(candidates) < MINIMUM_FINAL_QUERIES}
    write_json(output / "product_query_set_phase_a_manifest.json", manifest)
    tracked = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in {"product_query_set_phase_a_file_hash_manifest.jsonl"})
    write_jsonl(output / "product_query_set_phase_a_file_hash_manifest.jsonl", ({"path": str(path.relative_to(output)), "sha256": file_sha256(path)} for path in tracked))
    return manifest
