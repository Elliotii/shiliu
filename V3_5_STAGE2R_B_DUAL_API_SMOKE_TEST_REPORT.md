# Shiliu V3.5 Stage 2R-B Dual API Smoke Test Report

Date: 2026-07-23  
Scope: non-formal synthetic dual-provider Reviewer smoke test only.

## Executive Result

```text
Dual API Synthetic Smoke Test: Passed
Formal B1 Pilot: Not started
```

Both frozen Provider paths issued real API requests for the same synthetic Packet bytes and independently produced a valid ReviewerDraft that compiled into Canonical Annotation Review v2. No formal Query, formal Transcript, Gold, Held-out label, historical Review, Agreement result, or Adjudication content was sent to either Reviewer.

An operational caveat remains: the configured OpenAI-compatible endpoint returned intermittent request-level failures before a successful recorded Primary result. The successful response echoed `gpt-5.6-terra`, but endpoint reliability should be monitored before or during a tightly bounded Pilot.

## Provider Registry

### Primary

```yaml
provider_id: openai
usage: annotation_primary_review
model: gpt-5.6-terra
api_style: responses
reasoning_effort: high
temperature_policy: omitted_unless_supported
draft_schema_version: v3.5-reviewer-draft-v1
canonical_schema_version: v3.5-annotation-review-v2
prompt_version: v3.5-primary-reviewer-draft-prompt-v2
repair_prompt_version: v3.5-primary-reviewer-draft-repair-prompt-v1
max_repairs: 1
key_env_var: OPENAI_API_KEY
```

The configured base URL was consumed in memory and is intentionally omitted from this report.

### Secondary

```yaml
provider_id: deepseek
usage: annotation_secondary_review
model: deepseek-v4-pro
api_style: chat_completions
reasoning_effort: max
thinking: enabled
temperature_policy: omitted_unless_supported
draft_schema_version: v3.5-reviewer-draft-v1
canonical_schema_version: v3.5-annotation-review-v2
prompt_version: v3.5-secondary-reviewer-draft-prompt-v1
repair_prompt_version: v3.5-secondary-reviewer-draft-repair-prompt-v1
max_repairs: 1
key_env_var: DEEPSEEK_API_KEY
```

The current local DeepSeek installation retained its existing macOS Keychain source (`app.shiliu.llm:default`) as a compatibility fallback. The active adapter also supports `DEEPSEEK_API_KEY` from environment or ignored `.env.local`.

## SDK and API Shape

- OpenAI Python SDK: `2.46.0`.
- Responses request fields verified locally: `model`, `input`, `instructions`, `reasoning`, `text`, and `store`.
- Structured output: `text.format` with strict ReviewerDraft JSON Schema.
- Storage: `store=false`.
- No silent model fallback, API-style fallback, reasoning downgrade, or fallback to `gpt-5.4`.
- DeepSeek remains an explicit HTTP/Chat Completions adapter rather than being forced through the OpenAI endpoint.

## Synthetic Packet Integrity

```text
case_id: V2C_FIXTURE01
synthetic_fixture: true
source_file: research/v3_5/eval_v2/stage2r_a/fixtures/annotation_packet.synthetic.v2.json
packet_sha256: 63bca7b53e2a541c9189b368ce11104adfd8dec8ce85f18637efebc7feb9b3d6
primary_packet_sha256: 63bca7b53e2a541c9189b368ce11104adfd8dec8ce85f18637efebc7feb9b3d6
secondary_packet_sha256: 63bca7b53e2a541c9189b368ce11104adfd8dec8ce85f18637efebc7feb9b3d6
packet_hash_equal: true
segment_count: 3
first_segment_id: seg_1
last_segment_id: seg_3
source_artifact: artifact_fixture
source_version: version_fixture
timeline_run: run_1
```

Draft Schema SHA-256:

```text
3938a4a0bf0dd3191abaefe83453ed13aab0cf3d91c7d58e16fa99db1517d4ca
```

Canonical Annotation Review v2 Schema SHA-256:

```text
9bca2d6e77b9298161c37475f453c564552d1ac1dd5abd2164cec7a744c132df
```

## Reviewer Payload Audit

Both paths used the same allowed Packet top-level fields:

```text
annotation_protocol_version
case_id
case_input_sha256
full_raw_transcript
packet_version
query
query_language
review_output_schema_version
segment_schema
source_metadata
```

```text
primary_forbidden_field_scan: []
secondary_forbidden_field_scan: []
```

The payload builder rejects fields associated with Candidate Builder predictions, Selector predictions, Mechanical Gate predictions, Semantic Judge predictions, Sufficiency/Evidence Gold, Gold segment IDs, another Reviewer, Agreement, Adjudication, Held-out labels, historical Reviews, and system predictions.

Provider-specific request fields remained outside the canonical packet. Primary received the schema through Responses Structured Outputs; Secondary received the same schema in its system payload. Neither Reviewer received the other Reviewer's output.

## Primary Live Result

The selected successful Primary result was produced independently after the orchestrated attempt had preserved the successful Secondary result.

```text
requested_model: gpt-5.6-terra
response_model_echo: gpt-5.6-terra
initial_valid: true
initial_validation_errors: []
repair_attempted: false
repair_valid: not_applicable
raw_call_count_for_selected_path: 1
canonical_compilation_success: true
canonical_sha256: 0e36567c7efa7cc8963e1d1910030bbfeecc374115ad3ba1959bae0385efb79c
input_tokens: 1659
output_tokens: 339
cached_tokens: 0
provider_latency_ms: 7583
primary_end_to_end_latency_ms: 8644
finish_reason: completed
cost_usd: unavailable
```

