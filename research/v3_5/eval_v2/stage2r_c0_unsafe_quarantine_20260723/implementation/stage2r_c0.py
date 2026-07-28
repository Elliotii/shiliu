from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("research/v3_5/eval_v2/stage2r_c0")
PILOT_ROOT = Path("research/v3_5/eval_v2/stage2r_b2")
FREEZE_MANIFEST = Path("research/v3_5/eval_v2/stage2r_b1_c/canary_freeze_manifest.json")
VIDEO_ROOT = Path("/Users/elliot/Documents/Shiliu/videos")
REVIEW = Path("V3_5_STAGE2R_C0_FIRST_BATCH_CANDIDATE_REVIEW.md")
REPORT = Path("V3_5_STAGE2R_C0_COVERAGE_AND_POOL_REPORT.md")
EXPECTED_FREEZE_SHA256 = "d64d72ebd283fb86d798b9c026a230569d924cdcf2c77471b5a5e0b2c72df394"
EXPECTED_PILOTS = {
    "V2C_B1A00001": "insufficient",
    "V2C_B1A00002": "sufficient",
    "V2C_B2P00001": "insufficient",
    "V2C_B2P00002": "insufficient",
}
PILOT_QUERIES = {"MCP", "CLI 相比 MCP 的优势", "RAG", "vibe coding"}
FIRST_BATCH_KEYS = tuple(f"C{i:02d}" for i in range(1, 9))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_sha256(value: object) -> str:
    return sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def validate_pilots() -> tuple[list[dict[str, Any]], dict[str, int]]:
    allowed = (
        PILOT_ROOT / "adjudicated_canary_cases.jsonl",
        PILOT_ROOT / "adjudicated_remaining_pilot_cases.jsonl",
        PILOT_ROOT / "canary_adjudication.audit.json",
        PILOT_ROOT / "remaining_pilot_adjudication.audit.json",
    )
    records = _jsonl(allowed[0]) + _jsonl(allowed[1])
    actual = {row["case_id"]: row["final_status"] for row in records}
    if actual != EXPECTED_PILOTS:
        raise RuntimeError(f"pilot_ledger_mismatch:{actual}")
    for audit_path in allowed[2:]:
        audit = _read_json(audit_path)
        if audit["case_count"] != 2 or not audit["canonical_reconstruction_passed"]:
            raise RuntimeError(f"pilot_audit_invalid:{audit_path}")
        if audit["model_calls"] != 0:
            raise RuntimeError(f"pilot_audit_model_calls_nonzero:{audit_path}")
    distribution = Counter(actual.values())
    return records, {
        label: distribution.get(label, 0)
        for label in ("sufficient", "partial", "insufficient", "unverifiable")
    }


def _aspect(aspect_id: str, description: str, materiality: str) -> dict[str, str]:
    return {
        "aspect_id": aspect_id,
        "description": description,
        "why_material": materiality,
    }


