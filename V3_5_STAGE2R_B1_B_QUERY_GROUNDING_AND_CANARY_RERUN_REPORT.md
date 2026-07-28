# Shiliu V3.5 Stage 2R-B1-B — Query Grounding and Canary Re-run Report

Date: 2026-07-23  
Scope: OpenAI transport diagnosis plus exactly `V2C_B1A00001` and `V2C_B1A00002`.

## Executive Result

```text
Stage 2R-B1-B Canary Passed
Ready for Human Review and Remaining Pilot Decision
```

All four Reviewer paths produced Canonical Annotation Review v2 records. All four final Query Grounding validations are `valid`; Primary and Secondary received byte-identical Case Packet bytes for each Case; both complete Raw Transcripts were retained; and deterministic Draft compilation succeeded.

OpenAI transport is **high risk and is not Transport Stable**. The non-formal fixed Fixture failed all three byte-identical attempts with `unknown_http_400`. Both formal Primary paths nevertheless eventually returned model bodies. No HTTP 400 was preclassified as transient.

No Final Gold was created. No third Case or remaining Pilot Case was reviewed.

## Query Projection

Projection policy is frozen as `v3.5-query-projection-v1`.

### Case 1

```yaml
original_query: MCP
evaluation_view: single_video_topic_evidence
evidence_question: 该视频的完整原字幕是否实质讨论了 MCP？
projection_policy_version: v3.5-query-projection-v1
projection_status: annotatable
```

The projection only states the single-video evidence-sufficiency view. It does not add requests for what MCP is, how it works, or its advantages.

### Case 2

```yaml
original_query: 哪个视频解释了 CLI 相比 MCP 的优势？
evaluation_view: single_video_claim_evidence
evidence_question: 该视频的完整原字幕是否实质解释了 CLI 相比 MCP 的优势？
projection_policy_version: v3.5-query-projection-v1
projection_status: annotatable
```

The projection changes the collection-level retrieval phrasing into the conservative question appropriate for one supplied video. It preserves `CLI`, `MCP`, the comparison relation, and the requested advantage claim; it does not ask the Reviewer to choose the best video in the collection.

Neither projection changes the original Query’s substantive information need.

## Query-Grounded Reviewer Contract

The Reviewer Prompt now states that Required Aspects come only from `evidence_question`, that Transcript topics cannot redefine the Query, and that a Reviewer judges only the supplied video. Draft Aspect schema version `v3.5-reviewer-draft-v2` adds mandatory `query_anchor_texts` while leaving local deterministic A/S/G ID generation unchanged.

The local validator checks:

- every Anchor is an exact substring of `evidence_question`;
- every Aspect has at least one Anchor and remains bound to its core entity/relation;
- a comparison retains its query entities and relation;
- Required Spans have an explicit lexical or conservative query-term association with the mapped Aspect;
- absent core query entities cannot be replaced by unrelated Transcript topics and marked supported.

The validator never changes a label. Its states are `valid`, `query_grounding_warning`, and `query_grounding_invalid`. A warning requires Human Review; an invalid Draft may consume the single Draft Repair.

## Packet and Transcript Integrity

| Case | Packet payload SHA-256 | Segments | Raw Source SHA-256 | Packet hash | P/S bytes |
|---|---|---:|---|---|---|
| `V2C_B1A00001` | `26a2356b70bab12aea5573b3ae3f865cd023b98868a1e58c606ef47a85460fb2` | 106 / 106 | `f8e66789b120495738e2d0c9223107ffea348b70f0882a6f5f2c4ae27600361a` | valid | equal |
| `V2C_B1A00002` | `8ae0123eef74c1f85b395914fa1db122e9962d2fffa1e83061bea7850f6c59e1` | 374 / 374 | `087e661d7af23a3bf535f65fdec5f66402ccb781bd5db8698dd5c1ee912a1e5b` | valid | equal |

