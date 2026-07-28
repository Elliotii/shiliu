# P8 Product Initial Baseline Attempt 2 Blocking Report

```yaml
execution_status: blocked
attempt_id: P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_2
blocking_category: runtime_source_authority_failure
blocked_at_phase: Phase 1 — Blind Product Prediction
failed_query_id: PQS_V1_Q014
failure_code: no_supported_subtitle
recorded_at_utc: 2026-07-26T16:08:33Z
development_gold_opened: false
frozen_gold_opened: false
frozen_query_runs: 0
functional_component_behavior_changed: false
query_split_or_gold_changed: false
f1a_f1b_or_stage4_started: false
```

## Blocking check

The new Phase 0 authority and input checks passed. The formal Authority Index
SHA-256 was
`13e792483b0f5c4945a7a2802e56cd9f8076479d7c583b2022ac197acfb98421`.
All explicitly referenced runtime component hashes, the Product Default Auto
wiring, Router, snapshot DB, and artifact manifest matched their authorities.

During the one permitted blind sequence, nine queries produced complete
persisted Predictions and Traces. The tenth attempted query,
`PQS_V1_Q014`, reached Candidate Builder source resolution and raised:

```text
EvidenceContractError(code=no_supported_subtitle):
no authoritative raw subtitle is available
```

No complete terminal Prediction for `PQS_V1_Q014` was persisted. The P8
contract requires an immediate block when an infrastructure/runtime condition
leaves the formal Prediction set incomplete. The executor therefore did not
retry the query, did not continue the remaining four queries, did not create a
Prediction Freeze Seal, and did not open Development Gold.

## Blind Prediction progress

```yaml
planned_development_queries: 14
query_attempts: 10
terminal_predictions_persisted: 9
traces_persisted: 9
failed_query_without_terminal_prediction: PQS_V1_Q014
remaining_queries_not_run: 4
prediction_freeze_seal_created: false
development_gold_opened: false
```

Persisted query IDs:

```text
PQS_V1_Q003
PQS_V1_Q004
PQS_V1_Q005
PQS_V1_Q006
PQS_V1_Q007
PQS_V1_Q008
PQS_V1_Q011
PQS_V1_Q012
PQS_V1_Q013
```

## Preserved partial artifact identity

```yaml
input_manifest:
  path: blind_run/product_initial_baseline.input_manifest.json
  sha256: 8a39e05506bafcb080c099e9bcc23115b7ae6c34ce6e2460b70eb880c5ab2feb
predictions:
  path: blind_run/product_initial_baseline.predictions.jsonl
  record_count: 9
  sha256: 57b95e05078e7858dd1f48d24f158e11d6c96e1cc237b32789cbd67bf480f5a4
traces:
  count: 9
  query_ids:
    - PQS_V1_Q003
    - PQS_V1_Q004
    - PQS_V1_Q005
    - PQS_V1_Q006
    - PQS_V1_Q007
    - PQS_V1_Q008
    - PQS_V1_Q011
    - PQS_V1_Q012
    - PQS_V1_Q013
prediction_freeze_seal: not_created
```

The existing partial Prediction and Trace bytes are preserved. They must not be
presented as a complete baseline or scored against Development Gold.

## Prohibited-action audit

```yaml
development_gold_opened: false
frozen_gold_opened: false
frozen_query_runs: 0
best_of_n: false
gold_aware_retry: false
failed_query_retried: false
prediction_modified_after_gold: not_applicable
retrieval_router_builder_selector_gate_behavior_changed: false
query_split_gold_changed: false
checkpoint_1_started: false
f1a_started: false
f1b_started: false
stage4a_r_started: false
stage4b_started: false
```

This attempt is terminally blocked and does not authorize Checkpoint 1, F1A,
F1B, Stage 4A-R, Stage 4B, P9, or scoring of the partial Prediction set.