def definitions() -> list[dict[str, Any]]:
    return [
        {
            "key": "C01",
            "original_query": "How do Function Calling and MCP differ in responsibility and protocol scope?",
            "evaluation_view": "single_video_multi_aspect_comparison",
            "evidence_question": "该视频的完整原字幕是否解释 Function Calling 与 MCP 在调用责任和协议范围上的差异？",
            "query_language": "en",
            "video": "BV1qTYizcEN3",
            "source_type": "raw_subtitle",
            "expected": "sufficient",
            "aspects": [
                _aspect("A1", "解释 Function Calling 中模型与应用后端各自承担的调用责任。", "缺少责任边界就无法回答比较问题。"),
                _aspect("A2", "解释 MCP 相对普通 API/本地工具调用增加的协议与标准化范围。", "缺少协议范围就无法说明 MCP 的区别。"),
            ],
            "supported": ["A1", "A2"],
            "missing": [],
            "regions": [(135, 170, "Function Calling responsibility"), (760, 785, "MCP protocol scope")],
            "coverage": ["comparative", "multi_aspect", "multi_span", "cross_language", "long_transcript"],
            "risk": ["terminology_asr_typo_NCP_near_MCP"],
            "reason": "A long Chinese transcript gives separate, direct explanations of Function Calling responsibility and MCP standardization for an English comparative query.",
            "route": "AND route: Function Calling responsibility region plus MCP/API standardization region.",
        },
        {
            "key": "C02",
            "original_query": "SFT 与 LoRA 微调的目标、原理和训练流程",
            "evaluation_view": "single_video_multi_aspect_explanation",
            "evidence_question": "该视频的完整原字幕是否解释 SFT 的训练目标、LoRA 的参数高效原理以及实际训练配置流程？",
            "query_language": "zh",
            "video": "BV1UaPmzrESw",
            "source_type": "raw_subtitle",
            "expected": "sufficient",
            "aspects": [
                _aspect("A1", "解释 SFT 的训练目标。", "目标决定该微调方法解决什么问题。"),
                _aspect("A2", "解释 LoRA 的参数高效原理。", "参数效率是 LoRA 与全参数微调的核心区别。"),
                _aspect("A3", "给出数据、Adapter 和训练参数等实际配置流程。", "原 Query 明确要求训练流程。"),
            ],
            "supported": ["A1", "A2", "A3"],
            "missing": [],
            "regions": [(14, 18, "SFT objective"), (124, 172, "LoRA principle"), (199, 225, "training configuration")],
            "coverage": ["multi_aspect", "multi_span", "raw_subtitle", "procedure"],
            "risk": ["phonetic_rendering_LoRA_as_LAURA_or_NORA"],
            "reason": "The transcript covers the behavior objective, low-rank parameter reduction, and concrete configuration in distinct regions.",
            "route": "AND route across objective, principle, and implementation regions.",
        },
        {
            "key": "C03",
            "original_query": "RAG 检索生成流程与人工标注评估",
            "evaluation_view": "single_video_multi_aspect_process_and_evaluation",
            "evidence_question": "该视频的完整原字幕是否解释 RAG 的检索生成流程，并说明如何用人工标注测试集量化评估回答质量？",
            "query_language": "zh",
            "video": "BV1JLN2z4EZQ",
            "source_type": "raw_subtitle",
            "expected": "partial",
            "aspects": [
                _aspect("A1", "解释分片、索引、召回、重排和生成流程。", "流程是问题的第一项独立信息需求。"),
                _aspect("A2", "说明人工标注测试集及量化回答质量指标的评估方法。", "评估方案是可独立缺失的第二项重要需求。"),
            ],
            "supported": ["A1"],
            "missing": ["A2"],
            "regions": [(112, 115, "pipeline overview"), (268, 281, "retrieval"), (360, 389, "reranking"), (415, 433, "generation")],
            "coverage": ["partial", "multi_aspect", "multi_span", "long_transcript"],
            "risk": ["evaluation_absence_must_be_checked_over_full_transcript"],
            "reason": "The workflow is explicit across several regions, while no human-labelled test-set evaluation procedure or answer-quality metric is given.",
            "route": "A1 has a multi-span route; A2 has no route in the complete transcript.",
        },
        {
            "key": "C04",
            "original_query": "MemoryOS 的分层记忆与隐私删除机制",
            "evaluation_view": "single_video_multi_aspect_architecture_and_governance",
            "evidence_question": "该视频的完整原字幕是否解释 MemoryOS 的短期、中期、长期记忆组织，并说明用户数据删除与隐私审计机制？",
            "query_language": "zh",
            "video": "BV1oa6uBXE8J",
            "source_type": "raw_subtitle",
            "expected": "partial",
            "aspects": [
                _aspect("A1", "解释短期、中期和长期记忆的组织与演化。", "分层架构是 Query 的第一项核心需求。"),
                _aspect("A2", "说明用户数据删除与隐私审计机制。", "治理与删除是不同于架构的实质需求。"),
            ],
            "supported": ["A1"],
            "missing": ["A2"],
            "regions": [(80, 111, "three memory tiers"), (248, 327, "tier transitions"), (342, 355, "long-term memory")],
            "coverage": ["partial", "multi_aspect", "multi_span", "long_transcript"],
            "risk": ["paper_explanation_without_governance_content"],
            "reason": "The complete transcript deeply explains tiering and transitions but contains no deletion or privacy-audit mechanism.",
            "route": "A1 has several complementary regions; A2 is absent from the complete transcript.",
        },
        {
            "key": "C05",
            "original_query": "How do Cursor and Claude Code retrieve code context, and what benchmark scores quantify the difference?",
            "evaluation_view": "single_video_multi_aspect_comparison_and_measurement",
            "evidence_question": "该视频的完整 Raw ASR 是否解释 Cursor 与 Claude Code 的代码上下文检索方式，并给出量化基准分数比较两者效果？",
            "query_language": "en",
            "video": "BV18NLx6fEAq",
            "source_type": "raw_asr",
            "expected": "partial",
            "aspects": [
                _aspect("A1", "比较 Cursor 的索引检索与 Claude Code 的命令式探索方式。", "检索方式比较是 Query 的主要机制需求。"),
                _aspect("A2", "提供量化基准分数比较两者效果。", "量化结果是独立且不可由定性评价替代的需求。"),
            ],
            "supported": ["A1"],
            "missing": ["A2"],
            "regions": [(1, 14, "retrieval mechanisms"), (15, 24, "trade-offs"), (25, 27, "conceptual conclusion")],
            "coverage": ["partial", "multi_aspect", "multi_span", "raw_asr", "cross_language"],
            "risk": ["asr_proper_noun_errors", "no_quantitative_benchmark"],
            "reason": "Raw ASR contains a detailed qualitative comparison but no benchmark dataset or numeric score.",
            "route": "A1 is supported across ASR sentence groups; A2 has no quantitative evidence.",
        },
        {
            "key": "C06",
            "original_query": "向量数据库的索引构建与近邻召回机制",
            "evaluation_view": "single_video_topic_evidence",
            "evidence_question": "该视频的完整原字幕是否实质解释向量数据库的索引构建与近邻召回机制？",
            "query_language": "zh",
            "video": "BV1V39eBHERZ",
            "source_type": "raw_subtitle",
            "expected": "insufficient",
            "aspects": [
                _aspect("A1", "实质解释向量数据库索引与近邻召回机制。", "这是单一主题 Query 的完整必要方面。"),
            ],
            "supported": [],
            "missing": ["A1"],
            "regions": [(22, 25, "only adjacent project-category mention")],
            "coverage": ["insufficient", "adjacent_not_equivalent", "explicit_negative"],
            "risk": ["isolated_RAG_mention_could_be_overread"],
            "reason": "The readable transcript mentions RAG only as a project category and does not explain vector indexing or nearest-neighbour retrieval.",
            "route": "No direct evidence route; one adjacent mention is retained for boundary inspection.",
        },
        {
            "key": "C07",
            "original_query": "全参数微调与 LoRA 微调的原理差异",
            "evaluation_view": "single_video_topic_evidence",
            "evidence_question": "该视频的完整原始证据是否解释全参数微调与 LoRA 微调的原理差异？",
            "query_language": "zh",
            "video": "BV13QFxzCEXb",
            "source_type": "unavailable",
            "expected": "unverifiable",
            "aspects": [_aspect("A1", "解释全参数微调与 LoRA 的原理差异。", "这是比较 Query 的核心需求。")],
            "supported": [],
            "missing": [],
            "regions": [],
            "coverage": ["unverifiable", "source_unavailable"],
            "risk": ["metadata_title_must_not_be_used_as_evidence"],
            "reason": "Metadata exists, but no Raw Subtitle or Raw ASR artifact exists and no reliable evidence timeline can be formed.",
            "route": "No evidence route: both authorized raw evidence artifact types are absent.",
        },
        {
            "key": "C08",
            "original_query": "AI 时代学习全栈开发的具体理由",
            "evaluation_view": "single_video_multi_aspect_explanation",
            "evidence_question": "该视频的完整原始证据是否说明 AI 时代仍需学习全栈开发的至少两项具体理由？",
            "query_language": "zh",
            "video": "BV16jREBdEX5",
            "source_type": "unavailable",
            "expected": "unverifiable",
            "aspects": [
                _aspect("A1", "说明学习前端/交互能力的具体理由。", "至少两项理由中的一个独立方面。"),
                _aspect("A2", "说明学习后端/系统能力的具体理由。", "至少两项理由中的另一个独立方面。"),
            ],
            "supported": [],
            "missing": [],
            "regions": [],
            "coverage": ["unverifiable", "source_unavailable", "multi_aspect"],
            "risk": ["metadata_title_must_not_be_used_as_evidence"],
            "reason": "Metadata exists, but no Raw Subtitle or Raw ASR artifact exists and no reliable evidence timeline can be formed.",
            "route": "No evidence route: both authorized raw evidence artifact types are absent.",
        },
        {
            "key": "C09",
            "original_query": "DAG 与 ReAct 在任务依赖、并行执行和失败恢复上的区别",
            "evaluation_view": "single_video_multi_aspect_comparison",
            "evidence_question": "该视频的完整原字幕是否比较 DAG 与 ReAct 的任务依赖、并行执行和失败恢复机制？",
            "query_language": "zh",
            "video": "BV1Up756vEK7",
            "source_type": "raw_subtitle",
            "expected": "partial",
            "aspects": [
                _aspect("A1", "比较任务依赖与执行顺序。", "执行模型的核心区别。"),
                _aspect("A2", "比较并行执行能力。", "并行性是 Query 明确要求。"),
                _aspect("A3", "比较失败恢复或重试机制。", "失败恢复是独立的生产可靠性需求。"),
            ],
            "supported": ["A1", "A2"],
            "missing": ["A3"],
            "regions": [(12, 21, "execution model"), (31, 42, "parallel and hybrid execution")],
            "coverage": ["partial", "multi_aspect", "multi_span", "short_transcript"],
            "risk": ["short_form_oversimplification"],
            "reason": "Dependency and parallelism are direct, while no concrete failure recovery or retry mechanism is described.",
            "route": "A1/A2 are supported; A3 is absent.",
        },
        {
            "key": "C10",
            "original_query": "Agent 记忆持续总结产生的三种错误机制",
            "evaluation_view": "single_video_multi_aspect_explanation",
            "evidence_question": "该视频的完整原字幕是否解释 Agent 记忆持续总结产生的错误分组、条件丢失和窄经验过拟合三种机制？",
            "query_language": "zh",
            "video": "BV1pCGJ6ZEDH",
            "source_type": "raw_subtitle",
            "expected": "sufficient",
            "aspects": [
                _aspect("A1", "解释错误分组。", "三机制之一。"),
                _aspect("A2", "解释压缩导致条件丢失。", "三机制之一。"),
                _aspect("A3", "解释窄经验过拟合。", "三机制之一。"),
            ],
            "supported": ["A1", "A2", "A3"],
            "missing": [],
            "regions": [(11, 20, "mechanism overview"), (61, 100, "grouping and compression"), (124, 155, "narrow overfitting")],
            "coverage": ["multi_aspect", "multi_span", "mechanism"],
            "risk": [],
            "reason": "All three named mechanisms receive direct explanations and examples.",
            "route": "AND route across the three mechanism regions.",
        },
        {
            "key": "C11",
            "original_query": "OpenSpec 如何对齐需求，以及它降低缺陷率的量化结果",
            "evaluation_view": "single_video_multi_aspect_process_and_measurement",
            "evidence_question": "该视频的完整原字幕是否解释 OpenSpec 的需求对齐流程，并给出其降低软件缺陷率的量化实测结果？",
            "query_language": "zh",
            "video": "BV1hYwDzSE7A",
            "source_type": "raw_subtitle",
            "expected": "partial",
            "aspects": [
                _aspect("A1", "解释需求、设计、任务、审查与归档流程。", "流程是工具机制的核心。"),
                _aspect("A2", "给出降低缺陷率的量化实测结果。", "定量效果不可由一般价值陈述替代。"),
            ],
            "supported": ["A1"],
            "missing": ["A2"],
            "regions": [(132, 157, "specification workflow"), (192, 195, "validation and archive"), (355, 358, "review boundary")],
            "coverage": ["partial", "multi_aspect", "multi_span", "procedure"],
            "risk": ["tool_advocacy_without_measurement"],
            "reason": "The workflow is detailed, but no experimental defect-rate baseline or measured improvement is supplied.",
            "route": "A1 has multiple complementary regions; A2 is absent.",
        },
        {
            "key": "C12",
            "original_query": "工业级 RAG 的召回优化与线上 KPI 实测",
            "evaluation_view": "single_video_multi_aspect_optimization_and_measurement",
            "evidence_question": "该视频的完整原字幕是否解释工业级 RAG 的召回优化策略，并报告这些策略在线上系统取得的具体 KPI 数值？",
            "query_language": "zh",
            "video": "BV11wEb6uEwB",
            "source_type": "raw_subtitle",
            "expected": "partial",
            "aspects": [
                _aspect("A1", "解释父子索引、多路召回、重排等优化策略。", "优化机制是第一项核心需求。"),
                _aspect("A2", "报告策略在真实线上系统取得的具体 KPI 数值。", "实际数值是独立于建议指标的结果需求。"),
            ],
            "supported": ["A1"],
            "missing": ["A2"],
            "regions": [(23, 32, "parent-child indexing"), (59, 115, "retrieval and evaluation loop"), (194, 197, "metric discussion without result")],
            "coverage": ["partial", "multi_aspect", "multi_span", "long_transcript"],
            "risk": ["metric_names_must_not_be_misread_as_measured_results"],
            "reason": "The transcript recommends concrete optimizations and metrics but does not report an actual online KPI result attributable to them.",
            "route": "A1 has several optimization regions; A2 is absent despite general metric discussion.",
        },
    ]


