# 02 — Product Query Set and Remaining V3.5 Plan

> **文件名**：`02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md`  
> **文档状态**：Final，供 V3.5-B 渐进式按阶段读取  
> **版本范围**：Shiliu V3.5 — Evidence Resolution and Sufficiency  
> **执行负责人**：V3.5-B  
> **上位治理合同**：`01_V3_5_B_OPERATING_CONTRACT.md`  
> **当前事实、版本与 Artifact 权威**：`03_V3_5_DECISION_AND_ARTIFACT_INDEX.md`  
> **历史与交接原因**：`00_V3_5_A_CLOSEOUT_AND_V3_5_B_HANDOFF.md`  
> **编制日期**：2026-07-25

---

## F1A Preimplementation Recovery Amendment — 2026-07-27

This block supersedes earlier F1A attempt accounting and implementation-entry
language. The previous Session is unusable because discovery entered the Frozen
Gold tree, but no implementation, freeze seal, or scored run occurred.

```yaml
execution_status: complete
acceptance_status: pending_v3_5_b_review
recovery_amendment_status: execution_candidate_ready

P9_decision: execute
active_design: adaptive_bounded_coverage_swap_v1
current_builder: stage3b-acronym-w3.5-v1
design_changed: false
acceptance_thresholds_changed: false

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

next_formal_step: F1A_MAJOR_CYCLE_1_RECOVERY_EXECUTION
F1B_authorized: false
Stage4_started: false
```

The next execution must use a new Codex Session and
`F1A_RECOVERY_FILESYSTEM_ACCESS_POLICY.json`. Access is default-deny: only
Policy Seed Paths and exact transitively referenced paths are allowed.
Repository-root recursive search and every forbidden Frozen path pattern are
prohibited. A missing or ambiguous exact path blocks execution. This Amendment
stops before Builder implementation, Prediction generation, scoring, F1B, and
Stage 4.

---

## P9 Candidate Design Amendment — 2026-07-27

This block supersedes the fixed-slot Candidate Design only. It preserves the
accepted P9 execute decision, mechanisms, addressable set, non-goal, acceptance
thresholds and one-Major-Cycle boundary.

```yaml
P9:
  status: complete_and_accepted
  decision: execute
  design_amendment_status: execution_candidate_ready

failure_mechanism:
  primary: bounded_candidate_pruning_coverage_gap
  secondary: dedup_below_threshold_leaves_complement_gap

addressable_failures:
  count: 5
  ids:
    - PQS_V1_Q003
    - PQS_V1_Q004
    - PQS_V1_Q005
    - PQS_V1_Q008
    - PQS_V1_Q015

non_goal:
  - PQS_V1_Q018

active_f1a_candidate_design:
  name: adaptive_bounded_coverage_swap_v1
  initial_set: original_top_32
  swap_count_per_query: 0_to_4
  forced_swaps: false
  strict_set_improvement_required: true
  candidate_cap: 32

superseded_f1a_candidate_design:
  name: bounded_coverage_reserve_v1
  status: superseded_before_implementation
  implemented: false
  evaluated: false

F1A:
  implementation_authorized: false
  implementation_started: false
  major_cycles_max: 1
  major_cycles_used: 0
  major_cycles_remaining: 1

F1B_authorized: false
Stage4_started: false
next_formal_step: F1A_IMPLEMENTATION_CONTRACT
```

The next formal step is to draft and review a separate F1A Implementation
Contract. This Amendment does not generate that task and does not authorize
implementation.

---

## P8 Scoring / Checkpoint 1 Amendment — 2026-07-27

This amendment block supersedes only P8 scoring-derived numbers and the
corresponding Checkpoint 1 findings elsewhere in this plan.

```yaml
P7:
  status: complete_and_accepted

P8_prediction_set:
  status: valid_and_frozen
  formal_attempt: P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3
  prediction_count: 14
  prediction_seal_sha256: 069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617

P8_original_scoring:
  status: superseded_by_scoring_amendment

P8_scoring:
  original_status: superseded_by_scoring_amendment
  current_version: P8_SCORING_AMENDMENT_V1

P8_scoring_amendment:
  version: v3.5-p8-scoring-amendment-v1
  status: amendment_execution_candidate_ready
  candidate_builder:
    complete_group_coverage: 6/13
    required_span_recall: 0.6538461538461539
    required_aspect_coverage: 0.6538461538461539
    primary_failures: 6
  deterministic_selector:
    bundle_hit: 1/13
    required_span_recall: 0.12179487179487179
    required_aspect_coverage: 0.12179487179487179
    primary_failures: 5
  primary_failure_distribution:
    candidate_builder_failure: 6
    deterministic_selector_failure: 5
    source_unverifiable: 1
    gold_defined_evidence_absent: 1
    end_to_end_bundle_hit: 1

Checkpoint_1_amendment:
  status: amendment_execution_candidate_ready
  acceptance_status: pending_v3_5_b_review

P9:
  previous_attempt: safely_blocked_due_to_scoring_defect
  status: blocked_pending_v3_5_b_acceptance
  restart_readiness: true
  restarted: false

F1A_authorized: false
F1B_authorized: false
Stage4_started: false
```

The next formal action is V3.5-B review of the Amendment. P9 does not restart
inside the Amendment execution.

---

## 0. Document Purpose and Boundary

本文件是 V3.5-B 唯一的**剩余执行路线**。

它回答：

```text
接下来每一步具体做什么？
每一步的输入、输出和负责人是什么？
什么时候可以进入？
什么条件算完成？
失败时应修当前阶段、跳过、记录限制还是返回 Main Session？
```

本文件不负责：

- 复述 V3.5-A 的完整历史；
- 重新定义 V3.5 Mission、角色和禁止项；
- 列出全部现有 Artifact 路径、Hash 和版本；
- 充当 V3.5-B 的首轮启动 Prompt；
- 提前决定 F1A、F1B 或 Stage 4B 必须修改系统；
- 提前宣布 V3.5 已完成。

若本文件与其他正式文件发生冲突：

| 冲突领域 | 权威文件 |
|---|---|
| 权限、禁止项、Frozen Evaluation 隔离、Stop Rule | `01` |
| 当前事实、状态、版本、路径与 Hash | `03` |
| 历史原因和交接解释 | `00` |
| 新 Session 首轮行为 | `04` |
| 剩余阶段的具体顺序与 Gate | **本文件** |

---

## 1. Current Starting State

V3.5-B 接管时，路线从以下状态开始：

```yaml
handoff:
  v3_5_a_session_closeout_approved: true
  v3_5_version_complete: false
  next_owner: v3_5_b

product_search:
  default_mode: auto
  wiring_version: v3-product-search-default-auto-v1
  router_modified: false
  retrieval_retuned: false

stress_set_v2:
  role: evidence_sufficiency_stress_set_v2
  total: 31
  product_benchmark: false

corrected_stress_auto_track_a:
  evidence_bearing_cases: 20
  target_video_recall: 20/20
  complete_gold_group_candidate_coverage: 11/20
  bundle_hit: 1/20
  conditional_bundle_hit: 1/11

product_query_set_v1:
  final_set_frozen: false
  minimum: 20
  target: 24
  maximum: 24

stage3r_pqs_b0:
  task_contract: accepted_task_contract
  execution_candidate: unreviewed_execution_candidate
  review_owner: v3_5_b

remaining:
  product_initial_baseline: not_started
  f1a: paused
  f1b: paused
  stage4a_r: not_started
  stage4b: not_started
  minimal_api_ui_trace: not_started
  frozen_evaluation_set: formally_not_run
  v3_5_final_closeout: not_started
```

精确 Case ID、路径、Hash、Schema 和当前组件版本不在本文件重复，统一读取 `03`。

---

## 2. Execution Model

### 2.1 One Stage at a Time

V3.5-B 只允许一个正式阶段处于 `in_progress`。

```yaml
stage_status:
  - not_started
  - ready
  - in_progress
  - blocked
  - accepted
  - skipped
  - rejected
  - limitation_recorded
```

不得：

- 一边冻结 Query，一边运行 Product Baseline；
- 一边构造 Gold，一边按结果修改 Query；
- 一边运行 F1A，一边提前开发 F1B；
- 一边开发 Stage 4B，一边试跑 Frozen Evaluation；
- 一个 Codex Session 同时执行多个未关闭 Stage。

### 2.2 每个 Stage 的标准输出

除纯人工讨论阶段外，每个正式阶段至少形成：

```yaml
required_stage_outputs:
  - task_or_review_contract
  - machine_readable_manifest
  - execution_or_review_audit
  - human_readable_report
  - tests_or_mechanical_validation
  - decision_record
```

若阶段修改代码，还必须有：

```yaml
code_change_outputs:
  - before_state
  - diff_summary
  - focused_tests
  - regression_tests
  - before_after_metrics
  - version_or_policy_change
```

### 2.3 Stage Acceptance

Codex 输出 `Complete`、测试通过或文件存在，不等于 Stage Accepted。

V3.5-B 必须检查：

```yaml
acceptance_review:
  input_identity_verified: true
  scope_compliance_verified: true
  prohibited_actions_absent: true
  outputs_complete: true
  metrics_recomputed_or_hash_verified: true
  failure_attribution_reviewed: true
  next_stage_entry_gate_satisfied: true
```

### 2.4 Artifact Immutability

Stage 被接受后：

- 正式 Query、Split、Gold、Prediction、Manifest 和报告不得原地覆盖；
- 修正通过新版本或 Amendment 进行；
- 被 supersede 的资产继续保留；
- 新资产必须更新 `03` 的状态、版本、Hash 与 Supersession；
- 当前运行权威必须保持唯一。

---

## 3. Overall Route

