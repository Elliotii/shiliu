P8 Product Initial Baseline Complete

1. Input, code, config, index, snapshot and component identity: verified; Authority Index `13e792…8421`; commit `91a3406`; snapshot `20260720T094346Z_c7663365`, 143 videos / 1,412 chunks
2. Development query count and Frozen access: 14; Frozen Query runs `0`; Frozen Gold accessed `false`
3. Prediction run count and Prediction Freeze Seal SHA-256: 14/14 complete terminal Predictions and Traces; `069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617`
4. Development Gold first-open proof: Seal `2026-07-26T16:16:32.152Z`; first open `2026-07-26T16:16:59.818Z`; Prediction hash unchanged
5. Retrieval metric summary: Hit@1/3/5/10 = `71.43% / 92.86% / 92.86% / 100%`; Known Relevant Recall@1/3/5/10 = `67.86% / 89.29% / 92.86% / 100%`; empty results `0`; all 14 routed Hybrid
6. Candidate Builder metric summary: complete-group coverage `6/14 (42.86%)`; required-span recall `65.38%`; required-aspect coverage `60.71%`; invalid candidates `0`
7. Deterministic Selector metric summary: bundle hit `1/14 (7.14%)`; complete group available but not selected `5`; required-span recall `12.18%`; required-aspect coverage `11.31%`; compactness `83.10%`
8. Mechanical Gate metric summary: judge eligible `13`; terminal unverifiable `1`; invalid source `1`; invalid decisions `0`
9. Unjudged pair count: `109`
10. Bounded Reviewer outcomes: acceptable relevant `0`; explicit not relevant `0`; semantic-boundary unresolved `108`; source-blocked unresolved `1`
11. Unresolved Unjudged count: `109`
12. Decision-sensitive Unjudged count: `0`
13. Determinate query count and metric interval: `14` determinate, `0` indeterminate; Hit@1/3/5/10 lower–upper intervals equal `71.43% / 92.86% / 92.86% / 100%`
14. Development Retrieval Pool Addendum status: `development_retrieval_pool_addendum.v1` fixed and hashed; base Gold unchanged; no Unjudged item automatically treated as negative
15. Primary Failure Distribution: `candidate_builder_failure=7`, `deterministic_selector_failure=5`, `source_unverifiable=1`, `end_to_end_bundle_hit=1`
16. Stress Regression status: reused separately from frozen Corrected Stress Track A; Product Benchmark `false`; optimization authority `false`
17. Output paths and SHA-256: [Attempt 3 output](/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3); Scores `30cce533…466d`; [Report](/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/closeout/PRODUCT_INITIAL_BASELINE_REPORT.md) `4e0cd6a8…08c6`; Manifest `64241190…9be7`; Execution Decision `b479fb05…46e1`; File Hash Manifest `af3291a9…e646`
18. Test command and result: `.venv/bin/python -m pytest -q tests/test_pqs_v1_p8_product_initial_baseline_contract.py tests/test_pqs_v1_p5_split_r2_contract.py tests/test_pqs_v1_p6_gold_protocol_contract.py tests/test_pqs_v1_development_gold_seal_contract.py tests/test_pqs_v1_p7_final_closeout_contract.py tests/test_product_search_api.py tests/test_v3_5_stage3b_selector.py tests/test_v3_5_stage4a_gate.py tests/test_stage3r_track_a_auto_refresh_contracts.py` — `185 passed`
19. Functional component behavior changed: false; evaluation terminal serialization changed: true, as authorized
20. Query / Split / Gold changed: false
21. F1A / F1B / Stage 4 work started: false
22. Acceptance status: pending V3.5-B review
23. Current Codex Session can be closed: yes