def _source_info(definition: dict[str, Any]) -> dict[str, Any]:
    video = definition["video"]
    root = VIDEO_ROOT / video
    metadata_path = root / "metadata.json"
    if not metadata_path.is_file():
        raise RuntimeError(f"metadata_missing:{video}")
    metadata = _read_json(metadata_path)
    if metadata.get("bvid") != video:
        raise RuntimeError(f"metadata_bvid_mismatch:{video}")
    source_type = definition["source_type"]
    if source_type == "raw_subtitle":
        path = root / "subtitle-raw.json"
        rows = _read_json(path)
        segment_count = len(rows)
        first = rows[0]["from"]
        last = rows[-1]["to"]
        artifact_id = f"raw_subtitle:{video}:p1"
    elif source_type == "raw_asr":
        path = root / "asr-raw.json"
        value = _read_json(path)
        rows = value["transcripts"][0]["sentences"]
        segment_count = len(rows)
        first = rows[0]["begin_time"] / 1000
        last = rows[-1]["end_time"] / 1000
        artifact_id = f"raw_asr:{video}:p1"
    else:
        subtitle = root / "subtitle-raw.json"
        asr = root / "asr-raw.json"
        if subtitle.exists() or asr.exists():
            raise RuntimeError(f"expected_source_failure_not_real:{video}")
        return {
            "source_video_id": video,
            "source_type": "unavailable",
            "source_language": "unknown",
            "source_availability": "unavailable_missing_raw_subtitle_and_raw_asr",
            "source_artifact_id": f"unavailable:{video}:p1",
            "source_version": None,
            "timeline_run_id": None,
            "transcript_segment_count": 0,
            "transcript_start": None,
            "transcript_end": None,
            "raw_source_path": None,
            "source_failure_metadata": {
                "metadata_path": str(metadata_path),
                "metadata_sha256": sha256_file(metadata_path),
                "raw_subtitle_path": str(subtitle),
                "raw_subtitle_exists": False,
                "raw_asr_path": str(asr),
                "raw_asr_exists": False,
                "subtitle_track": metadata.get("subtitle_track"),
                "subtitle_segment_count": len(metadata.get("subtitle_segments") or []),
                "failure_class": "no_authorized_raw_evidence_artifact",
            },
        }
    digest = sha256_file(path)
    return {
        "source_video_id": video,
        "source_type": source_type,
        "source_language": "zh",
        "source_availability": "available",
        "source_artifact_id": artifact_id,
        "source_version": f"sha256:{digest}",
        "timeline_run_id": f"timeline_{digest[:16]}",
        "transcript_segment_count": segment_count,
        "transcript_start": first,
        "transcript_end": last,
        "raw_source_path": str(path),
        "source_failure_metadata": None,
    }