Checkpoint 1 has consolidated the accepted P7/P8 state. The active remaining
route begins at the independently authorized P9 decision stage:

```text
P9  F1A Candidate Builder Decision
↓
P10 F1B Deterministic Selector Decision
↓
Checkpoint 2
↓
P11 Stage 4A-R Mechanical Gate Revalidation
↓
P12 Stage 4B Semantic Sufficiency Development
↓
Checkpoint 3
↓
P13 Minimal API / UI / Trace Integration
↓
P14 Frozen Evaluation
↓
P15 V3.5 Final Closeout
```

P7、P8 与 Checkpoint 1 之前的路线已完成收口。F1A 和 F1B 是**必须关闭的决策阶段**，不是强制实现阶段；`P9_ready_for_authorization: true` 不等于 P9 或 F1A 已获授权。其他必经阶段不得跳过，除非 Main Session 正式修改 V3.5 范围。

---

# Workstream A — Product Query Set v1

## R0 — V3.5-B Intake Audit

### Owner

```yaml
owner: v3_5_b
execution_support: none
user_action_required: false
```

### Purpose

证明新负责人已正确读取正式交接包，并且没有把旧聊天、历史 Current State 或过时 Stage 建议当作当前权限。

### Inputs

```text
00_V3_5_A_CLOSEOUT_AND_V3_5_B_HANDOFF.md
01_V3_5_B_OPERATING_CONTRACT.md
03_V3_5_DECISION_AND_ARTIFACT_INDEX.md
02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md
```

启动行为由 `04` 规定。

### Allowed Actions

- 读取四份正文；
- 复述 Frozen Intake State；
- 检查文件缺失、Hash 冲突和职责冲突；
- 定点读取 Stage 3R-PQS-B0 Task Contract 与 Execution Candidate 的路径；
- 形成 P0 Review Plan；
- 提出真正阻塞 Intake 的缺失项。

### Outputs

```text
V3_5_B_INTAKE_AUDIT.md
V3_5_B_STAGE3R_PQS_B0_REVIEW_PLAN.md
```

### Entry Gate

```yaml
five_file_package_available: true
final_manifest_hashes_valid: true
v3_5_b_started_by_04: true
```

### Acceptance Gate

- 正确复述 Product Default Auto；
- 正确复述 `20/20 → 11/20 → 1/20`；
- 正确区分 Stress Set 与 Product Query Set；
- 正确说明 Stage 3R-PQS-B0 是 `unreviewed_execution_candidate`；
- 正确说明 F1A/F1B 暂停；
- 没有开始任何下游执行。

### Stop Rule

发现以下任一情况立即停止：

- 正式文件缺失；
- Final Manifest Hash 不匹配；
- `01/02/03` 出现无法按领域解释的冲突；
- 当前仓库的 Stage 3R-PQS-B0 Task Contract 或 Execution Candidate 缺失。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- 验收或执行 Stage 3R-PQS-B0；
- 生成 Product Query；
- 启动 Independent Session；
- 运行 Retrieval、Builder、Selector 或 Gate；
- 修改任何交接文件；
- 访问 Frozen Evaluation Gold。

### Next Stage

```text
P0 — Stage 3R-PQS-B0 Review
```

---

## P0 — Stage 3R-PQS-B0 Review

### Owner

```yaml
owner: v3_5_b
repository_evidence_provider: codex_read_only_if_needed
acceptance_authority: v3_5_b
```

### Purpose

对照已接受的 Task Contract，审查仓库中已有的 Neutral Authoring Packet Execution Candidate，决定它是否可以交给 Independent Product Query Session。

### Inputs

```text
STAGE3R_PQS_B0_NEUTRAL_AUTHORING_PACKET_EXPORT_TASK.md
V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md
PQS_V1_PRODUCT_SCENARIO_BRIEF.md
PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md
PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md
independent_query_draft.template.jsonl
PQS_V1_LEGACY_CANDIDATE_PACKET.md
legacy_candidate_review.template.jsonl
product_query_user_validation.template.jsonl
PQS_V1_INDEPENDENT_WEBGPT_HANDOFF.md
pqs_v1_content_map_provenance.jsonl
```

若实际文件名不同，以 `03` 和 Task Contract 为准。

### Allowed Actions

逐项核实：

1. Scenario Brief 是否真实描述拾流当前产品；
2. Content Map 是否只使用导航性材料；
3. Topic Cluster 是否有内部 Provenance；
4. Pass 1 是否与 Legacy Candidate 完全隔离；
5. Raw Transcript、Gold、系统成绩和 Failure 是否未泄漏；
6. 是否暗示 Answerability、Target Answer 或 Label；
7. 模板是否保持空白；
8. Codex 是否生成、筛选或修改了 Product Query；
9. Independent Handoff 是否只提供授权文件；
10. 内部 Provenance 是否不会交给独立 Session。

### Review Outcomes

```yaml
review_outcome:
  - accept
  - require_correction
  - reject
```

### Outputs

```text
V3_5_STAGE3R_PQS_B0_REVIEW_REPORT.md
stage3r_pqs_b0_review_decision.json
stage3r_pqs_b0_accepted_packet_manifest.json
```

### Entry Gate

```yaml
r0_intake_accepted: true
task_contract_hash_verified: true
execution_candidate_exists: true
```

### Acceptance Gate

```yaml
neutrality_leakage_errors: 0
blank_template_violations: 0
codex_authored_product_queries: 0
pass1_legacy_leakage: 0
unauthorized_transcript_or_gold_exposure: 0
accepted_packet_manifest_frozen: true
```

### Stop Rule

若不通过：

```text
只修 Authoring Packet
→ 重新审查 P0
```

不得进入 P1。

若修正需要改变 Product Query Authoring 方法、规模或独立性原则，返回 Main Session。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- 因文件看起来完整而机械接受；
- V3.5-A 参与验收；
- 让 Codex 代替 V3.5-B 决定；
- 提前生成 Independent Session 最终 Prompt；
- 将 Legacy Packet 暴露给 Pass 1；
- 修改 Task Contract 以迁就 Execution Candidate。

### Next Stage

```text
P1 — Independent Product Query Authoring
```

---

## P1 — Independent Product Query Authoring

### Owner

```yaml
author: independent_product_query_session
supervisor: v3_5_b
repository_role: none
user_action_required: false
```

### Purpose

在不受 Legacy 40、Stress Failure 和系统表现影响的情况下，独立提出自然、真实、符合拾流产品场景的问题候选。

### Inputs

仅允许：

```text
PQS_V1_PRODUCT_SCENARIO_BRIEF.md
PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md
PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md
independent_query_draft.template.jsonl
```

最终 Independent Session Prompt 只能由 V3.5-B 在 P0 通过后生成。

### Authoring Target

```yaml
candidate_target: 24_to_30
final_set_target: not_decided_in_this_stage
```

Query 类型只作覆盖参考：

- Definition；
- Purpose / Use Case；
- How-to / Process；
- Comparison / Trade-off；
- Conditions / Limitations；
- Evaluation / Quality；
- Reported Result；
- Natural Multi-aspect；
- Multi-video Synthesis；
- 少量 No-answer / Library Gap。

不得按类型或预期标签硬凑配额。

### Allowed Actions

- 基于 Product Scenario 和 Neutral Content Map 独立构思；
- 标记 Query Family、Intent、Complexity 和讨论风险；
- 标记可能过长、过度复合或需要用户确认的候选；
- 输出候选，不生成答案和系统预测。

### Required Candidate Fields

```yaml
query_candidate:
  draft_query_id:
  query_text:
  query_family:
  intent:
  single_or_multi_video:
  complexity:
  scenario_rationale:
  content_map_cluster_ids:
  needs_user_discussion:
  discussion_reason:
  authoring_origin: independent_pass1
```

不得记录 Target Video、Gold Span 或 Expected Status。

### Outputs

```text
independent_query_draft.pass1.jsonl
PQS_V1_PASS1_AUTHORING_REPORT.md
```

### Entry Gate

```yaml
p0_b0_review: accepted
independent_prompt_frozen: true
pass1_file_whitelist_frozen: true
```

### Acceptance Gate

- 候选数约 24–30；
- 没有答案、Gold、Target Video 或系统成功率；
- 没有看到 Legacy 40；
- Query 与当前拾流使用场景存在自然联系；
- Query 不是纯面试大纲或评测指令；
- 每条有可解释 Scenario / Content Map Grounding；
- 无明显重复或标题改写式造题。

P1 Acceptance 只表示候选池可进入 Reconciliation，不表示候选已成为正式 Product Query。

### Stop Rule

若候选不足：

- 允许在同一 P1 Session 内根据原材料完成一次缺口补齐；
- 不提供 Legacy 40；
- 不启动第二个独立 Authoring Session；
- 不扩大到第二轮 Independent Authoring。

若 20 条自然候选都无法形成，停止并升级 Main Session。

### Skip Policy

```yaml
skippable: false
independent_authoring_rounds_max: 1
```

### Forbidden

- 查看 Legacy Candidate Packet；
- 查看 Stress、Auto、Builder、Selector 或 Judge 结果；
- 生成答案；
- 预测系统能否回答；
- 为 sufficient / partial / insufficient / unverifiable 凑题；
- 根据标题列表机械改写；
- 直接确定最终 Query Set。

### Next Stage

```text
P2 — Legacy Candidate Reconciliation
```

---

## P2 — Legacy Candidate Reconciliation

### Owner

```yaml
reviewer: same_independent_product_query_session
supervisor: v3_5_b
user_action_required: false
```

### Purpose

在 Pass 1 完成后，才将 Legacy 40 条作为历史提案对照，补充被独立 Authoring 遗漏的自然需求，并淘汰规划化、评测化和过度复合问题。

