# Shiliu V3.5 Stage 2A — Eval Protocol and Review Packet Report

## 1. Stage Result

**Accepted with Follow-up Candidate**

Stage 2A produced a Gold-independent protocol draft, 20 primary candidates, 6 reserves, 26 review packets, 26 blank decision records, a packet validator, a preliminary leakage review, and passing targeted/full regression tests. The follow-up is a real data limitation: the frozen corpus has only one distinct English-source pooled query-video pair, so an English primary is present but no distinct English-source reserve or second primary can be formed without duplicating it. Only the V3.5 Version Session may accept this candidate and authorize human review.

## 2. Scope Compliance

Work stayed within protocol/schema definition, candidate sampling, packet generation, validation, tests, Current State, and reporting. No human label, Gold span, final reason, or split was inferred. Navigation aids are explicitly labeled `Navigation Aid Only — Not Annotation Boundary`. Candidate Builder, micro-windows, Selector, Sufficiency Judge, LLM use, API/UI changes, retrieval tuning, and formal evaluation were not started.

## 3. Repository Before / After

- Repository and resolved working directory: `/Users/elliot/new-systems/agent-job-prep/Shiliu`.
- Branch before/after: `codex/v3-domain-completion`.
- HEAD before/after: `8287c8d92378b87290274d02605cdc704cb8c470`.
- Staged files before/after: none.
- Before-state record: `/tmp/shiliu_v3_5_stage2a_before/manifest.md`.
- Pre-existing tracked changes preserved: `V3_CURRENT_STATE.md`, four retrieval files, `templates/base.html`, and `web.py`.
- Stage 1 changes preserved: existing reports, `src/shiliu/evidence/**`, Stage 1 tests, and the prior V3.5 Current State.
- Stage 2A intended changes: the files named in section 4.
- Unexpected changes: none detected.

The worktree remains intentionally dirty because accepted earlier V3/Stage 1 work was already uncommitted. No reset, clean, stash, checkout, switch, commit, or deletion was performed.

## 4. Files Created and Modified

Created:

- `V3_5_EVAL_PROTOCOL_DRAFT.md`
- `V3_5_STAGE2A_EVAL_PROTOCOL_AND_REVIEW_PACKET_REPORT.md`
- `src/shiliu/eval_v3_5/__init__.py`
- `src/shiliu/eval_v3_5/models.py`
- `src/shiliu/eval_v3_5/sampling.py`
- `src/shiliu/eval_v3_5/packets.py`
- `tests/test_v3_5_eval_stage2a.py`
- `research/v3_5/README.md`
- `research/v3_5/master_case_candidates.jsonl`
- `research/v3_5/master_case_reserves.jsonl`
- `research/v3_5/review_decisions.template.jsonl`
- `research/v3_5/review_packet_manifest.json`
- `research/v3_5/preliminary_leakage_report.json`
- 26 files under `research/v3_5/review_packets/`.

Modified: `V3_5_CURRENT_STATE.md` only. No frozen Stage 1, V3 Eval, Snapshot, Raw Artifact, retrieval, product, API, or UI file was modified by Stage 2A.

## 5. Stage 1 Contract Verification

The accepted contract versions are retained: source identity v2, source-version authority v1, timeline policy v1, frozen V3 transcript chunk policy v1, frozen-chunker replay v1, exact mapping v1, SearchCandidateSet v1, and trace policy v1.

All frozen file hashes matched intake:

| Frozen input | SHA-256 |
|---|---|
| Stage 1A report | `51d49541c2bbda28b96618b7df6299ea060135be5e25aecdbbd4dd69f471931d` |
| Stage 1B report | `606a86078f61ad7c564a7c673b247e88314cc26630d6a85c176d67b968f7220f` |
| `evidence/contracts.py` | `8417574849f0f36450f455dfc9ba00b6457762d7acee739fc5c271f9569f23b7` |
| `evidence/source.py` | `ba39ada4505b0b6eb65013ad0c70c4f3ee8c66acff1ad6d2919df5e5e5ec3754` |
| `evidence/mapping.py` | `e30a4873eace5d5b8a91ca58536d2345a6bd5fa7cb0f343ad3d8b349cb5e7ff0` |
| `evidence/authority.py` | `54f4c31eec6b55d65915cacbc389bc75490d54debf2f9df28aafbc6974042160` |
| `evidence/audit.py` | `50466a9db6b0f0b0e54e17c1a82c3cd20f8c889817dd32ad6134476e90c5767f` |
| `evidence/search.py` | `6eaf05e757d2e2fbacbf2ffd7978c4fe1df8deefecf0816fb2cb0c53f5c22959` |

## 6. Eval Protocol Draft Summary

`V3_5_EVAL_PROTOCOL_DRAFT.md` is draft version `v3.5-eval-protocol-draft-v1`; it is not frozen. It defines the independent annotation authority as Query + Target Video + Full Authoritative Raw Transcript, a unified Master Case Set, future Gold semantics, four-state Sufficiency, reason/action attribution, compared systems, metrics, tuning limits, one-shot held-out rules, leakage handling, and future lock preconditions.

No Development/Held-out split exists and no prompt/model was used.

## 7. Master Case Schema

Draft version: `v3.5-master-case-draft-v1`. It supports `query_video` and `query_corpus`, source identity/version and timeline state, sampling provenance, navigation aids, split constraints, preliminary leakage keys, unreviewed status, and applicable metrics. Validation fails closed on missing readable-source authority, invalid SHA-256, incompatible scope/source fields, and misuse of `development_only`.

Extra fields are forbidden. Consequently candidate manifests cannot contain Gold segment IDs/groups, Sufficiency labels, supported/missing aspects, final reason codes, or a split. `sampling_stratum` remains a sampling hypothesis only, not Gold.

## 8. Future Gold Schema

Draft decision version: `v3.5-review-decision-draft-v1`. A future completed decision records reviewer authority, required aspects, run-local Gold Evidence Groups, exact Stage 1 Segment IDs, reconstructed time spans, four-state label, supported/missing aspects, conflicts, reasons, notes, confidence, second-review need, and flags.

Evidence Groups are OR alternatives; required spans inside a group are AND. A group crossing Timeline Runs is invalid. Stage 2A templates deliberately contain no aspects or groups.

## 9. Four-state Label Draft

- `sufficient`: one complete Evidence Group supports every required aspect, with no material missing aspect.
- `partial`: reliable Raw evidence supports a meaningful subset and misses another material subset.
- `insufficient`: reliable Raw was reviewed but provides no useful primary answer; safe abstention applies.
- `unverifiable`: reliable Raw authority is unavailable or cannot be reliably reviewed.

The schema distinguishes `partial` from non-useful evidence and `insufficient` from absent authority.

## 10. Reason Code Draft

Draft version: `v3.5-reason-code-draft-v1`. It includes retrieval absence, candidate-without-support, semantic-neighbor-only, partial coverage, missing condition, conflict, title-only, subtitle missing, unreadable/version mismatch, unresolved language, and future runtime selector failure. Each reason maps to at most one primary action family: retrieval, evidence resolution, source recovery, selector recovery, or safe abstention.

## 11. Compared Systems and Metrics

Fine Evidence systems: E0 V3 Coarse Window Baseline, E1 Deterministic Fine Selector, E2 Structured LLM Fine Selector. Sufficiency systems: S0 Always Sufficient/Answer, S1 Deterministic Pre-gates, S2 Pre-gates + Structured LLM Sufficiency Judge.

Draft metrics cover Candidate Gold-group coverage/recall/compression; Selector set hit, Segment P/R/F1, start error, duration ratio, compression, invalid selection, abstain accuracy; and Sufficiency Macro-F1, per-class P/R, confusion, false-sufficient transitions, false-answer rate, reason match, and action-family match. Formal reports must include absolute counts, per-case failures, sample size, Wilson intervals, and small-sample uncertainty.

