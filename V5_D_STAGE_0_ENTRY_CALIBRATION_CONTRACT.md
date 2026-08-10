# Shiliu V5-D Stage 0 Contract — Bounded Entry Calibration

> Status: completed_and_accepted_by_main
> Version Charter: `V5_D_VERSION_CHARTER.md`
> Startup Plan: `V5_D_STARTUP_AND_EXECUTION_PLAN.md`
> Baseline branch: `codex/v5-main`
> Baseline accepted code commit: `8904e27df07becebae13110f9be17cd829373b20`
> Planning head at preparation: `f85d504`
> Planned execution branch: `codex/v5-d`
> Authorized by: user
> Authorized at: 2026-08-11
> Product implementation authorized: false
> Provider runs authorized: true within Contract, maximum total paid cost USD 2

---

# 1. Mission

在不预设 Failure Family、Candidate 或 Search Skill 的前提下，先冻结候选无关的代表性真实研究
任务，再用当前 No-Skill Baseline 在真实收藏语料和隔离运行环境中生成可重放 Trace，以判断是否
存在值得进入 V5-D Candidate 生命周期的、重复出现且可定位到 Search / Research Policy 的失败。

本 Stage 的成功不等于“必须找到 Candidate”。诚实的 `no_candidate_qualified` 或
`blocked_by_infrastructure_or_data` 都是有效研究结果。

---

# 2. Product / Program Outcome

Stage 0 完成后，Program 能够基于真实证据回答：

1. 当前产品是否存在至少一个重复 Search / Research Policy Failure Family；
2. 失败是否来自 Policy，而不是 data、retrieval implementation、index/provider 或 Runtime defect；
3. 是否有足够的未污染 related/unrelated reserve 支持后续可证伪实验；
4. V5-D 应进入 Stage 1、停止，还是先另行修复基础设施。

Stage 0 不向用户交付 Active Skill，也不改变产品行为。

---

# 3. Starting Baseline

执行开始时由 V5-D Session 现场核验并填入最终 Report；文档中的旧值不能替代现场事实。

```yaml
baseline:
  risk_level: 3
  program_branch: codex/v5-main
  accepted_code_commit: 8904e27df07becebae13110f9be17cd829373b20
  planning_head: f85d504
  execution_branch: codex/v5-d
  execution_head: to_be_recorded_after_authorized_startup
  working_tree_clean: to_be_verified

  db_schema_version: 14
  live_database_access: read_only_for_copy_and_identity
  live_database_write: false
  isolated_database_identity: to_be_recorded
  corpus_snapshot: to_be_recorded
  lexical_index_version: to_be_recorded
  dense_index_version: to_be_recorded
  source_version_set: to_be_recorded

  prompt_versions: to_be_recorded
  decision_view_version: to_be_recorded
  tool_contract_versions: to_be_recorded
  control_logic_commit: to_be_recorded
  retrieval_version: to_be_recorded
  provider_configuration: to_be_recorded_without_credentials
  active_skill_repo_version: none
  candidate_version: none
  no_skill_baseline: true

  case_manifest_id: to_be_frozen_before_failure_family
  case_manifest_hash: to_be_frozen_before_failure_family
  access_policy_hash: to_be_frozen_before_failure_family
```

若 mainline/schema/index/corpus/provider/scaffold 与规划事实材料性不一致，先报告差异；不得自行用新
Baseline 回填旧计划。

---

# 4. Case Selection and Freeze Protocol

## 4.1 Ordering invariant

以下顺序不可更改：

```text
Freeze candidate-independent coverage rubric
→ Select all representative task bodies
→ Freeze discovery/reserve assignment and hashes
→ Seal reserve bodies/Gold/access
→ Record No-Skill scaffold
→ Run discovery baselines
→ Classify failures
→ Only then qualify a Failure Family
→ Only after Stage 0 acceptance may a Candidate Hypothesis be frozen
```

在具体 Failure Family / Candidate Hypothesis 冻结之后选择“代表性任务”属于 contract violation。
不得为了证明 Query Decomposition、Rewrite、Counterexample、Source Diversity、Follow-up 或 Stop Policy
有效而反向挑题。

## 4.2 Candidate-independent coverage rubric

冻结 8 个真实、用户可理解、语料可回答的任务：

```yaml
case_count:
  discovery: 4
  sealed_reserve: 4
  total: 8

coverage_archetypes:
  - single_video_grounded_synthesis
  - multi_video_comparison
  - claim_with_counterevidence_or_limitations
  - collection_wide_or_source_diverse_research
```

每个 archetype 选择一个 discovery 和一个 sealed reserve。标签只描述用户目标、复杂度、语料边界
和输出要求，不写“预期失败”“应使用 Skill”或希望看到的搜索动作。

