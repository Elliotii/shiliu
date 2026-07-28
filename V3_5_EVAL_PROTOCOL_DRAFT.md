# Shiliu V3.5 Evaluation Protocol Draft

Status: **Draft only — not frozen**  
Version: `v3.5-eval-protocol-draft-v1`  
Human Gold: not created  
Development / Held-out: not created  
Prompt/model use in Stage 2A: none

## 1. Authority and Annotation Boundary

The human annotation authority for a `query_video` case is exactly:

```text
Query + Target Video + Full Authoritative Raw Transcript
```

Search hits, V3 chunks, approved intervals, product windows, keyword positions, AI chapters, titles, summaries, and failure notes are **Navigation Aid Only — Not Annotation Boundary**. Candidate Builder output does not exist and must never restrict Gold annotation.

Full Transcript Accessible ≠ Full Transcript Linearly Read From Start to End. The complete Raw Transcript must remain available as final authority, but reviewers should begin with mechanical navigation, inspect relevant context and alternative locations, and leave the suggested locations whenever needed. Accessibility prevents candidate-pool bias; it does not impose a linear full-transcript reading burden.

A `query_corpus` case contains a Query and no approved target-video evidence. It asks whether the frozen corpus has an obvious approvable target under the frozen library topic and V3 retrieval results. Query-corpus negative controls are curated out-of-domain controls; they are not exhaustive proofs that no possible video in the full corpus contains any related sentence. Human approval means no obvious video should be approved as a target evidence source under those bounded conditions. It does not fabricate a transcript, target, or automatic negative label, and it participates in Sufficiency, false-answer rate, no-search/no-answer behavior, and Reason Code evaluation—not Fine Evidence Span Metrics.

## 2. Draft Version Registry

```text
master_case_schema_version: v3.5-master-case-draft-v1
review_decision_schema_version: v3.5-review-decision-draft-v1
review_packet_version: v3.5-review-packet-v1
eval_protocol_draft_version: v3.5-eval-protocol-draft-v1
reason_code_draft_version: v3.5-reason-code-draft-v1

source_identity_version: v3.5-source-identity-v2
source_version_authority_version: v3.5-source-version-authority-v1
timeline_policy_version: v3.5-timeline-policy-v1
source_chunk_policy_version: v3-frozen-transcript-chunk-policy-v1
replay_implementation_version: v3.5-frozen-chunker-replay-v1
chunk_mapping_version: v3.5-exact-chunk-mapping-v1
search_candidate_contract_version: v3.5-search-candidate-v1
trace_policy_version: v3.5-search-trace-policy-v1
```

These Stage 2 schema/reason versions remain drafts until Stage 2C.

## 3. Unified Master Evaluation Case Set

One Master Case Set should support, when applicable, Candidate coverage, Fine Evidence selection, start-time error, duration/compression, Sufficiency, reason attribution, title-only/missing-source behavior, and negative controls. It is not split into duplicate “Evidence” and “Sufficiency” datasets.

Candidate manifests contain sampling hypotheses only. They explicitly forbid `gold_segment_ids`, `gold_evidence_groups`, `sufficiency_label`, final reason codes, and `split`. `split_constraint=development_only` is a robustness constraint for video 88, not an assigned split.

## 4. Master Case Schema

Required fields include case ID/version/scope; Query/language/type; optional target video/BVID; source state, artifact ID/version/type/language/timeline status; sampling stratum/origin/rationale; navigation aids; split constraint; preliminary leakage keys; unreviewed decision status; and applicable metrics.

Scopes:

- `query_video`: full-transcript Evidence, Sufficiency, anchor, duration, and coverage review.
- `query_corpus`: negative/no-target review; normally excluded from Fine Evidence span metrics.

Source states are `readable_raw`, `title_only`, `subtitle_missing`, and `query_corpus`. A readable source must have a verified 64-hex source version and v2 artifact ID. An unavailable source must not claim source authority.

