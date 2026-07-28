# V3 Stage 6B Evaluation Summary

Status: **Delivered** — pooled/judged frozen-Snapshot evaluation; not V3 acceptance.

## Condensed Judged Video Discovery Metrics

| Mode | N | R@5 | R@10 | MRR@10 | H@1 | H@5 | H@10 | Zero |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical | 22 | 0.350 | 0.403 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| dense | 22 | 0.784 | 0.880 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| hybrid | 22 | 0.784 | 0.882 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| auto | 22 | 0.777 | 0.882 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |

## Condensed Judged Evidence Retrieval Metrics

| Mode | N | R@5 | R@10 | MRR@10 | H@1 | H@5 | H@10 | Zero |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical | 22 | 0.365 | 0.409 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| dense | 22 | 0.778 | 0.875 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| hybrid | 22 | 0.787 | 0.877 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| auto | 22 | 0.778 | 0.876 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |

## Product evidence summary

| Mode | Window@1 | Window@2 | Duration P50 | Duration P90 | Max | Precise anchor median | Semantic navigation median |
|---|---:|---:|---:|---:|---:|---:|---:|
| lexical | 0.100 | 0.200 | 236.25 | 249.49 | 252.8 | 163.78 | None |
| dense | 0.700 | 0.900 | 236.1245 | 582.3749 | 1367.8 | 286.84 | 568.26 |
| hybrid | 0.700 | 1.000 | 235.94 | 580.2647 | 1367.8 | 207.48 | 568.26 |
| auto | 0.600 | 0.800 | 252.8 | 623.3114 | 1367.8 | 225.31 | 570.981 |

## Routing and operations

- Query type agreement: 24/24 (1.000).
- Mean Auto Oracle Gap `(Recall@10, MRR@10)`: `[0.003247, 0.0]`.
- Latency: `{"auto": {"count": 72, "max": 185.042333, "p50": 96.348229, "p95": 177.2136}, "dense": {"count": 72, "max": 169.808292, "p50": 95.66852, "p95": 158.678435}, "hybrid": {"count": 72, "max": 184.1795, "p50": 103.832104, "p95": 171.52995}, "lexical": {"count": 72, "max": 100.712625, "p50": 4.04475, "p95": 35.773633}}`.
- Cold Qwen load (informational): 4470.261 ms; provider load count 1.
- Filter violations: zero in all modes.
- Remaining unjudged candidates: 5; see `unjudged_sensitivity.md`.
- Classification: **Ready for Version Session Review with Follow-up**.