### Inputs

```text
independent_query_draft.pass1.jsonl
PQS_V1_LEGACY_CANDIDATE_PACKET.md
legacy_candidate_review.template.jsonl
```

不得回溯修改 P1 原始文件。

### Allowed Actions

每条 Legacy Candidate 只能标记：

```yaml
legacy_action:
  - absorb
  - revise
  - merge
  - exclude
  - reserve
```

同时说明：

- 是否与 P1 重复；
- 是否像项目规划问题；
- 是否像面试大纲；
- 是否过长或绑定多个独立需求；
- 是否自然对应产品使用；
- 若 revise / merge，具体改了什么。

### Outputs

```text
legacy_candidate_review.pass2.jsonl
product_query_unified_candidate_pool.jsonl
PQS_V1_PASS2_RECONCILIATION_REPORT.md
```

统一候选池必须保留：

```yaml
provenance:
  authoring_origins:
  source_candidate_ids:
  transformation:
  rationale:
```

### Entry Gate

```yaml
p1_accepted: true
pass1_original_hash_frozen: true
legacy_packet_hash_verified: true
```

### Acceptance Gate

- 40 条 Legacy Candidate 均有处理决定；
- Pass 1 原始候选未被覆盖；
- 没有把 Legacy 称为 Search Log；
- 所有 absorb / revise / merge 都可追溯；
- 统一候选池没有重复、明显过度复合和规划化问法；
- Reserve 不自动进入用户确认池。

### Stop Rule

出现下列情况停止并修当前 Stage：

- P1 与 P2 原始来源无法区分；
- Legacy Packet 泄漏系统成绩或 Gold；
- 大量 Legacy Candidate 被无理由吸收；
- 候选池通过堆叠而非自然筛选超过合理规模。

不得启动第二轮 Independent Authoring。

### Skip Policy

```yaml
skippable: false
legacy_reconciliation_rounds_max: 1
```

### Forbidden

- 根据系统表现决定 absorb / exclude；
- 让 V3.5-B 代替独立 Session 重写全部候选；
- 将 Reserve 计入正式 Query 数量；
- 因数量不足自动接受低质量 Legacy Candidate；
- 覆盖 P1 文件。

### Next Stage

```text
P3 — User Validation and One Revision
```

---

## P3 — User Validation and One Revision

### Owner

```yaml
final_product_plausibility_authority: user
facilitator: v3_5_b
query_editor: independent_session_or_v3_5_b_under_user_decision
```

### Purpose

由用户确认哪些问题真实、自然、可能在当前收藏夹产品中提出，并进行唯一一次正式 Revision。

### Inputs

```text
product_query_unified_candidate_pool.jsonl
product_query_user_validation.template.jsonl
```

### Review Method

按主题或使用场景分批，不一次展示全部技术元数据。

用户重点判断：

- 我是否真的可能这样问；
- 是否太像面试问题或项目规划；
- 是否过长；
- 是否将多个独立需求强行绑定；
- 是否应该拆分、合并或缩短；
- 是否存在重要使用场景遗漏；
- 是否是拾流产品中的信息需求，而不是 Agent 功能要求。

### User Actions

```yaml
user_action:
  - approve
  - revise
  - merge
  - split
  - reject
  - reserve
```

### Final Requirement

正式集合只允许：

```yaml
user_validated_as_plausible: true
```

的 Query 进入 P4。

### Outputs

```text
product_query_user_validation.completed.jsonl
product_query_candidate_pool.after_user_revision.jsonl
PQS_V1_USER_VALIDATION_REPORT.md
```

### Entry Gate

```yaml
p2_accepted: true
unified_candidate_pool_frozen: true
```

### Acceptance Gate

```yaml
approved_query_count:
  minimum: 20
  target: 24
  maximum: 24

all_formal_queries_user_validated: true
revision_rounds_used: 1
unresolved_query_discussions: 0
```

若自然 Query 恰好为 20–23 条，不为达到 24 硬造新问题。

### Stop Rule

- 少于 20 条自然 Query：停止并返回 Main Session；
- 超过 24 条：必须基于产品覆盖和重复度收口，不允许保留全部；
- 用户对某条 Query 的真实意图无法确认：移入 Reserve，不进入正式集合；
- 不得进行第二轮完整 User Revision。

### Skip Policy

```yaml
skippable: false
user_revision_rounds_max: 1
```

### Forbidden

- 向用户展示系统成绩以影响判断；
- 因 Query 可能难答而删除；
- 因 Query 可能容易答而保留；
- 为标签平衡强制加入 No-answer 或 partial；
- 将用户批准解释为“系统必须能答”。

### Next Stage

```text
P4 — Product Query Freeze
```

---

## P4 — Product Query Freeze

### Owner

```yaml
owner: v3_5_b
implementation_support: codex
user_confirmation_required: true
```

### Purpose

在任何正式 Product Retrieval 或 Gold 标注前，冻结最终 Query 文本、身份、来源和语义元数据。

### Inputs

```text
product_query_user_validation.completed.jsonl
product_query_candidate_pool.after_user_revision.jsonl
```

### Query Contract

每条正式 Query 至少包含：

```yaml
product_query:
  query_id:
  query_text:
  query_language:
  query_family:
  intent:
  single_or_multi_video:
  complexity:
  authoring_origin:
  source_candidate_ids:
  user_validated_as_plausible: true
  revision_history:
  leakage_group:
  topic_cluster:
```

不得包含：

- Gold Label；
- Target Video；
- Required Span；
- Expected Failure；
-系统结果；
-预期 Action。

### Outputs

```text
product_query_set_v1.locked.jsonl
product_query_set_v1.manifest.json
product_query_set_v1.lock.audit.json
PRODUCT_QUERY_SET_V1_FREEZE_REPORT.md
```

Manifest 至少记录：

```yaml
dataset_name: Shiliu Product Query Set v1
dataset_role: scenario_grounded_product_eval
historical_search_log_dataset: false
representative_of_all_users: false
query_count:
schema_version:
canonical_content_sha256:
source_artifact_hashes:
```

### Entry Gate

```yaml
p3_accepted: true
approved_query_count_between_20_and_24: true
all_formal_queries_user_validated: true
```

### Acceptance Gate

- Query 数量 20–24；
- Query ID 稳定且唯一；
- 文本、Origin、Family、Intent、Complexity、Leakage Group 完整；
- 两次序列化生成相同 Canonical Hash；
- 无 Gold 或系统结果字段；
- 用户确认记录和 Query Set 可机械追溯；
- Freeze Report 明确禁止结果驱动改写。

### Stop Rule

任何 Query 仍有语义歧义、重复或用户未确认时，不得冻结。

Query Freeze 后发现文字错误：

- 仅允许格式或无语义影响的 Amendment；
- 任何语义修改都需要新的 Query Set Version；
- 不得在当前 Version 中静默修改。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- 运行正式 Product Retrieval 后再改 Query；
- 因 Split 或 Gold 困难修改 Query；
- 因某类 Query 失败过多增删 Query；
- 覆盖原用户验证记录。

### Next Stage

```text
P5 — Development / Frozen Evaluation Split Freeze
```

---

## P5 — Development / Frozen Evaluation Split Freeze

### Owner

```yaml
owner: v3_5_b
implementation_support: codex
gold_visibility: none_at_split_time
```

### Purpose

在任何 Product Baseline 运行前，按确定性规则冻结 Development 与 Frozen Evaluation Set，防止按难度和结果后验分组。

### Inputs

```text
product_query_set_v1.locked.jsonl
```

### Split Guidance

若最终为 24 条，默认建议：

```yaml
development: 14
frozen_evaluation: 10
```

若为 20–23 条：

```yaml
development_ratio: approximately_60_percent
frozen_evaluation:
  minimum: 8
  maximum: 10
```

Split 应分层考虑：

- Query Family；
- Topic Cluster；
- Single / Multi-video；
- Complexity；
- Leakage Group；
- Language；
- No-answer / Library Gap 风险；
- Authoring Origin。

这些只用于避免泄漏和明显分布塌缩，不是标签配额。

### Allowed Actions

- 冻结确定性 Split Rule；
- 冻结 Seed；
- 将同 Leakage Group 放在同一 Split；
- 进行机械 Split Audit；
- 在不查看 Gold 和结果的前提下处理数量冲突。

### Outputs

```text
product_query_split_v1.locked.json
product_query_development_v1.locked.jsonl
product_query_frozen_evaluation_v1.locked.jsonl
product_query_split_v1.audit.json
PRODUCT_QUERY_SPLIT_V1_REPORT.md
```

### Entry Gate

```yaml
p4_query_set_frozen: true
formal_product_retrieval_run: false
gold_annotation_started: false
```

### Acceptance Gate

- Development 和 Frozen Evaluation 无交集；
- 全部 Query 精确分配；
- 同一 Leakage Group 不跨 Split；
- Rule、Seed、Family、Topic 和 Complexity 分布已记录；
- Split 在任何正式结果前冻结；
- Frozen Evaluation 文件的保护路径和访问 Guard 已建立；
- V3.5-B 仅知道 Query 和 Split Identity，不读取后续 Frozen Gold。

### Stop Rule

- 无法在 20–24 条内形成至少 8 条 Frozen Evaluation；
- Leakage Group 导致严重分区冲突；
- 需要查看系统结果才能决定 Split；

以上情况停止并返回 Main Session。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- 根据结果调整 Split；
- 为让 Frozen Evaluation 看起来平衡而查看 Gold；
- 拆散强 Leakage Group；
- 事后把失败 Case 移入 Development；
- 使用历史 `Held-out` 作为新主动术语。

### Next Stage

```text
P6 — Three-layer Gold Protocol Freeze
```