## 5. Future Human Gold Schema

A completed human record will contain reviewer/version/time, required aspects, Evidence groups, four-state label, supported/missing aspects, conflicts, primary reasons, notes, confidence, second-review flag, and reviewer flags.

### Required Aspects

Each reviewer-defined aspect has `aspect_id`, description, and `is_required`. Stage 2A leaves these blank and provides no automatic aspect decomposition.

### Evidence Group Semantics

```text
Gold Evidence Groups are OR.
Required Spans inside one Group are AND.
```

Any one complete group can satisfy an Evidence Set Hit. If a group needs two complementary spans, both spans must be present. A group must stay within one `timeline_run_id`; a cross-run group is invalid. Each span records exact Stage 1 segment IDs and reconstructed start/end. Human reviewers may create alternative groups that support the same required aspects.

## 6. Four-state Sufficiency Draft

### `sufficient`

At least one Evidence Group covers every required aspect, with no material missing condition or unresolved invalidating conflict. `supported_aspects` covers all required aspects and `missing_aspects` is empty.

### `partial`

Reliable Raw evidence supports at least one material aspect but misses at least one other material aspect. Both `supported_aspects` and `missing_aspects` are non-empty.

### `insufficient`

Reliable Raw Transcript was reviewed, but it cannot form a useful primary answer. This includes terminology-only mention, semantic neighbors, absent key conditions, or content that should lead to safe abstention. It differs from `partial`: partial answers a meaningful part; insufficient does not provide a useful primary answer.

### `unverifiable`

No reliable Raw Evidence authority is available: title-only, subtitle missing, unreadable source, version mismatch, or unresolved language that prevents reliable review. It differs from `insufficient`: insufficient has reliable body text; unverifiable does not.

## 7. Reason Code and Action-family Draft

| Reason code | Layer | Primary action family |
|---|---|---|
| `no_search_candidate` | Retrieval/Search | `retrieval_action` |
| `search_candidate_but_no_supporting_evidence` | Source/Corpus Gold | `safe_abstain` |
| `semantic_neighbor_only` | Source/Corpus Gold | `safe_abstain` |
| `partial_aspect_coverage` | Coverage | `evidence_resolution_action` |
| `missing_key_condition` | Coverage | `evidence_resolution_action` |
| `conflicting_evidence` | Coverage | `evidence_resolution_action` |
| `title_only` | Source | `source_recovery_action` |
| `subtitle_missing` | Source | `source_recovery_action` |
| `source_unreadable` | Source | `source_recovery_action` |
| `source_version_mismatch` | Source | `source_recovery_action` |
| `language_unresolved` | Source | `source_recovery_action` |
| `selector_failed` | Future runtime only | `selector_recovery_action` |

Each reason has at most one primary action family. `selector_failed` is vocabulary for future runtime attribution and normally cannot be original human Source Gold before a Selector exists.

## 8. Compared Systems

Fine Evidence:

```text
E0: V3 Coarse Window Baseline
E1: Deterministic Fine Selector
E2: Structured LLM Fine Selector
```

Sufficiency:

```text
S0: Always Sufficient / Always Answer
S1: Deterministic Pre-gates
S2: Deterministic Pre-gates + Structured LLM Sufficiency Judge
```

No Segment Dense Index, cross-encoder, reranker, or second formal LLM model is in scope.

## 9. Metrics Draft

Candidate metrics: `GoldGroupCoverage@K`, `BestGoldGroupSegmentRecall`, Candidate Compression, character count, and duration.

Selector metrics: `EvidenceSetHit@1`, Segment Precision/Recall/F1, Start-time Error, Duration Ratio, Compression vs V3, Invalid Selection Rate, and Abstain Accuracy.

For multiple spans, merge overlapping time intervals within the same Timeline Run and use the total union duration. A Gold Group spanning multiple runs is invalid.

