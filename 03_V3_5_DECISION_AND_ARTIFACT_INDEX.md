# 03 — V3.5 Decision and Artifact Index

> **文件名**：`03_V3_5_DECISION_AND_ARTIFACT_INDEX.md`  
> **文档状态**：Final，当前决策与 Artifact 索引权威  
> **文档职责**：V3.5-B 的决策状态、当前事实、版本、精确路径与 Hash 索引  
> **版本范围**：Shiliu V3.5 — Evidence Resolution and Sufficiency  
> **编制日期**：2026-07-27（F1A Preimplementation Recovery Amendment）  
> **下一版本负责人**：V3.5-B  
> **Artifact Inventory 记录数**：97  
> **未解决事实**：0

---

## F1A Preimplementation Recovery Amendment Authority

```yaml
execution_status: complete
acceptance_status: pending_v3_5_b_review
recovery_amendment_status: execution_candidate_ready

P9_decision: execute
active_design: adaptive_bounded_coverage_swap_v1
current_builder: stage3b-acronym-w3.5-v1

F1A:
  previous_attempt: invalid_preimplementation_attempt
  previous_attempt_reusable: false
  prior_session_must_close: true
  implementation_authorized: true
  implementation_started: false
  major_cycles_used: 0
  major_cycles_remaining: 1
  major_cycle_1_restart_authorized: true
  restart_is_second_cycle: false
  second_major_cycle_authorized: false
  next_execution_requires_new_session: true

filesystem_access:
  default: deny
  policy: research/v3_5/product_query_set_v1/f1a_preimplementation_recovery_amendment/F1A_RECOVERY_FILESYSTEM_ACCESS_POLICY.json
  repository_recursive_search_forbidden: true
  frozen_path_patterns_forbidden: true
  missing_exact_path_blocks: true

design_changed: false
acceptance_thresholds_changed: false
F1B_authorized: false
Stage4_started: false
next_formal_step: F1A_MAJOR_CYCLE_1_RECOVERY_EXECUTION
```

The Blocking Report is reclassified only with respect to attempt and
Major-Cycle accounting. Its incident evidence remains authoritative. No P8,
Checkpoint 1, P9, Candidate Design, Builder, Prediction, Scoring, Query, Split,
or Gold content is changed by this Amendment.

### Recovery Amendment Artifact Inventory

| Artifact | Status | Version | Repository path | SHA-256 | Meaning |
|---|---|---|---|---|---|
| Recovery Amendment Report | `unreviewed_execution_candidate` | `v3.5-b-f1a-preimplementation-recovery-v1` | `research/v3_5/product_query_set_v1/f1a_preimplementation_recovery_amendment/F1A_PREIMPLEMENTATION_RECOVERY_AMENDMENT_REPORT.md` | `1c9a23c925b90a5204e803a1db7b9e830eff3136f18ac9fc5d54c071b4eceb90` | incident verification and recovery consolidation |
| Recovery Manifest | `unreviewed_execution_candidate` | `v3.5-b-f1a-preimplementation-recovery-v1` | `research/v3_5/product_query_set_v1/f1a_preimplementation_recovery_amendment/f1a_preimplementation_recovery.manifest.json` | `8496ee20cbc4cc8bff7e46aa2f04985e00d9ce249dd294b9b304c4750bb8c422` | authority, input, and output identity |
| Recovery Audit | `unreviewed_execution_candidate` | `v3.5-b-f1a-preimplementation-recovery-v1` | `research/v3_5/product_query_set_v1/f1a_preimplementation_recovery_amendment/f1a_preimplementation_recovery.audit.json` | `27b5cc59dcb335184387ff53ccd6cbead1f4046ee0a498ae3abb73b68da2c492` | incident, scope, and isolation proof |
| Recovery Execution Decision | `unreviewed_execution_candidate` | `v3.5-b-f1a-preimplementation-recovery-v1` | `research/v3_5/product_query_set_v1/f1a_preimplementation_recovery_amendment/f1a_preimplementation_recovery.execution_decision.json` | `880560690cdd5c133f4c9aca5df33ceeb28a76b0f9073824bdf05288a88a44b5` | recovered Major Cycle 1 entry decision |
| Recovery Hash Manifest | `unreviewed_execution_candidate` | `v3.5-b-f1a-preimplementation-recovery-v1` | `research/v3_5/product_query_set_v1/f1a_preimplementation_recovery_amendment/f1a_preimplementation_recovery.file_hash_manifest.jsonl` | `59aa5d635bf51a03b3dd0f4201e533ca20d1cbf40a11397a7df808b48929c466` | verifies all sibling recovery outputs except itself |
| Recovery Amendment Ledger | `accepted_task_contract` | `v3.5-b-f1a-preimplementation-recovery-v1` | `research/v3_5/product_query_set_v1/f1a_preimplementation_recovery_amendment/V3_5_F1A_PREIMPLEMENTATION_RECOVERY_AMENDMENT_LEDGER.json` | `b04e68b13202be71f9623c3bfe03dcb34168eb7c4203e3a0fa5f8a9e1c70db06` | authoritative ledger copied byte-for-byte |
| Recovery Filesystem Policy | `accepted_task_contract` | `v1` | `research/v3_5/product_query_set_v1/f1a_preimplementation_recovery_amendment/F1A_RECOVERY_FILESYSTEM_ACCESS_POLICY.json` | `5ee37aece383d0c7f52da66e24303da1b8aae27c1fab935553bc0b655104c635` | frozen default-deny access contract copied byte-for-byte |

---

## 0. 文档边界

本文件只回答：

```text
当前哪些决定有效？
当前哪些组件、评测与交接资产是权威？
需要下钻时应读取哪个仓库文件？
```

本文件不负责：

- 复述 V3.5 的完整阶段历史；
- 规定 V3.5-B 的全部权限与禁止项；
- 展开 Product Query Set、F1A/F1B、Stage 4–6 的具体执行步骤；
- 充当 V3.5-B 的启动 Prompt。

对应职责分别由以下文件承担：

| 领域 | 正式文件 |
|---|---|
| V3.5-A 历史、收口与交接原因 | `00_V3_5_A_CLOSEOUT_AND_V3_5_B_HANDOFF.md` |
| V3.5-B 权限、Stage Gate、Stop Rule 与隔离 | `01_V3_5_B_OPERATING_CONTRACT.md` |
| Product Query Set 与剩余执行计划 | `02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md` |
| 当前事实、Decision Ledger、版本和 Artifact | **本文件** |
| 新 Session 的首轮行为 | `04_V3_5_B_START_PROMPT.md` |

---

## 1. Authority Model

正式交接包获主 Session 批准后，发生冲突时按**领域**确定权威，不使用一个文件覆盖所有问题。

| 冲突类型 | 第一权威 | 说明 |
|---|---|---|
| V3.5-B 可以或禁止做什么 | `01` | Operating Contract 决定权限 |
| 当前状态、版本、路径、Hash、Artifact 状态 | `03` | 本文件决定事实 |
| 下一阶段的输入、输出、Gate 和 Stop Rule | `02` | Remaining Plan 决定执行顺序 |
| 为什么形成当前决定 | `00` | Handoff 解释因果历史 |
| 新 Session 第一轮应如何响应 | `04` | Start Prompt 只控制启动行为 |

