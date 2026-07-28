# Stage 6B Failure Cases

These are observed frozen-baseline cases, not tuning inputs for this run.

## 1. Lexical versus Dense — Q01

```json
{
  "case": "Lexical versus Dense",
  "query_id": "Q01",
  "query": "MCP",
  "gold": [
    6,
    7,
    12,
    34,
    39,
    43,
    47,
    71,
    78,
    80,
    83,
    88,
    93,
    100,
    111,
    113
  ],
  "recall_at_10": {
    "lexical": 0.5625,
    "dense": 0.5,
    "hybrid": 0.5
  },
  "auto_mode": "lexical",
  "grouping_gain_hybrid": 1,
  "implementation_bug": false,
  "v3_5_candidate": true,
  "lexical_top_video_ids": [
    78,
    43,
    71,
    80,
    7
  ],
  "dense_top_video_ids": [
    71,
    39,
    80,
    78,
    83
  ],
  "hybrid_top_video_ids": [
    71,
    78,
    80,
    39,
    83
  ],
  "auto_top_video_ids": [
    78,
    43,
    71,
    80,
    7
  ],
  "auto_planned_mode": "lexical",
  "product_window_counts": {
    "lexical": 18,
    "dense": 22,
    "hybrid": 23,
    "auto": 18
  },
  "root_cause": "Observed rank/coverage difference under exact frozen signals; no implementation defect established.",
  "recommendation": "Deferred — Needs Version-session Decision; V3.5 candidate only if the Version Session accepts the evidence."
}
```

## 2. Dense semantic gain — Q06

```json
{
  "case": "Dense semantic gain",
  "query_id": "Q06",
  "query": "MCP 与 Function Calling 的区别",
  "gold": [
    83
  ],
  "recall_at_10": {
    "lexical": 0.0,
    "dense": 1.0,
    "hybrid": 1.0
  },
  "auto_mode": "hybrid",
  "grouping_gain_hybrid": 0,
  "implementation_bug": false,
  "v3_5_candidate": true,
  "lexical_top_video_ids": [],
  "dense_top_video_ids": [
    83,
    111,
    78,
    39,
    71
  ],
  "hybrid_top_video_ids": [
    83,
    111,
    78,
    39,
    71
  ],
  "auto_top_video_ids": [
    83,
    111,
    78,
    39,
    71
  ],
  "auto_planned_mode": "hybrid",
  "product_window_counts": {
    "lexical": 0,
    "dense": 19,
    "hybrid": 19,
    "auto": 19
  },
  "root_cause": "Dense query embedding retrieves human-relevant videos missed by exact lexical matching.",
  "recommendation": "Deferred — Needs Version-session Decision; V3.5 candidate only if the Version Session accepts the evidence."
}
```

## 3. Hybrid gain — Q02

```json
{
  "case": "Hybrid gain",
  "query_id": "Q02",
  "query": "RAG",
  "gold": [
    3,
    5,
    26,
    30,
    65,
    71,
    77,
    99,
    102,
    111,
    122,
    124,
    136,
    142
  ],
  "recall_at_10": {
    "lexical": 0.6428571428571429,
    "dense": 0.7142857142857143,
    "hybrid": 0.7142857142857143
  },
  "auto_mode": "lexical",
  "grouping_gain_hybrid": 3,
  "implementation_bug": false,
  "v3_5_candidate": true,
  "lexical_top_video_ids": [
    30,
    102,
    136,
    65,
    111
  ],
  "dense_top_video_ids": [
    26,
    77,
    5,
    30,
    71
  ],
  "hybrid_top_video_ids": [
    77,
    30,
    5,
    111,
    136
  ],
  "auto_top_video_ids": [
    30,
    102,
    136,
    65,
    111
  ],
  "auto_planned_mode": "lexical",
  "product_window_counts": {
    "lexical": 10,
    "dense": 14,
    "hybrid": 14,
    "auto": 10
  },
  "root_cause": "RRF combines lexical and dense candidates; gain is measured without parameter tuning.",
  "recommendation": "Deferred — Needs Version-session Decision; V3.5 candidate only if the Version Session accepts the evidence."
}
```

## 4. Hybrid no gain or loss — Q01

```json
{
  "case": "Hybrid no gain or loss",
  "query_id": "Q01",
  "query": "MCP",
  "gold": [
    6,
    7,
    12,
    34,
    39,
    43,
    47,
    71,
    78,
    80,
    83,
    88,
    93,
    100,
    111,
    113
  ],
  "recall_at_10": {
    "lexical": 0.5625,
    "dense": 0.5,
    "hybrid": 0.5
  },
  "auto_mode": "lexical",
  "grouping_gain_hybrid": 1,
  "implementation_bug": false,
  "v3_5_candidate": true,
  "lexical_top_video_ids": [
    78,
    43,
    71,
    80,
    7
  ],
  "dense_top_video_ids": [
    71,
    39,
    80,
    78,
    83
  ],
  "hybrid_top_video_ids": [
    71,
    78,
    80,
    39,
    83
  ],
  "auto_top_video_ids": [
    78,
    43,
    71,
    80,
    7
  ],
  "auto_planned_mode": "lexical",
  "product_window_counts": {
    "lexical": 18,
    "dense": 22,
    "hybrid": 23,
    "auto": 18
  },
  "root_cause": "RRF does not improve every query and can inherit or reorder dense/lexical noise.",
  "recommendation": "Deferred — Needs Version-session Decision; V3.5 candidate only if the Version Session accepts the evidence."
}
```

