# Unjudged-item Sensitivity

Remaining U_title items are never silently treated as N. Primary results use condensed judged ranks; conservative results retain original ranks with U non-relevant; discovery upper-bound treats U as discovery-relevant only.

## condensed_judged

| Mode | N | R@5 | R@10 | MRR@10 | H@1 | H@5 | H@10 | Zero |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical | 22 | 0.350 | 0.403 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| dense | 22 | 0.784 | 0.880 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| hybrid | 22 | 0.784 | 0.882 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| auto | 22 | 0.777 | 0.882 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |

## conservative_lower_bound

| Mode | N | R@5 | R@10 | MRR@10 | H@1 | H@5 | H@10 | Zero |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical | 22 | 0.350 | 0.403 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| dense | 22 | 0.784 | 0.880 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| hybrid | 22 | 0.784 | 0.882 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| auto | 22 | 0.777 | 0.882 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |

## discovery_upper_bound

| Mode | N | R@5 | R@10 | MRR@10 | H@1 | H@5 | H@10 | Zero |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical | 22 | 0.335 | 0.386 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| dense | 22 | 0.750 | 0.860 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| hybrid | 22 | 0.750 | 0.862 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| auto | 22 | 0.744 | 0.862 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |

Unjudged count: 5. Affected mode-query runs: 6. Ranking positions: `{"auto/Q07": [9], "auto/Q09": [10], "dense/Q07": [9], "dense/Q09": [10], "hybrid/Q07": [9], "hybrid/Q09": [10]}`.