选择标准：

- 来自真实收藏语料和合理用户研究需求；
- 任务可由当前 corpus 中的权威 Evidence 支持；
- 不依赖新下载数据或人工编造事实；
- 不从 Candidate 论文、Skill 示例或拟议 Trigger 反向生成；
- 不因为历史 trace 呈现特定失败而优先选择；历史 trace 最多用于校验任务分布是否真实存在；
- 同一主题的措辞改写不算不同任务。

## 4.3 Answerability check

Case Custodian 在运行前确认语料中存在支持完成任务的 Evidence，并冻结 source/evidence boundary
hash。该 check 不能运行 Candidate、调整 query 或向 Candidate designer 暴露 held-out Gold。若语料
不足，该题在 manifest 冻结前替换，并记录 selection reason；冻结后不得因 outcome 不好而替换。

## 4.4 Custody and access

推荐创建一个 bounded Held-out Custodian Session：

- 按已冻结 rubric 选择/哈希 8 个 task bodies；
- 向 V5-D Session 释放 4 个 discovery bodies；
- sealed reserve 只暴露 case ID、hash 和高层 archetype，不暴露 prompt body、Gold 或 Evidence refs；
- 保存 access log；
- 不参与 Candidate 设计、Failure Attribution 或实现；
- 结果先回到 V5-D Session，再由 Main 验收。

若没有独立 Session，应使用等强度的文件权限/加密封装与独立 custodian；不能让 Candidate designer
先阅读 reserve bodies 后仅靠“承诺不使用”声称真正 held-out。

## 4.5 User-frozen sealed reserve rule

4 个 reserve tasks 必须保持真正 sealed。在 Stage 0 discovery、Failure Attribution、Failure Family
qualification 以及任何 Candidate Hypothesis 形成过程中：

- 不得运行 reserve tasks；
- 不得查看其运行结果；
- 不得依据 reserve tasks 调整 discovery tasks；
- 不得依据 reserve tasks 调整 Failure Family 定义；
- 不得依据 reserve tasks 设计 Candidate、trigger、procedure 或 stop rule。

Reserve tasks 只有在后续正式评测用途被新的 Stage Contract 明确授权后才能解封。本 Stage 即使已经
资格化 Failure Family，也只能记录 reserve 的 ID/hash、access state 和未来 split 可行性，不能打开
task body、Gold、Evidence refs 或任何运行结果。

---

# 5. Authorized Changes

用户已批准本 Contract，当前只允许：

```yaml
allowed_changes:
  product_source_paths: []
  product_test_paths: []
  schema: false
  migrations: false
  prompts: false
  ui: false
  dependencies: false
  indexes: false
  live_database: false
  execution_docs_and_reports: true
  private_local_case_and_run_artifacts: true
  isolated_database_copy: true
  bounded_runner_configuration_without_product_behavior_change: true
```

Stage 0 可以用现有 CLI/API/Runtime 和临时命令运行；不得为完成 Stage 0 新建通用 runner、trace、eval
或 skill platform。如果现有可观察性不足以归因，结果为 `blocked_by_infrastructure_or_data`，再另行
提议最小 instrumentation Contract。

---

# 6. Explicitly Disallowed Changes

- Candidate Skill/Hypothesis package；
- Skill Repository、active pointer、retrieval/injection、Progressive Disclosure；
- Runtime、Search、Research、Prompt、Tool Contract、Evidence/Citation 行为；
- product tests、schema、migration、index rebuild 或 live fixture；
- V5-C Answer Presentation 或 generic Context/Tool/Workflow policy；
- Judge、Dataset/Split、Promotion、Invalid Run 或 Tool Permission 规则；
- live DB 写入、Provider 切换、上游下载、依赖或源码复制；
- 第二 Candidate、Post-V5、Pi generic harness 或 Agent Learning Platform；
- 因运行结果不理想而改题、改 threshold、重采样或删除失败。

---

# 7. Protected Invariants

```yaml
protected:
  - task_selection_precedes_failure_and_hypothesis_freeze
  - sealed_reserve_remains_unseen_by_candidate_designer
  - transcript_source_authority
  - stable_citation_and_source_version
  - no_skill_baseline
  - scaffold_fingerprint
  - case_manifest_and_access_policy_hash
  - provider_usage_and_cost_accounting
  - invalid_run_separation
  - no_live_data_mutation
  - no_candidate_or_active_skill
```

---

# 8. Authorized Runs and Budget

用户已按以下边界给予执行预授权：

