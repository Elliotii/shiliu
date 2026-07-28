# Product Query Split v1 — P5 Leakage-aware Split R2 Report

## Execution Decision

```yaml
execution_status: complete
acceptance_status: pending_v3_5_b_review
p5_formally_accepted_by_v3_5_b: false
split_version: PQS_V1_SPLIT_V1
development_count: 14
frozen_evaluation_count: 10
next_phase_authorized: false
```

The authoritative R2 package superseded the unexecuted 10 Development / 14 Frozen package. Only the R2 14 Development / 10 Frozen Evaluation assignment was materialized.

## Input Identity

- R2 Decision Ledger SHA-256: `af33dee545a577b1f467f9092396ec74ddfbe4d965f1ab0855b62a99b62b184c`
- P4 Canonical Content SHA-256: `fadf21c1992d848f2904192af479f6720a059c9aeb772ccfc4cee3b220942825`
- P4 Locked JSONL SHA-256: `35d33dcf4dd77f12cad4e0c118f2c2f2e371a3019320906a3d2134bb933dd59c`
- P4 locked query count: 24

## Assignment

- Development (14): PQS_V1_Q003, PQS_V1_Q004, PQS_V1_Q005, PQS_V1_Q006, PQS_V1_Q007, PQS_V1_Q008, PQS_V1_Q011, PQS_V1_Q012, PQS_V1_Q013, PQS_V1_Q014, PQS_V1_Q015, PQS_V1_Q017, PQS_V1_Q018, PQS_V1_Q019
- Frozen Evaluation (10): PQS_V1_Q001, PQS_V1_Q002, PQS_V1_Q009, PQS_V1_Q010, PQS_V1_Q016, PQS_V1_Q020, PQS_V1_Q021, PQS_V1_Q022, PQS_V1_Q023, PQS_V1_Q024
- Missing queries: 0
- Duplicate assignments: 0
- Leakage groups crossing splits: 0
- Canonical Split Assignment SHA-256: `3014e941a385022abf0bef99c6d9f1d0b82b6d5e7a0b2a22d6977189c8f85239`
- Development JSONL SHA-256: `e68d6bb405bafadb56c5333834d72c8155a7a310ca2e20341df4f412488a8935`
- Frozen Evaluation JSONL SHA-256: `faf962049281cba4c8a035e64068ef91b7cfa9159ea438cfe33052a225add44f`

## Frozen Protection

The Frozen Evaluation file is sealed at `research/v3_5/product_query_set_v1/split_v1/frozen_locked/product_query_frozen_evaluation_v1.locked.jsonl`. Its access guard is `research/v3_5/product_query_set_v1/split_v1/frozen_locked/FROZEN_EVALUATION_ACCESS_GUARD.json` with status `sealed_before_formal_evaluation`.

## Isolation

No Query text or frozen metadata changed. No Gold, Target Video, subtitle, system result, or failure record was read. Retrieval, Builder, Selector, and Judge calls were zero. No Gold, Product Baseline, F1A/F1B, or Stage 4 work was started.

This is a P5 execution candidate pending V3.5-B review. No next phase is authorized.

## Mechanical Validation

```text
.venv/bin/pytest -q tests/test_pqs_v1_user_validation_and_freeze_contract.py tests/test_pqs_v1_p5_split_r2_contract.py
46 passed
```
