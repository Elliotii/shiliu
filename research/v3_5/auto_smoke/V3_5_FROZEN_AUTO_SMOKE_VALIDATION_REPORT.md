# V3.5 Frozen Auto Smoke Validation Report

## Input

- Phase A case set: 10 cases, aligned: True
- Approved Q1/Q2: `research/v3_5/stage3r_qc/phase_b/input_freeze/approved_query_decisions.jsonl`; SHA-256 `d8e60a5525556a02b454508bc8a6f0915fd6402724713389e7a2d34264484f9a`
- Approved queries modified: False
- Exact-entity queries: 3; frozen sources recorded in the selection manifest

## Runtime

- Auto Router: `unversioned:SearchPlanner@sha256:0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e` via `SearchPlanner.plan`
- Router invoked for all logical executions: True
- Router decision/effective mode consistent: True
- Index/Snapshot identity: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`
- Embedding: `v3-qwen3-embedding-provider-v1` / `Qwen/Qwen3-Embedding-0.6B`
- RRF: `v3-stage2-rrf-v1`
- Retrieval configuration modified: False
- Product default modified: False

## Execution

- Logical Q0/Q1/Q2: 10/10/29
- Preflight / formal new calls / total actual new calls: 2/52/54
- Exact-query reuses: 0
- Router Q0: {'lexical': 0, 'hybrid': 10, 'dense': 0, 'other': 0}
- Router Q1: {'lexical': 1, 'hybrid': 9, 'dense': 0, 'other': 0}
- Router Q2: {'lexical': 0, 'hybrid': 29, 'dense': 0, 'other': 0}
- Router Exact: {'lexical': 3, 'hybrid': 0, 'dense': 0, 'other': 0}
- Embedding calls: 49
- Provider initialization/reuse: 1/48
- Latency: {'q0': {'count': 10, 'median_ms': 128.183, 'p95_ms': 166.713, 'max_ms': 166.713}, 'q1': {'count': 10, 'median_ms': 113.29, 'p95_ms': 183.943, 'max_ms': 183.943}, 'q2': {'count': 29, 'median_ms': 106.574, 'p95_ms': 169.285, 'max_ms': 173.108}, 'exact_entity': {'count': 3, 'median_ms': 23.855, 'p95_ms': 79.87, 'max_ms': 79.87}, 'lexical_routed': {'count': 4, 'median_ms': 13.15, 'p95_ms': 79.87, 'max_ms': 79.87}, 'hybrid_routed': {'count': 48, 'median_ms': 111.167, 'p95_ms': 173.108, 'max_ms': 183.943}}
- Runtime errors / external calls: 0/0
- Held-out accessed: false

## Recall

- Frozen Lexical Q0/Q1/Q2: 0/9, 0/9, 0/9
- Frozen Hybrid Q0/Q1/Q2: 9/9, 9/9, 9/9
- Auto Q0: 9/9
- Auto Q1: 8/9
- Auto Q2: 9/9
- Router misses: 1 (['V2C_C0C_958161474678bd3f'])

## Exact Entity

- Total: 3
- Routed lexical/hybrid: 3/0
- Auto target hits / Lexical control target hits: 3/3
- Clear regressions / runtime failures: 0/0

## Insufficient Diagnostic

- Case: `C2C_ee3fac675fc7d408`
- Auto Q0/Q1/Q2 hit: True/True/True
- Excluded from main recall because its frozen role is `insufficient_diagnostic`; this only reports topic discovery.

## Release Gate

- Status: **passed**
- Failure class: None
- Hybrid fallback recommendation: None
- Router modified: false
- Human review required: True
- Product default may be changed now: False
- Current Codex session should close: true