## 12. Candidate Sampling Method

Cases were sampled only from frozen V3 queries, judgments, Approved Interval seeds, title/no-body evidence, Snapshot source authority, and the accepted video 88 timeline fact. Selection targeted source diversity, exact/semantic/multi-aspect behavior, readable semantic negatives, no-body states, corpus negatives Q14/Q18, and timeline robustness. Existing hits and intervals are navigation aids only. No future system output or LLM was used.

## 13. Primary Candidate Set

| Case | Query | Target | Source/lang | Sampling stratum | Origin | Review rationale / special risk |
|---|---|---:|---|---|---|---|
| CASE_001 | MCP | 78 | AI/zh | likely positive | Approved interval | Full-source evidence-group review; shares exact seed with R001 |
| CASE_002 | MemoryOS | 40 | AI/zh | likely positive | Approved interval | Exact entity; query-family relation with C013 |
| CASE_003 | MCP 与 Function Calling 的区别 | 83 | AI/zh | possible partial | Approved interval | Multi-aspect/distributed support |
| CASE_004 | RAG | 3 | ASR/zh | likely positive | relevant evidence | Short ASR source |
| CASE_005 | 哪些内容讨论了 Agent 评测信号设计？ | 51 | ASR/zh | possible partial | relevant evidence | ASR and semantic coverage |
| CASE_006 | Claude Code | 37 | AI/en | semantic neighbor | pooled candidate | Only distinct English-source case |
| CASE_007 | RAG 项目怎么做工业优化 | 30 | AI/zh | possible partial | Approved interval | Multi-aspect semantic review |
| CASE_008 | Agent 长期记忆为什么越总结越可能有害？ | 58 | AI/zh | possible partial | relevant evidence | Distributed causal support |
| CASE_009 | 如何设计企业智能客服 Agent？ | 136 | AI/zh | possible partial | relevant evidence | Broad multi-aspect question |
| CASE_010 | AI 编程中的测试循环如何提高交付质量？ | 50 | AI/zh | possible partial | relevant evidence | Causal/process support |
| CASE_011 | Pi Agent 插件与配置 | 43 | human/zh | likely positive | relevant evidence | Human subtitle; query-family relation with C016 |
| CASE_012 | MCP | 88 | human/zh | multi-timeline | Stage 1 timeline | Two complete runs; `development_only` |
| CASE_013 | MemoryOS | 38 | AI/zh | semantic neighbor | judged negative | Readable negative distinction |
| CASE_014 | RAG 项目怎么做工业优化 | 135 | AI/zh | semantic neighbor | judged negative | Shares source/video with R005 |
| CASE_015 | Claude Code 记忆机制 | 137 | title-only | title-only | V3 title-only | No fake body; query-family relation with R004 |
| CASE_016 | Pi Agent 插件与配置 | 49 | title-only | title-only | V3 title-only | No fake body |
| CASE_017 | 量子纠错表面码阈值如何计算？ | corpus | none | negative control | Q14 | No fake target/transcript/label |
| CASE_018 | 如何为 Kubernetes Pod 排查 CrashLoopBackOff？ | corpus | none | negative control | Q18 | No fake target/transcript/label |
| CASE_019 | 哪里讲了 SFT 和 LoRA 微调动漫人格？ | 117 | AI/zh | likely positive | Approved interval | Shares source/video with R003 |
| CASE_020 | OpenSpec | 68 | AI/zh | likely positive | relevant evidence | Exact entity review |

No row above is a Gold or Sufficiency decision.

## 14. Reserve Candidate Set