Boundaries are `BV1zDTX6eEGu_seg_000001` → `BV1zDTX6eEGu_seg_000106` and `BV1o87764Ebs_seg_000001` → `BV1o87764Ebs_seg_000374`. Source segment counts, source digests, and packet source versions match; neither Transcript was truncated.

## Case 1 Result

Both Reviewers created exactly one query-derived Aspect, anchored to the exact substring `MCP`:

- Primary: `视频完整原字幕是否实质讨论MCP。`
- Secondary: `该视频的完整原字幕实质性讨论 MCP`

Neither Reviewer created an Aspect from unrelated Transcript topics. Both returned:

```text
status: insufficient
supported aspects: none
missing aspects: MCP discussion
required spans: none
evidence groups: none
confidence: high
```

Reason: the complete readable Raw Transcript contains no substantive discussion of MCP. Unrelated content is not evidence for the projected question. This satisfies the Case 1 minimum semantic requirement.

The mechanical agreement is `mandatory_human_review`: labels, supported state, empty evidence route, span state, and source agree, while deterministic wording overlap, missing-Aspect identity mapping, boundary notes, and Reason Codes differ.

## Case 2 Dual Review

Both Reviewers returned `sufficient`, high confidence, with one Required Aspect grounded in the CLI-versus-MCP advantage relation.

Primary anchors: `CLI`, `相比`, `MCP`, `优势`. It used two complementary Required Spans:

- `S1`, segments 154–159: the backend is separated and independently controlled through command-line form;
- `S2`, segments 161–168: MCP is less direct and slower for authorization, corner cases, and efficiency.

The single Evidence Group requires both spans (AND). Primary Reason Codes are `COMPARATIVE_EXPLANATION_SUPPORTED` and `CLI_ADVANTAGE_OVER_MCP_SUPPORTED`.

Secondary anchors the exact phrase `CLI 相比 MCP 的优势`. It used one wider Required Span covering segments 149, 150, 154–156, and 163–168. It emitted no Reason Code.

The mechanical result is `mandatory_human_review`. Label and time-region overlap agree; required span IoU is `0.5625`, with Primary recall `0.642857` and Secondary recall `0.818182`. Aspect wording, supported-Aspect deterministic mapping, Evidence Group shape, number/width of spans, boundary notes, and Reason Codes remain Human Review items. These permitted Case 2 differences do not block the Canary.

## Query Grounding Validation and Repair

Final results:

| Case | Primary | Secondary | Draft Repair |
|---|---|---|---:|
| `V2C_B1A00001` | `valid` | `valid` | 0 |
| `V2C_B1A00002` | `valid` | `valid` | 1 Secondary |

The validator did trigger during Case 2 Secondary processing. Its initial strict byte-level Aspect/Anchor binding rejected spacing differences between `CLI 相比 MCP 的优势` and `CLI相比MCP的优势`, causing the one permitted Repair. The Repair preserved the same semantics. The local rule was then corrected: Anchors must still be exact Evidence Question substrings, while Aspect binding may ignore spacing only when all significant query entities and relation terms remain present. The persisted Repair Draft was recompiled locally without another provider call.

Primary Case 2 initially produced a conservative lexical warning for the architecture span. Revalidation recognizes the explicit `CLI` ↔ `命令行` association. The final result is `valid`; no label, Aspect, span, or provider output changed. The audit records both corrections and confirms `provider_resampled=false`.

## OpenAI HTTP 400 Diagnosis

Before the formal Canary, the current OpenAI-compatible provider was tested with a fixed non-formal Fixture, `gpt-5.6-terra`, high reasoning effort, one prompt, one schema, one Packet byte sequence, and one provider configuration.