```yaml
runs:
  startup_audit:
    allowed: true
    mode: local_read_only
  case_freeze:
    allowed: true
    task_count: 8
  deterministic_preflight:
    allowed: true
    affected_tests_only: true
  discovery_product_cases:
    allowed: true
    valid_case_count: 4
    valid_runs_per_case: 1
    invalid_replacement_runs_per_case: 1
  provider:
    allowed: true
    provider: DeepSeek_current_product_configuration_only
    maximum_outer_attempts: 8
    maximum_logical_calls: 96_total
    maximum_input_tokens: 1000000_total
    maximum_output_tokens: 120000_total
    maximum_tool_calls: 400_total
    maximum_total_cost_usd: 2
    retries: invalid_provider_or_infrastructure_run_only
    provider_switch: false
  heldout:
    runtime_access_allowed: false
    candidate_designer_access_allowed: false
  live_database:
    write_allowed: false
```

任一上限先到即停止。不得把一次连续运行拆成多个包规避 USD 2。Keychain 只读使用现有凭据必须
在用户预授权中明确，不显示、不复制、不记录 credential value。

---

# 9. Run Integrity

每个 discovery run 前冻结：

- Case ID/body hash、corpus/source boundary；
- code commit、working tree、schema/temp DB hash；
- lexical/dense index version；
- Prompt、DecisionView、tool contract、control logic；
- Provider/model/temperature or equivalent deterministic settings；
- budgets、No-Skill state、active repo=`none`；
- expected output requirements and evaluator identity。

运行中记录 Task/Attempt/Trace/inner action/outer audit/Provider receipt、工具和 token/cost。运行后记录
Result、EvidenceUse/Citation、missing aspects、stop reason 和 environment hash。

不允许人工修改中间状态、补 Evidence、删失败 step 或在同一 valid case 上机会性重跑。

---

# 10. Failure Classification

每个 run 先按 `001` 分类，再判断是否为 Candidate source：

```yaml
run_result:
  - valid_success
  - valid_partial
  - valid_insufficient
  - product_quality_failure
  - implementation_failure
  - provider_failure
  - infrastructure_invalid_run
  - evaluation_invalid_run
```

对有效非成功结果进一步分类：

```yaml
failure_domain:
  - search_or_research_policy
  - retrieval_implementation_or_index
  - corpus_or_data_coverage
  - provider_quality_or_failure
  - runtime_or_state_machine
  - evaluator_or_contract
  - no_failure
```

零 hit、长回答、更多工具调用、Provider timeout 或单次错答都不自动等于 Search Policy Failure。

---

# 11. Failure Family Qualification Rule

只有同时满足以下条件，Stage 0 才能输出 `qualified_failure_family_found`：

1. 至少 2 个不同 discovery task 的运行有效，不是同一 query 的改写重跑；
2. 两个任务在语料中都存在足够权威 Evidence；
3. Runtime、index、Provider、source version 和 evaluator 健康，替代原因被证据排除；
4. 能在每条 Trace 中定位 first actionable step；
5. first actionable step 属于相同的 initial Search / Research Policy surface；
6. 失败对研究结果有可测影响，例如 required aspect、grounded citation、counterexample、source
   diversity、stop correctness，而不只是输出长度或 hit count；
7. 能写出尚未冻结为 Candidate 的初步 causal question 和未来 falsification shape；
8. Custodian 能在未打开的 reserve 中按预注册 metadata 映射至少 1 个 related 和 2 个 unrelated
   Case，并保留至少 1 个 spare；
9. 没有任何 Candidate、Trigger、Procedure 或 Stop Rule 已参与 Case 选择。

本 Stage 只资格化 Failure Family，不冻结 Candidate Hypothesis。Hypothesis 由 Stage 1 在 Stage 0 被
Main 接受后形成。

---

# 12. V5-A Compound-query Classification

V5-A case 只有在满足以下条件时才可进入 discovery pool，且不能获得特殊优先级：

```text
source Evidence exists
+ dense/lexical/index/model are healthy
+ failure repeats on another distinct task
+ first actionable step is decomposition/rewrite/search strategy
→ possible Search Policy Failure
```

如果 model/index unavailable、lexical fallback 实现不足或 Evidence 不存在，则分别归
`retrieval_implementation_or_index` 或 `corpus_or_data_coverage`。Stage 0 不负责修复，也不得将修复
后的召回提升写成 Candidate Skill 泛化。

---

# 13. Held-out and Future Eval Boundary

Stage 0 不运行 sealed reserve。Stage 2 只有在 Candidate frozen 后才开启：

- related held-out baseline/treatment；
- unrelated regression/negative transfer；
- Candidate-specific Environment Shift（如适用）。