| Case | Query | Target | Source/lang | Stratum | Origin | Special risk |
|---|---|---:|---|---|---|---|
| RESERVE_001 | 哪个视频解释了 CLI 相比 MCP 的优势？ | 78 | AI/zh | likely positive | Approved interval | Exact evidence seed shared with C001 |
| RESERVE_002 | 模型微调 | 125 | title-only | title-only | V3 title-only | No body authority |
| RESERVE_003 | LoRA | 117 | AI/zh | likely positive | Approved interval | Same source/video as C019 |
| RESERVE_004 | Claude Code 记忆机制 | 44 | AI/zh | possible partial | missing-content judgment | Query-family/source-state reconciliation |
| RESERVE_005 | 为什么复杂 Agent 使用 DAG Workflow 而不是 ReAct 循环？ | 135 | AI/zh | likely positive | Approved interval | Same source/video as C014 |
| RESERVE_006 | vibe coding | 34 | AI/zh | likely positive | relevant evidence | Exact-entity reserve |

## 15. Source / Language / Query Distribution

Primary source distribution: AI 12, ASR 2, human 2, title-only 2, query-corpus 2. Primary source-language distribution: zh 15, en 1, unavailable/not applicable 4. Query-language distribution: en 7, mixed 12, zh 1. Query types: exact entity 7, mixed entity 3, semantic question 10.

Primary strata: likely positive 6, possible partial 6, semantic neighbor negative 3, title-only 2, negative control 2, multi-timeline 1. Origins: Approved Interval 5, relevant evidence 7, judged negative 2, pooled candidate 1, title-only 2, negative control 2, Stage 1 multi-timeline 1. Timeline distribution: 15 single-run, 1 multiple-run, 4 without transcript authority.

Reserves add AI 5 and title-only 1. Human, ASR, title/no-body, semantic negatives, Q14, Q18, and video 88 coverage targets are met. The English-source primary target is met; the preferred distinct English reserve/second primary is not achievable from the frozen pooled pairs without duplication.

## 16. Review Packet Format

Each packet contains case/source identity, sampling provenance, review instructions, clearly bounded navigation aids, blank decision guidance, and either the complete authoritative Raw Transcript or an explicit no-body/query-corpus section. Readable transcript lines preserve Segment ID, raw ordinal, start/end, Timeline Run ID, text, and original order.

Manifest summary: 26 packets; 24 `query_video`; 2 `query_corpus`; 21 complete readable transcripts; 5 packets without body authority; 8,626 rendered transcript segments; 2,872,464 total bytes. Largest: CASE_012, 1,748 segments and 564,979 bytes.

## 17. Full Transcript Integrity

The generator and validator compare every readable packet against the source version, full Segment-ID sequence, segment count, first/last ordinal, packet hash, and Timeline Run headings. No transcript is truncated or sorted. Empty/raw ordinals are preserved by the Stage 1 loader and rendered as records.

CASE_012 renders video 88 as two complete Timeline Runs in original order and never creates a cross-run Gold group. Title-only packets contain no fabricated transcript. Query-corpus packets contain neither a fake target nor fake transcript. All 26 packet integrity checks pass.

## 18. Human Decision Template

`review_decisions.template.jsonl` contains 26 records, all `decision_status=unreviewed`, `sufficiency_label=unreviewed`, empty reviewer/time, empty required aspects, empty Gold groups, empty supported/missing aspects, empty reason codes, and unreviewed confidence/second-review status. Schema validation rejects any attempted Stage 2A prefill.

## 19. Preliminary Leakage Review

No formal split was assigned. Preliminary groups include:

- exact overlapping seed/source/video: CASE_001 + RESERVE_001 (`BV1G29EBGE8b:26-28`, video 78);
- same source/video: CASE_019 + RESERVE_003 (video 117), CASE_014 + RESERVE_005 (video 135);
- query families: C015/R004, C019/R003, C001/C012/R001, C002/C013, C011/C016, C007/C014;
- development-only: CASE_012.

These are future grouping constraints, not `leakage_group_id` assignments or split decisions.

## 20. Special Cases and Risks