---

## P6 — Three-layer Gold Protocol Freeze

### Owner

```yaml
protocol_owner: v3_5_b
human_decision_authority: user
implementation_support: codex
```

### Purpose

在打开原字幕进行正式标注前，冻结 Product Retrieval、Evidence 和 Sufficiency 三层 Gold 的定义、Schema、审查方式和隔离规则。

### Three-layer Gold Contract

```yaml
retrieval_gold:
  known_relevant_video_ids:
  acceptable_video_ids:
  hard_negative_video_ids:
  relevance_review_scope:
  exhaustive: false

evidence_gold:
  required_aspects:
  acceptable_evidence_groups:
  required_spans:
  optional_context_spans:

sufficiency_gold:
  status:
  supported_aspects:
  missing_aspects:
  reason_codes:
```

### Retrieval Gold Principles

Retrieval Gold 是：

```text
bounded / pooled judgment
```

不是：

```text
全库穷尽 Corpus Truth
```

因此：

```text
没有召回一个已知 Target Video
≠
没有召回任何可接受 Relevant Video
```

未在 Gold Pool 中的返回视频不得自动判为 Negative；必须标记：

```yaml
relevance_status: unjudged
action: human_relevance_adjudication
```

### Evidence Gold Principles

- 基于完整权威原字幕/ASR；
- `acceptable_evidence_groups` 之间为 OR；
- 同一 Group 内 `required_spans` 为 AND；
- Candidate Builder 输出不得限制 Gold；
- 标题、描述、AI Summary 和 AI Chapter 不作 Evidence Gold；
- Source Version、Timeline Run、Segment Identity 和时间必须可验证；
- 可记录 Optional Context，但不能用其替代 Required Span。

### Sufficiency Gold Principles

四态：

```yaml
sufficient:
  meaning: 全部材料 Required Aspects 获可靠 Evidence 支持

partial:
  meaning: 有意义子集获可靠支持，但仍缺少材料 Aspect

insufficient:
  meaning: 权威来源可审查，但无法支持可用主回答

unverifiable:
  meaning: 权威来源缺失、损坏、不可访问或无法可靠审查
```

### Review Policy

普通 Case：

```text
Initial Annotation
→ One Independent Review
```

高风险或分歧 Case：

```text
Initial Annotation
→ Independent Review
→ Second Reviewer or User Adjudication
```

高风险包括：

- no-answer；
- partial；
- multi-video；
- cross-language；
-严重 ASR；
- Source Authority 不稳定；
- Reviewer 分歧；
-多个可接受相关视频；
- Required Span 跨长距离。

### Outputs

```text
PRODUCT_QUERY_GOLD_PROTOCOL_V1.md
product_retrieval_gold.schema.json
product_evidence_gold.schema.json
product_sufficiency_gold.schema.json
product_gold_reason_code_registry.json
product_gold_review_policy.json
product_frozen_evaluation_isolation_contract.md
PRODUCT_QUERY_GOLD_PROTOCOL_FREEZE_REPORT.md
```

### Entry Gate

```yaml
p5_split_frozen: true
formal_gold_annotation_started: false
```

### Acceptance Gate

- 三层 Gold Schema 机械分离；
- Retrieval `exhaustive=false`；
- Evidence Gold 不依赖 Builder 输出；
- 四态定义无重叠；
- Review / Adjudication 路线完整；
- Frozen Evaluation Gold 保护路径与访问规则明确；
- Reason Code 可覆盖 Retrieval、Builder、Selector、Gate、Judge 和 Source Failure。

### Stop Rule

若协议仍把：

- Relevant Video；
- Evidence Span；
- Sufficiency Label；

混为一个 Gold 对象，则不得开始标注。

若必须建设新的标注平台才能执行，停止并采用文件化最小流程；仍不可行时升级 Main Session。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- 边标注边修改 Schema；
- 将人工 Target Video 当唯一可接受答案；
- 把 Candidate Builder Miss 写进 Gold；
- 把系统 Failure 写入 Query；
- 让 V3.5-B 查看 Frozen Gold 内容。

### Next Stage

```text
P7 — Product Gold Construction and Sealing
```

---

## P7 — Product Gold Construction and Sealing

### Owner

```yaml
workflow_owner: v3_5_b
annotation_support:
  - independent_reviewer
  - codex_for_packet_export_and_validation
final_human_decision: user
frozen_gold_visibility_to_v3_5_b: forbidden
```

### Purpose

按 P6 协议形成 Development 可用 Gold，并将 Frozen Evaluation Gold 独立密封。

### Inputs

```text
product_query_development_v1.locked.jsonl
product_query_frozen_evaluation_v1.locked.jsonl
PRODUCT_QUERY_GOLD_PROTOCOL_V1.md
权威原字幕 / ASR
Source / Segment / Timeline Identity
```

### Gold Construction Route

#### Development

```text
Query
→ Library Relevance Review
→ Relevant / Acceptable Video Pool
→ Full Raw Transcript Review
→ Evidence Groups and Required Spans
→ Sufficiency Decision
→ Independent Review
→ Adjudication if needed
```

#### Frozen Evaluation

采用隔离流程：

```text
Packet Export by Guarded Tooling
→ Independent Annotation / Review
→ User Adjudication where required
→ Gold Validation
→ Seal
```

V3.5-B 可以知道：

- Frozen Gold 构建完成；
- Case 数；
- Schema 和 Hash；
- 是否存在未决 Case。

V3.5-B 不得知道：

- Relevant / Acceptable Video；
- Evidence Group；
- Required Span；
- Sufficiency Label；
- Expected Failure。

### Development Retrieval Pool Handling

由于 Retrieval Gold 非穷尽：

1. 先形成已知 Relevant / Acceptable Seed Pool；
2. Development Baseline 若返回未判定视频，先标记 `unjudged`；
3. 冻结 Prediction，不修改系统；
4. 由用户或独立 Reviewer 只判断该视频是否相关；
5. 可通过版本化 Addendum 将新 Acceptable Video 加入 Development Pool；
6. 不得删除已有 Positive 来改善指标；
7. Pool Adjudication 完成前，不形成最终 Retrieval Failure Attribution。

Frozen Evaluation 的未判定返回项只能由隔离 Reviewer 在正式运行后统一判断，V3.5-B 不得看到 Case-level 内容后再开发。

### Outputs

Development：

```text
product_retrieval_gold.development.v1.jsonl
product_evidence_gold.development.v1.jsonl
product_sufficiency_gold.development.v1.jsonl
product_gold_review.development.v1.jsonl
product_gold_adjudication.development.v1.jsonl
```

Frozen：

```text
product_retrieval_gold.frozen.v1.sealed.jsonl
product_evidence_gold.frozen.v1.sealed.jsonl
product_sufficiency_gold.frozen.v1.sealed.jsonl
product_gold_frozen_v1.manifest.json
```

公共状态：

```text
product_gold_v1.validation.audit.json
PRODUCT_GOLD_V1_LOCK_REPORT.md
```

### Entry Gate

```yaml
p6_protocol_frozen: true
development_and_frozen_packets_separated: true
frozen_access_guard_active: true
```

### Acceptance Gate

- 全部 Development Query 有三层 Gold 或明确合法空值；
- 全部 Frozen Query 已完成并密封；
- 普通 Case 至少一次独立复核；
- 高风险/分歧 Case 完成第二 Review 或用户裁决；
- Evidence Group 由完整原字幕形成；
- Segment Identity、Source Version 和 Timeline 验证通过；
- 无 Candidate Builder / Selector 输出进入 Gold；
- Frozen Gold 无泄漏；
- Validation Audit 错误为 0；
- Development Gold 与 Frozen Gold Manifest Hash 锁定。

### Stop Rule

- 任一 Frozen Case Gold 泄漏给 V3.5-B；
- 标注者根据系统结果修改 Query；
- Evidence Gold 受 CandidateSet 限制；
- Source Authority 无法确认但被标为 `insufficient` 而非 `unverifiable`；
- 仍有未决高风险 Case。

出现 Frozen Gold 泄漏必须停止并返回 Main Session；不得自行换 Split 或重新封存后继续。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- 用 AI Summary 代替字幕；
- 用模型生成不存在的 Quote；
- 将完整 Frozen Gold 放入普通仓库搜索路径；
- 让 Codex 语义裁决 Gold；
- 为让 Gold 与系统输出一致而修改 Required Span。

### Next Stage

```text
P8 — Product Initial Baseline
```

---

# Workstream B — Product Initial Baseline and Bounded Evidence Repair

## P8 — Product Initial Baseline

### Owner

```yaml
owner: v3_5_b
executor: codex
development_gold_visible_after_prediction_freeze: true
frozen_gold_access: forbidden
```

### Purpose

在任何 F1A/F1B 修改前，冻结 Product Development 的真实端到端 Evidence Resolution 初始表现和 Failure Attribution。

### Runtime Chain

```text
Product Default Auto Retrieval
→ Candidate Builder
→ Deterministic Selector
→ Mechanical Gate v1
```

Stage 4B Semantic Judge 尚未实现，不属于本阶段初始链路。

### Inputs

```text
product_query_development_v1.locked.jsonl
product_query_split_v1.locked.json
product_gold_protocol_v1
current Product Default Auto
current Candidate Builder
current Deterministic Selector
current Mechanical Gate v1
frozen code / config / index / snapshot identity
```

### Execution Order

```text
1. Freeze Input Manifest
2. Run Predictions without opening Development Gold
3. Freeze Prediction and Trace Hashes
4. Open Development Gold
5. Score by layer
6. Route unjudged retrieval results to bounded relevance adjudication
7. Freeze Gold Addendum if needed
8. Recompute scores without rerunning predictions
9. Produce Failure Attribution
10. Close Initial Baseline
```