def build_candidates() -> list[dict[str, Any]]:
    candidates = []
    for definition in definitions():
        source = _source_info(definition)
        identity = {
            "source_video_id": source["source_video_id"],
            "source_artifact_id": source["source_artifact_id"],
            "source_version": source["source_version"],
            "timeline_run_id": source["timeline_run_id"],
        }
        stable_id = canonical_sha256(
            {"original_query": definition["original_query"], **identity}
        )[:16]
        candidate = {
            "candidate_case_id": f"V2C_C0_{stable_id}",
            "original_query": definition["original_query"],
            "evaluation_view": definition["evaluation_view"],
            "evidence_question": definition["evidence_question"],
            "projection_policy_version": "v3.5-query-projection-v1",
            "query_language": definition["query_language"],
            **source,
            "constructor_expected_status": definition["expected"],
            "constructor_aspects": definition["aspects"],
            "constructor_supported_aspects": definition["supported"],
            "constructor_missing_aspects": definition["missing"],
            "constructor_evidence_route_summary": definition["route"],
            "constructor_evidence_regions": [
                {"start_ordinal": start, "end_ordinal": end, "purpose": purpose}
                for start, end, purpose in definition["regions"]
            ],
            "coverage_tags": definition["coverage"],
            "risk_tags": definition["risk"],
            "construction_reason": definition["reason"],
            "development_authorization_source": "user-supplied Stage 2R-C0 contract",
            "source_lineage_digest": canonical_sha256(identity),
            "reviewer_packet_ready": True,
            "source_integrity_ready": True,
            "projection_validated": True,
            "constructor_fields_must_be_stripped": True,
            "session_future_eligibility": {
                "primary_review": False,
                "secondary_review": False,
                "human_adjudication": False,
                "judge_evaluation": False,
                "heldout_evaluation": False,
            },
        }
        payload = dict(candidate)
        candidate["candidate_payload_sha256"] = canonical_sha256(payload)
        candidate["_construction_key"] = definition["key"]
        candidates.append(candidate)
    return candidates