旧聊天、旧 Task Packet、历史阶段报告和 `V3_5_CURRENT_STATE.md` 下方的历史快照，不得覆盖最终交接包。

### 1.1 当前机器可读事实权威

```yaml
current_fact_freeze:
  repository_path: research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.r2.json
  sha256: 01189effe05e75af0736d388f996801fbae16fe90264638c00c4ddecf986226e
  status: current_source_of_truth
  schema_or_policy_version: h0-r2

current_state:
  repository_path: V3_5_CURRENT_STATE.md
  sha256: 92b77a1f26df6fe589366966a8d3cec11ad15e7d57d45e7ce308d54612e82ed6
  status: current_source_of_truth
```

`V3_5_CURRENT_STATE.md` 顶部 `F1A Preimplementation Recovery Amendment` 是当前运行状态候选；其下所有旧 Stage 状态、下一步、旧授权、预算和 `Held-out` 表述均是不可用于授权新工作的历史快照。

### 1.2 编制前归一化

H0-R2 已确认事实一致、无未决事实。本文件进一步吸收两项已批准的 Preflight 归一化：

1. R2 Authority Inventory 与 Hash Inventory 的实际记录数均为 **32**；H0-R2 Report 中的“31 records”是过时摘要，不作为当前计数。
2. Fact Freeze 权威链统一为：

```text
H0 Fact Freeze
→ H0-R1 Fact Freeze
→ H0-R2 Fact Freeze
```

只有 H0-R2 保持 `current_source_of_truth`；H0 与 H0-R1 均为 `superseded`。

---

## 2. Terminology Registry

### 2.1 当前术语

```yaml
active_term: Frozen Evaluation Set
```

历史资产中的下列名称只作为历史字段或别名保留：

```yaml
historical_aliases:
  - Held-out
  - Blind Held-out
  - Independent Held-out
```

不得用历史别名建立新的治理规则。

### 2.2 Stage 2R-B0 与 Stage 3R-PQS-B0 名称

必须区分：

```text
Stage 2R-B0
= Eval v2 Reviewer Clean Restart / Preflight 历史阶段

Stage 3R-PQS-B0
= Product Query Set Neutral Authoring Packet Export
```

当前剩余路线中的 B0 一律写作 `Stage 3R-PQS-B0`。

### 2.3 Eval 视图

| 名称 | 当前定位 |
|---|---|
| Eval v1 | 18-Case 历史实现基线 |
| Evidence Sufficiency Stress Set v2 | 31-Case 复杂证据压力集 |
| Product Query Set v1 | 尚未冻结的产品问题评测集 |
| Frozen Evaluation Set | Product Query Set 冻结后形成、开发期不可见 Gold 的正式评测分区 |

---

## 3. Current Frozen State

```yaml
checkpoint_1_amendment:
  status: complete_and_accepted
  acceptance_status: accepted

P7:
  status: complete_and_accepted
  package_version: PQS_V1_PRODUCT_GOLD_V1

P8_prediction_set:
  status: valid_and_frozen
  formal_attempt: P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3
  prediction_count: 14
  prediction_freeze_seal_sha256: 069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617
  frozen_query_runs: 0
  frozen_gold_accessed: false
  functional_component_behavior_changed: false
P8_original_scoring:
  status: superseded_by_scoring_amendment
  reason: builder_failure_eligibility_defect

P8_scoring:
  original_status: superseded_by_scoring_amendment
  current_version: P8_SCORING_AMENDMENT_V1

P8_scoring_amendment:
  version: v3.5-p8-scoring-amendment-v1
  status: amendment_execution_candidate_ready
  scoring_hash_root: 54bc35083f4410ace027452b64fc2d22432111be5a2036c0ce245e6319849795
  amended_baseline:
    retrieval_hit_at_10: 1.0
    primary_retrieval_failures: 0
    candidate_builder_complete_group_coverage: 6/13
    candidate_builder_required_span_recall: 0.6538461538461539
    candidate_builder_required_aspect_coverage: 0.6538461538461539
    candidate_builder_primary_failures: 6
    selector_bundle_hit: 1/13
    selector_required_span_recall: 0.12179487179487179
    selector_required_aspect_coverage: 0.12179487179487179
    selector_primary_failures: 5
    gate_invalid_decisions: 0
    primary_failure_distribution:
      candidate_builder_failure: 6
      deterministic_selector_failure: 5
      source_unverifiable: 1
      gold_defined_evidence_absent: 1
      end_to_end_bundle_hit: 1

governance:
  retrieval_reopen_by_default: false
  F1A_entry_signal: true
  F1A_authorized: false
  F1A_implementation_started: false
  F1A_major_cycles_max: 1
  F1A_major_cycles_used: 0
  F1A_major_cycles_remaining: 1
  F1B_candidate_signal: true
  F1B_authorized: false
  mechanical_gate_repair_signal: false
  frozen_gold_sealed: true
  Stage4_started: false
  P9_status: complete_and_accepted
  P9_decision: execute
  P9_design_amendment_status: execution_candidate_ready
  accepted_failure_mechanism:
    primary: bounded_candidate_pruning_coverage_gap
    secondary: dedup_below_threshold_leaves_complement_gap
  addressable_failure_count: 5
  q018_non_goal: true
  active_f1a_candidate_design: adaptive_bounded_coverage_swap_v1
  superseded_f1a_candidate_design: bounded_coverage_reserve_v1
  next_formal_step: F1A_IMPLEMENTATION_CONTRACT
```

---

## 4. Decision Ledger

状态词只使用：

```yaml
decision_status:
  - accepted
  - corrected
  - current_source_of_truth
  - historical
  - superseded
  - rejected
  - paused
  - not_started
  - accepted_task_contract
  - unreviewed_execution_candidate
```

