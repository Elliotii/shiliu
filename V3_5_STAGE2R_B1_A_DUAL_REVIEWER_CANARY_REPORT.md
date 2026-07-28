# Shiliu V3.5 Stage 2R-B1-A Dual-Reviewer Canary Report

Date: 2026-07-23  
Scope: exactly two non-Held-out Development Canary Cases.

## Executive Result

```text
Stage 2R-B1-A Canary: Blocked
Not Ready for Remaining Pilot
```

```text
Recommendation: Repair B1 Workflow Before Continuing
```

Three of four Reviewer paths produced valid Canonical Annotation Review v2 records. The fourth path—Case 1 Primary—exhausted the frozen budget of three byte-identical transport attempts after three transient HTTP 400 responses. Case 2 completed both paths and Semantic Agreement.

The Canary is blocked rather than passed with only an operational caveat because Case 1 Secondary produced a schema-valid but clearly query-ungrounded annotation: for query `MCP`, it defined unrelated transcript topics as Required Aspects and labeled the case `sufficient`. This is a Reviewer prompt/query-grounding workflow defect that must be repaired and re-canary-tested before expanding the Pilot.

No final Gold was created. No Human decision was inferred. No third Case or remaining Pilot Case was selected.

## Development Authorization and Governance Note

The only available non-Held-out candidate projection was:

```text
research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.jsonl
projection_version: v3.5-safe-non-heldout-candidate-projection-v1
pilot_candidate_allowed: true
held_out: false for all four matched source records
```

Its historical Recovery-A manifest declared `session_future_eligibility.annotation_review=false` and `pilot_case_mining=false`. The current B1-A instruction explicitly authorized selecting two Cases from the Eval v2 Development Pilot Candidate Pool. This current authorization was treated as a deliberate governance override and recorded rather than silently ignoring the older manifest.

The projection contains Queries and source digests but no prebuilt Case/Transcript binding. The Trusted Local Orchestrator therefore paired two authorized Queries with local non-Held-out Raw Sources without reading existing Gold or using a Gold label.

## Case Selection

### Case 1 — Ordinary negative-control candidate

```text
case_id: V2C_B1A00001
candidate_id: SAFEQ_b74c117c857397e307df
query_id: Q01
query: MCP
query_family: exact_entity_mcp
leakage_group: LGV2_VIDEO_BV1ZDTX6EEGU
case_class: ordinary
source/video: BV1zDTX6eEGu
source_type: raw_subtitle
source_language: zh
segment_count: 106
transcript_duration_seconds: 277.480
complexity_tags: [single_video, short_transcript, negative_control_candidate]
selection_reason: shortest single-video Source; mechanical MCP term count was zero; selected without Gold as an ordinary insufficient/negative-control candidate
development_authorization_source: current B1-A instruction + v3.5-safe-non-heldout-candidate-projection-v1
```

### Case 2 — Complex evidence-lookup candidate

```text
case_id: V2C_B1A00002
candidate_id: SAFEQ_3722c739c07887747c70
query_id: Q15
query: 哪个视频解释了 CLI 相比 MCP 的优势？
query_family: evidence_lookup_cli_vs_mcp
leakage_group: LGV2_VIDEO_BV1O87764EBS
case_class: complex
source/video: BV1o87764Ebs
source_type: raw_subtitle
source_language: zh
segment_count: 374
transcript_duration_seconds: 866.780
complexity_tags: [single_video, long_transcript, multi_aspect, evidence_lookup]
selection_reason: long multi-aspect comparison/evidence-lookup candidate with mechanical MCP/RAG term hits; selected without Gold
development_authorization_source: current B1-A instruction + v3.5-safe-non-heldout-candidate-projection-v1
```

The two Cases have different Source-derived Leakage Groups.

## Packet Audit

Allowed top-level fields for all four Reviewer payloads:

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

### Case 1

```text
primary_packet_sha256: a89a2a9142fd5896b0b0c7286d5fc88e4b0f0c3c1105d073f20b31b18973f852
secondary_packet_sha256: a89a2a9142fd5896b0b0c7286d5fc88e4b0f0c3c1105d073f20b31b18973f852
packet_hash_equal: true
first_segment_id: BV1zDTX6eEGu_seg_000001
last_segment_id: BV1zDTX6eEGu_seg_000106
primary_forbidden_field_scan: []
secondary_forbidden_field_scan: []
```

### Case 2

```text
primary_packet_sha256: 11ac62de7dc152f43ac79227d275b1ba0960ae996eb1723f834dc9018f35f794
secondary_packet_sha256: 11ac62de7dc152f43ac79227d275b1ba0960ae996eb1723f834dc9018f35f794
packet_hash_equal: true
first_segment_id: BV1o87764Ebs_seg_000001
last_segment_id: BV1o87764Ebs_seg_000374
primary_forbidden_field_scan: []
secondary_forbidden_field_scan: []
```

Selection reason, complexity tags, expected labels, search predictions, Gold, another Review, Agreement, and Human Adjudication were not included in either Reviewer Packet.

## Provider Results

### Case 1 Primary — OpenAI

