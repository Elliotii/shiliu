# Shiliu V3 Retrieval Evaluation Protocol

Status: `candidate protocol locked for Gold review`  
Protocol version: `v3-stage6-eval-protocol-v1`

This document fixes the Stage 6B measurement rules. Stage 6A does not calculate final quality metrics and does not lock Gold.

## 1. Evaluation corpus and judgments

Every run must use the immutable `shiliu_eval.db` identified by `corpus_manifest.json`. The live Product database is forbidden. A writable Backup-API derivative may be used only for isolated Raw and Presentation traces; its protected corpus/index table hashes must equal the snapshot after accounting for snapshot-only artifact path rebinding.

Judgments will be the human-reviewed pool produced from the union of Lexical, Dense, and Hybrid top-20 Product video results. Metric names and reports must say **Pooled/Judged Gold** and must not imply exhaustive judgment of every video in the corpus. Unjudged videos are not silently treated as relevant; Stage 6B must state its unjudged-item handling alongside every result table.

The 24 rows in `eval_queries.candidate.jsonl` become the Locked Query Set only after Version Session approval. The two negative controls remain in the denominator for zero-result and filter behavior, but have no relevant-video denominator for Recall or MRR.

## 2. Compared systems

- Lexical: explicit `mode=lexical`.
- Dense: explicit `mode=dense`.
- Hybrid: explicit `mode=hybrid`.

All three use the same snapshot, query, scope, filters, result limits, Product grouping, enrichment, and presentation versions. Explicit modes must execute without fallback. Auto is evaluated separately as a routing policy and is not a fourth base retriever.

## 3. Unit of relevance

A relevant video is a human-approved `video_id` for a query. A relevant interval is a human-approved closed interval `[gold_start, gold_end]` derived from authoritative raw subtitle segments. Product video order is the ranking used for video metrics. Raw-unit order is used only for duplicate/grouping analysis and trace diagnostics.

## 4. Base retrieval metrics

For a positive query with Pooled/Judged relevant set `G` and ordered Product top-K video set `R_K`:

- **Pooled/Judged Video Recall@K** = `|G ∩ R_K| / |G|`, for K=5 and K=10.
- **MRR@10** = `1/r`, where `r` is the first relevant Product video rank at or before 10; otherwise 0.
- **Hit@K** = 1 when at least one relevant Product video occurs at or before K, otherwise 0, for K=1, 5, and 10.
- **Zero-result Rate** = queries returning zero Product videos divided by all applicable queries. Report positive and negative-control strata separately.
- **Warm P50/P95 Latency** = median and linear-interpolated 95th percentile of server-side total latency after one excluded cold provider load. Use one Application/provider lifecycle, fixed execution order recorded in the run manifest, and report by explicit mode.

Macro averages give every applicable query equal weight. Also report per-category values and the applicable-query count. Negative controls are excluded from Recall/MRR/Hit denominators and reported separately.

## 5. Product-layer metrics

- **Raw Duplicate Occupancy@K (count)** = `raw_hit_count_K - unique_video_count_K`.
- **Raw Duplicate Occupancy@K (rate)** = `1 - unique_video_count_K / raw_hit_count_K`; define 0 when `raw_hit_count_K=0`. Report K=10, 20, and 50.
- **Unique Video Recall@10** = Pooled/Judged relevant unique videos among grouped Product top 10 divided by the Pooled/Judged relevant-video count.
- **Grouping Gain@10** = `relevant unique videos in grouped Product top 10 - relevant unique videos obtained by mapping Raw Unit top 10 to video_id`.
- **Relevant Window Found@N** = 1 when any of the first N returned windows for a relevant video has non-zero intersection with any approved Gold interval for that video; otherwise 0. Report N=1 and N=2 over applicable query-video pairs.
- **Window Duration Distribution** = count, min, P25, median, P75, P95, max, and histogram of `window_end-window_start` for returned windows on applicable pairs.
- **Window Overbreadth** = for a found prediction/gold pair, `max(0, predicted_duration - intersection_duration) / predicted_duration`; define only for positive predicted duration and report the best-overlap Gold interval per predicted window.
- **Precise Anchor Error** uses only anchors whose source is not `chunk_start_fallback`. For Gold `[gold_start,gold_end]`, error is 0 inside the interval, `gold_start-jump_time` before it, and `jump_time-gold_end` after it.
- **Semantic Chunk-navigation Error** applies only to `chunk_start_fallback` and uses the same distance-to-interval formula, but is reported separately and must not be called precise anchor error.
- **Filter Violation Rate** = returned videos violating at least one explicit structured filter divided by returned videos, reported overall and by filter field. A zero-result filtered query has denominator zero and is listed separately.

## 6. Auto routing policy metric

For each positive query, choose the explicit oracle retriever by lexicographically maximizing `(Pooled/Judged Video Recall@10, MRR@10)`, with mode name as a fixed final tie-break in `lexical,dense,hybrid` order. Report **Auto Oracle Gap** as the ordered pair:

```text
(oracle Recall@10 - Auto Recall@10,
 oracle MRR@10    - Auto MRR@10)
```

Also report Auto planned/executed mode, fallback, query type, routing reason, and the selected oracle mode. This definition cannot be changed during Stage 6B in response to observed results.

## 7. Interval matching and boundaries

Intervals are closed numeric second ranges from raw subtitle segment boundaries. Non-zero intersection means `max(pred_start,gold_start) < min(pred_end,gold_end)`. Touching at only one endpoint is not Found. When several Gold intervals exist, use the interval that minimizes anchor error and separately the one maximizing overlap for window metrics.

AI chapter boundaries and summaries are auxiliary presentation evidence only. They cannot create relevance, intervals, or anchor correctness.

## 8. Run controls

- Use `result_limit=20` and `max_windows_per_video=5` for pooling and retained diagnostics.
- Use explicit modes and assert `planned_mode=executed_mode=requested_mode`, `fallback=false`.
- Reuse one warm Qwen provider after a separately timed cold load.
- Record ordered video IDs, raw unit IDs, plan identity, retriever/index/model identities, timings, and bounded evidence.
- Do not tune queries, parameters, routing, retrievers, grouping, windows, or anchors after seeing metrics.
- Preserve raw per-query outputs so every aggregate can be recomputed.

## 9. Stage boundary

Stage 6A produces candidate queries, pools, suggested relevant videos, suggested raw-subtitle intervals, and a review packet only. It must not produce `eval_gold.locked.jsonl`, final Recall/MRR/Hit values, a best-retriever declaration, failure analysis, router changes, or V3 closeout.