| Decision | Status | Current authoritative meaning |
|---|---|---|
| V3.5 Mission = Evidence Resolution and Sufficiency | `accepted` | 将冻结 V3 SearchCandidateSet 转换为可审计 EvidenceBundle，并形成后续 SufficiencyDecision |
| 原字幕/ASR 是证据与时间权威 | `accepted` | 标题、描述、AI Summary、AI Chapter 仅作发现与导航 |
| V3 Retrieval Baseline 保持冻结 | `accepted` | 不重调 FTS5、Embedding、RRF、Router、Chunk、Ranking、Index 或 Filter |
| Product Default = Auto | `current_source_of_truth` | 前端初始模式和后端 omitted-mode 均为 Auto |
| Auto Router 本身未调参 | `accepted` | Product Default 接线不等于 Router 规则修改 |
| 旧 Explicit Lexical Track A `0/20` | `historical` | 只描述旧产品入口，不得用于声称 V3 Retrieval 整体失效 |
| Query Rewrite 是恢复 Stress Recall 的必要条件 | `rejected` | Hybrid/Auto 下 Original Query 已找回目标视频 |
| Eval v1：18 Master / 8 Dev / 10 Frozen Evaluation | `historical` | 保留为第一版协议、实现和机械 Gate 基线 |
| 31-Case Corpus | `current_source_of_truth` | 正式定位为 Evidence Sufficiency Stress Set v2，不是 Product Benchmark |
| Canonical Segment Scoring Identity | `current_source_of_truth` | `source_artifact_id + source_version + timeline_run_id + segment_ordinal` |
| Candidate Builder | `current_source_of_truth` | 当前版本 `stage3b-acronym-w3.5-v1` |
| Deterministic Fine Selector | `current_source_of_truth` | 当前版本 `v3.5-deterministic-fine-selector-v1` |
| Structured LLM Selector v1 | `rejected` | 初始有效 `0/5`，Repair 后有效 `3/5`；不得原样复活 |
| Mechanical Gate v1 | `historical` | 机械基线有效，但不能替代 Semantic Sufficiency Judge；需 Stage 4A-R |
| Corrected Auto Stress Track A | `current_source_of_truth` | `20/20 → 11/20 → 1/20`，当前瓶颈在 Builder / Selector |
| Oracle-video Track B | `historical` | 条件诊断路径，不是端到端结果，也不是 Auto Track A 的严格单调上限 |
| Legacy Product Query 40 条 | `historical` | 只作第二阶段 Reconciliation 参考，不是 Search Log 或正式 Product Set |
| Product Query Set v1 | `not_started` | 最终集合尚未冻结 |
| Product Query Authoring 定位 | `accepted` | Scenario-grounded、Library-grounded、Independent、User-validated |
| Product Query Authoring 轮数 | `accepted` | Pass 1 Independent Authoring 一轮；Pass 2 Legacy Reconciliation 一轮；User Validation / Revision 一轮 |
| Product Query Set 数量 | `accepted` | 最少 20、目标 24、最多 24 |
| Independent Product Query Session Prompt | `not_started` | 不由 V3.5-A 生成；V3.5-B 仅在 Stage 3R-PQS-B0 Review Gate 通过后，根据实际 Neutral Packet 生成 |
| Stage 3R-PQS-B0 Task Contract | `accepted_task_contract` | 合同已恢复并冻结 |
| Stage 3R-PQS-B0 Execution Candidate | `unreviewed_execution_candidate` | 仓库已有声称完成的结果，但仅 V3.5-B 可验收 |
| F1A Candidate Builder Repair | `not_started` | P9 已接受 `execute`；实施仍未授权，须先形成 `F1A_IMPLEMENTATION_CONTRACT` |
| F1B Selector Repair | `paused` | 必须等 Product Initial Baseline 与 F1A 决策完成 |
| F1A/F1B 修复周期 | `accepted` | 每项最多一个 Major Cycle；可以执行、跳过、拒绝或 `record_as_limitation` |
| Retrieval Gold / Evidence Gold / Sufficiency Gold 分层 | `accepted` | 三层 Gold 不得混为一个 Target-video Truth |
| Retrieval Gold 穷尽全库 | `rejected` | Product Retrieval Gold 是 bounded / pooled judgment，`exhaustive=false` |
| Frozen Evaluation Set 用于开发调参 | `rejected` | 开发期不得读取 Gold、Relevant Video、Evidence Group、Required Span 或正式结果 |
| Stage 4B Semantic Sufficiency Judge | `not_started` | Evidence Resolution 稳定后才允许进入 |
| Stage 4B Development Revision Budget | `accepted` | Initial Semantic Baseline 后最多一次 substantive generic revision；机械 Schema Repair 不得规避该上限 |
| Frozen Evaluation Formal Run Budget | `accepted` | 最多一次有效正式运行；结果暴露后禁止调参，无效运行是否重跑由 Main Session 决定 |
| V3.5 Final Answer Generation | `rejected` | V3.5 只输出 Evidence 和 Sufficiency，不生成最终答案 |
| Agentic Search / Memory / Harness | `rejected` | 属于后续版本，不进入 V3.5 |
| V3.5-B Context Checkpoints | `accepted` | Product Query Set + Initial Baseline、F1A/F1B 决策、Stage 4B Development 三个节点必须更新 Current State、Decision Ledger、Artifact Index 与 Remaining Plan |
| V3.5-A 交接后继续版本决策 | `rejected` | 正式交接后 V3.5-B 是唯一版本负责人 |
| V3.5-A Session Closeout | `accepted` | A 可以收口 |
| V3.5 Version Closeout | `not_started` | 整个版本仍需由 V3.5-B 完成 |
| P7 Product Gold Construction and Sealing | `accepted` | `PQS_V1_PRODUCT_GOLD_V1` 已正式接受；Development 14 与 Frozen 10 均已密封 |
| P8 Attempt 1 | `historical` | 无效安全阻塞记录；不是正式 Baseline |
| P8 Attempt 2 | `historical` | `invalid_incomplete_attempt`；9 条局部 Prediction 仅作不可修改失败审计，不进入评分 |
| P8 Attempt 3 Prediction Set | `accepted` | 唯一正式冻结 Prediction Set；14 条 Prediction；Seal `069fcf9e…04617` |
| P8 Attempt 3 Original Scoring | `superseded` | 因 Builder Failure Eligibility 缺陷被 `v3.5-p8-scoring-amendment-v1` 取代；原文件保留 |
| P8 Scoring Amendment v1 | `accepted` | 通用零 acceptable-group 资格修复；Scoring Hash Root `54bc3508…9795` |
| Product Initial Baseline Retrieval | `accepted` | Hit@10 `14/14`、Primary Retrieval Failure `0`；默认不重开 Retrieval 或 Router |
| F1A Candidate Builder Entry Signal | `accepted` | Amendment 后真实 Builder Primary Failure `6`，Entry Signal 保持 true；F1A 尚未授权 |
| F1B Deterministic Selector Candidate Signal | `accepted` | Selector Primary Failure `5` 且完整 Group 未选中 `5`；须等待 P9，F1B 尚未授权 |
| Product Initial Baseline Mechanical Gate | `accepted` | Invalid Decision `0`；当前无 Gate Repair Signal |
| Frozen Gold after P8 | `current_source_of_truth` | 保持密封；P8 Frozen Query runs `0`、Frozen Gold access `false` |
| Checkpoint 1 Original Derived Findings | `superseded` | 仅 P8 scoring 派生数字被 Checkpoint 1 Amendment v1 取代；P7 与冻结 Prediction 身份不受影响 |
| Checkpoint 1 Amendment v1 | `accepted` | `complete_and_accepted`；P8 Amendment 派生数字已成为当前权威 |
| P9 F1A Candidate Builder Decision | `accepted` | `execute`；接受主机制 `bounded_candidate_pruning_coverage_gap`、次机制 `dedup_below_threshold_leaves_complement_gap`；5 条可覆盖、Q018 为 non-goal |
| F1A Candidate Design `bounded_coverage_reserve_v1` | `superseded` | 在实施前被 Amendment 取代；`implemented=false`、`evaluated=false` |
| P9 Candidate Design Amendment v1 | `unreviewed_execution_candidate` | 唯一活跃设计 `adaptive_bounded_coverage_swap_v1`；F1A 实施尚未授权 |
| Stage 4A-R / Stage 4B after Checkpoint 1 | `not_started` | 均未授权、未启动 |

Checkpoint 1 Amendment 的历史停止点保持为 `P9_restarted: false`；随后
发生的 P9 Restart 已完成并接受，不回写或改写该历史审计事实。

---

## 5. Oracle-video Track B `2/20` 与 Corrected Auto Track A `1/20`

### 5.1 Hit Case IDs

```yaml
oracle_video_track_b_bundle_hits:
  - V2C_C0C_5725899059df795c
  - V2C_C0C_8228254ff69d7b3b

corrected_auto_track_a_bundle_hits:
  - V2C_C0C_9618a83c9df4f059

intersection: []
```

