# P9 Candidate Design Amendment Complete

1. P9 decision and mechanism identity  
   `execute`；主机制 `bounded_candidate_pruning_coverage_gap`，次机制 `dedup_below_threshold_leaves_complement_gap`，均未改变。

2. Original candidate design supersession  
   `bounded_coverage_reserve_v1` → `superseded_before_implementation`；`implemented: false`，`evaluated: false`，原文件完整保留。

3. Active amended design  
   唯一活跃设计：`adaptive_bounded_coverage_swap_v1`；状态：`implementation_candidate`。

4. Original Top-32 preservation  
   初始集合完整保留当前 Builder 原始 Top-32；Candidate Cap 固定为 32。

5. Outside candidate eligibility  
   仅允许同一现有 Candidate Pool 中 Top-32 后的候选；必须由现有 Query Anchor、Acronym/Entity Anchor 或 Retrieval Chunk Lineage 支持；禁止 Gold、Case ID 和 Video ID 运行时信号。

6. Redundancy victim rule  
   优先替换高区间/文本重叠且独占覆盖低的候选；不固定替换第 29–32 名。

7. Marginal coverage and swap rule  
   每条 Query 自适应执行 0–4 次换位；不强制换位；每次必须带来严格集合覆盖改善并保持 Query Support Guard 和全部预算。

8. Immutable budgets and trace contract  
   Candidate 32、每 Window 6 Segments/60 秒/500 字符、总计 600 秒/6000 字符及 Selector Budget 均不变。已冻结原始 Top-32、合格外部候选、Victim 排序、逐次换位、覆盖/冗余前后值、最终集合和 No-swap Reason Trace 字段。

9. Addressable failures / Q018 non-goal / acceptance thresholds  
   可覆盖失败保持 5 条：Q003、Q004、Q005、Q008、Q015；Q018 保持 non-goal。验收门槛未改变：Complete Group ≥ `8/13`、Builder Primary Failures ≤ `4`、Span Recall ≥ `69.23%`、Aspect Coverage ≥ `69.23%`、既有 Builder Hit 回归 `0`。

10. Authority updates  
    已更新 [V3_5_CURRENT_STATE.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/V3_5_CURRENT_STATE.md)、[03_V3_5_DECISION_AND_ARTIFACT_INDEX.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/03_V3_5_DECISION_AND_ARTIFACT_INDEX.md) 和 [02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md)。下一正式步骤记录为 `F1A_IMPLEMENTATION_CONTRACT`。

11. Output paths and SHA-256  
    根目录：[design_amendment_v1](/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1)

    - `P9_CANDIDATE_DESIGN_AMENDMENT_REPORT.md` — `7bcfde2082b9898d196acdb23401a02838e1300ff8278dfe269456d92efea965`
    - `p9_candidate_design_amendment.json` — `25f8cced57e73e43704e1668cafbbfe3e6370dc39950a0314987bee25f6320e3`
    - `f1a_candidate_design.amended_v1.json` — `139129cf8c1d2f0b7b164070b727ba87ac4189948785d8bcfe5c4f7442ed3004`
    - `p9_candidate_design_amendment.manifest.json` — `2ff97267a9710dca58cb4586a7a00db8eee608f97eb26f770e8b5cb2e5e5bfc3`
    - `p9_candidate_design_amendment.audit.json` — `6635b043b40a31240dcff27cdb237fa7923d71c8175c3bacd3aef99b99abb5f8`
    - `p9_candidate_design_amendment.execution_decision.json` — `377ac08f5879b085623829549c3b76ca64c2b5cb1ebd80175982ff4b22dacc33`
    - `p9_candidate_design_amendment.file_hash_manifest.jsonl` — `9723f4641ccce74222255580aa82ec588d32ff9491ee6bc4741acadb608ef66c`
    - `V3_5_P9_CANDIDATE_DESIGN_AMENDMENT_LEDGER.json` — `a35df94c09e6d7d2be7363b21ed999007a735ff449b71b1e21575bc040ac93f4`

12. Test command and result  
    `python3.11 -m pytest -o addopts='' -q tests/test_v3_5_p9_candidate_design_amendment_contract.py tests/test_v3_5_p9_f1a_candidate_builder_decision_restart_contract.py tests/test_pqs_v1_p8_scoring_amendment_contract.py tests/test_v3_5_checkpoint_1_amendment_contract.py`  
    Result: `50 passed in 0.08s`；Hash Manifest `7/7` verified。

13. Code / Prediction / Scoring / Query / Split / Gold changed  
    `false / false / false / false / false / false`。未重跑 Prediction 或 Scoring。

14. Frozen access and downstream stage status  
    `frozen_gold_opened: false`；`f1a_implementation_authorized: false`；`f1a_implementation_started: false`；`f1a_major_cycles_remaining: 1`；`f1b_authorized: false`；`stage4_started: false`。

15. Acceptance status: pending V3.5-B review

16. Whether current Codex Session can be closed  
    `yes`
