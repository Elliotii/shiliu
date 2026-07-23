# V3.5 Stage 3R-QC Phase B-R Mode-Corrected Diagnostic Report

## Status

Stage 3R-QC Phase B-R Complete

Ready for Human Mode-corrected Diagnostic Review

## Product Path

- Main page path: `search.html -> search.js -> POST /api/search -> ProductSearchRequest -> ProductSearchService -> SearchOrchestrator`.
- Frontend explicitly sends mode: `true`.
- Frontend initial/default mode: `lexical`.
- Backend schema default: `lexical`.
- View P effective mode: `lexical`; Auto router invoked: `false`.
- View P equals View L by all effective runtime fields: `true`.
- Product results were reused from frozen lexical results; Product was not rerun.

## Runtime Preflight

- Snapshot/index identity: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.
- Lexical index: `v3-stage1-lexical-v1`; Hybrid fusion: `v3-stage2-rrf-v1`.
- Dense provider/model: `v3-qwen3-embedding-provider-v1` / `Qwen/Qwen3-Embedding-0.6B`.
- Corpus: `143` videos, `1412` chunks; dense vectors `1555` at `512` dimensions.
- Known-positive `Q01 / MCP`: lexical `10` results; product reused lexical; hybrid `10` results.
- Runtime/index/scope failure: `false`.
- Retrieval configuration modified or index rebuilt: `false`.

## Execution

- View L: fully reused from Phase B/Q0 baseline; new calls `0`.
- View P: fully reused from View L; new calls `0`.
- View H formal logical/unique/new/cache: `49` / `49` / `49` / `0`.
- Local query embedding calls: formal `49`, preflight `1`; embedding cache hits `0`.
- External calls: `0`; held-out access: `false`; candidate builder/selector calls: `0`.

## Recall Matrix

| View | Q0 | Q1 | Q2 |
|---|---:|---:|---:|
| L Explicit Lexical | 0/9 (0.0%) | 0/9 (0.0%) | 0/9 (0.0%) |
| P Product Default | 0/9 (0.0%) | 0/9 (0.0%) | 0/9 (0.0%) |
| H Explicit Hybrid | 9/9 (100.0%) | 9/9 (100.0%) | 9/9 (100.0%) |

Empty-result comparisons are frozen in `analysis/empty_result_matrix.json`.

## Query Contract

- Product Q1 recovery over Q0: `0`.
- Product Q2 additional recovery: `0`.
- Hybrid Q1 recovery over Q0: `0`.
- Hybrid Q2 additional recovery: `0`.

## Retrieval Mode

- Lexical-to-Product recovery: `0`.
- Product-to-Hybrid recovery: `9`.
- Persistent across modes: `0`.
- When Product misses and Hybrid hits, Product used explicit lexical; no Auto router decision withheld Hybrid.

## Insufficient Diagnostic

`C2C_ee3fac675fc7d408` is reported separately and excluded from all n=9 recall denominators. Its result only diagnoses whether a natural discovery query retrieves the topic video, not whether that video establishes time savings or error-rate claims.

## Historical Interpretation

Phase B lexical execution, empty-result metrics, input freeze, and runtime audit remain valid. Its global `persistent_retrieval_gap` attribution is superseded because only Explicit Lexical was run. Stage 3R Track A represents the current product default only because current code resolves Product Default to the same effective lexical configuration.

## Decision

- `frozen_hybrid_capable_but_product_default_gap`

This diagnostic stops for human review. It does not authorize Router changes, Product Query Set work, F1A/F1B, Stage 4, or V4.