### 5.2 精确差异

| Case | Oracle-video Track B | Corrected Auto Track A | Exact reason |
|---|---|---|---|
| `V2C_C0C_5725899059df795c` | Complete Gold Group；Bundle Hit | Complete Gold Group；Selector Failure | 两条路径都有完整 Gold Group，但 Auto Selector 没有选中命中 Bundle，归因为 `complete_gold_group_available_but_not_selected` |
| `V2C_C0C_8228254ff69d7b3b` | Complete Gold Group；Bundle Hit | Builder Failure | Auto 找到目标视频 Rank 1，但只覆盖 `7/8` Gold Segment，归因为 `target_video_retrieved_without_complete_gold_group` |
| `V2C_C0C_9618a83c9df4f059` | 无 Complete Gold Group；Bundle Miss | Complete Gold Group；Bundle Hit | Auto 候选路径形成了 Oracle Track B 历史运行中没有形成的完整 Gold Group |

权威 Case-level 审计：

```text
research/v3_5/handoff_draft/fact_freeze/
track_b_vs_auto_bundle_hit_diff.audit.json
```

正式解释：

> Oracle-video Track B 是固定目标视频条件下的历史诊断路径，不是 Corrected Auto Product Track A 的严格单调上限。两条路径的运行输入和 CandidateSet 可以不同，因此其 Bundle Hit 不具有集合包含关系。

---

## 6. Version and Policy Registry

### 6.1 Evidence identity and mapping

| Contract / Policy | Version |
|---|---|
| Source Artifact Identity | `v3.5-source-identity-v2` |
| Source Version Authority | `v3.5-source-version-authority-v1` |
| Timeline Policy | `v3.5-timeline-policy-v1` |
| Exact Chunk Mapping | `v3.5-exact-chunk-mapping-v1` |
| Frozen Transcript Chunk Policy | `v3-frozen-transcript-chunk-policy-v1` |
| Frozen Chunker Replay | `v3.5-frozen-chunker-replay-v1` |
| SearchCandidateSet | `v3.5-search-candidate-v1` |
| Search Trace Policy | `v3.5-search-trace-policy-v1` |
| Canonical Scoring Identity Bridge | `v3.5-stage3r-segment-identity-bridge-v1` |

Source Identity v1 是 Gold Lock 前的 provisional 版本，已被 Source Identity v2 supersede。

### 6.2 Evidence resolution and sufficiency

| Component | Current version / state |
|---|---|
| Candidate Builder | `stage3b-acronym-w3.5-v1` |
| ASR Acronym Normalization | `v3.5-stage3b-asr-acronym-anchor-v1` |
| Deterministic Fine Selector | `v3.5-deterministic-fine-selector-v1` |
| Structured LLM Selector v1 | `rejected` |
| Mechanical Sufficiency Gate | `v3.5-mechanical-sufficiency-gate-v1` — historical |
| Product Default Wiring | `v3-product-search-default-auto-v1` |
| Corrected Stress Auto Refresh | `v3.5-stage3r-track-a-auto-refresh-v1` |

### 6.3 Eval

| Eval asset | Version / identity |
|---|---|
| Eval v1 Gold Lock | `v3.5-gold-lock-v1` |
| Stress Set v2 executable manifest | `v3.5-stage2r-final-executable-31-v1` |
| Stress Set v2 canonical corpus content SHA-256 | `a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148` |
| Active evaluation term | `Frozen Evaluation Set` |

---

## 7. Supersession and Historical-status Map

```text
Source Identity v1
→ superseded by Source Identity v2

Historical Product Default Lexical
→ superseded by Product Default Auto
→ wiring version v3-product-search-default-auto-v1

Historical Explicit Lexical Stress Track A
→ retained as historical precondition
→ superseded for product capability claims by Corrected Auto Track A

Eval v1
→ retained as historical implementation baseline
→ not deleted
→ not the current Stress Set or Product Query Set

31-Case Eval v2 Corpus
→ retained as Evidence Sufficiency Stress Set v2
→ not superseded by Product Query Set
→ serves a different evaluation role

Product Query Phase A / Phase A-R
→ retained as legacy reference
→ not the final Product Query Set

H0 Fact Freeze
→ superseded by H0-R1

H0-R1 Fact Freeze
→ superseded by H0-R2

H0-R2 Fact Freeze
→ current handoff fact source of truth
```

---

## 8. Artifact Index

本节的 SHA-256 均为当前仓库文件的 byte-level SHA-256；若存在独立 canonical content hash，会在 Notes 中单独标明。

### 8.1 Current handoff authority

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| V3.5 current state | `current_source_of_truth` | `F1A Preimplementation Recovery Amendment` | `V3_5_CURRENT_STATE.md` | `92b77a1f26df6fe589366966a8d3cec11ad15e7d57d45e7ce308d54612e82ed6` | current F1A recovery execution-candidate state |
| H0-R2 fact freeze | `current_source_of_truth` | `h0-r2` | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.r2.json` | `01189effe05e75af0736d388f996801fbae16fe90264638c00c4ddecf986226e` | corrected handoff facts |
| H0-R2 execution audit | `accepted` | `h0-r2` | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze_r2_execution.audit.json` | `08653df1d369fd794340ec679de9d1964ff8db873caa16c8f7ef22a808019603` | H0-R2 audit |
| H0-R2 report | `accepted` | `h0-r2` | `research/v3_5/handoff_draft/fact_freeze/HANDOFF_FACT_FREEZE_R2_REPORT.md` | `091fc61f86f853d94e10e4b168860a429c8501e6eb05ae0bdcd91014fa5ffa4a` | H0-R2 report |

### 8.2 Eval v1 historical baseline

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Eval v1 protocol | `accepted` | `not_embedded` | `research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md` | `01f1dd8d6f26bd68962ccb42b489f5be3d086cef2ed0fe90616cb9d3e43db90f` | Eval v1 protocol |
| Eval v1 master split | `accepted` | `not_embedded` | `research/v3_5/gold/master_case_membership.locked.json` | `e95e23e6f9d4043b01d43e04c7a53ed56fe7577d2a1bcfc0b7b8996d12d60a93` | Eval v1 master split |
| Eval v1 development split | `accepted` | `not_embedded` | `research/v3_5/gold/development_gold.8_cases.locked.jsonl` | `5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0` | development split |
| Eval v1 frozen evaluation split | `accepted` | `not_embedded` | `research/v3_5/gold/heldout_gold.10_cases.locked.jsonl` | `6b7d06a6a0f3eeb61a9bc542ee8c2a8d12fc6d52fbb6576f64eff72d0d662789` | frozen evaluation split; No evaluation was run or interpreted. |
| Eval v1 gold lock | `accepted` | `v3.5-gold-lock-v1` | `research/v3_5/gold/gold_lock_manifest.json` | `268d9b68e29cc7f242375ba108d9d99ef536e2f413c3747d9f95f7ab97588075` | gold lock; Historical field held_out is an alias; active handoff term is frozen_evaluation_set. |

### 8.3 Stress Set v2

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Stress set v2 manifest | `current_source_of_truth` | `v3.5-stage2r-final-executable-31-v1` | `research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.manifest.json` | `bc557d87f6c457aba74af06ee6c3408399b619cb3a21b3f13411f1173923da5f` | 31-case stress identity; Canonical corpus content hash is recorded separately.; content/manifest SHA-256 `a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148` |
| Stress set v2 corpus | `accepted` | `not_embedded` | `research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.jsonl` | `a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148` | 31-case stress corpus; Canonical corpus content hash is distinct from file SHA-256. |

