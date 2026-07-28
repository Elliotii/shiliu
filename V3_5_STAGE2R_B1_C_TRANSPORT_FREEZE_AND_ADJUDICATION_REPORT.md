# Shiliu V3.5 Stage 2R-B1-C — Transport, Freeze, and Adjudication Report

Date: 2026-07-23  
Scope: two-call non-formal OpenAI transport verification, attempt-level Usage persistence, accepted Canary workflow freeze, and a two-Case Human Adjudication bundle.

## Executive Result

```text
Stage 2R-B1-C Transport Verification Blocked
Canary Workflow Not Released for Remaining Pilot
```

The bounded OpenAI verification did not meet its 2/2 condition: one call returned HTTP 400 and no model body; one call returned a `gpt-5.6-terra` model body. Exactly two independent calls were made, each with one Transport Attempt, no Retry, and no Draft Repair. No additional provider call was made after the result.

The already accepted B1-B Reviewer workflow was nevertheless hashed and frozen, attempt-level Usage persistence was implemented for future calls, and the two unchanged Canary reviews were assembled into one blank Human Adjudication bundle. Freezing records component identity; it does not authorize Remaining Pilot while Transport verification is blocked and Human Adjudication is pending.

## 1. OpenAI Transport Verification

Fixture classification:

```text
non_formal_transport_fixture
not_master_case: true
not_gold: true
```

Both calls used the same Provider, `gpt-5.6-terra` model, Prompt, Draft Schema, high reasoning configuration, Packet bytes, and payload fingerprint:

```text
4b7e9700d04be14a7949e2c7cb5b2d4f335f17743e3e0ee740bf6c0b4bace8a1
```

| Call | Attempts | Retry | HTTP | Safe category | Body | Response model | Input | Output | Cached | Latency |
|---|---:|---:|---|---|---|---|---:|---:|---:|---:|
| 1 | 1 | 0 | 400 | `unknown_http_400` | no | unavailable | unavailable | unavailable | unavailable | 3,290ms |
| 2 | 1 | 0 | unavailable on successful SDK response | `none` | yes | `gpt-5.6-terra` | 1,166 | 167 | 0 | 7,339ms E2E / 7,332ms provider |

Safe Provider error code for Call 1 was `bad_response_status_code`; request ID and non-sensitive response headers were unavailable. No raw error body was persisted.

```yaml
openai_transport_fix_verified: false
model_body_count: 1
http_400_count: 1
payload_fingerprints_identical: true
```

Therefore, the HTTP 400 fix did **not** pass 2/2 verification. The successful call did echo the requested model; the failed call had no response model to echo.

## 2. Attempt-Level Usage Persistence

Every new real Provider Attempt is now persisted independently with:

```text
provider
case_id
reviewer_role
attempt_index
attempt_type
selected_for_final
http_status
model_body_returned
input_tokens
output_tokens
cached_tokens
provider_latency_ms
end_to_end_latency_ms
safe_error_category
```

The Initial Draft and Draft Repair paths produce separate records. Unselected Draft usage remains recorded. Missing token or latency data is written as `unavailable`, never zero.

Both B1-C Fixture Attempts have separate records at:

```text
research/v3_5/eval_v2/stage2r_b1_c/provider_attempt_usage.jsonl
```

B1-C Usage is complete for the two permitted Attempts: 1,166 input tokens, 167 output tokens, and 0 cached tokens for the single returned body. The failed transport correctly retains unavailable token fields.

B1-B history was not re-invoked or fabricated to fill missing usage. Its selected-body values remain available, but it did not persist every historical attempt body separately. B1-B and combined totals are therefore explicitly classified as `lower_bound`:

```text
research/v3_5/eval_v2/stage2r_b1_c/historical_usage_completeness.json
research/v3_5/eval_v2/stage2r_b1_c/usage_batch_summary.json
```

## 3. Frozen Canary Workflow

The following accepted versions are frozen:

| Component | Frozen version |
|---|---|
| Query Projection | `v3.5-query-projection-v1` |
| Reviewer Draft Schema | `v3.5-reviewer-draft-v2` |
| Primary Prompt | `v3.5-primary-reviewer-draft-prompt-v3-query-grounded` |
| Secondary Prompt | `v3.5-secondary-reviewer-draft-prompt-v2-query-grounded` |
| Query Grounding Validator | `v3.5-query-grounding-validator-v1` |
| Review Compiler | `v3.5-review-compiler-v1` |
| Canonical Review Schema | `v3.5-annotation-review-v2` |
| Agreement | `v3.5-annotation-agreement-v2` |

The manifest records SHA-256 values for the governing source files and frozen B1-B artifacts.

```text
Freeze Manifest:
research/v3_5/eval_v2/stage2r_b1_c/canary_freeze_manifest.json

Freeze Manifest SHA-256:
d64d72ebd283fb86d798b9c026a230569d924cdcf2c77471b5a5e0b2c72df394

freeze_status:
frozen_for_remaining_pilot
```

