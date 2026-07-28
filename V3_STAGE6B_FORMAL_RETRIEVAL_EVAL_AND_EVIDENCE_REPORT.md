# Shiliu V3 Stage 6B Formal Retrieval Evaluation and Evidence Report

Recommended classification: **Ready for Version Session Review with Follow-up**

## 1. Scope and Stop Boundary

This execution validated the amended human ledger, locked Gold, ran the frozen Snapshot baseline, calculated the specified discovery/evidence/product/routing/latency metrics, and produced diagnostics and failure evidence. It did not change queries, Planner, routing, fallback, retrieval, embeddings, chunking, grouping, windows, anchors, summaries, or the Web surface. It did not create `V3_CLOSEOUT.md` or start V3.5/V4.

## 2. Git and Input Audit

Execution remained on `codex/v3-domain-completion` at HEAD `8287c8d92378b87290274d02605cdc704cb8c470`. The pre-existing dirty Stage 5/6A worktree was preserved. All required ledgers, manifests, pool rows, protocols, Stage reports, and incremental-review artifacts existed and parsed.

## 3. Snapshot Identity

- Snapshot ID: `20260720T094346Z_c7663365`
- Base DB: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db`
- Base SHA-256 before/after: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`
- Eval work DB: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/eval_work_stage6b_20260720T094346Z.db`
- Artifact root: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts`
- Snapshot validation: `integrity_check=ok`, zero foreign-key violations, and `retrieval_units=FTS=Dense=1,555`.

## 4. Human Decision Ledger Validation

The amended ledger has 24 unique records covering Q01–Q24 and partitions exactly the same 452 pooled candidates once each. It contains no duplicate, missing, or out-of-pool judgment. The first ledger remains preserved.

## 5. Human Ledger Amendment Audit

- Original SHA-256: `ff14628c2f8daaa1c269e517b398847b66c3c5f7bcabaa06fe911805624bab29`
- Amended SHA-256: `e93fd09bd06151d8665f50a17cc24bc2673105d21886e77b8a4cfa12f7ba0257`
- Allowed pairs accounted for: 5/5.
- Actual label changes: 4; justified retained `U_title`: 1; unexpected changes: 0.
- Query text, eval category, expected/runtime query type, filter, held-out flag, negative-control flag, and all existing intervals remained unchanged.

The machine-readable audit is `human_ledger_amendment_audit.json`.

## 6. Five-row Incremental Review Resolution

| Query / Video | Original | Amended | Human evidence record | New interval |
|---|---|---|---|---|
| Q02 / 3 | `U_title` | `R_evidence` | chunk index 1, `104.110–181.980s` | No |
| Q07 / 44 | `U_title` | `U_title` | retained because frozen subtitle covers only `36.680/3609s` | No |
| Q07 / 45 | `U_title` | `N` | human reason recorded | No |
| Q07 / 93 | `U_title` | `R_evidence` | chunk index 2, `231.230–350.550s` | No |
| Q07 / 108 | `U_title` | `N` | human reason recorded | No |

These are accepted ledger facts, not Codex semantic reinterpretations.

## 7. Original vs Amended Label Counts

| Label | Original | Amended | Delta |
|---|---:|---:|---:|
| R_evidence | 102 | 104 | +2 |
| R_title | 6 | 6 | 0 |
| N | 335 | 337 | +2 |
| U_title | 9 | 5 | -4 |
| OOS | 0 | 0 | 0 |

## 8. Impact of Amendment on Gold

Video-discovery Gold gained Videos 3 under Q02 and 93 under Q07. Evidence-retrieval Gold gained the same two pairs. Videos 45 and 108 became judged N. Video 44 remains unjudged. No interval Gold changed; the total remains ten.

## 9. Eligibility and Filter Validation

All 452 candidates satisfy `archived=false` and `ignored=false`. Q19 folder, Q20 marked, Q21 uploader, and Q22–Q24 temporal constraints have zero violations. Favorite-time values are Unix seconds interpreted in UTC with inclusive SQL/Python comparisons: `favorite_time >= from` and `favorite_time <= to`.

## 10. Q04 Asset Inconsistency Resolution

Video 125 remains absent from the Q04 complete pool and was not added to Q04 Gold. It remains independently judged under Q24. Automated cross-file comparison found no second suggested/reviewed ID outside its query pool.

## 11. Q10 Evidence Verification

Video 135/BV1Up756vEK7 has a manifest-declared, present, parseable, SHA-matching raw subtitle. Segment indices 1–2 exactly produce `1.120–6.300s`. The source remains `authoritative_raw_subtitle`; Q10 retains `R_evidence` and its interval.