## 5. Same-video grouping — Q02

```json
{
  "case": "Same-video grouping",
  "query_id": "Q02",
  "query": "RAG",
  "gold": [
    3,
    5,
    26,
    30,
    65,
    71,
    77,
    99,
    102,
    111,
    122,
    124,
    136,
    142
  ],
  "recall_at_10": {
    "lexical": 0.6428571428571429,
    "dense": 0.7142857142857143,
    "hybrid": 0.7142857142857143
  },
  "auto_mode": "lexical",
  "grouping_gain_hybrid": 3,
  "implementation_bug": false,
  "v3_5_candidate": false,
  "lexical_top_video_ids": [
    30,
    102,
    136,
    65,
    111
  ],
  "dense_top_video_ids": [
    26,
    77,
    5,
    30,
    71
  ],
  "hybrid_top_video_ids": [
    77,
    30,
    5,
    111,
    136
  ],
  "auto_top_video_ids": [
    30,
    102,
    136,
    65,
    111
  ],
  "auto_planned_mode": "lexical",
  "product_window_counts": {
    "lexical": 10,
    "dense": 14,
    "hybrid": 14,
    "auto": 10
  },
  "root_cause": "Several raw units from one video occupy raw ranks; Product grouping restores unique-video coverage.",
  "recommendation": "Delivered behavior; no change recommended from this case."
}
```

## 6. Negative-control semantic false positives — Q14

```json
{
  "case": "Negative-control semantic false positives",
  "query_id": "Q14",
  "query": "量子纠错表面码阈值如何计算？",
  "gold": [],
  "top_results": {
    "lexical": [],
    "dense": [
      91,
      90,
      39
    ],
    "hybrid": [
      91,
      90,
      39
    ]
  },
  "auto_mode": "hybrid",
  "implementation_bug": false,
  "v3_5_candidate": true,
  "lexical_top_video_ids": [],
  "dense_top_video_ids": [
    91,
    90,
    39,
    116,
    103
  ],
  "hybrid_top_video_ids": [
    91,
    90,
    39,
    116,
    103
  ],
  "auto_top_video_ids": [
    91,
    90,
    39,
    116,
    103
  ],
  "auto_planned_mode": "hybrid",
  "product_window_counts": {
    "lexical": 0,
    "dense": 23,
    "hybrid": 23,
    "auto": 23
  },
  "root_cause": "Dense similarity always returns nearest neighbors even when the corpus has no Relevant Gold.",
  "recommendation": "Deferred — Needs Version-session Decision; V3.5 candidate only if the Version Session accepts the evidence."
}
```

## 7. Negative-control semantic false positives — Q18

```json
{
  "case": "Negative-control semantic false positives",
  "query_id": "Q18",
  "query": "如何为 Kubernetes Pod 排查 CrashLoopBackOff？",
  "gold": [],
  "top_results": {
    "lexical": [],
    "dense": [
      29,
      93,
      15
    ],
    "hybrid": [
      29,
      93,
      15
    ]
  },
  "auto_mode": "hybrid",
  "implementation_bug": false,
  "v3_5_candidate": true,
  "lexical_top_video_ids": [],
  "dense_top_video_ids": [
    29,
    93,
    15,
    90,
    64
  ],
  "hybrid_top_video_ids": [
    29,
    93,
    15,
    90,
    64
  ],
  "auto_top_video_ids": [
    29,
    93,
    15,
    90,
    64
  ],
  "auto_planned_mode": "hybrid",
  "product_window_counts": {
    "lexical": 0,
    "dense": 18,
    "hybrid": 18,
    "auto": 18
  },
  "root_cause": "Dense similarity always returns nearest neighbors even when the corpus has no Relevant Gold.",
  "recommendation": "Deferred — Needs Version-session Decision; V3.5 candidate only if the Version Session accepts the evidence."
}
```

## 8. Evidence window overbreadth — Q08

```json
{
  "case": "Evidence window overbreadth",
  "query_id": "Q08",
  "query": "RAG 项目怎么做工业优化",
  "mode": "dense",
  "video_id": 30,
  "window": {
    "window_rank": 1,
    "start": 0.76,
    "end": 1368.56,
    "duration": 1367.8,
    "gold_start": 28.23,
    "gold_end": 32.96,
    "intersection": 4.73,
    "coverage": 1.0,
    "duration_over_gold": 289.1754756871036,
    "nonrelevant_fraction": 0.9965418920894867,
    "jump_time": 1285.26,
    "jump_source": "chunk_start_fallback",
    "anchor_error": 1252.3
  },
  "implementation_bug": false,
  "v3_5_candidate": true,
  "lexical_top_video_ids": [],
  "dense_top_video_ids": [
    30,
    102,
    5,
    77,
    71
  ],
  "hybrid_top_video_ids": [
    30,
    102,
    5,
    77,
    71
  ],
  "auto_top_video_ids": [
    30,
    102,
    5,
    77,
    71
  ],
  "auto_planned_mode": "hybrid",
  "product_window_counts": {
    "lexical": 0,
    "dense": 12,
    "hybrid": 12,
    "auto": 12
  },
  "root_cause": "Temporal merging joins broad adjacent chunks; this is a deferred quality limitation, not a Stage 6B implementation bug.",
  "recommendation": "Deferred — Needs Version-session Decision; V3.5 candidate only if the Version Session accepts the evidence."
}
```