### 8.4 Evidence identity and search contracts

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Stage 1A source identity | `accepted` | `not_embedded` | `V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md` | `51d49541c2bbda28b96618b7df6299ea060135be5e25aecdbbd4dd69f471931d` | source identity |
| Stage 1B search contract | `accepted` | `not_embedded` | `V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md` | `606a86078f61ad7c564a7c673b247e88314cc26630d6a85c176d67b968f7220f` | search contract |
| Stage 3R-S1 canonical segment identity | `current_source_of_truth` | `v3.5-stage3r-segment-identity-bridge-v1` | `research/v3_5/stage3r_s1/contracts/segment_identity_bridge_contract.json` | `daa53e497bbb7da315f645e7016d5394e9fab86ff0c4fe45daf335720cea2668` | scoring identity; source_artifact_id + source_version + timeline_run_id + segment_ordinal |

### 8.5 Active evidence-resolution components

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Candidate Builder | `current_source_of_truth` | `stage3b-acronym-w3.5-v1` | `src/shiliu/evidence/stage3b.py` | `8a2ed841efdf42f048347bf23ed1170a67ce7be0f3b03823eabef31847a80458` | candidate construction |
| Normalization policy | `accepted` | `v3.5-stage3b-asr-acronym-anchor-v1` | `research/v3_5/stage3b/stage3b_run_manifest.json` | `74a6e5cc2fef342b77022257ae4b623423342c8fc94adc74208e6028c728aba8` | candidate normalization |
| Deterministic selector | `current_source_of_truth` | `v3.5-deterministic-fine-selector-v1` | `src/shiliu/evidence/stage3a.py` | `34774d6c166680e7523010f9d1d950f9aa1b890487f46427279164cdedaed552` | fine selection |
| Structured LLM selector v1 | `rejected` | `not_embedded` | `research/v3_5/stage3b/structured_selector_contract.json` | `a5ab067151f06aa3417b1f2cd305146a1667b59655be47a2647a6965dedbaf2a` | evaluated selector; preferred_selector: deterministic |
| Mechanical Gate v1 | `historical` | `v3.5-mechanical-sufficiency-gate-v1` | `research/v3_5/stage4a/mechanical_gate_contract.json` | `f255c42a46825b77f45b7d8c54b1f5746cfed2f5d8d501a4cb9aef6d09b93051` | mechanical baseline; requires_stage4a_r: true |

### 8.6 Product search and corrected stress baseline

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Product Default Auto wiring | `current_source_of_truth` | `v3-product-search-default-auto-v1` | `research/v3_5/product_default_auto_wiring/product_default_auto_wiring_manifest.json` | `5d5d42ad7501f8a9d917a17b7b6116da4f84f3d5d974f8a54e3dbcd88cb588f9` | product default; router_modified: false; retrieval_modified: false |
| Frozen Auto Smoke | `accepted` | `not_embedded` | `research/v3_5/auto_smoke/frozen_auto_smoke_manifest.json` | `565c1ff6209143c386bef8ddb308d9cf9e0ab5f793be59d45fb8fe90fc7c04ea` | frozen Auto smoke |
| Corrected Stress Track A | `current_source_of_truth` | `v3.5-stage3r-track-a-auto-refresh-v1` | `research/v3_5/stage3r_qc/track_a_auto_refresh/stage3r_track_a_auto_refresh_manifest.json` | `f09a6895ffb4d3bc3112871fadf3962815aa93054c174d13f08da2cf05f92ad9` | corrected product Auto stress; 20/20 → 11/20 → 1/20 |
| Historical Oracle-video Track B | `historical` | `not_embedded` | `research/v3_5/stage3r_s1/rescore/track_b_metrics.json` | `4b2816b194cbc66fcb6dfd9c04f59c6509df3ae9c3f5d7b3ee64e96e4ab84ea4` | conditional Oracle diagnostic; 11/20 coverage; 2/20 bundle hit; never end-to-end. |

### 8.7 Product Query preparation

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Product Query Phase A | `historical` | `not_embedded` | `research/v3_5/product_query_set_v1/phase_a/product_query_set_phase_a_manifest.json` | `8fdf1e9d78eb7ff863ef98a6ad0922fa285358ab56962ed0d2253e9447be2274` | legacy_product_query_reference_only; Not the final Product Query Set. |
| Product Query Phase A-R | `historical` | `not_embedded` | `research/v3_5/product_query_set_v1/phase_a_r/product_query_set_phase_a_r_manifest.json` | `806f78e93c617e7c4b0b71ad0db4e10ecb36015e4ed7a574e9f1dd4f1fc181dd` | legacy_product_query_reference_only; Not the final Product Query Set. |
| Stage 3R-PQS-B0 Neutral Authoring Packet Export Task | `accepted_task_contract` | `not_embedded` | `research/v3_5/product_query_set_v1/authoring_packet/STAGE3R_PQS_B0_NEUTRAL_AUTHORING_PACKET_EXPORT_TASK.md` | `2e2eea765e7400141b715cea77c89e0e88f98ef3f9d1f69b468110acf8dc1cc0` | V3.5-B task contract; Restored byte-for-byte from approved Session text. |
| Stage 3R-PQS-B0 execution candidate report | `unreviewed_execution_candidate` | `not_embedded` | `research/v3_5/product_query_set_v1/authoring_packet/V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md` | `fe9033d74f2820cc37f1051409cc25af29561b8c4aa0abd13986f5249f8bf7aa` | B0 execution candidate; Report claim: complete; acceptance: unreviewed; owner: v3_5_b. |

