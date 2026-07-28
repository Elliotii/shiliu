# Shiliu V3.5 Stage 2R-B2 — Remaining Safe-Pool Pilot Report

Date: 2026-07-23  
Scope: deterministic Canary adjudication intake plus the two remaining candidates from the sole authorized Safe Projection.

## Executive Result

```text
Stage 2R-B2 Complete
Remaining Safe-Pool Pilot Reviewed
Awaiting Human Adjudication
```

The two user-authored Canary decisions were deterministically expanded from the frozen Primary Canonical Reviews, validated, and persisted as `pilot_adjudicated`. No Human Decision was inferred and no model was called during adjudication expansion.

The Safe Projection contained exactly two remaining candidates. Both were processed with the frozen Reviewer workflow. All four Reviewer paths returned a model body on the first Attempt, compiled to Canonical Review v2, and passed Query Grounding. There were no HTTP 400s, Transport Exhaustions, or Draft Repairs. Both new Cases require Human Review.

No Final Gold was created, no third Case or Reviewer was added, and Stage 2R-C was not entered.

## 1. Canary Human Adjudication Intake

The user decision file contains exactly:

- `V2C_B1A00001` — `approve_primary`;
- `V2C_B1A00002` — `approve_primary`.

Under the user’s explicit deterministic-expansion authorization, each `final_*` field was copied exactly from the corresponding frozen Primary Canonical Annotation Review v2. Aspect, Group, and Span IDs and ordering were preserved. Case 2’s two spans retain their complete Segment IDs, Source, Version, Timeline, and timestamps.

Validation passed for:

```text
case_count: 2
case_ids: exact
four-state labels: valid
aspect partitions: valid
group references: valid
span closure: valid
segment IDs: valid
source/version/timeline: valid
canonical time reconstruction: valid
human_action unchanged: true
adjudication_reason unchanged: true
model_calls during expansion: 0
```

Persisted records:

```text
research/v3_5/eval_v2/stage2r_b2/adjudicated_canary_cases.jsonl
research/v3_5/eval_v2/stage2r_b2/canary_adjudication.audit.json
```

Both records use `adjudication_status=pilot_adjudicated`; none uses `final_master_gold`, `heldout_gold`, or `gold_lock_complete`.

## 2. Frozen Workflow and Safe Inventory

Verified immutable inputs:

```text
Freeze Manifest SHA-256:
d64d72ebd283fb86d798b9c026a230569d924cdcf2c77471b5a5e0b2c72df394

Human Bundle SHA-256:
00137397059ab02e0155c4b1af94e239e7f591c830319c3a0ebe6975495de356

Safe Projection SHA-256:
2c2fd3e0d06452201119f22ab3b68dcdfc738f91d19a916e50dbb9fd2051b564
```

The Safe Projection has four candidates. After excluding the two already reviewed candidates, exactly two remained:

| Candidate | Query | B2 Case |
|---|---|---|
| `SAFEQ_4c4b6895fe044589f229` | `RAG` | `V2C_B2P00001` |
| `SAFEQ_ab03f4a17565fae4de35` | `vibe coding` | `V2C_B2P00002` |

No other Query Pool was read or used.

The frozen V3 navigation indexes initially contained zero units. The same frozen lexical and dense index versions were rebuilt from current local sources without changing V3 code, retrieval logic, Raw Sources, or protocol versions. Frozen V3 Search then selected `BV1o87764Ebs` for both remaining queries—lexical navigation for RAG and dense navigation for vibe coding. Search ranking and excerpts were not sent to either Reviewer.

## 3. Query Projection and Packet Integrity

### V2C_B2P00001

```yaml
original_query: RAG
evaluation_view: single_video_topic_evidence
evidence_question: 该视频的完整原字幕是否实质讨论了 RAG？
projection_status: annotatable
```

### V2C_B2P00002

```yaml
original_query: vibe coding
evaluation_view: single_video_topic_evidence
evidence_question: 该视频的完整原字幕是否实质讨论了 vibe coding？
projection_status: annotatable
```

Neither projection adds definitions, tutorials, architecture, advantages, or comparison requirements. No Case was `not_annotatable`.

Both Cases use the complete 374-segment Raw Subtitle for `BV1o87764Ebs`, with boundaries `BV1o87764Ebs_seg_000001` → `BV1o87764Ebs_seg_000374`. The Raw Source and Packet source version both resolve to:

```text
sha256:087e661d7af23a3bf535f65fdec5f66402ccb781bd5db8698dd5c1ee912a1e5b
```

Packet hashes validate, Source identity/timeline checks pass, no Transcript is truncated, and Primary/Secondary Packet bytes are identical for each Case.

## 4. Reviewer Results

### V2C_B2P00001 — RAG

| Path | Attempts | Repairs | Canonical | Grounding | Label |
|---|---:|---:|---|---|---|
| OpenAI Primary | 1 | 0 | valid | valid | `insufficient` |
| DeepSeek Secondary | 1 | 0 | valid | valid | `insufficient` |

Both Reviewers define one RAG-grounded Required Aspect, support none, mark that Aspect missing, and select no Required Span or Evidence Group. Both judge that the full Transcript discusses AI-agent development/testing rather than RAG.

Agreement is `mandatory_human_review`. The labels, empty evidence routes, and span regions agree, while deterministic Aspect identity matching, missing-Aspect mapping, Boundary Notes, and Reason Codes differ.

### V2C_B2P00002 — vibe coding

| Path | Attempts | Repairs | Canonical | Grounding | Label |
|---|---:|---:|---|---|---|
| OpenAI Primary | 1 | 0 | valid | valid | `sufficient` |
| DeepSeek Secondary | 1 | 0 | valid | valid | `insufficient` |

