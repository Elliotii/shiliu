# Product Query Set v1 — P3 User Validation Report

## Status

```yaml
execution_status: complete
acceptance_status: pending_v3_5_b_review
reviewed_candidates: 41
formal_selected: 24
reserve: 11
rejected: 6
revision_rounds_used: 1
unresolved_discussions: 0
all_formal_queries_user_validated: true
system_performance_used: false
gold_or_expected_labels_used: false
```

All 41 decisions from the hash-verified User Decision Ledger were materialized in candidate-ID order. The formal set contains 23 Corpus-aware Codex candidates and one user-discussion candidate (`PQC_USER_001`). Eleven plausible reserve candidates remain outside the first formal set. Six rejected candidates remain in the completed ledger for audit traceability.

User approval means the question is genuinely plausible for this user. It does not assert that the current system must answer it, and it does not assign a Gold or sufficiency label.

No candidate was generated, reselected, or rewritten by Codex during P3. No Retrieval, Builder, Selector, Gate, Judge, Split, Gold, or Product Baseline work was run.

## Mechanical Validation

```text
.venv/bin/pytest -q tests/test_pqs_corpus_aware_candidate_generation_contract.py tests/test_pqs_corpus_aware_candidate_generation_audit_identity.py tests/test_pqs_v1_user_validation_and_freeze_contract.py
42 passed
```
