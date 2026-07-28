# V3.5 Stage 2R-A Schema and Protocol Lock Report

Final status: **Stage 2R-A Complete — Ready for Pilot Review**

Date: 2026-07-22 (Asia/Shanghai)  
Repository: `/Users/elliot/new-systems/agent-job-prep/Shiliu`  
Branch / unchanged HEAD: `codex/v3-domain-completion` / `8287c8d92378b87290274d02605cdc704cb8c470`

## Executive result

Stage 2R-A froze the Master Evaluation Corpus v2 contracts and exercised the complete local-only annotation flow with synthetic data. It did not enter Stage 2R-B, select pilot cases, create formal reviews or Gold, call a reviewer model, call DeepSeek, modify Frozen V3, or open protected held-out content.

The original dirty worktree was recorded in `research/v3_5/eval_v2/stage2r_a/audits/repository_before_snapshot.txt` and preserved. All Stage 2R-A additions carry `v2`, `eval_v2`, or `stage2r_a`. No Eval v1 path appears in the Stage 2R-A change set; no v1 migration or overwrite was performed.

## Required findings

1. **Eval v1 unchanged:** yes. It remains a read-only historical baseline. Stage 2R-A only added the explicit v2 namespace/assets and updated Current State.
2. **Held-out access:** `heldout_accessed: false`; `forbidden_access_attempts: 0`. No Held-out Case, Gold, ledger, packet, span, aspect, group, or label asset was read. Current State and public contracts were the only allowed historical sources.
3. **Master Case v2 frozen:** yes, `v3.5-master-case-v2`, with exactly identity, corpus truth, retrieval, evidence, and sufficiency layers. Answer/Agentic Search Gold are schema-forbidden.
4. **Four states frozen:** yes. `sufficient`, `partial`, `insufficient`, and `unverifiable` have strict machine invariants; partial is semantic support plus semantic absence, not uncertainty.
5. **Semantic/Span Gold separated:** yes. Aspects and evidence spans are separate objects joined by checked IDs.
6. **Group OR / Span AND:** yes. Multiple groups are alternatives; every required span in a selected group is complementary. Optional context never counts as core support.
7. **Full Raw Transcript packet:** yes. Packets contain the complete ordered segment sequence and bind first/last segment declarations. Search results, chunks, summaries, and candidate windows are absent.
8. **Independent prompts:** yes. Primary and blind Secondary prompts use equivalent rules but separate wording and prompt families. Secondary does not reference checking Primary.
9. **Reviewer isolation:** one fresh context/request per case; identical input hash required; no cross-case state, other-review output, Gold, adjudication, system prediction, or label distribution. Secondary request construction takes only packet + Secondary prompt. No invocation function sends a network request.
10. **Deterministic agreement:** yes. Local NFKC/case/punctuation normalization, exact/token aspect comparison, set overlap, segment/time IoU, bidirectional recall, source and reason-code comparison. No LLM is used.
11. **Mandatory adjudication:** label/aspect/group disagreement; partial; multiple spans/groups; ASR error; cross-language; unclear source/version/run; low confidence; boundary/conflict; invalid repair; large region difference; suspected outside knowledge; incomplete transcript review; and extreme label disagreement.
12. **Reproducible spot check:** SHA-256 over seed `stage2r-a-v2` plus opaque case ID; default 20%, validated configurable range 15–25%.
13. **Annotator–Judge loop controls:** distinct prompt families, blind inputs, no predictions in packets, mutual Reviewer/Judge output isolation, immutable frozen Gold except independently discovered error + new Gold version, and final human authority. DeepSeek may later also be evaluated as Semantic Judge. Gold freezing, prompt separation, blind inputs and human adjudication are required to reduce shared-model reviewer risk.
14. **Leakage before split:** schema captures family, video, content lineage/repost, uploader series, terminology/template, region, paraphrase, and positive/negative rewrite keys. Any key crossing splits produces an explicit conflict and rejects the split. Case-random split is forbidden.
15. **Views:** deterministic projections exist for V3 Retrieval, V3.5 Fine Evidence, and V3.5 Sufficiency. The Retrieval view explicitly says diagnostic-only and grants no V3 retuning authority. V4 views do not exist.
16. **Real Codex reviewer calls:** 0.
17. **Real DeepSeek API calls:** 0.
18. **Provider key safety:** configuration was checked only as Boolean (`provider_configured: false` at execution). Requests/traces never contain a key value or Authorization header value; logs use `provider_usage=annotation_secondary_review`; redaction is tested.
19. **Tests:** directed plus isolation-safe core regression: 30 passed; one Starlette/httpx deprecation warning. A broader subset attempt was stopped at collection by a pre-existing `tests.test_pipeline` import failure in `test_duration_policy_patch.py`; no test from that failed collection ran. The clean 30-test run excludes Eval/Gold suites by design to preserve held-out isolation.
20. **Pilot readiness:** yes, for an 8–12 new-case pilot (recommended 10) after human review of this lock.
21. **Pilot blockers:** no Stage 2R-A blocking condition. Operational prerequisites for 2R-B are user authorization, case mining under frozen leakage rules, and available full Raw Source for reviewable cases.
22. **Main-session escalation:** none triggered. The work did not require Frozen V3 changes, source reprocessing, platformization, or premature semantic Judge work.