## 12. R_title / U_title Audit

All six `R_title` occurrences lack frozen raw subtitles and transcript chunks. Remaining U rows Q07/112, Q09/23, Q22/142, and Q23/41 also lack body evidence. Q07/44 is the only U row with a raw artifact and is explicitly authorized by the amended human ledger because its frozen subtitle covers only the introduction.

## 13. Gold Lock Results

Gold Lock completed with 24 queries, 452 judgments, 110 discovery-relevant occurrences (`104 R_evidence + 6 R_title`), five U rows, zero OOS rows, and ten intervals. Q14/Q18 retain empty Relevant sets.

## 14. Locked Query and Gold Schema

`eval_queries.locked.jsonl` keeps independent `eval_category`, `expected_query_type`, and `actual_query_type`. `eval_gold.locked.jsonl` keeps discovery, evidence, title-only, N, U, OOS, eligibility audit, and interval sets separately. All sets are mutually exclusive and sorted; discovery equals evidence union title-only.

## 15. Evaluation Protocol

Every mode used the same Snapshot, query, scope, filters, Product pipeline, Gold, `result_limit=10`, `max_windows_per_video=5`, and `raw_top_k=50`. Lexical/Dense/Hybrid were explicit and never fell back. Auto was evaluated only as routing policy. Each mode had one warm-up and 72 measured requests (24 queries × 3 stable repetitions).

## 16. Unjudged-item Policy

Five `U_title` candidates remain. Primary metrics are **Condensed Judged Metrics**; Conservative Lower Bound retains original ranks and treats U as non-relevant; Discovery Upper-bound Sensitivity treats U as discovery-relevant only. U never enters Evidence Gold. Full affected mode/query ranking positions are in `unjudged_sensitivity.md`; no U was silently converted to N.

## 17. Negative Controls

| Mode | Q14 results / zero | Q18 results / zero | Top results |
|---|---|---|---|
| Lexical | 0 / yes | 0 / yes | none |
| Dense | 10 / no | 10 / no | Q14 Video 91; Q18 Video 29 |
| Hybrid | 10 / no | 10 / no | Q14 Video 91; Q18 Video 29 |
| Auto | 10 / no | 10 / no | planned Hybrid for both |

Dense/Hybrid nearest-neighbor output is potentially deceptive for both negative controls; no result suppression was added to manufacture zero-result behavior.

## 18. Video Discovery Metrics

Primary Condensed Judged macro metrics over 22 positive queries:

| Mode | Recall@5 | Recall@10 | MRR@10 | Hit@1 | Hit@5 | Hit@10 | Zero-result |
|---|---:|---:|---:|---:|---:|---:|---:|
| Lexical | 0.3500 | 0.4033 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.5000 |
| Dense | 0.7840 | 0.8801 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Hybrid | 0.7840 | 0.8820 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Auto | 0.7775 | 0.8816 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |

These are pooled/judged metrics, not exhaustive-corpus recall.

## 19. Evidence Retrieval Metrics

Only `R_evidence` contributes:

| Mode | Evidence R@5 | Evidence R@10 | Evidence MRR@10 | Hit@1 | Hit@5 | Hit@10 |
|---|---:|---:|---:|---:|---:|---:|
| Lexical | 0.3654 | 0.4093 | 0.5000 | 0.5000 | 0.5000 | 0.5000 |
| Dense | 0.7777 | 0.8751 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Hybrid | 0.7868 | 0.8770 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Auto | 0.7777 | 0.8763 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

`R_title` does not improve these values.

## 20. Category-level Metrics

The complete category table is in `eval_results.csv`. Notable primary discovery Recall@10: Lexical is 0 for mixed-entity, semantic-topic-question, and evidence-lookup categories, while Dense/Hybrid reach 0.881, 0.813, and 1.000 respectively. Exact-entity Recall@10 is approximately 0.841–0.843 across the three base retrievers.

## 21. Held-out Metrics

Held-out positive discovery Recall@10 is Lexical `0.3704`, Dense `0.8972`, Hybrid `0.8995`, and Auto `0.8995`. Non-held-out anchors are Lexical `0.5513`, Dense/Hybrid `0.8036`, and Auto `0.8013`. Single- and multi-positive strata are included in JSON/CSV.

## 22. Raw Duplicate Occupancy

Mean duplicate rates at Raw @10/@20/@50 are:

| Mode | @10 | @20 | @50 |
|---|---:|---:|---:|
| Lexical | 0.1153 | 0.1319 | 0.1474 |
| Dense | 0.4847 | 0.5556 | 0.6515 |
| Hybrid | 0.4681 | 0.5535 | 0.6465 |
| Auto | 0.3417 | 0.4083 | 0.4824 |

## 23. Unique Video Recall and Grouping Gain

Discovery Unique Video Recall@10 equals Product Recall@10. Mean discovery Grouping Gain@10 is Lexical `+0.455`, Dense `+0.591`, Hybrid `+0.500`, and Auto `+0.636` relevant unique videos per positive query. Same-video grouping materially restores Product-level coverage.

## 24. Relevant Window Metrics

Across ten approved query-video pairs, Window Found@1/@2 is Lexical `0.10/0.20`, Dense `0.70/0.90`, Hybrid `0.70/1.00`, and Auto `0.60/0.80`.

## 25. Window Duration and Overbreadth

| Mode | P50 seconds | P90 | Max | >120s | >300s | Mean coverage | Mean predicted/Gold duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| Lexical | 236.25 | 249.49 | 252.80 | 0.667 | 0.000 | 0.667 | 20.85× |
| Dense | 236.12 | 582.37 | 1367.80 | 0.773 | 0.364 | 0.409 | 68.81× |
| Hybrid | 235.94 | 580.26 | 1367.80 | 0.708 | 0.333 | 0.417 | 64.09× |
| Auto | 252.80 | 623.31 | 1367.80 | 0.706 | 0.412 | 0.471 | 66.98× |

Window overbreadth is a major observed limitation. No temporal-merge change was made.

## 26. Precise Anchor Error

Precise anchors include only `exact_query_phrase`, `exact_entity_term`, and `keyword_overlap`. Median/P90 errors are Lexical `163.78/454.80s`, Dense `286.84/783.30s`, Hybrid `207.48/698.05s`, and Auto `225.31/740.68s`. Hybrid Within-5/15/30s is `0.286/0.286/0.286` over seven eligible returned windows.

## 27. Semantic Navigation Distance

`chunk_start_fallback` is reported separately and is not sentence-level precision. Dense/Hybrid median distance is `568.26s`, with Relevant Window Found `0.412`; Auto median is `570.98s`, found `0.455`. Lexical returned no semantic-fallback window on applicable pairs.

## 28. Filter Violation Rate

Violation rate is exactly zero for every mode and every explicit filter query. The current system evaluates structured filters only; it does not parse natural-language filters.

## 29. Auto Router and Oracle Gap

Query-type agreement is `24/24`. Auto’s mean fixed lexicographic Oracle Gap `(Recall@10, MRR@10)` is `(0.003247, 0.0)`. Auto matches the selected oracle on eight positive queries. Q02 is the single case where Auto chose Lexical and another mode had higher Recall@10; Q21 chose Hybrid while the fixed tie-break selected Lexical. Router behavior was not modified.

## 30. Latency and Provider Lifecycle

| Mode | Samples | P50 ms | P95 ms | Max ms |
|---|---:|---:|---:|---:|
| Lexical | 72 | 4.045 | 35.774 | 100.713 |
| Dense | 72 | 95.669 | 158.678 | 169.808 |
| Hybrid | 72 | 103.832 | 171.530 | 184.180 |
| Auto | 72 | 96.348 | 177.214 | 185.042 |

Cold Qwen load was `4470.261ms`, operational/informational only. One Application-scoped provider was reused; load count stayed 1 on MPS with no duplicate load.

## 31. Dense Truncation Analysis

Snapshot revalidation found 1,412 transcript chunks, 28 above 512 tokens (1.983%), max 547, across 13 videos. Stage 6A top-100 pooling saw truncated chunks affect 17 query IDs; Stage 6B top-50 formal runs saw truncated raw hits for fewer queries because of the smaller Raw cutoff. Some truncated videos are Relevant Gold, but frozen evidence cannot establish whether query-relevant content lies after token 512. Classification: **Needs Further Evidence**. No chunking/projection/embedding change was made.

## 32. Cross-language Diagnostic

The Snapshot records 129 `zh`, one `en`, and 14 unknown subtitle-language values, but cannot reliably distinguish original English, author Chinese, platform translation, or English ASR. No Chinese-query/English-subtitle pair is Relevant Gold, so cross-language Recall is **Unknown**. Read-only retrieval observations are in `cross_language_diagnostic.md`; no translation was generated.

