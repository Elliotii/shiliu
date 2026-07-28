# V3.5 Stage 3R Track A Auto Product Refresh

Status: **Stage 3R-QC-R Complete**. The run used the 20 frozen Evidence-bearing cases, each original query, and a ProductSearchRequest with the `mode` field omitted. Backend default: `auto`; wiring: `v3-product-search-default-auto-v1`.

## Input and Runtime

- Evidence-bearing cases: 20/20. Original Query used for every request: yes. `mode` omitted: yes. Backend Auto Default applied: yes.
- Router: `unversioned:SearchPlanner@sha256:0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e`. Index/snapshot: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1` / `20260720T094346Z_c7663365`. Lexical: `v3-stage1-lexical-v1`. Dense provider/model/RRF: `v3-qwen3-embedding-provider-v1` / `Qwen/Qwen3-Embedding-0.6B` / `v3-stage2-rrf-v1`.
- Builder/normalization: `stage3b-acronym-w3.5-v1` / `v3.5-stage3b-asr-acronym-anchor-v1`. Selector/policy: `v3.5-deterministic-fine-selector-v1` / `v3.5-deterministic-fine-selector-v1`.
- No configuration or algorithm was modified; the router, retrieval, builder, selector, and index remained frozen.

| Metric | Historical Explicit Lexical Track A | Corrected Product-default Auto Track A |
| --- | ---: | ---: |
| Target Video Recall | 0/20 | 20/20 |
| Complete Gold Group Candidate Coverage | 0/20 | 11/20 |
| Bundle Hit | 0/20 | 1/20 |

Router distribution: `{'lexical': 0, 'hybrid': 20, 'dense': 0, 'other': 0}`. Target-rank distribution: `{'rank_1': 15, 'rank_1_to_3': 4, 'rank_1_to_5': 1, 'rank_1_to_10': 0, 'miss': 0}`.

Empty results: `0`. Router misses: `0`.

Builder conditional coverage given target-video retrieval: `11/20`. Selector conditional bundle hit given a complete candidate group: `1/11`.

Failure attribution: retrieval `0`, builder `9`, selector `10`, end-to-end hits `1`, blocked `0`. Total: 20/20. Builder failures are target-video hits without a complete Gold Group; selector failures are complete-group candidate sets whose selected bundle missed every complete Gold Group.

The frozen Oracle-video Track B remains a conditional diagnostic only: 11/20 complete candidate coverage and 2/20 bundle hits. It is not an end-to-end Product result. The historical 0/20 lexical result is consistent with the prior Product-default lexical wiring; this refresh attributes all 20 historical target-video misses to that historical default path, not to the frozen Auto run.

Product Query Set/F1A/F1B: not started. Held-out: not accessed. Structured LLM selector, sufficiency judge, final-answer, external LLM, and external network calls: all 0 (`{'product_search_calls': 20, 'router_calls': 20, 'lexical_effective_calls': 0, 'hybrid_effective_calls': 20, 'dense_effective_calls': 0, 'candidate_builder_calls': 20, 'deterministic_selector_calls': 20, 'structured_llm_selector_calls': 0, 'sufficiency_judge_calls': 0, 'final_answer_calls': 0, 'external_llm_calls': 0, 'external_network_calls': 0, 'heldout_accessed': False}`). This evaluation is complete and intentionally stops for human review; it does not authorize closing the Codex session.

The historical lexical assets were read-only and retained. This refresh is a new frozen baseline and stops for human review.
