from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


CASE_IDS = ("V2C_B2P00001", "V2C_B2P00002")
B2_ROOT = Path("research/v3_5/eval_v2/stage2r_b2")
FREEZE_MANIFEST = Path("research/v3_5/eval_v2/stage2r_b1_c/canary_freeze_manifest.json")
BUNDLE = Path("V3_5_STAGE2R_B2_INDEPENDENT_HUMAN_ADJUDICATION_BUNDLE.md")
WEBGPT_PROMPT = Path("V3_5_STAGE2R_B2_WEBGPT_ADJUDICATION_PROMPT.md")
TEMPLATE = Path(
    "research/v3_5/eval_v2/stage2r_b2_inputs/"
    "remaining_pilot_human_decisions.user.template.jsonl"
)
AUDIT_ROOT = Path("research/v3_5/eval_v2/stage2r_b2_h")
REPORT = Path("V3_5_STAGE2R_B2_H_ADJUDICATION_PACKAGE_REPORT.md")


def build_package() -> dict[str, object]:
    freeze = _read(FREEZE_MANIFEST)
    case_assets = {case_id: _load_case(case_id) for case_id in CASE_IDS}
    protected = tuple(
        path
        for case_id in CASE_IDS
        for path in (
            B2_ROOT / case_id / "primary/canonical_review.json",
            B2_ROOT / case_id / "secondary/canonical_review.json",
            B2_ROOT / case_id / "agreement.json",
            B2_ROOT / case_id / "human_review_packet.md",
        )
    )
    before = {path.as_posix(): sha256_file(path) for path in protected}
    _validate_shared_transcript(case_assets)

    BUNDLE.write_text(render_bundle(case_assets, freeze), encoding="utf-8")
    WEBGPT_PROMPT.write_text(render_webgpt_prompt(), encoding="utf-8")
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE.write_text(
        '{"case_id":"V2C_B2P00001","human_action":"","adjudication_reason":""}\n'
        '{"case_id":"V2C_B2P00002","human_action":"","adjudication_reason":""}\n',
        encoding="utf-8",
    )
    after = {path.as_posix(): sha256_file(path) for path in protected}
    if before != after:
        raise RuntimeError("source review or agreement changed during packaging")

    bundle_text = BUNDLE.read_text(encoding="utf-8")
    prompt_text = WEBGPT_PROMPT.read_text(encoding="utf-8")
    template_rows = [
        json.loads(line) for line in TEMPLATE.read_text(encoding="utf-8").splitlines()
    ]
    transcript = case_assets[CASE_IDS[0]]["packet"]["full_raw_transcript"]
    if bundle_text.count('"segment_id":') != 374:
        raise RuntimeError("bundle transcript segment count mismatch")
    if [row["case_id"] for row in template_rows] != list(CASE_IDS):
        raise RuntimeError("template case inventory mismatch")
    if any(row["human_action"] or row["adjudication_reason"] for row in template_rows):
        raise RuntimeError("template human decision was prefilled")
    secret_terms = re.findall(
        r"(?i)(?:api[_-]?key\s*[:=]|authorization\s*[:=]|bearer\s+[A-Za-z0-9._-]+)",
        bundle_text + prompt_text + TEMPLATE.read_text(encoding="utf-8"),
    )
    if secret_terms:
        raise RuntimeError("secret-like material in package")

    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    audit = {
        "case_count": 2,
        "case_ids": list(CASE_IDS),
        "primary_review_source_sha256": {
            case_id: sha256_file(B2_ROOT / case_id / "primary/canonical_review.json")
            for case_id in CASE_IDS
        },
        "secondary_review_source_sha256": {
            case_id: sha256_file(B2_ROOT / case_id / "secondary/canonical_review.json")
            for case_id in CASE_IDS
        },
        "agreement_source_sha256": {
            case_id: sha256_file(B2_ROOT / case_id / "agreement.json")
            for case_id in CASE_IDS
        },
        "protected_sha256_before": before,
        "protected_sha256_after": after,
        "source_assets_unchanged": before == after,
        "full_transcript_segment_count": len(transcript),
        "first_segment_id": transcript[0]["segment_id"],
        "last_segment_id": transcript[-1]["segment_id"],
        "no_transcript_truncation": len(transcript) == 374,
        "bundle_transcript_objects": bundle_text.count('"segment_id":'),
        "human_decision_prefilled": False,
        "heldout_or_gold_read": False,
        "previous_human_decision_read": False,
        "project_metrics_read": False,
        "model_calls": 0,
        "reviewer_calls": 0,
        "agreement_rerun": False,
        "final_gold_created": False,
        "stage2r_c_entered": False,
        "secret_scan_passed": not secret_terms,
        "bundle_path": BUNDLE.as_posix(),
        "bundle_sha256": sha256_file(BUNDLE),
        "webgpt_prompt_path": WEBGPT_PROMPT.as_posix(),
        "webgpt_prompt_sha256": sha256_file(WEBGPT_PROMPT),
        "template_path": TEMPLATE.as_posix(),
        "template_sha256": sha256_file(TEMPLATE),
    }
    _write_json(AUDIT_ROOT / "package_integrity.audit.json", audit)
    REPORT.write_text(render_report(audit), encoding="utf-8")
    return audit