### Required Metrics

#### Retrieval

- any-acceptable-video Recall；
- known-relevant-video Recall；
- Rank@1 / @3 / @5 / @10；
- Empty Result；
- Router Distribution；
- Unjudged Return Count；
- Metadata-only / Transcript Candidate Availability；
- Latency。

#### Candidate Builder

- Complete Acceptable Evidence Group Coverage；
- Required Span Coverage；
- Aspect Coverage；
- Candidate Count；
- Evidence Compression；
- Window Width；
- Cross-run / invalid Candidate；
- Source / Language / ASR 分层。

#### Deterministic Selector

- Bundle Hit；
- Complete-group-available-but-not-selected；
- Required Span Recall；
- Aspect Coverage；
- Compactness；
- Redundancy；
- Selected Candidate Count；
- Latency。

#### Mechanical Gate

- `judge_eligible`；
- `terminal_unverifiable`；
- invalid identity/source/timeline；
- unknown operational state；
- mechanically complete / incomplete；
- invalid decision count。

### Required Failure Attribution

```yaml
primary_failure:
  - retrieval_failure
  - retrieval_gold_unjudged
  - candidate_builder_failure
  - deterministic_selector_failure
  - mechanical_gate_failure
  - source_unverifiable
  - gold_defined_evidence_absent
  - identity_or_scoring_defect
  - end_to_end_bundle_hit
```

每条 Query 只能有一个 Primary Attribution，但可记录 Secondary Factors。

### Outputs

```text
product_initial_baseline.predictions.jsonl
product_initial_baseline.traces/
product_initial_baseline.scores.json
product_initial_baseline.per_query.jsonl
product_initial_baseline.failure_attribution.jsonl
product_initial_baseline.manifest.json
PRODUCT_INITIAL_BASELINE_REPORT.md
```

同时生成 Stress Regression，但不得以 Stress 为唯一优化目标：

```text
stress_set_v2_regression.initial_product_baseline.json
```

### Entry Gate

```yaml
p7_development_gold_complete: true
p7_frozen_gold_sealed: true
query_split_and_gold_hashes_verified: true
current_component_versions_verified_against_03: true
```

### Acceptance Gate

本阶段的 Acceptance 不要求达到预设成绩，而要求：

- Prediction 在 Gold 打开前冻结；
- Frozen Evaluation 未访问；
- 所有 Development Query 有完整终态；
- 分层 Metrics 可复算；
- Unjudged Retrieval 已完成人工相关性处理或明确保留；
- Primary Attribution 覆盖全部 Query；
- Identity / Scoring 缺陷与真实系统失败分开；
- Stress Regression 单独报告；
- 没有修改 V3 Retrieval、Auto Router、Query、Split 或 Gold；
- Manifest、Trace 和 Hash 完整。

### Stop Rule

立即停止：

- Prediction 前读取 Development Gold；
- Frozen Gold 泄漏；
- Index / Code / Component Version 与 `03` 不一致；
- 运行中自动修改 Query 或 Gold；
- Scorer 无法区分 Acceptable Video 与单一 Target Video；
- Primary Failure 依赖猜测而不是 persisted assets。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- 同时实现 F1A/F1B；
- 先看结果再选择 Baseline 配置；
- Best-of-N；
- 用 Stress Set 调 Router；
- 修改 Product Default Auto；
- 将 Mechanical Gate 结果称为 Semantic Sufficiency。

### Next Stage

```text
Checkpoint 1
→ P9 — F1A Candidate Builder Decision
```

---

## Checkpoint 1 — Product Query Set and Product Initial Baseline

### Required State Update

```text
V3_5_CURRENT_STATE.md
03 Decision Ledger
03 Artifact Index
02 Remaining Plan
```

### Must Record

- Product Query Set 数量、版本和 Hash；
- Development / Frozen Evaluation Split；
- 三层 Gold 状态；
- Frozen Gold 隔离状态；
- Initial Baseline 分层 Metrics；
- Primary Failure Distribution；
- F1A 是否满足 Entry Gate；
- F1B 的潜在 Case 只作候选，不提前授权；
- 当前 Session 是否继续或交接 continuation Session。

---

## P9 — F1A Candidate Builder Decision

### Owner

```yaml
decision_owner: v3_5_b
executor_if_authorized: codex
major_cycles_max: 1
```

### Purpose

决定是否对 Product Development 暴露的**通用 Candidate Builder Failure**执行一次有限修复。

### Inputs

```text
PRODUCT_INITIAL_BASELINE_REPORT.md
product_initial_baseline.failure_attribution.jsonl
product_query_development Gold
Stress Set v2 regression
current Candidate Builder implementation
```

### Entry Gate

必须全部满足：

```yaml
product_initial_baseline_accepted: true
product_builder_failures_exist: true
failures_not_caused_by_retrieval: true
failures_not_caused_by_gold_identity_or_scoring_bug: true
generic_mechanism_identified: true
frozen_evaluation_not_accessed: true
```

### Decision Outcomes

```yaml
decision:
  - execute
  - skip
  - reject
  - record_as_limitation
```

### Allowed Generic Directions

仅当 Baseline 支持时：

- 邻接 Segment 补齐；
- Query Aspect Coverage；
- 远距离 Required Span 组合；
- Candidate Budget 分配；
- ASR Acronym / Entity Robustness；
- Candidate 去重；
- 同视频多 Anchor 组合；
- Timeline-safe Window Assembly；
- Metadata-only Video 到字幕 Candidate 的合法桥接。

### Major Cycle

若 `execute`：

```text
Freeze Failure Definition
→ Freeze Generic Design
→ Implement Once
→ Run Full Product Development Regression
→ Run Stress Regression
→ Review Latency / Candidate Budget / Noise
→ Close F1A
```

一个 Cycle 内允许修复实现 Bug，但不得通过连续设计改写规避 Cycle 上限。

### Required Outputs

```text
F1A_CANDIDATE_BUILDER_DECISION.md
f1a_decision.json
```

若执行：

```text
F1A_CANDIDATE_BUILDER_TASK.md
f1a_before_after_predictions/
f1a_before_after_metrics.json
f1a_regression.audit.json
F1A_CANDIDATE_BUILDER_REPORT.md
```

### Acceptance Gate

无论执行与否，必须：

- 决策有 Product Baseline 证据；
- 不以单一 Stress Case 为理由；
- 不修改 V3 Retrieval 或 Router；
- 不注入 Gold Span；
- 不增加 Case/Video 特判；
- 记录 Product Dev、Stress、Latency、Candidate Count、Compression、Noise 和回归；
- 形成最终 Candidate Builder Version 或明确保留当前版本；
- F1A 状态关闭，不再开放第二个 Major Cycle。

### Stop Rule

- 通用机制无法明确；
- 修复需要 Segment Dense Index 或重型 Reranker；
- 修复依赖 Query / Gold 修改；
- Product Dev 没有真实 Builder Failure；
- 一次 Cycle 后仍需第二套方案；
- 普通 Product Query 已表现良好，只剩极端 Stress Failure。

此时选择 `reject` 或 `record_as_limitation`，不得扩大项目。

### Skip Policy

```yaml
skippable: true
major_cycles_max: 1
```

### Forbidden

- Case ID / Video ID 规则；
- Gold Segment 注入；
- 无限扩 Window；
- 为 Stress 指标过度工程；
- 读取 Frozen Evaluation；
- F1A 未关闭就进入 F1B 实现。

### Next Stage

```text
P10 — F1B Deterministic Selector Decision
```

---

## P10 — F1B Deterministic Selector Decision

### Owner

```yaml
decision_owner: v3_5_b
executor_if_authorized: codex
major_cycles_max: 1
```

### Purpose

决定是否对 Product Development 中“完整可接受 Evidence Group 已在 CandidateSet 中，但 Deterministic Selector 未选中”的通用失败执行一次有限修复。

### Inputs

```text
F1A final decision and final Candidate Builder baseline
Product Development per-query candidates and bundles
Stress Regression
current Deterministic Selector
```

### Entry Gate

```yaml
f1a_decision_closed: true
final_candidate_builder_baseline_frozen: true
complete_group_available_but_not_selected_exists_in_product_development: true
selector_failure_not_caused_by_schema_identity_or_scorer: true
frozen_evaluation_not_accessed: true
```

若 Product Development 不存在该失败：

```yaml
recommended_decision: skip_or_reject
```

不得仅因 Stress Set 存在 Selector Failure 强制实施。

### Decision Outcomes

```yaml
decision:
  - execute
  - skip
  - reject
  - record_as_limitation
```

### Allowed Generic Directions

- Aspect-aware Coverage；
- Set-cover-like Combination；
- Span Complementarity；
- Controlled Redundancy；
- Coverage / Compactness Trade-off；
- Candidate Group Scoring；
- Multi-span Bundle Assembly；
- Stable Tie-breaking；
- Candidate Budget-aware Selection。

### Major Cycle

若 `execute`：

```text
Freeze Selector Failure Definition
→ Freeze Generic Objective
→ Implement Once
→ Full Product Development Regression
→ Stress Regression
→ Review Coverage / Compactness / Latency
→ Close F1B
```

### Required Outputs

```text
F1B_DETERMINISTIC_SELECTOR_DECISION.md
f1b_decision.json
```

若执行：

```text
F1B_DETERMINISTIC_SELECTOR_TASK.md
f1b_before_after_predictions/
f1b_before_after_metrics.json
f1b_regression.audit.json
F1B_DETERMINISTIC_SELECTOR_REPORT.md
```

### Acceptance Gate

