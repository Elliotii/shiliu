# Scope and Isolation Audit

| Check | Result |
| --- | --- |
| SearchPlanner / Auto Router rules or thresholds modified | No |
| Retrieval algorithm, Qwen provider, BM25, RRF, Top-K, filters, scope, index, or chunking modified | No |
| Frozen `research/v3_5/stage3r/**`, `stage3r_s1/**`, `stage3r_qc/**`, or `auto_smoke/**` assets modified | No |
| Index rebuilt | No |
| Stress Track A started | No |
| Product Query Set started | No |
| F1A / F1B started | No |

The only compatibility change outside the product wiring surface is the explicit lexical mode in the Stage 3A historical replay source. This prevents an old internal caller from silently adopting the new Product API default.