def render_bundle(cases: dict[str, dict[str, object]], freeze: dict[str, object]) -> str:
    lines = [
        "# Shiliu V3.5 Stage 2R-B2 — Independent Human Adjudication Bundle",
        "",
        "用途：  ",
        "本文件仅用于对两个 V3.5 Evidence Sufficiency Case 进行人工裁决。",
        "",
        "裁决者：  ",
        "用户是最终决策者；WebGPT 仅作为独立裁决辅助者。",
        "",
        "禁止：  ",
        "不得根据标签配额、项目进度或 Reviewer 多数票裁决。",
        "",
        "本文件自包含全部裁决规则、两侧冻结 Review、Mechanical Agreement，以及唯一证据权威——完整共享 Raw Transcript。无需仓库、外部路径、其他报告或历史对话。",
        "",
        "## Frozen Adjudication Rules",
        "",
        "- `sufficient`：完整 Raw Transcript 足以支持 Evidence Question 的全部必要方面。",
        "- `partial`：至少一个重要方面被支持，但至少一个重要方面仍缺失。",
        "- `insufficient`：Source 可读，但没有足够证据支持信息需求。",
        "- `unverifiable`：Source 不可用、不可解析或无法可靠验证。",
        "",
        "Raw Subtitle / Raw ASR 是唯一证据和时间权威。Title、Description、AI Summary、Search Result 不得作为 Gold Evidence。Evidence Groups 之间是 OR；同一 Evidence Group 内 Required Spans 是 AND。",
        "",
        "Mechanical Agreement 只负责发现差异，不代表语义多数票或自动 Gold。",
        "",
        "### Frozen Versions",
        "",
        f"- Query Projection: `{freeze['query_projection_version']}`",
        f"- Canonical Review: `{freeze['canonical_review_schema_version']}`",
        f"- Agreement: `{freeze['agreement_version']}`",
        "",
    ]
    for case_id in CASE_IDS:
        lines.extend(_render_case(cases[case_id]))
    lines.extend(_render_transcript_appendix(cases[CASE_IDS[0]]["packet"]))
    return "\n".join(lines) + "\n"


def _render_case(asset: dict[str, object]) -> list[str]:
    packet = asset["packet"]
    source = packet["source_metadata"]
    transcript = packet["full_raw_transcript"]
    case_id = packet["case_id"]
    lines = [
        f"## Case — {case_id}",
        "",
        "### 1. Case Identity",
        "",
        f"- `case_id`: `{case_id}`",
        f"- `original_query`: {packet['original_query']}",
        f"- `evaluation_view`: `{packet['evaluation_view']}`",
        f"- `evidence_question`: {packet['evidence_question']}",
        f"- `projection_policy_version`: `{packet['projection_policy_version']}`",
        f"- `source_video`: `{source['video_id']}`",
        f"- `source_type`: `{source['source_type']}`",
        f"- `source_language`: `{source['source_language']}`",
        f"- `source_version`: `{source['source_version']}`",
        f"- `timeline_run`: `{source['timeline_run_id']}`",
        f"- `transcript_segment_count`: `{len(transcript)}`",
        f"- `transcript_start`: `{transcript[0]['start_time']:.3f}s`",
        f"- `transcript_end`: `{transcript[-1]['end_time']:.3f}s`",
        f"- `packet_sha256`: `{asset['review_run']['packet_sha256']}`",
        "- Complete evidence authority: see **Appendix A — Complete Shared Raw Transcript**.",
        "",
    ]
    lines.extend(_render_review("2. Primary Review", asset["primary"], packet))
    lines.extend(_render_review("3. Secondary Review", asset["secondary"], packet))
    lines.extend(_render_agreement(asset["agreement"]))
    lines.extend(_render_questions(case_id))
    lines.extend(_render_decision_block(case_id))
    return lines