### 8.8 Handoff audit history

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| H0 fact freeze | `superseded` | `not_applicable` | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.json` | `17811fe8fad57d3f0850c24afa5868b94790d46b9204132716f9e1d5eb084959` | historical_draft_audit; Superseded by H0-R1; retained only as historical audit evidence. |
| H0 report | `historical` | `not_applicable` | `research/v3_5/handoff_draft/fact_freeze/HANDOFF_FACT_FREEZE_REPORT.md` | `91e5abb8f61556143792beefadd61f3de0089d35ea728387c072829d422d3576` | historical_draft_audit; superseded_by: h0_r_corrected_fact_freeze |
| H0-R fact freeze | `superseded` | `h0-r1` | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.r1.json` | `8e9bb58ff6f6be3fe791803e1638ca50a20a85ffdf752a9889be024a9088826c` | corrected handoff facts; Superseded by H0-R2. The R2 inventory retained a stale `current_source_of_truth` status; this handoff index applies the approved preflight normalization. |
| H0-R execution audit | `accepted` | `h0-r1` | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze_r1_execution.audit.json` | `c5a85def10fa5837a3b97b2ba48ac2dc49bad52d0dd79ce540c788f9d03ba502` | H0-R execution audit |
| H0-R report | `accepted` | `h0-r1` | `research/v3_5/handoff_draft/fact_freeze/HANDOFF_FACT_FREEZE_R1_REPORT.md` | `3dbae1c23c2482ebf29445032f52c8b78182e6e727b56c26a6217025bc10c084` | H0-R report |

### 8.9 P7 Product Gold Package

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| P7 aggregate package manifest | `accepted` | `PQS_V1_PRODUCT_GOLD_V1` | `research/v3_5/product_query_set_v1/gold_construction_v1/p7_final_closeout/p7_product_gold_v1.manifest.json` | `afad8112a6667fc465f7d8a1c7fc44cb22fca93759b425ef9f83203f1ed515df` | P7 accepted aggregate identity |
| P7 closeout report | `accepted` | `PQS_V1_PRODUCT_GOLD_V1` | `research/v3_5/product_query_set_v1/gold_construction_v1/p7_final_closeout/P7_PRODUCT_GOLD_CLOSEOUT_REPORT.md` | `edf4c0c2c4dd543e72ae256a6c75ec7e00a9a2472d672ebd22af51e5ce153863` | mechanical closeout |
| Development Gold seal | `accepted` | `DEVELOPMENT_GOLD_V1` | `research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1/development_gold_v1.seal.json` | `1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a` | 14-query Development seal |
| Frozen Gold seal | `current_source_of_truth` | `FROZEN_GOLD_V1` | `research/v3_5/product_query_set_v1/gold_construction_v1/frozen_guarded/frozen_cycle_v1/internal_protected/frozen_gold_v1.seal.json` | `166e7c463de06e31d6c831d97c00f54dcf149312fb77cb66505bf15985c584a8` | 10-query sealed; content not opened by Checkpoint 1 |

### 8.10 P8 Product Initial Baseline

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Attempt 3 Input Manifest | `accepted` | `P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/blind_run/product_initial_baseline.input_manifest.json` | `c5316a7451ac2a0b9e63d77b4c2e42dadb0886bd24fd477ef69c5462028dcc53` | blind input identity |
| Attempt 3 Predictions | `accepted` | `P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/blind_run/product_initial_baseline.predictions.jsonl` | `b34f173ac99208f4adb72966880ab7e9cf97d3e27157084792502f103e709038` | 14 frozen predictions |
| Attempt 3 Trace Root | `accepted` | `P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/blind_run/product_initial_baseline.traces/` | `f8636d55680e4e3ef72b196f31afe8743c692d48c66ed0a647443679e7353071` | canonical root hash from Prediction Seal |
| Attempt 3 Prediction Seal | `accepted` | `P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/blind_run/product_initial_baseline.prediction_freeze.seal.json` | `069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617` | sealed before Development Gold open |
| Attempt 3 Scores | `superseded` | Product Initial Baseline original scoring | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring/product_initial_baseline.scores.json` | `30cce533265015cfcc5fd35992e43583d9f2a968928d2e012a9f49ee6c07466d` | preserved; superseded_by_scoring_amendment |
| Attempt 3 Per-query | `superseded` | Product Initial Baseline original scoring | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring/product_initial_baseline.per_query.jsonl` | `0c91f361c2ea2091e796960dc2d7a1995336f14a548034263d13635accda892d` | preserved; superseded_by_scoring_amendment |
| Attempt 3 Failure Attribution | `superseded` | Product Initial Baseline original scoring | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring/product_initial_baseline.failure_attribution.jsonl` | `75924ba07023825a44fe7d0d2ab78a22798edb680eb5251238f61afe25292865` | preserved; Builder eligibility defect |
| Attempt 3 Unjudged Pool | `accepted` | Product Initial Baseline | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/unjudged/product_initial_baseline.unjudged_pool.jsonl` | `a5b61b57fb7b037a0e7404c2868c8c26b7c646c5a5fe46e1daae69b61cb78aa9` | 109 pairs |
| Development Retrieval Pool Addendum | `accepted` | `development_retrieval_pool_addendum.v1` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/unjudged/development_retrieval_pool_addendum.v1.jsonl` | `5b93da12cdb47188c65e22f8de2449a9b48645e2f5c6e9aa641c29f6db330ce0` | unresolved items retained explicitly |
| Attempt 3 Stress Regression | `accepted` | Stress Set v2 regression | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/stress_regression/stress_set_v2_regression.initial_product_baseline.json` | `a8c5855ab8b91222fd016d0d700b90ae335c4a7d150bd82d819e270f08bf97b6` | separate from Product Benchmark |
| Attempt 3 Report | `superseded` | Product Initial Baseline original derived findings | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/closeout/PRODUCT_INITIAL_BASELINE_REPORT.md` | `4e0cd6a87303561fb09700580837d12fef09a6fc65ab315253e56c00dbfd08c6` | preserved; scoring-derived findings superseded |
| Attempt 3 Manifest | `superseded` | Product Initial Baseline original derived findings | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/closeout/product_initial_baseline.manifest.json` | `64241190018e694d7004be7fd0e52bc313d6e6122389c8bced23497e1acf9be7` | preserved; Prediction identity remains valid |
| Attempt 3 Execution Decision | `historical` | Product Initial Baseline original execution | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/closeout/product_initial_baseline.execution_decision.json` | `b479fb053ad364fa9f06cb448752541a49ddb0069bd32e3428566072fbd646e1` | original execution retained; scoring amended |
| Attempt 3 Hash Manifest | `historical` | Product Initial Baseline original package | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/closeout/product_initial_baseline.file_hash_manifest.jsonl` | `af3291a9e5e1a4a1567943fc311896cda54f4692c1970719ab4c4776c4c5e646` | preserves original 33/33 identities |

### 8.11 P8 Scoring Amendment v1

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| P8 Scoring Amendment Report | `unreviewed_execution_candidate` | `v3.5-p8-scoring-amendment-v1` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/P8_SCORING_AMENDMENT_REPORT.md` | `292d823e3eb3345b320659afde2fc4cfaf3a001cef3e56904989d233a122c656` | generic eligibility repair summary |
| Amended Scores | `unreviewed_execution_candidate` | `v3.5-p8-scoring-eligibility-v2` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/p8_scoring_amendment.scores.json` | `8271d68f7942f960650b1638330935fa3d1298702893d61133cbf8598ed425ec` | explicit per-metric denominators |
| Amended Per-query | `unreviewed_execution_candidate` | `v3.5-p8-scoring-eligibility-v2` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/p8_scoring_amendment.per_query.jsonl` | `f3e886735ae8400c9e42e59312660e3de84b8b05008de42aa52046740259d108` | 14 eligibility-valid query rows |
| Amended Failure Attribution | `unreviewed_execution_candidate` | `v3.5-p8-scoring-eligibility-v2` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/p8_scoring_amendment.failure_attribution.jsonl` | `2f6fc2b4cd10c8240d1395d096f7dcf7c97bafde43026d0df0e454e50ea3d7a9` | one primary outcome per query |
| P8 Scoring Amendment Manifest | `unreviewed_execution_candidate` | `v3.5-p8-scoring-amendment-v1` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/p8_scoring_amendment.manifest.json` | `183c562e949999b631ec147eacab5c336e08ab5d425e723d67ad6e629e3edb5e` | Scoring Hash Root `54bc3508…9795` |
| P8 Scoring Amendment Audit | `unreviewed_execution_candidate` | `v3.5-p8-scoring-amendment-v1` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/p8_scoring_amendment.audit.json` | `fa7fb2d3d4167b9a25f4fe9251d28e2629ccc5f059cefd94451a051cdd2a49f9` | immutable-input and scope proof |
| P8 Scoring Amendment Execution Decision | `unreviewed_execution_candidate` | `v3.5-p8-scoring-amendment-v1` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/p8_scoring_amendment.execution_decision.json` | `2237383507b1b4d7c4a315467f6540e8d6e7fa690ee386d67c575480fe36503c` | pending V3.5-B review |
| P8 Scoring Amendment Decision Ledger | `accepted_task_contract` | `v3.5-b-p8-scoring-amendment-v1` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/V3_5_P8_SCORING_CHECKPOINT_1_AMENDMENT_DECISION_LEDGER.json` | `2c8c8502da58e835cf23d7d6c6df41f2e5bde7484cee7a9ab9fe3def23bfc5e9` | authoritative ledger copied byte-for-byte |
| P8 Scoring Amendment Hash Manifest | `unreviewed_execution_candidate` | `v3.5-p8-scoring-amendment-v1` | `research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/scoring_amendment_v1/p8_scoring_amendment.file_hash_manifest.jsonl` | `0d1b6a8a22a6ff11c0334c0aa412f12feafa97c2acd0d4f56eb5938cd18b140c` | verifies all Amendment outputs except itself |

### 8.12 Original Checkpoint 1

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Checkpoint 1 Report | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-v1` | `research/v3_5/checkpoints/checkpoint_1/CHECKPOINT_1_REPORT.md` | See `checkpoint_1.file_hash_manifest.jsonl` | generated by this checkpoint |
| Checkpoint 1 Manifest | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-v1` | `research/v3_5/checkpoints/checkpoint_1/checkpoint_1.manifest.json` | See `checkpoint_1.file_hash_manifest.jsonl` | reference-only manifest |
| Checkpoint 1 Audit | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-v1` | `research/v3_5/checkpoints/checkpoint_1/checkpoint_1.audit.json` | See `checkpoint_1.file_hash_manifest.jsonl` | scope and identity proof |
| Checkpoint 1 Execution Decision | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-v1` | `research/v3_5/checkpoints/checkpoint_1/checkpoint_1.execution_decision.json` | See `checkpoint_1.file_hash_manifest.jsonl` | pending V3.5-B review |
| Checkpoint 1 Decision Ledger | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-v1` | `research/v3_5/checkpoints/checkpoint_1/V3_5_CHECKPOINT_1_DECISION_LEDGER.json` | See `checkpoint_1.file_hash_manifest.jsonl` | authoritative input copied byte-for-byte |
| Checkpoint 1 Hash Manifest | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-v1` | `research/v3_5/checkpoints/checkpoint_1/checkpoint_1.file_hash_manifest.jsonl` | self-hash intentionally excluded | verifies all other Checkpoint 1 outputs |

The original Checkpoint 1 package is retained. Its P8 scoring-derived findings
are `superseded_by_checkpoint_1_amendment_for_derived_findings`; its P7 and
frozen P8 Prediction identities remain valid.

### 8.13 Checkpoint 1 Amendment v1

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Checkpoint 1 Amendment Report | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-amendment-v1` | `research/v3_5/checkpoints/checkpoint_1/amendment_v1/CHECKPOINT_1_AMENDMENT_REPORT.md` | `6be88e8bc4ebfe0e9f28fbb0a4719a94118bac3a8e4060241c069249d31795b6` | amended derived findings |
| Checkpoint 1 Amendment Completion Response | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-amendment-v1` | `research/v3_5/checkpoints/checkpoint_1/amendment_v1/CHECKPOINT_1_AMENDMENT_COMPLETION_RESPONSE.md` | `59be3309b91fa9a1a2eb22aa0580ed3323f4fe7e321c51c4976d8abf0553dacf` | formal 14-item completion response |
| Checkpoint 1 Amendment Manifest | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-amendment-v1` | `research/v3_5/checkpoints/checkpoint_1/amendment_v1/checkpoint_1_amendment.manifest.json` | `cbf210691bc8d0881eedd39e9d286db064d9453d3d26675baa0bba7fd508e1a6` | references P8 Scoring Hash Root |
| Checkpoint 1 Amendment Audit | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-amendment-v1` | `research/v3_5/checkpoints/checkpoint_1/amendment_v1/checkpoint_1_amendment.audit.json` | `9853847a73eff4e65e03cb1f33cc63e0745d0ac4d7d95c9929cdce97f5fd5f40` | identity and no-rerun proof |
| Checkpoint 1 Amendment Execution Decision | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-amendment-v1` | `research/v3_5/checkpoints/checkpoint_1/amendment_v1/checkpoint_1_amendment.execution_decision.json` | `2a328016fd1e3ff56355532c91169874aaf3fae33cf45f36c7f4e44d11abe10c` | P9 remains blocked |
| Checkpoint 1 Amendment Hash Manifest | `unreviewed_execution_candidate` | `v3.5-b-checkpoint-1-amendment-v1` | `research/v3_5/checkpoints/checkpoint_1/amendment_v1/checkpoint_1_amendment.file_hash_manifest.jsonl` | `10ac689da35919557a5956c4cdfefcf829544344d0fcdf71b3a5f8a047969283` | verifies the four sibling Amendment contract outputs; self-hash excluded |