The manifest also freezes the rule that a future protocol-level defect must stop execution and create a new Eval Protocol Version; the frozen components may not be edited in place based on a new Case.

Because Transport verification failed and Human Adjudication is pending, `frozen_for_remaining_pilot` is a version-integrity state, not an authorization to start the Pilot.

## 4. Original Canary Review Integrity

Hashes were captured for both Cases’ Initial/Repair Drafts, Canonical Reviews, Agreements, and original Human Packets before and after bundle generation. All before/after hashes are identical:

```yaml
original_review_artifacts_unchanged: true
human_decision_prefilled: false
final_gold_created: false
third_case_selected: false
```

Integrity audit:

```text
research/v3_5/eval_v2/stage2r_b1_c/canary_freeze_and_bundle_integrity.audit.json
```

Neither Canary Reviewer was called again.

## 5. Unified Human Adjudication Bundle

Bundle:

```text
V3_5_STAGE2R_B1_C_CANARY_HUMAN_ADJUDICATION_BUNDLE.md
SHA-256: 00137397059ab02e0155c4b1af94e239e7f591c830319c3a0ebe6975495de356
```

Each Case is separate and includes its projected Query fields, Source identity, Transcript boundaries, Packet hash, both complete Canonical Reviews, Required Aspect partitions, Evidence Groups, Required Span segment IDs/timestamps/raw text, Reason Codes, confidence, boundary notes, mechanical Agreement metrics, and the requested Case-specific Human questions.

Each Case ends with a blank template supporting:

```text
approve_primary
approve_secondary
merge_and_revise
reject_both
```

No action, final status, Aspect, Span, Reason Code, or adjudication reason was filled. No majority vote or automatic Gold formation was applied. The bundle is ready to hand to the user for Human Adjudication.

## 6. Safety and Frozen-Boundary Audit

- No Held-out Gold, Review, or Adjudication asset was accessed.
- Neither `research/v3_eval/eval_queries.candidate.jsonl` nor `research/v3_eval/eval_queries.locked.jsonl` was accessed.
- Eval v1 and Frozen V3 were not modified.
- Query Projection semantics, Query-grounding Prompt principles, four-state definitions, Evidence Group OR, Required Span AND, Agreement thresholds, Canonical Schema, Compiler IDs, and Mandatory Human Review were not redesigned.
- No API Key, Authorization value, Base URL, raw error body, or full request Transcript was persisted.
- B1-C secret scan passed with no violations.
- No third Case, Remaining Pilot Case, Final Gold, or automatic Human Decision was created.

## 7. Tests

Fifty-seven directed tests passed, covering:

- identical payload fingerprints across both Fixture calls;
- exactly one Attempt per call and prohibited Retry;
- independent attempt-level Usage persistence;
- Initial Draft / Draft Repair separation;
- unavailable tokens remaining `unavailable`;
- Freeze Manifest source and artifact hash reproduction;
- bundle immutability and blank Human Decisions;
- no third Case or Final Gold;
- Reviewer Draft, Compiler, Query Grounding, dual-provider safety, Canary integrity, Safe Projection, clean-restart, and recovery guards.

The unrestricted Full Regression was not run because its broader evaluation surfaces are outside B1-C’s anti-contamination boundary and could access explicitly prohibited Eval/Held-out assets. The complete directed B1-C and relevant regression set passed; this is a scope restriction, not a test failure.

## 8. Required Answers

1. OpenAI 400 fix passed 2/2: **No; 1/2 returned a model body.**
2. HTTP 400 still occurred: **Yes; one.**
3. Response Model echoed: **Yes for the successful call (`gpt-5.6-terra`); unavailable for the failed call.**
4. Each Attempt Usage independently recorded: **Yes for all B1-C and future attempts.**
5. Historical Usage fabricated or backfilled: **No; missing B1-B usage remains unavailable and totals are lower bounds.**
6. Frozen versions: **Projection, Draft Schema, both Prompts, Grounding Validator, Compiler, Canonical Review, and Agreement versions listed above.**
7. Freeze Manifest path/hash: **`research/v3_5/eval_v2/stage2r_b1_c/canary_freeze_manifest.json` / `d64d72ebd283fb86d798b9c026a230569d924cdcf2c77471b5a5e0b2c72df394`.**
8. Original Canary Reviews unchanged: **Yes, verified byte-for-byte by SHA-256.**
9. Human bundle path: **`V3_5_STAGE2R_B1_C_CANARY_HUMAN_ADJUDICATION_BUNDLE.md`.**
10. Held-out/Gold accessed: **No.**
11. Eval v1/Frozen V3 modified: **No.**
12. Ready for user adjudication: **Yes.**
13. Remaining Pilot permitted: **No.**

```yaml
remaining_pilot_authorized: false
reason: awaiting human adjudication of both Canary Cases
```

## Final Status

```text
Stage 2R-B1-C Transport Verification Blocked
Canary Workflow Not Released for Remaining Pilot
```