## 33. AI Summary Diagnostic

Frozen video units include title (143), description (127), AI conclusion/key-points/detailed-notes (102 each), entities (94), and AI chapters (101), plus other metadata. AI chapters participate in lexical video-unit text but are excluded from the frozen Dense projection quota policy. Video-unit-only raw hits include both relevant and N cases, demonstrating discovery help and misleading recall potential. AI content is never used as interval/anchor Gold; raw subtitle/ASR remains timing and citation authority.

## 34. Failure Cases

Eight factual cases cover lexical/dense differences, Dense semantic gain, Hybrid gain/no-gain, same-video grouping, both negative controls, and window overbreadth. Each records explicit-mode top IDs, Auto choice, Product-window counts, root cause, bug status, and V3.5 candidacy in `failure_cases.md`. No implementation bug was established; quality findings remain deferred.

## 35. Regression Tests

| Exact command | Exit | Passed | Failed | Skipped | Warnings |
|---|---:|---:|---:|---:|---:|
| `.venv/bin/python -m pytest tests/test_eval_gold_lock.py -q` | 0 | 3 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_metrics.py -q` | 0 | 4 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_runner.py -q` | 0 | 3 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_reporting.py -q` | 0 | 2 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_snapshot.py -q` | 0 | 2 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_query_schema.py -q` | 0 | 2 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_candidate_pool.py -q` | 0 | 2 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_review_packet.py -q` | 0 | 1 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_product_search_api.py -q` | 0 | 11 | 0 | 0 | 1 |
| `.venv/bin/python -m pytest tests/test_search_enrichment.py -q` | 0 | 75 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_search_consolidation.py -q` | 0 | 10 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest -q` | 0 | 518 | 0 | 0 | 7 |

The full-suite command used no `PYTHONPATH`. Warnings are the known Starlette/httpx deprecation and six multiprocessing/fork deprecations. One preliminary new-test run exposed only an exact-float assertion issue; the test was minimally corrected to use approximate comparison, without changing metrics or formal results.

## 36. Product and Index Integrity

Snapshot SHA and protected Eval work corpus/index hashes remained unchanged. Eval work counts stayed 144 videos and 1,555 units/FTS/vectors; only isolated traces changed from `82→374` Raw and `52→344` Presentation. Live counts stayed 144/1,555/1,555/1,555 and Live traces stayed `82/52`; Live protected hashes were unchanged during formal execution.

## 37. Delivered / Degraded / Deferred Findings

- **Delivered:** amended-ledger audit, deterministic Gold, Snapshot isolation, explicit-mode/Auto evaluation, two relevance layers, three U policies, category/held-out strata, grouping/filter/latency evidence, stable repetitions, complete tests.
- **Degraded:** Lexical does not serve semantic/mixed/evidence queries under exact phrase semantics; Dense/Hybrid negative controls return misleading nearest neighbors; evidence windows are broad; anchor precision is weak.
- **Deferred:** default-mode/routing product decision, negative-control rejection policy, window/anchor changes, Dense truncation causality, cross-language translation/indexing, summary-field policy, any V3.5 work.

## 38. Recommended V3 Decisions

The Version Session should treat Dense/Hybrid recall evidence as delivered but separately judge operational latency and negative-control behavior. Same-video grouping and structured filters have positive evidence. Window and anchor quality should not be accepted as precise evidence navigation without follow-up. Keep all algorithm changes outside this baseline run.

## 39. Exact Questions for Version Session

1. Should Dense/Hybrid retrieval evidence be accepted while retaining or changing the current default-mode policy?
2. Is always-return-nearest-neighbors behavior on negative controls acceptable, or should a future calibrated rejection policy be scoped?
3. Are current window and anchor metrics acceptable as coarse navigation only, or should they be degraded/deferred to V3.5?
4. Does the 28-chunk truncation overlap justify a targeted evidence study before changing chunking/embedding policy?
5. Should cross-language retrieval remain Unknown for V3 and translation/index work be deferred?
6. Is a small closure session required before V3 closeout, and which findings are accepted, degraded, or deferred?

## 40. Recommended Classification

**Ready for Version Session Review with Follow-up**

Human Ledger Amendment: Validated  
Gold Lock: Completed  
Stage 6B Formal Evaluation: Delivered  
V3 Closeout: Not Started

## 41. Stop Boundary

Stage 6B stops here. No `V3_CLOSEOUT.md` exists, no V3 acceptance is declared, and no retrieval-quality issue was repaired or tuned. The next action belongs to the V3 Version Session.