### 8.14 P9 F1A Candidate Builder Decision Restart

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| P9 Completion Response | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/P9_F1A_CANDIDATE_BUILDER_DECISION_COMPLETION_RESPONSE.md` | `b71a3b1d4fdebb036e6421bdb5e1be68b82732a5e6d5e15b7d05f77b6649616c` | accepted completion record |
| F1A Candidate Builder Decision | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/F1A_CANDIDATE_BUILDER_DECISION.md` | `972e5b371afe26b0dfe8a1ddf3bc13abd7c6c44ffda9fa4cb4cfaf2330bc50ec` | accepted `execute` decision evidence |
| F1A Decision | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/f1a_decision.json` | `98561230262305f6a5972412d610ad115d03e74c722bfc6181e885bf2762dfe4` | machine-readable decision |
| Failure Analysis | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/f1a_failure_analysis.jsonl` | `fecf1c574b6a1397282f00badaa35af1ac07fcf8e96b439e0ddc74ed71760173` | six case records |
| Mechanism Taxonomy | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/f1a_mechanism_taxonomy.json` | `9c7b15b5bf456348747e25b5a6a942f966689f6d10b7c2a7e5b22d3f92403973` | accepted mechanisms |
| Original Candidate Design | `superseded` | `bounded_coverage_reserve_v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/f1a_candidate_design.json` | `8e591d14163178bb5ab6ad4c446324c7baaa9184773709403c20dbe409f7bad7` | preserved; superseded before implementation |
| P9 Decision Manifest | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/f1a_decision.manifest.json` | `006a5cc1cd8456a6b610ad46a94be7908ed8710f565024c186b2e52a51bc7e73` | input and output identity |
| P9 Decision Audit | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/f1a_decision.audit.json` | `09705b2616438b779e0fea50747c3e9f7d65204d375689f58e6a6de8bb20c10d` | no implementation or Frozen access |
| P9 Decision Execution Decision | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/f1a_decision.execution_decision.json` | `559b9084c9326918e878530413595f5ee10f4eda720c022529d8eda545030456` | `execute`, not authorization |
| P9 Decision Hash Manifest | `accepted` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/f1a_decision.file_hash_manifest.jsonl` | `ca62384ef3bef10953195198497c226299cb49351cd1a780d282d847b075c3f0` | accepted package hash root |
| P9 Restart Decision Ledger | `accepted_task_contract` | `v3.5-b-p9-f1a-decision-restart-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/V3_5_P9_F1A_CANDIDATE_BUILDER_DECISION_RESTART_LEDGER.json` | `2e92fe85d5ef6ede8c3a4746ab8e7270dd4329e33152d8fea385d9b2b429ce1a` | authoritative restart ledger |

### 8.15 P9 Candidate Design Amendment v1

| Artifact | Status | Version / Policy | Repository path | SHA-256 | Authority / notes |
|---|---|---|---|---|---|
| Candidate Design Amendment Report | `unreviewed_execution_candidate` | `v3.5-b-p9-candidate-design-amendment-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1/P9_CANDIDATE_DESIGN_AMENDMENT_REPORT.md` | `7bcfde2082b9898d196acdb23401a02838e1300ff8278dfe269456d92efea965` | design-only amendment |
| Candidate Design Amendment | `unreviewed_execution_candidate` | `v3.5-b-p9-candidate-design-amendment-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1/p9_candidate_design_amendment.json` | `25f8cced57e73e43704e1668cafbbfe3e6370dc39950a0314987bee25f6320e3` | amendment state |
| Amended F1A Candidate Design | `unreviewed_execution_candidate` | `adaptive_bounded_coverage_swap_v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1/f1a_candidate_design.amended_v1.json` | `139129cf8c1d2f0b7b164070b727ba87ac4189948785d8bcfe5c4f7442ed3004` | unique active implementation candidate |
| Candidate Design Amendment Manifest | `unreviewed_execution_candidate` | `v3.5-b-p9-candidate-design-amendment-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1/p9_candidate_design_amendment.manifest.json` | `2ff97267a9710dca58cb4586a7a00db8eee608f97eb26f770e8b5cb2e5e5bfc3` | input/output identity |
| Candidate Design Amendment Audit | `unreviewed_execution_candidate` | `v3.5-b-p9-candidate-design-amendment-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1/p9_candidate_design_amendment.audit.json` | `6635b043b40a31240dcff27cdb237fa7923d71c8175c3bacd3aef99b99abb5f8` | scope and governance proof |
| Candidate Design Amendment Execution Decision | `unreviewed_execution_candidate` | `v3.5-b-p9-candidate-design-amendment-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1/p9_candidate_design_amendment.execution_decision.json` | `377ac08f5879b085623829549c3b76ca64c2b5cb1ebd80175982ff4b22dacc33` | pending V3.5-B review |
| Candidate Design Amendment Hash Manifest | `unreviewed_execution_candidate` | `v3.5-b-p9-candidate-design-amendment-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1/p9_candidate_design_amendment.file_hash_manifest.jsonl` | `9723f4641ccce74222255580aa82ec588d32ff9491ee6bc4741acadb608ef66c` | verifies all sibling outputs except itself |
| Candidate Design Amendment Ledger | `accepted_task_contract` | `v3.5-b-p9-candidate-design-amendment-v1` | `research/v3_5/product_query_set_v1/f1a_candidate_builder_decision_restart/design_amendment_v1/V3_5_P9_CANDIDATE_DESIGN_AMENDMENT_LEDGER.json` | `a35df94c09e6d7d2be7363b21ed999007a735ff449b71b1e21575bc040ac93f4` | authoritative ledger copied byte-for-byte |

---

## 9. On-demand Reading Guide

V3.5-B 不接收全部历史聊天或全部中间资产。需要下钻时按问题读取：

| 问题 | 第一读取路径 |
|---|---|
| 当前交接状态 | `V3_5_CURRENT_STATE.md` 顶部 H0-R 区块 |
| 当前机器可读事实 | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.r2.json` |
| Source / Segment / Timeline Identity | `V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md` |
| SearchCandidateSet 与 V3 接入 | `V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md` |
| Eval v1 Protocol / Split / Gold Lock | `research/v3_5/gold/` 下的 locked assets |
| 31-Case Stress Set v2 | `research/v3_5/stage3r/input/stage2r_final_corpus/` |
| Canonical Segment Scoring | `research/v3_5/stage3r_s1/contracts/segment_identity_bridge_contract.json` |
| Candidate Builder | `src/shiliu/evidence/stage3b.py` |
| Deterministic Selector | `src/shiliu/evidence/stage3a.py` |
| Structured LLM Selector 负结果 | `V3_5_STAGE3B_STRUCTURED_FINE_SELECTOR_REPORT.md` 与对应 contract |
| Mechanical Gate v1 | `research/v3_5/stage4a/mechanical_gate_contract.json` |
| Auto Router Smoke | `research/v3_5/auto_smoke/` |
| Product Default Auto Wiring | `research/v3_5/product_default_auto_wiring/` |
| Corrected Stress Track A | `research/v3_5/stage3r_qc/track_a_auto_refresh/` |
| `2/20` 与 `1/20` 差异 | `research/v3_5/handoff_draft/fact_freeze/track_b_vs_auto_bundle_hit_diff.audit.json` |
| Legacy Product Query 候选 | `research/v3_5/product_query_set_v1/phase_a/` 与 `phase_a_r/` |
| Stage 3R-PQS-B0 合同 | `research/v3_5/product_query_set_v1/authoring_packet/STAGE3R_PQS_B0_NEUTRAL_AUTHORING_PACKET_EXPORT_TASK.md` |
| Stage 3R-PQS-B0 执行候选 | `research/v3_5/product_query_set_v1/authoring_packet/V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md` |

