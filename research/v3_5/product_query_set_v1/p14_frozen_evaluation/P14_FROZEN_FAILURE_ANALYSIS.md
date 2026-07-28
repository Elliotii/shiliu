# P14 Frozen Failure Analysis

This analysis attributes frozen results only. No repair, rerun, tuning, or
component change was performed.

## Per-case failures

- `PQS_V1_Q001`: expected `sufficient`, actual `unverifiable` — `mechanical_source_unverifiable`.
- `PQS_V1_Q002`: expected `sufficient`, actual `unverifiable` — `mechanical_source_unverifiable`.
- `PQS_V1_Q009`: expected `sufficient`, actual `unverifiable` — `mechanical_source_unverifiable`.
- `PQS_V1_Q010`: expected `sufficient`, actual `partial` — `builder_incomplete`.
- `PQS_V1_Q016`: expected `sufficient`, actual `sufficient` — `builder_incomplete`.
- `PQS_V1_Q020`: expected `sufficient`, actual `sufficient` — `builder_incomplete`.
- `PQS_V1_Q021`: expected `sufficient`, actual `insufficient` — `builder_incomplete`.
- `PQS_V1_Q022`: expected `sufficient`, actual `unverifiable` — `mechanical_source_unverifiable`.
- `PQS_V1_Q023`: expected `sufficient`, actual `partial` — `builder_incomplete`.
- `PQS_V1_Q024`: expected `sufficient`, actual `unverifiable` — `mechanical_source_unverifiable`.

## Post-result controls

- Prediction reruns: none.
- Prompt, policy, model, component, Gold, scorer, or projection changes: none.
- V3.5 tuning performed: none.