```text
attempts: 3 / 3
HTTP statuses: 400, 400, 400
safe provider error code: bad_response_status_code
classification: unknown_http_400 for all attempts
request IDs: unavailable
non-sensitive response headers: unavailable
payload fingerprint: 4b7e9700d04be14a7949e2c7cb5b2d4f335f17743e3e0ee740bf6c0b4bace8a1
fingerprint consistent: true
attempt latencies: 3297ms, 1828ms, 1545ms
model body returned: false, false, false
```

The safe evidence does not distinguish invalid parameter, model unavailability, gateway rejection, or capacity/rate. The correct classification is therefore `unknown_http_400`. API Key, Authorization, Base URL, request Transcript content, and raw error bodies were not persisted.

## Provider Reliability, Usage, Latency, and Cost

### Formal OpenAI Primary

| Case | Attempts | 400 failures | Selected attempt | Input tokens | Output tokens | Provider latency | E2E latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| `V2C_B1A00001` | 3 | 2 | 3 | 23,386 | 282 | 13,051ms | 19,911ms |
| `V2C_B1A00002` | 2 | 1 | 2 | 76,154 | 960 | 15,084ms | 17,581ms |

Formal path success is 2/2 (`100%`); attempt-level success is 2/5 (`40%`). Both formal paths obtained model bodies, but three of five attempts returned `unknown_http_400`. Together with the 0/3 diagnostic result, Transport must be recorded as high risk and **must not** be called stable.

### DeepSeek V4 Pro Max

| Case | Transport calls | Canonical result | Selected input tokens | Selected output tokens | Selected provider latency | E2E latency |
|---|---:|---|---:|---:|---:|---:|
| `V2C_B1A00001` | 1 | valid | 16,137 | 2,181 | 36,639ms | 36,699ms |
| `V2C_B1A00002` | 2 (initial + Repair) | valid after Repair | 52,469 | 6,019 | 92,802ms | 152,116ms |

DeepSeek used `deepseek-v4-pro`, `reasoning_strength=max`, and `provider_usage=annotation_secondary_review`. All three transport calls returned model bodies; both Reviewer paths compiled successfully. The Case 2 manifest retains selected Repair usage; separate token counts for its initial model body were not persisted, so aggregate token totals are lower bounds rather than complete billing totals.

Selected successful bodies total at least 168,146 input tokens and 9,442 output tokens. Formal end-to-end latency totals 226,307ms across four paths. Provider cost was unavailable for every call and is reported as unavailable rather than estimated.

## Leakage, Frozen Boundaries, and Access Audit

- No Held-out, Gold, Human Adjudication, `eval_queries.candidate.jsonl`, or `eval_queries.locked.jsonl` content was accessed.
- No expected label, keyword statistics, selection reason, previous Review, Agreement, Human opinion, or Gold was sent to a Reviewer.
- Secret scan passed with no Authorization, Bearer token, or supplied secret value in output artifacts.
- Four-state definitions, Semantic/Span Gold rules, Evidence Group OR / Required Span AND, Canonical Annotation Review v2, deterministic A/S/G compilation, Agreement thresholds, Mandatory Human Review, Safe Projection, Eval v1, and Frozen V3 were not changed.
- No Final Gold or Human Decision was written.

## Remaining Pilot Recommendation

The query-projection and query-grounding defects are repaired, so the Canary passes and is ready for Human Review and an explicit Remaining Pilot decision. Do not automatically enter the Remaining Pilot in this run. Human review should first resolve both mandatory-review packets, and the decision owner should explicitly accept or mitigate the observed OpenAI transport risk.

## Human Review Packets

- Case 1: `research/v3_5/eval_v2/stage2r_b1_b_canary/B1B_V2C_B1A00001_0b975c6b5eb9/human_review_packet.md`
- Case 2: `research/v3_5/eval_v2/stage2r_b1_b_canary/B1B_V2C_B1A00002_fe057eee3b4a/human_review_packet.md`

Both contain `Human decision: pending` and are not Final Gold.

## Final Status

```text
Stage 2R-B1-B Canary Passed
Ready for Human Review and Remaining Pilot Decision
```