def _render_review(heading: str, review: dict[str, object], packet: dict[str, object]) -> list[str]:
    body = review["review"]
    by_id = {item["segment_id"]: item for item in packet["full_raw_transcript"]}
    lines = [
        f"### {heading}",
        "",
        f"- `status`: `{body['status']}`",
        "- `required_aspects`:",
        "```json",
        json.dumps(body["required_aspects"], ensure_ascii=False, separators=(",", ":")),
        "```",
        f"- `supported_aspects`: `{json.dumps(body['supported_aspects'], ensure_ascii=False)}`",
        f"- `missing_aspects`: `{json.dumps(body['missing_aspects'], ensure_ascii=False)}`",
        "- `evidence_groups`:",
        "```json",
        json.dumps(body["acceptable_evidence_groups"], ensure_ascii=False, separators=(",", ":")),
        "```",
        "- `optional_context`:",
        "```json",
        json.dumps(body.get("optional_context_spans", []), ensure_ascii=False, separators=(",", ":")),
        "```",
        f"- `reason_codes`: `{json.dumps(body['reason_codes'], ensure_ascii=False)}`",
        f"- `confidence`: `{body['confidence']}`",
        f"- `boundary_notes`: {body['boundary_notes'] or '(empty)' }",
        "- `required_spans`:",
        "",
    ]
    if not body["required_spans"]:
        lines.append("  - None.")
    for span in body["required_spans"]:
        raw_text = "".join(by_id[segment_id]["text"] for segment_id in span["segment_ids"])
        source_identity = {
            key: span[key]
            for key in (
                "video_id", "source_artifact_id", "source_version", "timeline_run_id",
                "source_language", "source_type",
            )
        }
        lines.extend(
            [
                f"  - `span_id`: `{span['span_id']}`",
                f"    - `segment_ids`: `{json.dumps(span['segment_ids'], ensure_ascii=False)}`",
                f"    - `start_time`: `{span['start_time']:.3f}s`",
                f"    - `end_time`: `{span['end_time']:.3f}s`",
                f"    - `raw_text`: {raw_text}",
                f"    - `supported_aspects`: `{json.dumps(span['required_aspect_ids'], ensure_ascii=False)}`",
                f"    - `source_identity`: `{json.dumps(source_identity, ensure_ascii=False, separators=(',', ':'))}`",
            ]
        )
    return lines + [""]


def _render_agreement(agreement: dict[str, object]) -> list[str]:
    return [
        "### 4. Mechanical Agreement",
        "",
        "Mechanical Agreement 只负责发现差异，不代表语义多数票或自动 Gold。",
        "",
        f"- `label_agreement`: `{agreement['label_exact_agreement']}`",
        f"- `required_aspect_agreement`: `{json.dumps(agreement['required_aspect_agreement'], ensure_ascii=False)}`",
        f"- `supported_aspect_agreement`: `{json.dumps(agreement['supported_aspect_agreement'], ensure_ascii=False)}`",
        f"- `missing_aspect_agreement`: `{json.dumps(agreement['missing_aspect_agreement'], ensure_ascii=False)}`",
        f"- `evidence_group_agreement`: `{json.dumps(agreement['evidence_group_agreement'], ensure_ascii=False)}`",
        f"- `required_span_iou`: `{json.dumps(agreement['required_span_overlap'], ensure_ascii=False)}`",
        f"- `time_region_agreement`: `{json.dumps(agreement['time_region_overlap'], ensure_ascii=False)}`",
        f"- `source_agreement`: `{agreement['source_agreement']}`",
        f"- `reason_code_agreement`: `{json.dumps(agreement['reason_code_agreement'], ensure_ascii=False)}`",
        f"- `mandatory_human_review_triggers`: `{json.dumps(agreement['mandatory_triggers'], ensure_ascii=False)}`",
        "",
    ]