```text
provider: openai
requested_model: gpt-5.6-terra
response_model_echo: unavailable
transport_attempt_count: 3
selected_successful_attempt: none
transport_failures:
  - attempt 1: http_400_transient, status 400, latency 1743ms, retry delay 500ms
  - attempt 2: http_400_transient, status 400, latency 1099ms, retry delay 1000ms
  - attempt 3: http_400_transient, status 400, latency 869ms, no further retry
transport_payload_fingerprint_all_attempts: 46578ef0a8fb407ce888da6705bc7f78c3c2da5408ee927b6a56f33123f2816f
draft_received: false
draft_repair_attempted: false
canonical_compilation_success: false
end_to_end_latency_ms: 5220
tokens: unavailable
cost: unavailable
```

All three attempts retained identical Packet bytes, model, prompt, schema, reasoning, and Provider configuration. No Draft Repair was consumed because no model body was obtained.

### Case 1 Secondary — DeepSeek

```text
provider: deepseek
requested_model: deepseek-v4-pro
response_model_echo: deepseek-v4-pro
transport_attempt_count: 1
initial_valid: true
draft_repair_attempted: false
canonical_compilation_success: true
canonical_sha256: ad42593cdfb6f5801d4039e52403e12f35ab0c7f4e021e33fee554ed9042cb9a
input_tokens: 15946
output_tokens: 5913
cached_tokens: unavailable
provider_latency_ms: 66991
end_to_end_latency_ms: 67046
finish_reason: stop
cost: unavailable
```

Mechanical validation passed, but Human review identified a critical semantic defect: the Draft did not ground Required Aspects in the query `MCP`. It instead selected unrelated facts about an AI assistant, idea generation, and an AI conference, then labeled the case `sufficient`. This result must not become Gold.

### Case 2 Primary — OpenAI

```text
provider: openai
requested_model: gpt-5.6-terra
response_model_echo: gpt-5.6-terra
transport_attempt_count: 3
selected_successful_attempt: 3
transport_failures:
  - attempt 1: http_400_transient, status 400, latency 1078ms, retry delay 500ms
  - attempt 2: http_400_transient, status 400, latency 1280ms, retry delay 1000ms
initial_valid: true
draft_repair_attempted: false
canonical_compilation_success: true
canonical_sha256: caddcf4799eabe965db2af876558b04522effa329fdaafbee9c8ea924d53936d
input_tokens: 75882
output_tokens: 1176
cached_tokens: 0
provider_latency_ms: 17035
end_to_end_latency_ms: 20913
finish_reason: completed
cost: unavailable
```

The three attempts used the same payload fingerprint:

```text
d95c64c537dcb92cfa1f21b5709f6b4148ef7524329b301ff8f1aa02d90b1c00
```

### Case 2 Secondary — DeepSeek

```text
provider: deepseek
requested_model: deepseek-v4-pro
response_model_echo: deepseek-v4-pro
transport_attempt_count: 1
initial_valid: true
draft_repair_attempted: false
canonical_compilation_success: true
canonical_sha256: e63dd0605b8e3c6757a2d5663bf52d083ba92ff1daabd8b2b1a94687dd0ec32e
input_tokens: 52295
output_tokens: 5704
cached_tokens: unavailable
provider_latency_ms: 79945
end_to_end_latency_ms: 79961
finish_reason: stop
cost: unavailable
```

## Transport and Draft Repair Accounting

```text
total_reviewer_paths: 4
canonical_successes: 3
provider_transport_failures: 1 path
openai_transport_attempts: 6
openai_transient_http_400_failures: 5
deepseek_transport_attempts: 2
draft_repairs_attempted: 0
maximum_draft_repairs_observed: 0
```

Transport retry and Draft Repair remained separate. No retry changed Packet bytes, Prompt, Schema, model, reasoning, or Provider.

## Agreement

### Case 1

```text
overall_agreement_status: not_available
reason: Primary transport attempts exhausted before a Draft was returned
human_review_required: true
```

The successful Secondary result was retained. Agreement was not fabricated from a single Review.

### Case 2

```text
label_agreement: true
primary_label: sufficient
secondary_label: sufficient
required_aspect_agreement: unresolved, score 0.0714285714
supported_aspect_agreement: disagree, score 0.0
missing_aspect_agreement: agree, score 1.0
evidence_group_agreement: disagree, score 0.0
required_span_iou: agree, score 0.7
primary_span_recall: 0.7
secondary_span_recall: 1.0
optional_context_iou: 1.0
time_region_overlap: agree, score 1.0
source_agreement: true
reason_code_agreement: disagree, score 0.0
boundary_notes_equal: true
confidence_difference: 0
overall_agreement_status: mandatory_human_review
```

Mandatory triggers:

```text
required_aspect_unresolved
supported_aspect_disagreement
evidence_group_disagreement
multiple_required_spans
reason_code_disagreement
```

The two Reviewers selected the same overall time region and overlapping segments. Primary split the route into three required spans and used reason code `DIRECT_SUPPORT`; Secondary used one wider required span and no reason code. Their Aspect wording was semantically close to a Human reader but fell below the deterministic token-overlap threshold, correctly requiring Human review rather than automatic approval.