- Entry Failure 在 Product Dev 中真实存在；
- 未原样恢复 Structured LLM Selector v1；
- 未建设新的 LLM Selector 项目；
- 未修改 Candidate Builder 掩盖 Selector Failure；
- Product Dev、Stress、Latency、Selected Count、Redundancy、Compactness 和回归完整；
- 最终 Deterministic Selector Version 冻结；
- F1B 状态关闭，不再开放第二个 Major Cycle。

### Stop Rule

- Product Dev 没有 Selector Failure；
- 需要 LLM 全文重排；
- 需要读取 Gold Candidate ID；
- 一次 Cycle 后仍需第二套方案；
- 改善只发生在一个 Stress Case；
- Compactness 或延迟明显失控。

选择 `reject` 或 `record_as_limitation`，不得扩大。

### Skip Policy

```yaml
skippable: true
major_cycles_max: 1
```

### Forbidden

- 原样恢复旧 Structured LLM Selector；
- Gold Candidate Hint；
- Case-specific Prompt；
- Frozen Evaluation 调参；
- 将 LLM 作为默认逃生通道；
- Best-of-N Bundle Selection。

### Next Stage

```text
Checkpoint 2
→ P11 — Stage 4A-R
```

---

## Checkpoint 2 — F1A / F1B Decisions

### Required State Update

```text
V3_5_CURRENT_STATE.md
03 Decision Ledger
03 Artifact Index
02 Remaining Plan
```

### Must Record

- F1A outcome；
- F1B outcome；
- Major Cycle 是否使用；
-最终 Candidate Builder / Selector 版本；
- Product Dev before/after；
- Stress Regression；
- 延迟、Candidate Budget、Compression、Compactness；
- 已知 Limitation；
- Stage 4A-R 冻结输入；
- 是否需要新的 V3.5-B continuation Session。

Checkpoint 2 后：

```yaml
f1a_open: false
f1b_open: false
evidence_resolution_development_baseline: frozen
```

---

# Workstream C — Sufficiency, Minimal Integration and Version Closeout

## P11 — Stage 4A-R Mechanical Gate Revalidation

### Owner

```yaml
owner: v3_5_b
executor: codex
```

### Purpose

在最终 Product Development Evidence Resolution Baseline 上重新验证机械合法性、终态映射和 Judge Input Readiness，使历史 Mechanical Gate v1 不再依赖过时 Stage 3A 输入。

### Inputs

```text
final Product Development predictions
final Candidate Builder
final Deterministic Selector
current Mechanical Gate v1
Development Gold for scoring only
Stress Set regression
```

### Scope

验证：

- Evidence Identity；
- Source Version；
- Timeline Run；
- Segment / Candidate / Bundle 合法性；
- EvidenceBundle 非空和 Schema 完整性；
- Mechanical Completeness；
- Title-only / Metadata-only / no-subtitle 状态；
- `judge_eligible` 与 `terminal_unverifiable`；
- unknown operational state；
- API Contract；
- Failure Attribution。

### Outputs

```text
stage4a_r.predictions.jsonl
stage4a_r.per_query.jsonl
stage4a_r.metrics.json
stage4a_r.manifest.json
STAGE4A_R_MECHANICAL_GATE_REVALIDATION_REPORT.md
```

### Entry Gate

```yaml
checkpoint_2_complete: true
f1a_closed: true
f1b_closed: true
final_evidence_resolution_baseline_frozen: true
```

### Acceptance Gate

- 全部 Product Dev Query 有机械终态；
- invalid Evidence 不进入 Semantic Judge；
- Source / Version / Timeline Failure 保守降级；
- unknown state = 0；
- invalid decision = 0；
- Judge Input Adequacy 单独报告；
- Mechanical Gate 不输出 Semantic Sufficiency 声明；
- Product 与 Stress 结果分开；
- Stage 4B Input Contract 冻结。

### Stop Rule

- 仍存在非法 Evidence 进入 `judge_eligible`；
- `unverifiable` 与 `insufficient` 机械映射混乱；
- Mechanical Gate 依赖 Gold；
- 必须修改 V3 Retrieval 才能通过；
- API Contract 仍不稳定。

只修机械缺陷，不提前修改 Semantic Judge。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- 将 Mechanical Gate Accuracy 当最终 Sufficiency；
- 用 Gold Label 决定 Runtime State；
- 重新打开 F1A/F1B；
- 进入 Frozen Evaluation。

### Next Stage

```text
P12 — Stage 4B Semantic Sufficiency Development
```

---

## P12 — Stage 4B Semantic Sufficiency Development

### Owner

```yaml
owner: v3_5_b
executor: codex
semantic_human_authority: user
```

### Purpose

实现并验证真正的 Semantic Sufficiency Judge，使系统在合法 EvidenceBundle 上区分：

```text
sufficient
partial
insufficient
unverifiable
```

同时控制 false-sufficient 和 false-answer。

### Runtime Input Boundary

Judge Runtime 可以读取：

```yaml
allowed_runtime_inputs:
  - original_query_or_evidence_question
  - evidence_bundle
  - evidence_source_metadata
  - source_language
  - source_type
  - mechanical_gate_state
  - policy_version
```

Judge Runtime 不得读取：

```yaml
forbidden_runtime_inputs:
  - gold_status
  - gold_required_aspects
  - gold_evidence_groups
  - gold_required_spans
  - expected_failure
  - case_id_specific_hint
  - target_answer
```

`required_aspects` 只存在于 Eval Gold；Runtime Judge 必须从 Query 和 Evidence 自主形成 `supported_aspects` 与 `missing_aspects`。

### Three Diagnostic Tracks

```yaml
track_a:
  role: end_to_end_product_sufficiency
  input: Product Auto Retrieval → Builder → Selector → Gate → Judge
  product_claim_eligible: true

track_b:
  role: oracle_video_conditional_sufficiency
  input: known relevant video → Builder → Selector → Gate → Judge
  product_claim_eligible: false

track_c:
  role: oracle_evidence_judge_only
  input: approved Development Evidence Group → Gate → Judge
  product_claim_eligible: false
```

Track B 隔离 Retrieval；Track C 隔离 Retrieval、Builder 和 Selector。二者只能解释组件上限或失败归因。

### Semantic Policy

```yaml
sufficient:
  all_material_aspects_supported: true

partial:
  meaningful_subset_supported: true
  material_aspects_missing: true

insufficient:
  authoritative_source_reviewable: true
  usable_main_answer_not_supported: true

unverifiable:
  authoritative_source_unavailable_or_unreliable: true
```

### Development Sequence

```text
1. Freeze Judge Request / Decision Schema
2. Freeze Initial Prompt / Policy / Model
3. Run Product Development Track A
4. Run Development Diagnostic Track B / C
5. Freeze Predictions
6. Score against Development Sufficiency Gold
7. Perform Failure Analysis
8. Allow at most one substantive generic semantic revision
9. Rerun full Product Development and diagnostics
10. Freeze final Prompt / Policy / Model
```

Schema-only repair在预测未被接受、且没有利用 Gold 语义时可单独记录，不用于规避语义 Revision 上限。

### Required Metrics

- Four-state Confusion Matrix；
- Macro-F1（若各类支持，否则明确不可用）；
- Accuracy；
- Per-class Precision / Recall；
- False-sufficient；
- False-insufficient；
- Abstention / Unverifiable；
- Supported Aspect Precision / Recall；
- Missing Aspect Precision / Recall；
- Invalid Structured Output；
- Repair Rate；
- Latency；
- Token / Cost；
- Track A / B / C 分开结果。

### Outputs

```text
stage4b_sufficiency_request.schema.json
stage4b_sufficiency_decision.schema.json
stage4b_semantic_policy.md
stage4b_prompt_registry.json
stage4b_development_predictions.track_a.jsonl
stage4b_development_predictions.track_b.jsonl
stage4b_development_predictions.track_c.jsonl
stage4b_development_metrics.json
stage4b_failure_analysis.jsonl
stage4b_manifest.json
STAGE4B_SEMANTIC_SUFFICIENCY_DEVELOPMENT_REPORT.md
```

### Entry Gate

```yaml
p11_stage4a_r_accepted: true
judge_input_contract_frozen: true
development_sufficiency_gold_available: true
frozen_gold_access: false
```

### Acceptance Gate

Acceptance 不是机械追求某个未预先批准的分数，而要求：

- Runtime 未读取 Gold；
- 四态 Policy 可执行且无重叠；
- Structured Output 有效；
- false-sufficient 被单独审查；
- Track A/B/C 分开；
- Product Claim 只使用 Track A；
- Prompt / Policy / Model / Temperature / Schema 版本冻结；
- Revision 次数未超限；
- 全部失败、回归和限制记录；
- Minimal Integration 输出合同稳定。

若结果不足以支持产品声明，可接受为 `completed_with_limitation`，但不得掩盖问题。

### Stop Rule

- 需要 Gold Required Aspect 作为 Runtime 输入；
- 需要多 Agent Reviewer 或复杂新架构；
- 一个 Revision 后仍反复改变方向；
- 只能通过 Case-specific Prompt 改善；
- false-sufficient 无法控制；
-成本或延迟显著超出最小产品边界；
-必须进入 Final Answer Generation。

阻断性问题返回 Main Session；非阻断问题记录 Limitation。

### Skip Policy

```yaml
skippable: false
semantic_revision_cycles_after_initial_baseline_max: 1
```

### Forbidden

- 使用 Frozen Gold；
- 将 Mechanical Gate 当语义 Judge；
- Track C 冒充产品结果；
- 生成最终答案；
- 将 Gold Aspect 写进 Prompt；
-无限 Prompt 调优；
- Best-of-N 或选择最好一次。

### Next Stage

```text
Checkpoint 3
→ P13 — Minimal API / UI / Trace Integration
```