def _render_questions(case_id: str) -> list[str]:
    if case_id == "V2C_B2P00001":
        questions = (
            "完整字幕是否实质讨论了 RAG？",
            "是否批准 `insufficient`？",
            "Required Aspect 应采用 Primary 还是 Secondary 的表达？",
            "是否需要保留 Boundary Note？",
            "Reason Code 应采用哪一版？",
            "最终应批准 Primary、批准 Secondary、合并修改，还是拒绝双方？",
        )
    else:
        questions = (
            "字幕是否实质讨论了 `vibe coding`？",
            "描述 Coding Agent Workflow 是否足以等价为讨论 `vibe coding`？",
            "是否必须明确提及术语或概念边界？",
            "Primary 选择的 296–312 段是否构成直接支持？",
            "应判 `sufficient`、`partial` 还是 `insufficient`？",
            "最终应批准 Primary、批准 Secondary、合并修改，还是拒绝双方？",
        )
    return ["### 5. Questions for the Human Adjudicator", ""] + [
        f"{index}. {question}" for index, question in enumerate(questions, start=1)
    ] + [""]


def _render_decision_block(case_id: str) -> list[str]:
    return [
        "### 6. Simplified Decision Block",
        "",
        "Allowed `human_action`: `approve_primary`, `approve_secondary`, `merge_and_revise`, or `reject_both`.",
        "For `merge_and_revise`, add `base_review` (`primary` or `secondary`) and a finite `changes` object. Do not copy a complete Canonical Review. For `reject_both`, provide the reason and do not create Gold.",
        "",
        "```json",
        json.dumps(
            {"case_id": case_id, "human_action": "", "adjudication_reason": ""},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "```",
        "",
    ]


def _render_transcript_appendix(packet: dict[str, object]) -> list[str]:
    lines = [
        "## Appendix A — Complete Shared Raw Transcript",
        "",
        "The two Cases use the same complete 374-Segment Raw Subtitle. The following JSONL preserves every Segment in original order without summarization, deletion, merging, or text correction.",
        "",
        "```jsonl",
    ]
    for segment in packet["full_raw_transcript"]:
        lines.append(
            json.dumps(
                {
                    "segment_id": segment["segment_id"],
                    "start_time": segment["start_time"],
                    "end_time": segment["end_time"],
                    "raw_text": segment["text"],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    return lines + ["```", ""]


def render_webgpt_prompt() -> str:
    return """# Independent WebGPT Adjudication Prompt

你是两个 V3.5 Evidence Sufficiency Case 的独立裁决辅助者。WebGPT 是独立裁决辅助者，用户仍是最终人工决策者。

你只可以依据用户上传的 `V3_5_STAGE2R_B2_INDEPENDENT_HUMAN_ADJUDICATION_BUNDLE.md`：

1. 独立阅读两个 Case 及 Appendix A 的完整 Raw Transcript；
2. 不使用外部知识替代字幕证据；
3. 不根据两个 Reviewer 的多数票裁决，也不默认任何 Reviewer 更可信；
4. 不考虑项目标签配额、阶段进度、系统表现或预期 Label；
5. 对每条 Case 判断 Evidence Question 是否被完整 Raw Transcript 支持；
6. 在 `adjudication_reason` 中简洁包含：你的判断、直接字幕依据、对另一侧观点的反驳，以及最终 `human_action` 建议；
7. 最终响应只能输出两行简化 JSONL，顺序为 `V2C_B2P00001`、`V2C_B2P00002`；
8. 不生成完整 Canonical Gold，不复制完整 Review；
9. 不修改或发明 Segment ID、Source、Version、Timeline 或时间；
10. 无法可靠裁决时使用 `reject_both`，不得猜测。

允许的输出：

- `approve_primary`：只需 `case_id`、`human_action`、非空 `adjudication_reason`；
- `approve_secondary`：同上；
- `merge_and_revise`：还必须包含 `base_review` 和有限 `changes` Patch；
- `reject_both`：说明拒绝理由，不形成 Gold。

`changes` 只可记录有限 Patch，例如 `final_status`、`replace_required_aspect_text`、`remove_required_spans`、`add_reason_codes`、`remove_reason_codes`、`replace_boundary_notes`。不要手工填写完整 Segment、Evidence Group、Source 或 Canonical 对象。

最终格式（仅两行，无 Markdown fence、无额外文字）：

{"case_id":"V2C_B2P00001","human_action":"","adjudication_reason":""}
{"case_id":"V2C_B2P00002","human_action":"","adjudication_reason":""}
"""


def render_report(audit: dict[str, object]) -> str:
    return f"""# Shiliu V3.5 Stage 2R-B2-H — Adjudication Package Report

## Result

```text
Stage 2R-B2-H Complete
Independent Adjudication Package Ready
Awaiting External Human-Assisted Adjudication
```

## Required Answers

1. Only the two specified Cases included: **Yes — `V2C_B2P00001` and `V2C_B2P00002`.**
2. Complete shared transcript included: **Yes — 374/374 segments, once in Appendix A, from `{audit['first_segment_id']}` through `{audit['last_segment_id']}`.**
3. Any Review or Agreement modified: **No; before/after SHA-256 maps are identical.**
4. Any Human Decision prefilled: **No.**
5. Held-out/Gold read: **No.**
6. Model called: **No; model calls and Reviewer calls are both 0. Agreement was not rerun.**
7. Bundle: `{audit['bundle_path']}`  
   SHA-256: `{audit['bundle_sha256']}`
8. WebGPT Prompt: `{audit['webgpt_prompt_path']}`  
   SHA-256: `{audit['webgpt_prompt_sha256']}`
9. Template JSONL: `{audit['template_path']}`  
   SHA-256: `{audit['template_sha256']}`
10. Ready for an independent WebGPT Session: **Yes; the Bundle is self-contained.**
11. Final Gold formed: **No.**
12. Stage 2R-C entered: **No.**

## Integrity

- Case count and IDs are exact.
- Primary Reviews, Secondary Reviews, Agreements, and source Human Packets are hash-identical before/after packaging.
- Full shared transcript count is 374; first/last Segment IDs are correct; no truncation occurred.
- No expected Label, previous Human Decision, project metrics, secret, or external Case was introduced.
- Decision template contains exactly two blank records.

## Final Status

```text
Stage 2R-B2-H Complete
Independent Adjudication Package Ready
Awaiting External Human-Assisted Adjudication
```
"""


def _load_case(case_id: str) -> dict[str, object]:
    root = B2_ROOT / case_id
    return {
        "packet": _read(root / "primary/reviewer_packet.json"),
        "secondary_packet": _read(root / "secondary/reviewer_packet.json"),
        "primary": _read(root / "primary/canonical_review.json"),
        "secondary": _read(root / "secondary/canonical_review.json"),
        "agreement": _read(root / "agreement.json"),
        "review_run": _read(root / "review_run.json"),
    }


def _validate_shared_transcript(cases: dict[str, dict[str, object]]) -> None:
    first = cases[CASE_IDS[0]]["packet"]
    second = cases[CASE_IDS[1]]["packet"]
    if first["full_raw_transcript"] != second["full_raw_transcript"]:
        raise RuntimeError("case transcripts are not identical")
    if len(first["full_raw_transcript"]) != 374:
        raise RuntimeError("shared transcript is not 374 segments")
    if first["full_raw_transcript"][0]["segment_id"] != "BV1o87764Ebs_seg_000001":
        raise RuntimeError("first segment mismatch")
    if first["full_raw_transcript"][-1]["segment_id"] != "BV1o87764Ebs_seg_000374":
        raise RuntimeError("last segment mismatch")
    for case_id in CASE_IDS:
        asset = cases[case_id]
        if asset["packet"] != asset["secondary_packet"]:
            raise RuntimeError(f"provider packet mismatch:{case_id}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    print(json.dumps(build_package(), ensure_ascii=False, indent=2))