## Human Review Assets

Both Human Review Packets remain pending and are not Gold:

- Case 1: `research/v3_5/eval_v2/stage2r_b1_a_canary/B1A_V2C_B1A00001_ad03c89d1122/human_review_packet.md`
- Case 2: `research/v3_5/eval_v2/stage2r_b1_a_canary/B1A_V2C_B1A00002_f3f8350c79f2/human_review_packet.md`

Case 1 requires Human review of the Secondary query-grounding failure and has no Primary annotation. Case 2 requires Human review of Aspect equivalence, whether one wide span or three complementary spans is preferable, and whether `DIRECT_SUPPORT` should be normalized or omitted.

Each Packet provides Case identity, Query, Source, transcript boundaries, full transcript reference, Reviewer status, Aspects, partitions, Evidence Groups, selected Segment IDs, reconstructed times, Raw Text, Source identity, Agreement fields, and explicit review questions.

## Audit Assets

Root:

```text
research/v3_5/eval_v2/stage2r_b1_a_canary/
```

Assets include:

- `case_selection.audit.json`;
- per-Case `review_run.json`;
- per-Reviewer `reviewer_packet.json`;
- per-Reviewer `packet_manifest.json`;
- `reviewer_draft.initial.json` when a body was returned;
- `reviewer_draft.repair.json` only if Repair occurs (none occurred);
- per-Reviewer `reviewer_validation.json`;
- `canonical_review.json` when compilation succeeds;
- per-Reviewer `provider_result_manifest.json`;
- per-Case `agreement.json` or explicit unavailable Agreement record;
- per-Case `human_review_packet.md`;
- `secret_scan.audit.json`.

Case 1 Primary has no initial Draft or Canonical Review file because the Provider returned no model body. Its absence is explicitly represented in validation and Provider manifests rather than persisting a fabricated placeholder.

## Secret and Boundary Audit

```text
OpenAI key source: ignored .env.local
DeepSeek key source: macOS Keychain compatibility fallback
.env.local ignored: true
.env.local tracked: false
persisted_file_count_scanned: 29
secret_value_violations: 0
authorization_persistence_violations: 0
secret_scan_passed: true
forbidden_payload_scan_passed: true for all four paths
Held-out Case selected/read: false
Held-out Gold read: false
existing Gold read: false
final Gold written: false
```

No HTTP envelope, Authorization Header, API Key, Key fragment, configured OpenAI base URL, or raw exception body was persisted.

## Schema and Compiler

Canonical Annotation Review v2 Schema SHA-256:

```text
9bca2d6e77b9298161c37475f453c564552d1ac1dd5abd2164cec7a744c132df
```

The Canonical Schema was not modified. All three successful paths used the deterministic compiler to generate local A/S/G IDs and reconstruct Source, Version, Timeline, Segment, and time identity from the Packet.

## Tests

Pre-call directed command:

```bash
PYTHONPATH=.:src .venv/bin/pytest -q \
  tests/test_v3_5_eval_v2_reviewer_draft.py \
  tests/test_v3_5_eval_v2_review_compiler.py \
  tests/test_v3_5_eval_v2_recovery_b.py \
  tests/test_v3_5_eval_v2_dual_provider.py \
  tests/test_v3_5_eval_v2_canary.py
```

Result:

```text
26 passed
```

The same directed suite passed again after the Provider calls.

Complete regression command:

```bash
PYTHONPATH=.:src .venv/bin/pytest --disable-warnings
```

Result:

```text
707 passed, 7 warnings in 21.55s
```

No invocation-environment failure occurred in this Session's Canary test commands.

## Required Repair Before Continuing

1. Version and strengthen the ReviewerDraft prompt so every Required Aspect must be derived from the Query's information need; unrelated transcript facts must never become Required Aspects or sufficiency evidence.
2. Add a deterministic post-Draft query-grounding validation or mandatory Human trigger for cases where Aspect semantics have negligible relation to the Query.
3. Diagnose the configured OpenAI-compatible endpoint's intermittent HTTP 400 behavior. Five of six Canary transport attempts returned 400 even though the unchanged request shape can succeed.
4. Re-run these same two Canary Cases after the prompt/grounding repair. Do not add a third Case until both are reviewed.
5. Obtain the user's Human decisions for both Packets; do not automatically freeze either result as Gold.

## Final Decision

```text
Stage 2R-B1-A Canary Blocked
Not Ready for Remaining Pilot
Repair B1 Workflow Before Continuing
```

The minimum mechanical threshold of three successful Canonical paths was reached, and the fourth failure was a recorded transport failure. Nevertheless, the ordinary negative-control annotation demonstrates a material query-grounding defect, while OpenAI transport reliability is poor. Expanding to the remaining Pilot Cases before repairing and re-running the Canary would risk producing structurally valid but semantically invalid annotation assets.

No remaining Pilot, final Gold, Stage 2R-C, Stage 3R, Stage 4B, or later stage was started.
