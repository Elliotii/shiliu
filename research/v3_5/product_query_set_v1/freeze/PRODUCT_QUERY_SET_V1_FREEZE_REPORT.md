# Product Query Set v1 — P4 Freeze Report

## Execution Decision

```yaml
execution_status: complete
acceptance_status: pending_v3_5_b_review
product_query_set_formally_accepted_by_v3_5_b: false
p5_authorized: false
```

## Locked Identity

- Query count: 24
- Query ID range: `PQS_V1_Q001`–`PQS_V1_Q024`
- Schema version: `v3.5-product-query-set-v1`
- Canonicalization version: `json-array-sort-keys-utf8-v1`
- Canonical Content SHA-256: `fadf21c1992d848f2904192af479f6720a059c9aeb772ccfc4cee3b220942825`
- Repeated Canonical Content SHA-256: `fadf21c1992d848f2904192af479f6720a059c9aeb772ccfc4cee3b220942825`
- Locked JSONL byte-level SHA-256: `35d33dcf4dd77f12cad4e0c118f2c2f2e371a3019320906a3d2134bb933dd59c`
- Canonical hash repeatable: true

## Provenance and Isolation

The locked set exactly materializes the ledger's 24 `final_query_specs`, with revision histories derived mechanically from the corresponding user decisions. It contains 23 Corpus-aware Codex-origin queries and one user-discussion-origin query. Reserve and rejected candidates in the locked set: 0.

No Query text was changed by Codex. No Gold, Target Video, SearchCandidateSet, system result, Split, or Product Baseline was read or created. Retrieval, Builder, Selector, Gate, and Judge calls: 0.

This is a P4 execution candidate pending V3.5-B review. Semantic changes after freeze require a new dataset version.

## Mechanical Validation

```text
.venv/bin/pytest -q tests/test_pqs_corpus_aware_candidate_generation_contract.py tests/test_pqs_corpus_aware_candidate_generation_audit_identity.py tests/test_pqs_v1_user_validation_and_freeze_contract.py
42 passed
```