---

## Checkpoint 3 — Stage 4B Development

### Required State Update

```text
V3_5_CURRENT_STATE.md
03 Decision Ledger
03 Artifact Index
02 Remaining Plan
```

### Must Record

- Stage 4A-R 状态；
- Stage 4B Prompt / Policy / Model / Schema；
- Track A/B/C Development 结果；
- False-sufficient / False-insufficient；
- Revision 次数；
- Known Limitations；
- Minimal Integration Input / Output Contract；
- Frozen Evaluation Readiness Blockers；
- 是否需要新的 V3.5-B continuation Session。

Checkpoint 3 后：

```yaml
semantic_development_iteration_open: false
frozen_evaluation_still_locked: true
```

---

## P13 — Minimal API / UI / Trace Integration

### Owner

```yaml
owner: v3_5_b
executor: codex
```

### Purpose

将 V3.5 的 Evidence 与 Sufficiency 能力接入最小可演示产品闭环，但不实现最终答案或 Agent 行为。

### Allowed Outputs

```yaml
evidence:
  - evidence_bundle_id
  - evidence_ids
  - source_type
  - source_language
  - start_time
  - end_time
  - quote_text_or_source_text
  - selector_method

sufficiency:
  - status
  - supported_aspects
  - missing_aspects
  - reason_codes
  - confidence
  - policy_version

trace:
  - trace_id
  - search_identity
  - source_version
  - component_versions
  - terminal_state
```

### UI Boundary

允许：

- Evidence Preview；
-原字幕时间范围；
-四态状态；
-支持/缺失 Aspect；
-Reason Code；
-可审计 Trace；
-保守错误状态。

禁止：

- 最终自然语言答案；
- 多视频综合结论；
-下一步行动；
-Agent Loop；
-Memory；
-用户决策替代。

### Outputs

```text
minimal_v3_5_api_contract.json
minimal_v3_5_trace_contract.json
minimal_v3_5_ui_contract.md
minimal_integration_tests/
MINIMAL_API_UI_TRACE_INTEGRATION_REPORT.md
V3_5_CLOSEOUT_DRAFT_PRE_FROZEN.md
```

`V3_5_CLOSEOUT_DRAFT_PRE_FROZEN.md` 只记录正式运行前已经冻结的版本、Product Development、Stress Regression、Known Limitations 和待填 Frozen Evaluation 章节，不得预写或推测 Frozen 结果。

### Entry Gate

```yaml
checkpoint_3_complete: true
stage4b_prompt_policy_frozen: true
stage4b_output_contract_stable: true
```

### Acceptance Gate

- Product Search → Evidence → Sufficiency 链路可调用；
- Quote 和时间直接来自权威原字幕/ASR；
- 所有 Version 和 Trace 可见；
- 无 Final Answer；
- 错误与 `unverifiable` 路径可表达；
- API / UI / Trace Schema 测试通过；
- Existing Product Search 不回归；
- Frozen Evaluation Runner 可以复用同一正式链路；
- Pre-Frozen Closeout Draft 已生成，所有 Frozen Evaluation 结果字段保持空白。

### Stop Rule

- 接入需要大规模前端重构；
- 必须生成最终答案才可展示；
- Trace 无法绑定 Component Version；
- UI 修改侵入 V4 Agentic Search；
- Evidence 文本由模型重写。

优先缩小 Integration，不扩大范围。

### Skip Policy

```yaml
skippable: false
minimum_scope_reduction_allowed: true
```

### Forbidden

- 建设完整聊天产品；
-加入多轮 Agent；
-加入 Memory；
-使用 AI Summary 作为 Quote；
-为 Demo 绕过正式 Gate；
-接入 Frozen Gold。

### Next Stage

```text
P14 — Frozen Evaluation
```

---

## P14 — Frozen Evaluation

### Owner

```yaml
run_authority: v3_5_b
executor: isolated_codex_runner
gold_visibility_during_development: forbidden
formal_result_acceptance: v3_5_b
rerun_authority_after_result_exposure: main_session_only
```

### Purpose

在 Query、Split、Gold、实现、Prompt、Policy、模型、Runner 和 Closeout Draft 全部冻结后，对 Product Frozen Evaluation Set 进行一次正式运行。

### Pre-run Freeze

必须冻结：

```yaml
release_candidate:
  product_query_set_hash:
  split_hash:
  frozen_gold_manifest_hash:
  code_commit_or_worktree_manifest:
  index_or_snapshot_identity:
  product_wiring_version:
  candidate_builder_version:
  selector_version:
  mechanical_gate_version:
  semantic_prompt_version:
  semantic_policy_version:
  model:
  temperature:
  api_trace_contract_version:
  runner_version:
```

### Formal Run Sequence

```text
1. Verify Protected Inputs
2. Verify no Development writes remain
3. Freeze Release Candidate Manifest
4. Execute once
5. Freeze Raw Predictions and Traces
6. Isolated scoring against sealed Gold
7. Independently adjudicate any unjudged retrieval return
8. Freeze final scores without rerunning predictions
9. Expose final aggregate and permitted case-level diagnostics
10. Close Frozen Evaluation
```

### Required Reporting Layers

#### Product End-to-end

```text
Auto Retrieval
→ Candidate Builder
→ Deterministic Selector
→ Mechanical Gate
→ Semantic Judge
```

#### Component Metrics

- Retrieval；
- Builder；
- Selector；
- Mechanical Gate；
- Semantic Judge；
- Latency / Cost；
- Failure Attribution。

#### Diagnostic Tracks

Oracle-video / Oracle-evidence 可以在 Frozen Evaluation 中作为隔离诊断，但：

- 必须预先冻结；
-不得影响 Product Prediction；
-不得称为端到端产品表现；
-不得用于正式结果暴露后调参。

### Outputs

```text
frozen_evaluation_release_candidate.manifest.json
frozen_evaluation_raw_predictions.jsonl
frozen_evaluation_traces/
frozen_evaluation_scores.json
frozen_evaluation_per_query.jsonl
frozen_evaluation_failure_attribution.jsonl
frozen_evaluation_execution.audit.json
FROZEN_EVALUATION_REPORT.md
```

### Entry Gate

```yaml
query_and_split_frozen: true
frozen_gold_sealed: true
f1a_f1b_closed: true
stage4a_r_complete: true
stage4b_complete: true
minimal_integration_complete: true
implementation_frozen: true
development_iteration_stopped: true
closeout_draft_ready: true
```

### Acceptance Gate

- 正式运行只执行一次；
- Release Candidate Hash 全部匹配；
- Frozen Gold 在运行前未泄漏；
- Prediction 和 Trace 完整；
- Unjudged Retrieval 由隔离人工流程判断；
- Product / Component / Diagnostic 报告分开；
- 无 Best-of-N、Cherry-pick 或结果后调参；
- Formal Run 有效；
-所有失败和限制进入 Closeout。

### Invalid Run Rule

只有机械失败可标记无效，例如：

- Runner 崩溃；
-输入损坏；
-输出未完整写入；
-版本 / Hash 不匹配；
-隔离协议破坏。

必须：

```text
Preserve Invalid Run
→ Mark formal_run_invalid
→ Stop
→ Escalate Main Session
```

V3.5-B 不得自行看过结果后作废并重跑。

### Stop Rule

- 任一 Frozen Gold 泄漏；
- Release Candidate 不匹配；
-试图在运行后改 Prompt / Policy / Query / Gold；
-多次运行选择最好结果；
-正式运行无效。

### Skip Policy

```yaml
skippable: false
formal_valid_runs_max: 1
```

### Forbidden

- 结果后调参；
-重复语义检查寻找更好结果；
-将失败 Case 移回 Development；
-改 Gold 迎合输出；
-自动启动 V4；
-将 Oracle Track 作为 Product Result。

### Next Stage

```text
P15 — V3.5 Final Closeout
```

---

## P15 — V3.5 Final Closeout

### Owner

```yaml
closeout_author: v3_5_b
acceptance_authority: main_session
```

### Purpose

形成可供主 Session 判断是否接受 V3.5、是否进入 V4 的最终版本结论。

### Inputs

- Product Query Set、Split 和三层 Gold；
- Product Initial Baseline；
- F1A / F1B Decision；
- Stage 4A-R；
- Stage 4B；
- Minimal Integration；
- Frozen Evaluation；
- Stress Set v2 Regression；
- Eval v1 Historical Baseline；
-全部 Component、Prompt、Policy、Schema、Trace 和 Hash。

### Required Report Views

#### 1. Product Development View

- Query Set 定位；
- Development 分层结果；
- F1A/F1B before/after 或 Skip/Reject；
- Stage 4B Development；
- Minimal Integration。

#### 2. Frozen Evaluation View

- 端到端产品结果；
-分层组件结果；
-失败归因；
-延迟与成本；
-有效性和隔离审计。

#### 3. Stress Set View

- 复杂 Evidence Resolution；
-Builder / Selector Regression；
-不将其称为 Product Benchmark。

#### 4. Eval v1 Historical View

- 早期 Identity、Gold、Builder、Selector 和 Mechanical Gate 基线；
-不与 Product / Frozen Eval 混合。

#### 5. Diagnostic Boundaries

```yaml
track_a:
  product_claim_eligible: true

track_b:
  oracle_video_conditional: true
  product_claim_eligible: false

track_c:
  oracle_evidence_judge_only: true
  product_claim_eligible: false
```

#### 6. Known Limitations

至少包括：

- Retrieval Gold 非穷尽；
- Product Query Set 非真实历史 Search Log；
- Source / ASR / Cross-language 限制；
-未修复 Stress Failure；
-Builder / Selector / Judge Limitation；
-模型、成本、延迟；
-未实现 Final Answer 与 Agentic Search。