### Primary transient observations

- The initial dual smoke attempt returned a sanitized Primary request failure.
- A diagnostic request returned HTTP 400 without a usable provider error code.
- An identical diagnostic request subsequently succeeded.
- The next recorded full-payload Primary call succeeded and compiled.
- No failed request produced a Draft, so no schema Repair was consumed.

These were transport/provider attempts, not ReviewerDraft repair attempts. The selected successful annotation path used one call and zero repairs.

## Secondary Live Result

```text
requested_model: deepseek-v4-pro
response_model_echo: deepseek-v4-pro
initial_valid: true
initial_validation_errors: []
repair_attempted: false
repair_valid: not_applicable
raw_call_count_for_selected_path: 1
canonical_compilation_success: true
canonical_sha256: 785fa41a5ff907d1ef65cfcc1233667d9259579dcf90e9cc0dd00fdc4e21d301
input_tokens: 1435
output_tokens: 1634
cached_tokens: unavailable
provider_latency_ms: 21919
recorded_orchestrated_attempt_end_to_end_latency_ms: 23567
finish_reason: stop
cost_usd: unavailable
```

The successful Secondary result was retained even though Primary failed in that orchestrated attempt. A separate DeepSeek diagnostic request also succeeded. Secondary required no repair.

## Independent Completion

- Primary failure did not suppress or discard the successful Secondary result.
- Secondary provider exceptions are represented independently and do not suppress Primary execution.
- Primary provider exceptions are represented independently and do not suppress Secondary execution.
- Each validation path performs at most one ReviewerDraft repair.
- Canonical A/S/G IDs are generated locally by the same deterministic compiler and are never requested from either model.

Because the selected successful Primary and Secondary results completed in separate independent calls after a transient Primary failure, there is no single both-success wall-clock latency value. The individual provider and end-to-end measurements above are authoritative.

## Secret Audit

```text
OPENAI_API_KEY configured: true
OpenAI key source: ignored dotenv
DeepSeek key configured: true
DeepSeek key source: macOS Keychain compatibility fallback
.env.local git ignored: true
.env.local git tracked: false
authorization_persisted: false
request_header_values_persisted: false
raw_request_artifact_persisted: false
raw_response_artifact_persisted: false
primary_result_secret_scan: pass
secondary_result_secret_scan: pass
report_secret_scan: pass
```

No Key value, Key prefix/suffix, Authorization value, base URL, or unnecessary Provider header is included in this report or a request manifest. Provider errors retain only sanitized classification/status data.

## Agreement Readiness

The Agreement Checker was corrected so cross-Reviewer comparison does not directly equate local IDs such as Primary `A1/S1/G1` with Secondary `A1/S1/G1`.

It now compares:

- sufficiency status;
- normalized Aspect semantics;
- supported/missing Aspect partitions by semantic description;
- required Segment sets and IoU;
- time-region overlap;
- source identity;
- Evidence Group Aspect–Segment relationships;
- reason codes and confidence.

A directed test compiles semantically equivalent partial Reviews with reversed Aspect array order and verifies agreement for required, supported, missing, and Evidence Group semantics.

## Tests

Pre-live Provider-directed suite:

```text
23 passed
```

Post-live complete project regression:

```text
704 passed, 7 warnings in 20.82s
```

The first broad regression command without an explicit project `PYTHONPATH` failed during collection because repository-local `tests`, `research`, and `eval` packages were not importable. Re-running with `PYTHONPATH=.:src` passed all 704 tests. This was an invocation-environment issue, not a test assertion regression.

## Engineering Changes

- Added frozen Reviewer Provider Registry.
- Added safe `.env.local` loader with redacted representations and missing-key errors that name only the variable.
- Added OpenAI Responses adapter for `gpt-5.6-terra`.
- Retained and wrapped the existing DeepSeek HTTP path as a unified Reviewer adapter.
- Added common canonical Packet bytes, Payload Audit, request manifest, and Result Envelope.
- Added provider-independent completion/error handling.
- Added strict ReviewerDraft prompt compatible with the Draft Schema; the prior Stage 2R-A prompt expected a Canonical review body and was not reused as the model-facing Draft prompt.
- Added DeepSeek Draft Schema delivery.
- Corrected cross-Reviewer Agreement semantics.
- Added `.env.example` containing variable names only.
- Added OpenAI SDK dependency.

## Final Decision

```text
Stage 2R-B Dual API Synthetic Smoke Test Passed
Formal B1 Pilot was not started
```

All ten smoke-test acceptance conditions were established for the selected successful Primary and Secondary results:

1. Both Providers issued real requests.
2. Primary echoed `gpt-5.6-terra`.
3. Secondary echoed `deepseek-v4-pro`.
4. Packet hashes were identical.
5. Both produced valid Initial Drafts; neither required Repair.
6. Both compiled into Canonical Annotation Review v2.
7. Canonical Schema was not modified by the live flow.
8. No Secret was persisted.
9. Reviewer payload forbidden-field scans were empty.
10. A Provider failure did not discard the other Provider's result.

The OpenAI endpoint's intermittent request failures are recorded as an operational caveat, not hidden. No formal Case selection, formal annotation, B1 Pilot, Stage 2R-C, Stage 3R, or later-stage work was performed.