---

## 10. Known Incomplete Work vs Unresolved Facts

### 10.1 Unresolved facts

```text
None.
```

### 10.2 已知但尚未完成的工作

以下不是事实不确定性，而是明确未完成的版本任务：

- Stage 3R-PQS-B0 Execution Candidate 尚未由 V3.5-B 验收；
- Product Query Set v1 尚未生成、用户确认或冻结；
- Development / Frozen Evaluation Split 尚未冻结；
- Product Retrieval / Evidence / Sufficiency Gold 尚未形成；
- Product Initial Baseline 尚未运行；
- F1A/F1B 尚未决策；
- Stage 4A-R 尚未开始；
- Stage 4B 尚未开始；
- Minimal API / UI / Trace 尚未完成；
- Frozen Evaluation Set 尚未正式运行；
- V3.5 Final Closeout 尚未完成。

---

## 11. Draft Review Checklist

本文件在进入 `00` 编制前应满足：

```yaml
document_scope:
  complete_version_history_repeated: false
  remaining_plan_duplicated: false
  operating_contract_duplicated: false

fact_authority:
  artifact_inventory_records: 32
  unresolved_facts: 0
  current_fact_freeze_count: 1
  current_fact_freeze: handoff_fact_freeze.r2.json

terminology:
  active_evaluation_term: Frozen Evaluation Set
  ambiguous_b0_reference_count: 0

critical_decisions:
  product_default_auto: present
  v3_retrieval_frozen: present
  stress_set_role: present
  builder_selector_versions: present
  structured_llm_selector_rejected: present
  b0_owner_v3_5_b: present
  independent_query_prompt_owned_by_v3_5_b: present
  context_checkpoints: present
  f1a_f1b_paused: present
  final_answer_out_of_scope: present

artifact_integrity:
  missing_paths_in_inventory: 0
  stale_artifacts_in_inventory: 0
  hash_mismatch_between_authority_and_hash_inventory: 0
```
