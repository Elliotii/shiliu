# Stage 4B Failure Analysis

The three-track comparison was performed only after the Initial Predictions Freeze.

## Per-case attribution

- `PQS_V1_Q003` gold `sufficient`; A/B/C `insufficient/sufficient/sufficient` → `upstream_retrieval_or_resolution`.
- `PQS_V1_Q004` gold `sufficient`; A/B/C `insufficient/sufficient/sufficient` → `upstream_retrieval_or_resolution`.
- `PQS_V1_Q005` gold `sufficient`; A/B/C `partial/sufficient/sufficient` → `upstream_retrieval_or_resolution`.
- `PQS_V1_Q007` gold `sufficient`; A/B/C `insufficient/sufficient/sufficient` → `upstream_retrieval_or_resolution`.
- `PQS_V1_Q012` gold `sufficient`; A/B/C `insufficient/sufficient/sufficient` → `upstream_retrieval_or_resolution`.
- `PQS_V1_Q013` gold `sufficient`; A/B/C `partial/sufficient/partial` → `judge_policy_boundary_or_reasoning`.
- `PQS_V1_Q014` gold `sufficient`; A/B/C `unverifiable/sufficient/sufficient` → `upstream_retrieval_or_resolution`.
- `PQS_V1_Q017` gold `insufficient`; A/B/C `insufficient/partial/partial` → `judge_policy_boundary_or_reasoning`.
- `PQS_V1_Q018` gold `sufficient`; A/B/C `partial/sufficient/sufficient` → `upstream_retrieval_or_resolution`.

## Layer conclusion

- No Builder, Selector, Mechanical Gate, Retrieval, Evidence Identity Contract, or Gold
  change was made; Sufficiency contracts received only the frozen additive compatibility patch.
- Structured-output/schema, evidence-ID, and trace failures: none.
- Track B used an approved known-relevant-video authoritative-span projection;
  it did not replay the full formal Builder/Selector path and is diagnostic only.
  Consequently, A/B/C layer attribution involving Track B is provisional.
- Frozen Evaluation accessed: false.