Sufficiency metrics: Macro-F1, per-class Precision/Recall, confusion matrix, Sufficient Precision, Partial→Sufficient, Insufficient→Sufficient, Unverifiable→Sufficient, false-answer rate on Insufficient+Unverifiable, Primary Reason Exact Match, and Action Family Match.

Every formal report must also include absolute correct/error counts, a per-case failure table, sample size, Wilson intervals for key proportions, and explicit small-sample uncertainty. Readiness targets are reference signals, never mechanical pass lines.

## 10. Development and Held-out Rules Draft

Development may support micro-window parameters, deterministic scoring, parser fixes, generic guardrails, Selector prompts, Sufficiency prompts/policy, and failure analysis after the split is formally frozen.

Held-out forbids prompt/model/threshold/micro-window tuning, case-specific rules, video-specific exceptions, and repeated inspection/retuning.

Draft prompt limits: at most one formally adopted LLM model and approximately three substantive prompt versions per component. Parser-only structured-output fixes may be tracked separately. No LLM is used in Stage 2A.

### Active Human Review Workflow

```text
Round 1: 6-case Label Calibration
Round 2: Remaining necessary Primary Cases
Round 3: Targeted Reserve Activation only when required
```

Stage 2B does not require 26/26 Stage 2A decisions by default. Stage 2C Gold Lock requires every activated final Master Case to be completed, not every Primary plus every Reserve.

Reserve candidates are inactive by default. A Reserve may be activated only when a Primary is unusable, remains ambiguous after calibration, class/source coverage is materially insufficient, leakage invalidates a Primary, or additional unverifiable coverage is required. Activation must record `activation_reason`, `replaced_or_supplemented_case`, `activated_at`, and `authorized_by`.

Review effort is classified as Quick authority confirmation, Seed-assisted evidence verification, Focused semantic review, Deep multi-aspect review, or Robustness review. Packet size does not dictate review depth.

## 11. Formal Run Rules Draft

- One frozen semantic Held-out run.
- No best-of-N, cherry-picking, or Gold-visible rerun.
- A normal valid but poor model response is not rerunnable.
- Infrastructure-only reruns are limited to connection failure before valid response, no usable provider response, runner crash, or corrupted work DB.
- Preserve the first failed Trace, keep system versions unchanged, do not inspect Held-out Gold, and record the rerun reason.

## 12. Preliminary Leakage Rules

Before any split, detect same query family, near rewrite, same video, same/overlapping approved interval, same core Raw range, and same source artifact. These are preliminary keys, not final `leakage_group_id` values.

Q01–V78 and Q15–V78 share the exact interval seed and must remain in one future leakage group candidate. Other same-video/source relationships also require grouped split review. No Development/Held-out assignment exists in Stage 2A.

## 13. Human Review and Lock Preconditions

Stage 2A templates accept only `decision_status=unreviewed` and blank Gold/label fields. A future Gold lock must reject every incomplete record, validate source version and Segment IDs, require run-local groups, validate four-state aspect constraints, resolve duplicate/leakage groups, and record reviewer authority.

The active first-round order is CASE_015, CASE_017, CASE_013, CASE_001, CASE_003, and CASE_012. Remaining necessary Primary cases are considered only after calibration; Reserve review is targeted and authorization-gated. A reviewer should set `needs_second_review=yes` for ambiguous aspect decomposition, conflicts, borderline sufficient/partial or partial/insufficient cases, unresolved language, timeline-run uncertainty, or alternative groups whose equivalence is uncertain.

## 14. English and Cross-language Coverage Boundary

```text
English-source coverage: one readable semantic-neighbor candidate
English-source positive evidence: not established
Cross-language evidence resolution: not evaluated
```

The frozen real case pool contains only one distinct English-source pooled query-video pair, and it is not a cross-language positive case. The protocol therefore makes no claim that English positive coverage or cross-language evaluation is complete.