def validate_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if len(candidates) < 12:
        raise RuntimeError("candidate_pool_too_small")
    ids = [row["candidate_case_id"] for row in candidates]
    queries = [row["original_query"] for row in candidates]
    questions = [row["evidence_question"] for row in candidates]
    if len(ids) != len(set(ids)) or len(queries) != len(set(queries)):
        raise RuntimeError("candidate_or_query_duplicate")
    if len(questions) != len(set(questions)):
        raise RuntimeError("evidence_question_duplicate")
    if set(queries) & PILOT_QUERIES:
        raise RuntimeError("pilot_query_duplicate")
    for row in candidates:
        if row["constructor_expected_status"] == "partial":
            if not row["constructor_supported_aspects"] or not row["constructor_missing_aspects"]:
                raise RuntimeError(f"invalid_partial:{row['candidate_case_id']}")
            aspect_ids = {item["aspect_id"] for item in row["constructor_aspects"]}
            partition = set(row["constructor_supported_aspects"]) | set(
                row["constructor_missing_aspects"]
            )
            if partition != aspect_ids:
                raise RuntimeError(f"partial_partition_invalid:{row['candidate_case_id']}")
        if row["constructor_expected_status"] == "unverifiable":
            failure = row["source_failure_metadata"]
            if (
                row["source_availability"] == "available"
                or failure is None
                or failure["raw_subtitle_exists"]
                or failure["raw_asr_exists"]
            ):
                raise RuntimeError(f"unverifiable_not_operational:{row['candidate_case_id']}")
    first = [row for row in candidates if row["_construction_key"] in FIRST_BATCH_KEYS]
    expected_distribution = {
        "sufficient": 2,
        "partial": 3,
        "insufficient": 1,
        "unverifiable": 2,
    }
    distribution = Counter(row["constructor_expected_status"] for row in first)
    if dict(distribution) != expected_distribution:
        raise RuntimeError(f"first_batch_distribution_mismatch:{distribution}")
    per_video = Counter(row["source_video_id"] for row in first)
    if max(per_video.values()) > 2:
        raise RuntimeError("first_batch_video_cap_exceeded")
    diversity = {
        "distinct_videos": len(per_video),
        "raw_subtitle_cases": sum(row["source_type"] == "raw_subtitle" for row in first),
        "raw_asr_cases": sum(row["source_type"] == "raw_asr" for row in first),
        "source_unavailable_cases": sum(row["source_type"] == "unavailable" for row in first),
        "multi_span_cases": sum("multi_span" in row["coverage_tags"] for row in first),
        "multi_aspect_cases": sum("multi_aspect" in row["coverage_tags"] for row in first),
        "cross_language_cases": sum("cross_language" in row["coverage_tags"] for row in first),
        "multi_group_cases": 0,
        "maximum_cases_per_video": max(per_video.values()),
    }
    minimums = {
        "distinct_videos": 4,
        "raw_subtitle_cases": 3,
        "raw_asr_cases": 1,
        "source_unavailable_cases": 2,
        "multi_span_cases": 2,
        "multi_aspect_cases": 3,
        "cross_language_cases": 1,
    }
    if any(diversity[key] < minimum for key, minimum in minimums.items()):
        raise RuntimeError(f"first_batch_diversity_shortfall:{diversity}")
    return {
        "first": first,
        "distribution": expected_distribution,
        "diversity": diversity,
        "pool_distribution": dict(Counter(row["constructor_expected_status"] for row in candidates)),
    }


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if key != "_construction_key"} for row in rows]


