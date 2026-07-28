# Targeted Regression

Executed 2026-07-25 with the repository virtual environment and `PYTHONPATH` set to the repository root.

```text
pytest -q \
  tests/test_retrieval.py tests/test_dense_retrieval.py \
  tests/test_retrieval_lifecycle.py tests/test_qwen_embedding_provider.py \
  tests/test_search_api.py tests/test_product_search_api.py \
  tests/test_search_orchestration.py tests/test_search_planner.py \
  tests/test_search_consolidation.py tests/test_search_enrichment.py \
  tests/test_search_display_metadata.py tests/test_search_page.py \
  tests/test_frozen_auto_smoke_contracts.py \
  tests/test_frozen_auto_smoke_execution.py tests/test_frozen_auto_smoke_gate.py \
  tests/test_stage3r_projection_and_isolation.py \
  tests/test_stage3r_qc_phase_b_r_contracts.py \
  tests/test_stage3r_qc_phase_b_r_execution.py
```

Result: **262 passed**.

The focused Product-default subset (`test_product_search_api.py`, `test_search_page.py`, `test_search_orchestration.py`, and `test_search_planner.py`) collected 57 tests and passed as part of that run.

Validated behaviors include UI default/payload, Product API omission provenance, explicit-mode bypasses, Auto exact-entity lexical routing, Auto semantic hybrid routing, scope/filter forwarding, product/raw trace linkage, retrieval mode behavior, provider lifecycle coverage, and V3.5 isolation/frozen-history contracts.