- CASE_012 requires run-local annotation and must never enter Held-out because its robustness behavior informed Stage 1/2 design.
- CASE_015, CASE_016, and RESERVE_002 have title-only authority; reviewers must not infer body evidence.
- CASE_017/018 require corpus-level no-target review and do not participate in span metrics unless a human later approves a target.
- CASE_006 is the only real English-source pooled pair. Duplicating it would create nominal rather than independent coverage.
- Semantic-neighbor and possible-partial strata remain hypotheses; reviewers may overturn them.

## 21. Tests and Regression

Targeted command exited 0: 8 collected, 8 passed, 0 failed/skipped, approximately 0.7 seconds. It covers schema rejection, blank decisions, OR/AND and four-state semantics, sampling targets, packet categories/completeness, all readable Segment sequences, video 88 runs, leakage keys, and frozen-integrity checks.

Full command exited 0: 551 collected, 551 passed, 0 failed/skipped, 7 warnings, 10.09 seconds. The warnings are one existing Starlette/httpx deprecation and six multiprocessing `fork()` deprecations. Existing 543 tests therefore have no regression; all 8 new tests pass.

## 22. Snapshot / Artifact / Eval Integrity

- Snapshot DB SHA-256 remains `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.
- Snapshot trace rows remain 82 raw and 52 presentation.
- Artifact manifest SHA-256 remains `36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f`; 372 `status=ok` artifacts pass the existing manifest hash/size regression.
- Locked query/Gold hashes remain `21382e…c36ba` and `873b5f…5b300`; amended ledger remains `e93fd0…0257`.
- Gold-lock/amendment audits, Eval JSON/CSV/per-query results, failure report, V3 protocol, and Stage 6B report match the V3.5 intake fingerprints recorded by the supplementary Phase 0 audit.
- Counts remain 24 queries, 452 judgments, and 10 Approved Intervals.

No integrity conflict or drift was detected.

## 23. V3_5_CURRENT_STATE Update

Current State now records Stage 1 as frozen, Stage 2A complete awaiting human review, protocol status as draft/not frozen, 20 primary/6 reserve/26 packet counts, zero completed reviews, no Gold or split, draft versions, leakage risks, the single-English-case limitation, and updated time estimates. Stage 2A used approximately 0.75–1.25 effective hours; cumulative V3.5 estimate is 4.25–6.25 hours.

## 24. Human Review Handoff

Version Session should authorize a human to fill a copy of `research/v3_5/review_decisions.template.jsonl` while reading the corresponding files in `research/v3_5/review_packets/`. Recommended order: C015/C016/R002 and C017/C018; C012; C004/C005/C006; C013/C014; then remaining likely-positive/multi-aspect cases.

For each case, define required aspects independently, then create one or more alternative Gold Evidence Groups. Groups are OR; all required spans within a group are AND; every group must stay in one Timeline Run and cite exact packet Segment IDs. Set `needs_second_review=true` for ambiguous aspect decomposition, conflicts, borderline partial/insufficient decisions, unresolved language, or uncertain alternative-group equivalence. Never use a navigation aid as the annotation boundary.

## 25. Findings Ledger

| Type | Finding | Evidence / impact |
|---|---|---|
| Confirmed Fact | 20 primary, 6 reserve, and 26 blank decisions exist. | JSONL counts and validator pass. |
| Confirmed Fact | 21 packets contain complete Raw Transcripts totaling 8,626 segments. | Packet manifest and source-sequence validation. |
| Confirmed Fact | Video 88 is rendered as two runs and constrained to development only. | CASE_012 manifest/packet/tests. |
| Confirmed Fact | No Gold fields or split are present. | Extra-forbid schemas, blank-template and manifest tests. |
| Confirmed Fact | Frozen Stage 1/Snapshot/Eval integrity checks pass. | Hashes, trace counts, 551-test regression. |
| Inference | The chosen strata provide useful review diversity. | Frozen provenance and distributions; humans may overturn hypotheses. |
| Unknown | Final Gold groups, Sufficiency labels, reason codes, and case usability. | Human review has not started. |
| Blocking Risk | None for Stage 2A handoff. | Required minimum counts and mandatory coverage are met. |
| Recommendation | Keep exact-seed/same-source/query-family cases together during future split review. | Preliminary leakage report. |
| Recommendation | Do not fabricate a second English-source case; record the corpus limitation. | Only Q23–video 37 is a distinct English-source pooled pair. |

## 26. Remaining Risks

Human review may reject candidates, discover ambiguous aspect boundaries, or require reserve substitution. The small case set will produce wide uncertainty intervals. Leakage keys are preliminary and require human consolidation. Title-only and corpus controls cannot yield fine-span Gold without new human-approved source authority. The English-source distribution is structurally thin. None of these authorizes automatic Gold creation or split assignment.

## 27. Stage 2B Inputs

Stage 2B receives the draft protocol, primary/reserve manifests, 26 source-complete packets, blank decision templates, packet manifest/hashes, leakage precheck, validation code/tests, and the human handoff rules above. It must preserve source versions and Segment IDs, complete decisions under human authority, and return ambiguities for second review. Stage 2C—not Stage 2A—may validate completed decisions, finalize leakage groups, create/freeze a split, and lock Gold if authorized.

## 28. Escalation Assessment

No immediate escalation is required. Version Session decision is required to accept Stage 2A and begin human review. The preferred extra English-source reserve is unavailable from frozen real assets; this is reported as a bounded data limitation, not repaired through duplication or fabricated evidence.

## 29. Exact Commands Executed

Principal verification commands (all read-only except the authorized Stage 2A generator writing `research/v3_5/**`):

```bash
cd /Users/elliot/new-systems/agent-job-prep/Shiliu
pwd -P
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git rev-parse HEAD
git diff --name-status
git diff --cached --name-status
git ls-files --others --exclude-standard

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m shiliu.eval_v3_5.packets
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_v3_5_eval_stage2a.py
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest --collect-only -q -p no:cacheprovider

shasum -a 256 V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md src/shiliu/evidence/contracts.py src/shiliu/evidence/source.py src/shiliu/evidence/mapping.py src/shiliu/evidence/authority.py src/shiliu/evidence/audit.py src/shiliu/evidence/search.py
shasum -a 256 research/v3_eval/eval_queries.locked.jsonl research/v3_eval/eval_gold.locked.jsonl research/v3_eval/eval_gold_review.decisions.amended.jsonl research/v3_eval/gold_lock_audit.json research/v3_eval/human_ledger_amendment_audit.json research/v3_eval/eval_results.json research/v3_eval/eval_results.csv research/v3_eval/eval_per_query_results.jsonl research/v3_eval/failure_cases.md research/v3_eval/V3_EVAL_PROTOCOL.md V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md
shasum -a 256 /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db research/v3_eval/artifact_manifest.jsonl
sqlite3 -readonly /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db "select count(*) from retrieval_search_traces; select count(*) from retrieval_search_presentations;"
git status --short --branch
git diff --cached --name-status
git rev-parse HEAD
```

One diagnostic probe used two incorrect read-only names (`artifacts/manifest.json` and `search_raw_traces`), returned “not found/no such table,” and made no change; the authoritative manifest and table names were then resolved and checked as shown above.

## 30. Stop Statement

Shiliu V3.5 Stage 2A execution is complete.

No V3 Retrieval, Stage 1 Contract, V3 Gold, Snapshot, Raw Artifact, or Formal Eval result was intentionally modified.

No V3.5 Gold was created.
No Development / Held-out split was created.
No Candidate Builder, Selector, Sufficiency Judge, Answer Generation, Agent, Memory, Harness, Translation Pipeline, or V4 work was started.

Navigation aids were used only to prepare human review packets and did not constrain the annotation scope.

Additional recommendations were recorded only and were not implemented.