#### 7. V4 Input Contract

只定义后续输入，不执行 V4：

```text
AI Summary helps choose videos
→ Raw Transcript supports cited answer
```

V4 可接收：

- Product Auto Search；
- EvidenceBundle；
- SufficiencyDecision；
- Trace；
- Failure Reason；
- Source / Time Authority。

V4 不得把 Summary 提升为 Evidence。

### Outputs

```text
V3_5_FINAL_CLOSEOUT.md
V3_5_FINAL_DECISION_LEDGER.md
V3_5_FINAL_ARTIFACT_MANIFEST.json
V3_5_FINAL_REGRESSION_REPORT.md
V3_5_TO_V4_INPUT_CONTRACT.md
```

### Entry Gate

```yaml
p14_frozen_evaluation_valid: true
all_required_stage_decisions_closed: true
all_current_artifacts_indexed: true
known_limitations_complete: true
```

### Acceptance Gate

V3.5-B 只能提交：

```text
V3.5 Acceptance Recommendation
```

Closeout 必须：

- 区分 Product、Frozen、Stress 和 Historical；
- 区分 Track A/B/C；
- 不隐藏负结果；
- 不把 skipped repair 写成完成；
- 不把 Limitation 写成未来承诺；
- 所有路径、Hash、版本和 Supersession 完整；
- `V3_5_CURRENT_STATE.md` 更新为 closeout candidate；
- Main Session 决策问题清楚。

### Stop Rule

- Frozen Evaluation 无效；
- Artifact / Hash 不完整；
- Product 和 Stress 结果混淆；
- Track B/C 被当作产品结果；
- 仍有开放 F1A/F1B 或 Stage 4 Decision；
- V4 能力已经被偷偷实现。

### Skip Policy

```yaml
skippable: false
```

### Forbidden

- V3.5-B 自行宣布 Accepted；
- 自动启动 V4；
- 只汇报最佳指标；
- 删除历史负结果；
- 承诺未完成修复；
- 将 Final Answer 纳入 V3.5。

### Next Stage

```text
Main Session Review
→ Accept V3.5 / Require Bounded Closeout Patch / Reject Version Closeout
```

---

## 4. Stage Skip Matrix

| Stage | Skippable | Rule |
|---|---:|---|
| R0 Intake Audit | No | 新负责人必须证明正确接管 |
| P0 Stage 3R-PQS-B0 Review | No | 未验收 Packet 不得启动独立出题 |
| P1 Independent Authoring | No | Product Query 的独立性来源 |
| P2 Legacy Reconciliation | No | 已批准的第二阶段历史参考处理 |
| P3 User Validation | No | 产品真实性最高权威 |
| P4 Query Freeze | No | 防止结果驱动改写 |
| P5 Split Freeze | No | 防止后验分组 |
| P6 Gold Protocol Freeze | No | 防止三层 Gold 混淆 |
| P7 Gold Construction | No | Baseline 和 Formal Eval 的评分基础 |
| P8 Product Initial Baseline | No | F1A/F1B 唯一进入依据 |
| P9 F1A | **Decision may skip** | Stage 必须关闭，但实现可以 skip/reject |
| P10 F1B | **Decision may skip** | Stage 必须关闭，但实现可以 skip/reject |
| P11 Stage 4A-R | No | 最终 Evidence Baseline 的机械验证 |
| P12 Stage 4B | No | V3.5 Mission 的 Semantic Sufficiency 核心 |
| P13 Minimal Integration | No | 可缩到最低范围，但不可取消 |
| P14 Frozen Evaluation | No | 正式版本评估 |
| P15 Final Closeout | No | 主 Session 接受依据 |

---

## 5. Context Checkpoint Summary

| Checkpoint | Trigger | 必须冻结 |
|---|---|---|
| 1 | Product Query Set + Product Initial Baseline | Query、Split、Gold、Initial Prediction、Failure Attribution |
| 2 | F1A/F1B Decisions | 最终 Builder、Selector、Evidence Resolution Baseline |
| 3 | Stage 4B Development | Prompt、Policy、Model、Schema、Track A/B/C Development |

每次 Checkpoint 必须更新：

```text
V3_5_CURRENT_STATE.md
01_V3_5_B_OPERATING_CONTRACT.md（仅必要 Amendment）
02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md
03_V3_5_DECISION_AND_ARTIFACT_INDEX.md
```

如果上下文过长、旧方案反复、文件漂移或版本负责人无法准确复述当前 Gate：

```text
Freeze Checkpoint
→ Create Continuation Handoff
→ Start New V3.5-B Continuation Session
```

不得把权威交回 V3.5-A。

---

## 6. Cross-stage Invariants

整个剩余路线始终必须满足：

```yaml
v3_retrieval_retuning: forbidden
auto_router_retuning: forbidden
product_default_mode: auto

stress_set_role: evidence_sufficiency_stress_set
stress_set_as_product_benchmark: forbidden

query_result_driven_rewrite: forbidden
independent_authoring_rounds_max: 1
legacy_reconciliation_rounds_max: 1
user_revision_rounds_max: 1
final_query_count_max: 24

retrieval_gold_exhaustive: false
evidence_gold_from_full_raw_transcript: true
frozen_gold_visibility_during_development: forbidden

f1a_major_cycles_max: 1
f1b_major_cycles_max: 1
structured_llm_selector_v1_revival: forbidden

final_answer_generation: forbidden
agentic_search: forbidden
memory_and_harness: forbidden

frozen_evaluation_valid_runs_max: 1
post_frozen_result_tuning: forbidden
```

---

## 7. Escalation Summary

必须返回 Main Session：

- Product Query Set 无法在 20–24 条收口；
- Product Query 独立性无法维持；
- 三层 Gold 无法分离；
- Frozen Gold 泄漏；
- 需要重调 V3 Retrieval 或 Auto Router；
- F1A/F1B 一轮后仍有阻断性通用失败；
- Stage 4B 需要复杂新架构、多 Agent Reviewer 或显著新增成本；
- Minimal Integration 必须进入 Final Answer；
- Formal Frozen Evaluation 无效且需要重跑；
- V3.5 开始侵入 V4/V5；
-准备 V3.5 Final Closeout。

普通 Bug、局部 Schema、单次合法 Development 修正和非阻断 Limitation 不需要升级。

---

## 8. Remaining-plan State Ledger

Checkpoint 1 固化状态：

| Stage | Status |
|---|---|
| R0 Intake Audit | `complete_and_accepted` |
| P0 Stage 3R-PQS-B0 Review | `complete_and_accepted` |
| P1 Independent Authoring | `complete_and_accepted` |
| P2 Legacy Reconciliation | `complete_and_accepted` |
| P3 User Validation | `complete_and_accepted` |
| P4 Query Freeze | `complete_and_accepted` |
| P5 Split Freeze | `complete_and_accepted` |
| P6 Gold Protocol Freeze | `complete_and_accepted` |
| P7 Gold Construction | `complete_and_accepted` |
| P8 Product Initial Baseline | Prediction Set `valid_and_frozen` (`P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3`); original scoring superseded; Amendment v1 execution candidate |
| Checkpoint 1 | Original derived findings superseded; Amendment v1 `execution_candidate_ready`; acceptance `pending_v3_5_b_review` |
| P9 F1A Decision | Previous attempt safely blocked; `blocked_pending_v3_5_b_acceptance`; not restarted; F1A not authorized |
| P10 F1B Decision | `candidate_signal_recorded`; waits for P9; F1B not authorized |
| Checkpoint 2 | `not_started` |
| P11 Stage 4A-R | `not_started` |
| P12 Stage 4B | `not_started` |
| Checkpoint 3 | `not_started` |
| P13 Minimal Integration | `not_started` |
| P14 Frozen Evaluation | `formally_not_run` |
| P15 Final Closeout | `not_started` |

每次 Stage Acceptance 或 Checkpoint 后更新本表，不得只更新聊天记录。

---

## 9. Draft Self-review Checklist

```yaml
scope:
  full_v3_5_history_repeated: false
  role_contract_redefined: false
  complete_existing_artifact_index_repeated: false
  start_prompt_repeated: false

route:
  intake_present: true
  formal_stages: 16
  checkpoints: 3
  stage_order_unambiguous: true

stage_template:
  owner_present: true
  purpose_present: true
  inputs_present: true
  actions_present: true
  outputs_present: true
  entry_gate_present: true
  acceptance_gate_present: true
  stop_rule_present: true
  skip_policy_present: true
  forbidden_present: true
  next_stage_present: true

product_query:
  independent_pass1: present
  legacy_pass2: present
  user_pass3: present
  minimum_20_target_24_maximum_24: present
  result_driven_rewrite_forbidden: present

gold:
  retrieval_evidence_sufficiency_separated: true
  retrieval_gold_exhaustive_false: true
  full_raw_transcript_authority: true
  frozen_gold_isolated: true
  unjudged_retrieval_route_defined: true

baseline_and_repairs:
  prediction_frozen_before_dev_gold: true
  layered_failure_attribution: true
  f1a_optional_implementation: true
  f1b_optional_implementation: true
  major_cycles_max_1_each: true

sufficiency:
  stage4a_r_present: true
  stage4b_tracks_a_b_c_separated: true
  runtime_gold_inputs_forbidden: true
  false_sufficient_priority: true
  final_answer_out_of_scope: true

frozen_evaluation:
  release_candidate_freeze: true
  one_valid_formal_run: true
  post_result_tuning_forbidden: true
  invalid_run_escalation: true

closeout:
  product_frozen_stress_historical_views_separated: true
  v3_5_b_cannot_self_accept: true
  v4_input_only_no_v4_execution: true
```