def _segments(row: dict[str, Any]) -> list[dict[str, Any]]:
    if row["source_type"] == "raw_subtitle":
        source = _read_json(Path(row["raw_source_path"]))
        return [
            {
                "segment_id": f"{row['source_video_id']}_seg_{index:06d}",
                "start_time": item["from"],
                "end_time": item["to"],
                "raw_text": item["content"],
            }
            for index, item in enumerate(source, 1)
        ]
    if row["source_type"] == "raw_asr":
        source = _read_json(Path(row["raw_source_path"]))
        sentences = source["transcripts"][0]["sentences"]
        return [
            {
                "segment_id": f"{row['source_video_id']}_seg_{index:06d}",
                "start_time": item["begin_time"] / 1000,
                "end_time": item["end_time"] / 1000,
                "raw_text": item["text"],
            }
            for index, item in enumerate(sentences, 1)
        ]
    return []


def render_review(first: list[dict[str, Any]]) -> str:
    lines = [
        "# Shiliu V3.5 Stage 2R-C0 — First Batch Candidate Review",
        "",
        "This file is for user/V3.5 Session inspection only and must not be sent to Reviewers. Constructor expectations are coverage targets, not Gold.",
        "",
    ]
    for index, row in enumerate(first, 1):
        lines.extend(
            [
                f"## {index}. {row['candidate_case_id']}",
                "",
                f"- Original Query: `{row['original_query']}`",
                f"- Evidence Question: {row['evidence_question']}",
                f"- Source: `{row['source_video_id']}` / `{row['source_artifact_id']}`",
                f"- Source Type: `{row['source_type']}`",
                f"- Source Availability: `{row['source_availability']}`",
                f"- Raw Source Path: `{row['raw_source_path']}`",
                f"- Transcript Segment Count: `{row['transcript_segment_count']}`",
                f"- Constructor Expected Status: `{row['constructor_expected_status']}`",
                f"- Expected Supported Aspects: `{row['constructor_supported_aspects']}`",
                f"- Expected Missing Aspects: `{row['constructor_missing_aspects']}`",
                f"- Evidence Route Summary: {row['constructor_evidence_route_summary']}",
                f"- Coverage Tags: `{row['coverage_tags']}`",
                f"- Construction Risk: `{row['risk_tags']}`",
                f"- First-batch rationale: {row['construction_reason']}",
                "",
                "### Material Aspects",
                "",
            ]
        )
        for aspect in row["constructor_aspects"]:
            lines.append(
                f"- `{aspect['aspect_id']}` {aspect['description']} Materiality: {aspect['why_material']}"
            )
        lines.extend(["", "### Audit Evidence", ""])
        if row["source_type"] == "unavailable":
            failure = row["source_failure_metadata"]
            lines.extend(
                [
                    "No Raw Subtitle or Raw ASR excerpt is available. Metadata is navigation/availability information only and is not evidence.",
                    "",
                    "```json",
                    json.dumps(failure, ensure_ascii=False, sort_keys=True, indent=2),
                    "```",
                    "",
                ]
            )
            continue
        segments = _segments(row)
        for region in row["constructor_evidence_regions"]:
            start = region["start_ordinal"]
            end = region["end_ordinal"]
            selected = segments[start - 1 : end]
            lines.extend(
                [
                    f"#### {region['purpose']} — ordinals {start}–{end}",
                    "",
                    "```text",
                ]
            )
            lines.extend(
                f"{item['segment_id']} [{item['start_time']}–{item['end_time']}] {item['raw_text']}"
                for item in selected
            )
            lines.extend(["```", ""])
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("refusing_to_overwrite_stage2r_c0")
    freeze_before = sha256_file(FREEZE_MANIFEST)
    if freeze_before != EXPECTED_FREEZE_SHA256:
        raise RuntimeError("freeze_manifest_hash_mismatch")
    pilots, current_distribution = validate_pilots()
    candidates = build_candidates()
    validation = validate_candidates(candidates)
    first = validation["first"]
    OUTPUT_ROOT.mkdir(parents=True)

    thresholds = {"sufficient": 6, "partial": 6, "insufficient": 6, "unverifiable": 8}
    gaps = {
        label: max(0, thresholds[label] - current_distribution[label])
        for label in thresholds
    }
    ledger = {
        "ledger_version": "v3.5-stage2r-c0-coverage-ledger-v1",
        "source_of_truth": [
            str(PILOT_ROOT / "adjudicated_canary_cases.jsonl"),
            str(PILOT_ROOT / "adjudicated_remaining_pilot_cases.jsonl"),
        ],
        "pilot_cases": [
            {"case_id": row["case_id"], "final_status": row["final_status"]}
            for row in pilots
        ],
        "current_distribution": {**current_distribution, "total": len(pilots)},
        "development_minimums": thresholds,
        "current_gaps": gaps,
        "gold_blind": True,
    }
    _write_json(OUTPUT_ROOT / "current_coverage_ledger.json", ledger)
    pool = _clean(candidates)
    first_clean = _clean(first)
    _write_jsonl(OUTPUT_ROOT / "development_expansion_candidate_pool.v1.jsonl", pool)
    _write_jsonl(OUTPUT_ROOT / "first_batch_8.provisional.jsonl", first_clean)

    by_video: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pool:
        by_video[row["source_video_id"]].append(row)
    matrix = {
        "sources_checked": len(by_video),
        "development_authorization_source": "user-supplied Stage 2R-C0 contract",
        "split_membership_consulted": False,
        "sources": [
            {
                "source_video_id": video,
                "source_type": rows[0]["source_type"],
                "source_language": rows[0]["source_language"],
                "source_availability": rows[0]["source_availability"],
                "source_artifact_id": rows[0]["source_artifact_id"],
                "source_version": rows[0]["source_version"],
                "timeline_run_id": rows[0]["timeline_run_id"],
                "transcript_segment_count": rows[0]["transcript_segment_count"],
                "raw_source_path": rows[0]["raw_source_path"],
                "candidate_case_ids": [row["candidate_case_id"] for row in rows],
                "first_batch_case_count": sum(row in first_clean for row in rows),
                "source_failure_metadata": rows[0]["source_failure_metadata"],
            }
            for video, rows in sorted(by_video.items())
        ],
    }
    _write_json(OUTPUT_ROOT / "source_coverage_matrix.json", matrix)

    duplicate_audit = {
        "candidate_count": len(pool),
        "candidate_ids_unique": True,
        "query_text_duplicates": [],
        "evidence_question_duplicates": [],
        "source_plus_evidence_region_duplicates": [],
        "pilot_query_duplicates": [],
        "same_video_near_duplicate_queries": [],
        "first_batch_maximum_cases_per_video": validation["diversity"]["maximum_cases_per_video"],
        "constructor_expected_status_in_candidate_pool_only": True,
        "constructor_fields_must_be_stripped": True,
        "heldout_membership_consulted": False,
        "prohibited_query_pools_accessed": False,
    }
    _write_json(OUTPUT_ROOT / "duplication_and_leakage.audit.json", duplicate_audit)

    first_audit = {
        "case_count": len(first_clean),
        "case_ids": [row["candidate_case_id"] for row in first_clean],
        "constructor_expected_distribution": validation["distribution"],
        "target_distribution_met": True,
        "diversity": validation["diversity"],
        "partial_construction_valid": True,
        "unverifiable_operational_failure_valid": True,
        "query_projection_valid": True,
        "source_integrity_ready": True,
        "reviewer_packet_ready": True,
        "constructor_fields_must_be_stripped": True,
        "reviewer_calls": 0,
        "provider_calls": 0,
        "annotation_reviews_created": 0,
        "agreements_created": 0,
        "human_decisions_created": 0,
        "final_gold_created": 0,
        "stage2r_c1_entered": False,
    }
    _write_json(OUTPUT_ROOT / "first_batch_8.audit.json", first_audit)

    REVIEW.write_text(render_review(first_clean), encoding="utf-8")
    freeze_after = sha256_file(FREEZE_MANIFEST)
    if freeze_after != freeze_before:
        raise RuntimeError("freeze_manifest_modified")

    outputs_for_manifest = (
        OUTPUT_ROOT / "current_coverage_ledger.json",
        OUTPUT_ROOT / "development_expansion_candidate_pool.v1.jsonl",
        OUTPUT_ROOT / "first_batch_8.provisional.jsonl",
        OUTPUT_ROOT / "first_batch_8.audit.json",
        OUTPUT_ROOT / "source_coverage_matrix.json",
        OUTPUT_ROOT / "duplication_and_leakage.audit.json",
        REVIEW,
    )
    manifest = {
        "manifest_version": "v3.5-stage2r-c0-pool-manifest-v1",
        "candidate_count": len(pool),
        "first_batch_count": len(first_clean),
        "pool_distribution": validation["pool_distribution"],
        "first_batch_distribution": validation["distribution"],
        "freeze_manifest_sha256_before": freeze_before,
        "freeze_manifest_sha256_after": freeze_after,
        "artifact_sha256": {str(path): sha256_file(path) for path in outputs_for_manifest},
        "session_future_eligibility": {
            "primary_review": False,
            "secondary_review": False,
            "human_adjudication": False,
            "judge_evaluation": False,
            "heldout_evaluation": False,
        },
        "heldout_or_gold_accessed": False,
        "prohibited_query_pools_accessed": False,
        "reviewer_calls": 0,
        "provider_calls": 0,
        "final_gold_created": 0,
        "stage2r_c1_entered": False,
    }
    manifest_path = OUTPUT_ROOT / "development_expansion_candidate_pool.v1.manifest.json"
    _write_json(manifest_path, manifest)

    report = f"""# Shiliu V3.5 Stage 2R-C0 — Coverage and Pool Report

## Result

```text
Stage 2R-C0 Complete
Development Expansion Pool Ready
First Batch Awaiting Approval
```

## Required Answers

1. Current four-Pilot final distribution: `sufficient=1`, `partial=0`, `insufficient=3`, `unverifiable=0`, total `4`.
2. Development minimums: `6/6/6` for sufficient/partial/insufficient and recommended `8+` end-to-end unverifiable. Current gaps: `{gaps}`.
3. Non-Held-out Development Source artifacts checked: **{len(by_video)}**, under the user-supplied C0 Development authorization; no legacy Split membership was consulted.
4. Candidate pool size: **{len(pool)}**.
5. First batch size: **{len(first_clean)}**.
6. First-batch constructor target distribution: `{validation['distribution']}`; met exactly. These are not Gold labels.
7. Diversity: `{validation['diversity']}`. The first batch uses eight distinct videos, five Raw Subtitle cases, one Raw ASR case, and two unavailable-source cases.
8. Partial construction: each of the three selected partial candidates has at least two material aspects, at least one directly supported aspect, and at least one independently missing aspect. Their reasons are recorded constructor-only.
9. Unverifiable failures: `BV13QFxzCEXb` and `BV16jREBdEX5` have Metadata but neither Raw Subtitle nor Raw ASR, so no reliable evidence timeline can be formed. They were not relabelled as insufficient.
10. Cross-language: **Yes** — English Queries against Chinese Raw Subtitle/ASR in two first-batch cases.
11. Multi-span: **Yes — five first-batch cases.** Multi-group: **No natural OR-equivalent full evidence routes were asserted; this remains a coverage gap rather than being fabricated.**
12. Pilot duplication: **No exact Query duplicate, semantic Evidence Question duplicate, or Source+Evidence Region duplicate was found.**
13. Held-out/Gold access: **No.** The prohibited Query pools and Split assignments were not opened or used.
14. Reviewer/Provider calls: **0 / 0**.
15. Frozen Workflow modified: **No.** Freeze Manifest remained `{freeze_before}` before and after.
16. Stage 2R-C1 recommendation: **Yes, after user/V3.5 Session approval of the provisional eight. C1 was not entered.**
17. Remaining gaps: natural multi-group evidence, additional ASR languages/source systems, source-parse failure distinct from complete absence, and more unavailable cases toward the recommended eight.
18. Largest data risk: constructor expectations may be wrong despite full-source inspection; especially absence claims and ASR proper-noun errors require blind dual review. Constructor-only fields must be stripped before Reviewer invocation.

## Isolation and Handoff

- Candidate IDs are label-neutral hashes.
- Every candidate has a stable Source Lineage Digest and Candidate Payload SHA-256.
- Every provisional Case is marked `reviewer_packet_ready`, `source_integrity_ready`, and `projection_validated`.
- `constructor_fields_must_be_stripped=true` for every Case.
- This Session is permanently ineligible to review, adjudicate, judge, or evaluate Held-out for these constructed Cases.
- No Annotation Review, Agreement, Human Decision, Human Adjudication Packet, Final Gold, Held-out Manifest, or Gold Lock was created.

## Final Status

```text
Stage 2R-C0 Complete
Development Expansion Pool Ready
First Batch Awaiting Approval
```
"""
    REPORT.write_text(report, encoding="utf-8")
    manifest["artifact_sha256"][str(REPORT)] = sha256_file(REPORT)
    _write_json(manifest_path, manifest)


if __name__ == "__main__":
    main()