## Frozen identities and thresholds

| Contract | Version |
|---|---|
| Master Case | `v3.5-master-case-v2` |
| Annotation Packet | `v3.5-annotation-packet-v2` |
| Annotation Review | `v3.5-annotation-review-v2` |
| Annotation Agreement | `v3.5-annotation-agreement-v2` |
| Annotation Protocol | `v3.5-annotation-protocol-v2` |
| Primary Prompt | `v3.5-primary-reviewer-prompt-v2` |
| Secondary Prompt | `v3.5-secondary-reviewer-prompt-v2` |
| Leakage Policy | `v3.5-leakage-policy-v2` |
| Pilot Selection Policy | `v3.5-pilot-selection-policy-v2` |

Aspect token-overlap threshold is 0.80. Required segment IoU and time-region IoU thresholds are each 0.50. A pass additionally requires valid outputs, identical packet hash, exact label, source agreement, aspect agreement, evidence group agreement, evidence-region agreement, and no mandatory trigger.

## Dry run and fixture coverage

The local dry-run request builder was executed twice against the same synthetic full-transcript packet. Outputs were byte-identical and hash-identical; SHA-256: `2b1282b2f258fd3caaeeee0331d7db00a65350a0a9f35d6bcde51f5f1bc13e0d`. Recorded provider calls: 0.

Synthetic fixtures/tests cover single/multi-span sufficient, genuine partial, semantic-neighbor insufficient, unavailable-source unverifiable, group OR, span AND, optional context, same-label aspect/region divergence, invalid segment, cross-run, input mismatch, successful one-repair, invalid-after-repair, mandatory review, deterministic spot check, leakage conflict, secret redaction, and all projections. They contain no real Case or held-out content.

## Model-call, usage, time, and rework accounting

Future per-case call design is two fresh blind calls (Primary Codex-side, Secondary DeepSeek V4 Pro Max), followed by deterministic local agreement and user adjudication when required. Review metadata reserves `input_tokens`, `output_tokens`, `cached_tokens`, `estimated_cost_usd`, latency, timestamps, validation status, and repair count. Aggregate operations must additionally record initial-valid, repair, invalid-after-repair, error categories, and rework reason.

- Codex execution estimate for Stage 2R-A: approximately 0.5–0.75 effective hours.
- Human workload estimate before/during the 10-case pilot: approximately 4–8 hours, dominated by full-transcript reading and mandatory adjudication; actual duration depends on transcript length and disagreement.
- Model/token/cost incurred by annotation: 0 calls / 0 tracked tokens / USD 0.
- Rework reasons in this implementation: dry-run output directory creation was made explicit after the first local CLI attempt; one proposed regression test was excluded after a pre-existing collection import failure. Neither caused provider access or Gold changes.

Time is recorded for planning only and was not used to reduce Gold or protocol requirements. Future corpus stopping criteria remain coverage, saturation, and marginal value.

## Change inventory

- State/report: `V3_5_CURRENT_STATE.md`, this report.
- Locked documents: `V3_5_MASTER_CORPUS_V2_SCHEMA.md`, `V3_5_ANNOTATION_PROTOCOL_V2.md`, `V3_5_EVAL_PROTOCOL_V2.md`.
- Implementation: `src/shiliu/eval_v3_5/eval_v2/` (contracts, hashing, packet generation, validation/repair, agreement, adjudication, leakage, projections, provider/request safety, isolation guard, CLI, asset generator).
- Machine assets/prompts/fixtures/audits/dry run/manifest: `research/v3_5/eval_v2/stage2r_a/`.
- Directed test: `tests/test_v3_5_eval_v2_stage2r_a.py`.

## Remaining risks

The pilot must validate model comprehension of partial and independently worded aspects, full-transcript context limits, adjudication load, and ASR/cross-language behavior. Deterministic text overlap intentionally routes semantic ambiguity to humans and may increase review rate. The single synthetic corpus packet proves flow integrity, not reviewer quality. These are Pilot concerns, not reasons to change Frozen V3 or start Stage 4B.

## Gate

Schema locked; Annotation Protocol locked; Reviewer Prompts locked; Agreement Metrics locked; Human Review Rules locked; Leakage Rules locked; Pilot Selection Policy locked; Projection Contracts locked; dry run passed; directed and isolation-safe tests passed; Eval v1 unchanged; Held-out untouched; real provider calls 0; formal Gold cases 0.

**Stage 2R-A Complete — Ready for Pilot Review. Stop before Stage 2R-B.**