任何 reserve 一旦参与 Candidate、Trigger、Procedure、Stop Rule、threshold 或 evaluator 调整，立即
降级为 development。只能从原 manifest 的 unopened spare 替换；reserve 耗尽则不具备 held-out
generalization 证据。Environment Shift 不是 Portfolio-ready 硬门。

---

# 14. Success and Exit Criteria

```yaml
success:
  mechanical:
    baseline_and_manifest_identity_complete: true
    four_discovery_runs_valid_or_invalid_honestly_accounted: true
    provider_tool_token_cost_receipts_complete: true
    reserve_access_log_clean: true
  evidence:
    every_claim_points_to_trace_run_hash_or_manifest: true
    invalid_runs_excluded: true
    alternative_causes_recorded: true
  outcome:
    exactly_one_of:
      - qualified_failure_family_found
      - no_candidate_qualified
      - blocked_by_infrastructure_or_data
```

`qualified_failure_family_found` 不等于 Candidate validated，也不授权 Stage 1 Contract 或产品实现。
Stage 0 只能提交 Failure Family、建议 Candidate 方向和 Stage 1 Entry 条件；随后停止等待用户再次
明确授权。

---

# 15. Pause Conditions

- Case rubric/manifest 没有先于具体 failure/hypothesis 冻结；
- Custodian 或 Version Session 发现反向选题、held-out 泄漏或 access log 异常；
- 需要产品代码、product tests、schema、migration、index rebuild 或 live DB write；
- baseline identity 不完整或 run 不能重放；
- 需要新 Provider、Provider switch、额外 credential 或将超过任一预算上限；
- 连续 invalid run 说明基础设施不健康；
- Failure 只有一个 task、Evidence 不存在或 first actionable step 不可定位；
- 需要修改 Judge/Gold/Split/Verifier/Promotion/Tool Permission；
- 需要下载上游、复制代码、跨入 Candidate/Skill platform；
- 私人数据可能进入 Git/报告或外部服务边界不清。

---

# 16. Required Report

默认只提交一个：

```text
V5_D_STAGE_0_ENTRY_CALIBRATION_REPORT.md
```

报告必须包含：

- startup baseline 和 branch/commit/tree；
- candidate-independent rubric、manifest/access hashes 和 freeze timestamps；
- discovery/reserve counts、custody/access history；
- 4 个 discovery run 的 redacted ID、Trace、result class、usage/cost；
- failure classification、first actionable evidence、alternative causes；
- invalid/provider/infrastructure events；
- V5-A compound-query classification（若实际进入 pool）；
- reserve 是否足以支持 future related/unrelated，不暴露 bodies/Gold；
- 三选一 Exit Decision；
- Candidate、product code、live DB、upstream、Provider scope 的实际 non-actions；
- Git status 和下一建议。

Raw Case bodies、Gold、完整 Evidence、Raw Provider response、credential 和 temp DB 不提交 Git。其本地
artifact ID/hash/access policy 写入报告即可。

---

# 17. Main Session Acceptance Scope

Main 进行一次有限验收：

- 审核任务冻结是否先于 failure/hypothesis；
- 抽查 manifest/access hash、2 条关键 Trace 和 failure-domain 排除证据；
- 核对 4 个 discovery 结果、invalid 和总成本；
- 确认 reserve 未打开且可支持 future split；
- 不为普通 runner/fixture 问题增加多个 Gate；
- 作出 `accept / partial_accept / rework / pause / reject`。

Main 不设计 Candidate，不读取 held-out Gold，不实施代码，也不把 Session 的 PASS 当正式接受。

---

# 18. Current Authorization and Non-actions

```yaml
current:
  contract_prepared: true
  contract_accepted_by_user: true
  V5_D_session_created: true
  case_manifest_created: true
  stage_0_execution_started: true
  stage_0_execution_completed: true
  stage_0_accepted_by_main: true
  stage_0_exit_decision: qualified_failure_family_found
  provider_runs_performed: true_within_contract
  credentials_accessed: true_via_runtime_without_value_exposure
  live_database_modified: false
  product_code_modified: false
  product_tests_modified: false
  candidate_hypothesis_frozen: false
  candidate_skill_created: false
  skill_repository_created: false
  active_skill_promoted: false
  upstream_downloaded: false
  git_merge_push_tag: false
  stage_1_execution_authorized: false
  stage_2_execution_authorized: false
  stage_3_execution_authorized: false
```

本 Contract 已完成。Main 接受 `qualified_failure_family_found`，但该结论只资格化
`non_progress_search_repetition_without_recovery` Failure Family；不得自动解释为 Stage 1、Candidate、
reserve 解封、Provider 或产品实施授权。