Primary treats the concrete Codex/coding-agent workflow—designing regression tests, implementing code, rerunning tests, feeding results back, and autonomously iterating—as a substantive discussion of vibe coding. It selects segments 296–312 (`665.870s`–`717.500s`) as one Required Span.

Secondary requires an explicit substantive discussion of the `vibe coding` topic/term and finds none, so it selects no evidence.

Agreement is `mandatory_human_review`, with label, supported/missing partition, Evidence Group, evidence region, source metric, Boundary Note, and Reason Code disagreements. This semantic disagreement was retained for the user; it did not trigger resampling or automatic adjudication.

## 5. Transport, Repair, and Attempt Usage

| Case / Role | Attempts | HTTP 400 | Body | Input | Output | Cached | Provider latency | E2E latency |
|---|---:|---:|---|---:|---:|---|---:|---:|
| RAG / Primary | 1 | 0 | yes | 76,104 | 471 | 0 | 8,925ms | 9,610ms |
| RAG / Secondary | 1 | 0 | yes | 52,461 | 1,897 | unavailable | 30,524ms | 30,567ms |
| vibe coding / Primary | 1 | 0 | yes | 76,120 | 1,386 | 0 | 20,961ms | 20,973ms |
| vibe coding / Secondary | 1 | 0 | yes | 52,472 | 1,250 | unavailable | 22,292ms | 22,308ms |

Totals:

```text
Provider Attempts: 4
Model bodies: 4
HTTP 400: 0
Transport Exhaustions: 0
Draft Repairs: 0
Canonical Reviews: 4 / 4 (100%)
Input tokens: 257,157
Output tokens: 5,004
Known cached tokens: 0
Provider latency total: 82,702ms
End-to-end latency total: 83,458ms
Cost: unavailable
```

Every real Attempt is present in:

```text
research/v3_5/eval_v2/stage2r_b2/provider_attempt_usage.jsonl
```

Input/output usage is available for all returned bodies. DeepSeek cached-token usage was unavailable and was not converted to zero, so overall Usage completeness is correctly classified as `lower_bound`.

## 6. New Human Review Packets

- `research/v3_5/eval_v2/stage2r_b2/V2C_B2P00001/human_review_packet.md`
- `research/v3_5/eval_v2/stage2r_b2/V2C_B2P00002/human_review_packet.md`

Each Packet includes Query Projection, Source metadata, complete Transcript reference, both Review results, selected raw regions, Agreement, per-Attempt Usage, Repair count, and a blank Human Decision template. Neither is prefilled or Final Gold.

## 7. Safety and Integrity

- Held-out/Gold assets were not accessed.
- `research/v3_eval/eval_queries.candidate.jsonl` and `research/v3_eval/eval_queries.locked.jsonl` were not accessed.
- Eval v1 and Frozen V3 code/protocol were not modified.
- Frozen Prompt, Projection, Grounding Validator, Draft Schema, Compiler, Canonical Schema, Agreement thresholds, and Human Review rules remain hash-identical to the Freeze Manifest.
- No expected label, Search Ranking, Selection Reason, previous Review, Agreement, Human Decision, Gold, or AI Summary entered a Reviewer Packet.
- Secret scan passed.
- No protocol defect was detected.
- No third Reviewer, third Case, extra Query Pool, Final Gold, or Master Corpus expansion was created.

Integrity audit:

```text
research/v3_5/eval_v2/stage2r_b2/pilot_integrity.audit.json
```

## 8. Tests

Sixty-seven directed tests passed, covering B1-C Freeze Manifest regression, decision expansion/reconstruction, Safe Projection and Held-out guards, Query Projection/Grounding, Draft/Compiler, OpenAI five-Attempt and DeepSeek three-Attempt bounds, byte-identical retry fingerprints, Attempt Usage, unavailable Agreement states, blank Human Packets, no Final Gold, no third Reviewer/Case, and clean-restart/recovery integrity.

The unrestricted Full Regression was not run because broader evaluation tests may access assets explicitly prohibited by this stage. The complete directed B2 and relevant frozen-workflow regression set passed.

## 9. Required Answers

1. Canary Human decisions validly persisted: **Yes; two `pilot_adjudicated` records.**
2. Any Human Decision inferred automatically: **No.**
3. Remaining Safe Projection count: **2.**
4. Candidates processed: **`SAFEQ_4c4b6895fe044589f229` and `SAFEQ_ab03f4a17565fae4de35`.**
5. Query Projections: **RAG and vibe coding single-video topic-evidence questions listed above.**
6. Any `not_annotatable`: **No.**
7. Primary Attempts: **1 per Case.**
8. Secondary Attempts: **1 per Case.**
9. HTTP 400 count: **0.**
10. Transport Exhaustion: **No.**
11. Draft Repair count: **0.**
12. Canonical Review success: **4/4, 100%.**
13. Query Grounding: **valid on all four paths.**
14. Agreement: **mandatory Human Review for both Cases; label agreement on RAG and label disagreement on vibe coding.**
15. Token/Latency/Usage: **257,157 input, 5,004 output, 83,458ms E2E; overall lower bound because DeepSeek cached tokens are unavailable.**
16. New Human Packets: **the two paths listed above.**
17. Held-out/Gold accessed: **No.**
18. Eval v1/Frozen V3 modified: **No code or protocol modification; navigation indexes were rebuilt at their frozen versions.**
19. Recommend expanding a new Safe Candidate Pool now: **No; the authorized pool is complete and these Cases await adjudication.**
20. Ready to enter Stage 2R-C: **Not authorized.**

```yaml
stage2r_c_authorized: false
reason: awaiting human adjudication of remaining Pilot Cases
```

## Final Status

```text
Stage 2R-B2 Complete
Remaining Safe-Pool Pilot Reviewed
Awaiting Human Adjudication
```
