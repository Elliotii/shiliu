# Shiliu V5-D Startup and Long-range Execution Plan

> Prepared by: Shiliu V5 Main Codex Session
> Prepared at: 2026-08-10
> Status: stage_2_authorized
> Governing Charter: `V5_D_VERSION_CHARTER.md`
> Accepted calibration: `V5_D_STARTUP_DIRECTION_CALIBRATION.md`
> Execution authorization: Stage 2 Frozen Paired Evaluation only
> Execution started: true
> V5-D Version Session created: true

---

# 1. Planning Decision

V5-D 沿用 A/B/C 已验证的治理主干，但把正式门禁压缩为四个 Stage，并增加一条关键停止规则：

```text
Stage 0 没有资格化真实、重复、可归因的 Search Policy Failure
→ 不创建 Candidate
→ 不建设 Skill / Eval / Learning Platform
→ 诚实停止或先修复被证明的基础设施问题
```

这既保留完整技术质量，也避免为了展示 self-improvement 制造失败、扩张 Candidate 类型或重复
建设 V5-A durability、V5-B lineage、V5-C authority。

---

# 2. Authoritative Inputs

本计划以以下材料为权威输入：

1. 用户对 `V5_D_STARTUP_DIRECTION_CALIBRATION.md` 的正式接受和三条补充约束；
2. V5 长期路线和 `00` Session 治理、`001` 研究与证据治理；
3. `V5_PROGRAM_CURRENT_STATE.md`、`V5_PROGRAM_DECISION_LEDGER.md`；
4. V5-A/B/C accepted code、Closeout、known limits 和 live schema 14 事实；
5. Program Registry / Research Log 的当前上游状态；
6. 真实 Git、源码、测试、数据库、index 和运行证据。

路线冻结“仍要证明什么”；Charter 冻结“本版本承诺证明什么”；Stage Contract 冻结“一轮允许
做什么”。本计划不是产品实现授权。

---

# 3. Lessons Applied from V5-A / V5-B / V5-C

## 3.1 Retained practices

- 一个持续 Version Session 主导整个子版本，不为每个 Stage 创建长期 Session；
- Main 只在 Charter/Stage 边界、材料性返工和版本收口做有限验收；
- 普通小 Bug、fixture、projection、runner 和测试入口问题由 Version Session 在 Contract 内自主修复；
- directed + affected tests 是 Stage 默认，完整 default suite 留到材料性 shared-core 变化或 closeout；
- live DB 操作、migration、Provider、凭据、promotion 和不可逆动作必须有显式边界；
- 报告只索引证据，invalid/provider failure 与产品质量分开。

## 3.2 Complexity reductions

- 只有 4 个正式 Stage，不新增 Gate A/B/C 或每个 lifecycle object 的独立 Stage；
- Stage 内设计、实现、修复、复跑合成一次 Implementation/Evaluation Report；
- 不为每个 Candidate 状态创建文件或 Session；
- Stage 0 用小型冻结 manifest 和既有 Runtime 运行，不先建 Eval Platform；
- 初始最多一个 Candidate；没有真实增益就停止；
- Stage 3 才在 validated Candidate 周围建设最小 repository / applicability / rollback；
- 不重复运行完整 no-provider suite，除非改动风险或 closeout 要求。

---

# 4. Session and Authority Model

```text
User
  ↓ material scope/cost, execution pre-authorization, human promotion
V5 Main Session
  ↓ Charter/Contract boundary, limited acceptance, Program state, version Git
One persistent V5-D Version Session
  ↓ optional bounded specialist input for the same active Stage
Upstream Research / Held-out Custodian / Frozen Eval Reviewer
```

```yaml
session_limits:
  active_subversion_limit: 1
  active_formal_stage_or_goal_limit: 1
  persistent_V5_D_version_sessions: 1
  one_long_session_per_stage: false
  specialist_sessions_are_second_formal_line: false
```

V5-D Session 拥有版本内部研究、设计、实现、普通修复、测试和报告权；不能自我接受、修改
Program authority、合入 mainline、Push/Tag、修改长期路线或自行启动 Post-V5。Main 不修改产品代码。

Held-out Custodian / Eval specialist 只在 Stage 0/2 的污染隔离确实需要时创建，且只服务当前正式
Stage。它们不拥有 Candidate 设计或阶段接受权。

Goal 模式适合：Stage 1 多文件 lifecycle 实施、Stage 2 多轮冻结实验、Stage 3 promotion/rollback
纵向集成。Stage 0 任务冻结和少量运行无需为了形式强制 Goal 模式。

---

# 5. Startup Sequence

用户完成执行预授权后，Main 才执行以下启动动作：

1. 再次只读核验 `codex/v5-main`、HEAD、clean tree、schema 14、index/corpus identity 和服务状态；
2. 从本规划 docs commit 创建独立 `codex/v5-d` branch/worktree；
3. 创建并唤起一个持续 V5-D Version Session；
4. 让 Version Session 读取 Charter、Startup Plan、Stage 0 Contract、Program State 和直接相关 Ledger；
5. Version Session 在执行分支创建精简 `V5_D_CURRENT_STATE.md`、`V5_D_DECISION_LEDGER.md`；
6. 只完成 Stage 0 startup audit、case freeze 和授权运行；
7. Version Session 提交单一 Stage 0 Report；
8. Main 有限验收后提交停止、基础设施另行定约或 Stage 1 Entry 建议；无论结果如何都停止，等待
   用户再次明确授权 Stage 1。

启动不等于 Stage 1 Candidate 实施授权。

---

# 6. Full Stage Dependency and Contract Plan

## 6.1 Stage 0 — Bounded Entry Calibration

**Owner:** V5-D Version Session；必要时一个 bounded Held-out Custodian。

**Goal:** 在候选无关的冻结任务上运行当前 No-Skill Baseline，资格化真实重复 Policy Failure，
或者诚实证明当前没有 Candidate / 存在基础设施阻塞。

**Authoritative boundary:** `V5_D_STAGE_0_ENTRY_CALIBRATION_CONTRACT.md`。

**Allowed after authorization:**

- 只读 audit mainline、corpus/index/schema/config；
- 在本地隔离 DB/copy 中运行当前产品 Runtime；
- 冻结和哈希 case/scaffold/access manifests；
- 运行有限真实 DeepSeek Research baseline；
- 记录 Trace、成本、invalid run、failure classification；
- 生成 docs/evidence manifest 和 Stage 0 Report。

**Non-goals:**

- Candidate/Hypothesis 的预设或实现；
- Skill repository、progressive disclosure、promotion；
- 产品 Runtime/schema/prompt/index 修改；
- live DB 写入或 migration；
- 为暴露失败而选题、伪造 Gold 或重复采样到期望结果。

**Entry Gate:**

- 用户明确批准执行包；
- V5-D branch/worktree/session 已按本计划建立；
- mainline、schema、index、corpus、provider/no-skill identity 可核验；
- case selection protocol 先于任何 Failure Family/Hypothesis；
- Provider/Keychain/cost 权限明确。

**Exit Gate:**

```yaml
one_of:
  - qualified_failure_family_found
  - no_candidate_qualified
  - blocked_by_infrastructure_or_data
```

只有第一项可进入 Stage 1。Main 验收 Stage 0 时检查 case freeze 时间/哈希、Trace、first-actionable
evidence、invalid 分类和未打开 reserve pool，不复跑所有 Provider Case。

## 6.2 Stage 1 — Attribution and One Candidate

**Owner:** 同一个 V5-D Version Session；材料性上游研究可交 bounded specialist。

**Goal:** 把 Stage 0 已接受 Failure Family 转化为可审计 Attribution、冻结 Hypothesis 和一个
inactive Candidate package。

**Contract must freeze:**

- accepted failure family / source trace IDs；
- first actionable step 与 alternative causes；
- falsification conditions；
- applicable/non-applicable scope；
- Candidate type、trigger、precondition、procedure、stop/forbidden behavior；
- protected evaluator/split/promotion boundaries；
- Stage 2 exact validation plan；
- schema/migration/module budget和 rollback plan。

**Allowed after its Contract acceptance:**

- 最小 Experience/Attribution/Hypothesis/Candidate lifecycle；
- 一个 versioned Candidate package；
- 机械 validator、lineage、API/inspection surface；
- JIT source/test research that answers a concrete gap；
- temp-DB tests and directed affected regression。

**Non-goals:**

- Active/shadow injection；
- held-out access；
- Candidate 自动生成无限变体；
- generic SkillOS/curator/eval framework；
- 第二 Candidate family；
- Provider treatment comparison，除非 Contract 为诊断最小验证单独授权。

**Entry Gate:** Stage 0 `qualified_failure_family_found` 已由 Main 接受；Case manifest 和 reserve pool
仍完整；Stage 1 Contract 已接受。

**Exit Gate:** Attribution 可定位 first actionable step，Hypothesis 可证伪，Candidate 可确定性验证、
不进入 active Runtime，Stage 2 plan 可执行；否则 `falsified/inconclusive/rework`。

## 6.3 Stage 2 — Frozen Paired Evaluation

**Owner:** V5-D Session 组织；推荐由独立 Eval specialist 持有 held-out bodies/Gold 并生成密封结果。

**Goal:** 在冻结 Scaffold 下证明或拒绝 Candidate，而不是调出好看的分数。

**Contract must freeze:**

- experiment ID、scaffold fingerprint、code/candidate/no-skill version；
- dataset/split/access policy hash；
- source、held-out related、unrelated case counts；
- evaluator/judge/metrics/thresholds；
- baseline/treatment order和 provider envelope；
- invalid run、retry、contamination、cost和停止规则；
- Candidate claim 是否需要 Environment Shift。

**Core evaluation:**

```text
Source cases: explain original failure; not generalization evidence
Held-out related: prove improvement on new same-family tasks
Unrelated: prove acceptable regression and negative transfer
Environment shift: conditional, not Portfolio-ready hard gate
```

**Non-goals:**

- 运行中调整 Trigger/Procedure/Stop Rule 后继续使用同一 held-out；
- 因 Provider Failure 删除样本或重采样；
- 让 Candidate 读 Judge/Gold/Split；
- 用更多 hits/longer answer 代替 grounded outcome；
- promotion 或 product injection。

**Entry Gate:** Stage 1 accepted；Candidate frozen；held-out uncompromised；准确 Provider 预算由用户
明确授权覆盖。

**Exit Gate:**

```yaml
candidate_decision:
  - validated
  - rejected
  - inconclusive
```

`validated` 必须同时通过 related generalization、unrelated regression、negative transfer、Evidence /
Citation 和成本 Gate。只有 `validated` 可进入 Stage 3。

## 6.4 Stage 3 — Controlled Use and Closeout

**Owner:** 同一个 V5-D Session；Main 负责最终 acceptance、merge/live-safe closeout。

**Goal:** 围绕已验证的一个 Candidate，形成最小可用、可解释、可回退、可回滚的产品生命周期。

**Contract must freeze:**

- validated Candidate/experiment hash；
- repository/active version authority；
- applicability gate、progressive disclosure token/tool budget；
- shadow → human promotion → active transitions；
- baseline fallback、deprecate/rollback、late-result fence；
- user-visible explanation/control；
- live DB/migration/backup/smoke strategy；
- post-promotion monitoring and rollback threshold。

**Allowed after its Contract acceptance:**

- 最小 Candidate repository 和 active pointer；
- applicability-gated injection，只注入匹配且已批准的一个 Candidate；
- shadow、人工 promote/reject/deprecate/rollback；
- baseline fallback、restart/recovery/idempotency；
- compact UI/API/observability；
- risk-directed regression、rollback demo、closeout。

**Non-goals:**

- 通用 Skill Retrieval/Marketplace；
- 多 Candidate orchestration；
- 自动 promotion、自改 Runtime/Verifier、跨项目学习；
- Post-V5 background companion；
- Environment Shift forced demo when irrelevant。

**Entry Gate:** Stage 2 Candidate `validated` 且 Main accepted；用户对 promotion authority 和任何 live
mutation 作明确决定；Stage 3 Contract accepted。

**Exit Gate:** human promotion、correct applicability、wrong/no-match fallback、restart、deprecate、rollback
和 related/unrelated regression 均有证据；mainline/live-safe closeout 完成；known limits 公开。

---

# 7. Case, Contamination and Invalid-run Governance

## 7.1 Candidate-independent selection

Stage 0 在任何具体 Failure Family/Hypothesis 冻结前完成：

```text
define user-representative coverage rubric
→ select discovery + sealed reserve cases
→ verify answerability without running a Candidate
→ freeze task bodies, corpus/source boundary and hashes
→ seal reserve access
→ only then run discovery baseline and form failure diagnosis
```

Case 不能因为“容易暴露 query decomposition/source diversity failure”而被选择。任务标签只描述
用户需求、语料范围、复杂度和答案要求，不描述预期失败或拟用 Skill。

## 7.2 Held-out integrity

- Candidate designer只看到 discovery cases；
- reserve bodies/Gold 由独立 custody 或等价 access fence 隔离；
- Stage 2 才依据预注册 task metadata、而非 outcome，把 reserve 映射为 related/unrelated；
- 任何用于设计、调 Trigger/Procedure/Stop Rule 或阈值的 reserve，立即变成 development；
- 只能由同一 Stage 0 manifest 中未打开的 reserve 替换；没有合格 reserve 时不声称泛化；
- 如果要新建 case generation，必须重置 Candidate/Eval cycle，先冻结新 manifest，再设计/调整
  Candidate，不能保留旧 held-out claim。

## 7.3 Invalid run

```yaml
invalid_classes:
  - provider_failure
  - infrastructure_invalid_run
  - evaluation_invalid_run
  - implementation_failure
```

只有 Contract 允许且 setup 未改变时，invalid run 才能等价重跑。机会性重采样、静默丢弃、人工改
中间结果或在看到 outcome 后改 Case/threshold 都使实验失效。Invalid run 不计入改善/退化，也不能
触发 Candidate 调参。

---

# 8. Reuse of V5-A / V5-B / V5-C

| Need | Reuse | Must not rebuild |
| --- | --- | --- |
| durable run/restart | V5-A Task/Attempt/Checkpoint/lease/receipts | second task runtime or generic runner |
| replayable trace | V5-A Trace/inner action/outer audit | parallel telemetry platform |
| Evidence/Citation | V4/V5-A shared grounding and source version | new truth/citation authority |
| experience lineage | V5-B Workspace `system_experience` / Event / Receipt | free-form memory pool |
| artifact/corpus context | V5-B ArtifactRoute/Topic/Page/Corpus state | graph or corpus platform |
| user confirmation/rollback | V5-B/C append-only decision/revision/tombstone | new generic approval system |
| explicit choice/permission | V5-C authority and route precedence | autonomous workflow router |
| no-skill baseline | current runtime with no active Skill | duplicate baseline engine |

如果某个已接受机制缺少 V5-D 必需字段，应窄扩展现有 identity/lineage，而不是复制服务。

---

# 9. JIT Upstream Research Plan

本规划轮不需要互联网下载或新 adoption。Stage 0 也默认不需要上游研究。

## 9.1 Stage 1 conditional P0

- `searchcli`：只有本地既有 Plan/Run/Report/Compare/Promotion 结构不足以定约时，做 fixed-commit
  source/test review；不接入 Volcengine 服务，不先复制 CLI；
- `skilladaptor`：只有 V5-A Trace 到 first-actionable attribution 的映射存在具体缺口时，做 bounded
  Localizer/Linker/Validator source/test spike；不允许其改 Active Skill；
- `hdso_paper`：冻结 Hypothesis/paired evaluation 时读取 primary paper，作为方法参考，不把训练设置
  或论文结论当作拾流证据。

## 9.2 Stage 2 conditional

- `youtu_agent`：只有现有 V5-A/B experiment/receipt identity 不能表达 Stage 2 manifest 时，审阅固定
  Commit 的相关 source/tests；不采用完整 Agent Framework 或训练/rollout platform。

## 9.3 Deferred until validation

- `skillos_paper`、`muse_autoskill_paper` 只有在 Candidate 已 validated 且最小 lifecycle 仍有具体缺口
  时进入；如果一个本地 package + active pointer 足够，则不研究、不实现完整 SkillOS。

所有材料性 episode 都必须更新 Research Log 并形成 adoption decision。当前
`implementation_authorized=false` 保持不变。

---

# 10. Provider, Tool, Token and Cost Plan

下面是执行预授权建议，不代表当前已获授权。任一 hard cap 先到即停止。

| Phase | Outer runs | Provider logical calls | Input / output token cap | Tool-call cap | Paid-cost cap |
| --- | ---: | ---: | ---: | ---: | ---: |
| current planning | 0 | 0 | 0 / 0 | local read-only only | $0 |
| startup audit / case freeze | 0 | 0 | 0 / 0 | 200 local read-only | $0 |
| Stage 0 discovery | 4 valid + at most 4 invalid replacements | 96 total | 1,000,000 / 120,000 total | 400 total | USD 2 total |
| Stage 1 mechanical implementation | 0 by default | 0 | 0 / 0 | no paid cap | $0 |
| Stage 2 paired eval proposal | up to 12 valid + contract-bounded invalid replacements | freeze later | freeze later | freeze later | estimate before Contract; likely separate authorization if > USD 2 |
| Stage 3 shadow/smoke | contract-dependent | contract-dependent | freeze later | freeze later | separate only if paid runs are necessary |

Stage 0 建议只使用仓库当前配置的 DeepSeek model role，不自动切 Provider。每个 discovery task 只
消耗一个 valid baseline；只有 provider/infrastructure invalid 且 setup 未变时可重跑一次。所有 calls、
tokens、tool calls、transport attempts、receipts 和 USD estimate 必须落在 manifest。

Stage 2 不应在 Candidate、Case 数量和 evaluator 尚未冻结时获得模糊无限预算。若最终计划超过
USD 2，Version Session 先提交精确 Plan/Run budget，由用户单独批准；不得拆分请求规避上限。

Codex/Session 上下文用量不作为产品 Eval 成本。Version Session 使用 Current State + Ledger + 当前
Contract 做定向恢复，不反复加载全部历史；Goal 模式只用于确实多步骤的实施/评测。

---

# 11. Data and Privacy Boundary

- Stage 0/2 使用本地隔离的 live DB copy 或等价 temp DB，读取真实 corpus/index，不写 live DB；
- 不把私人 Query、全文 Evidence、Raw Provider response、凭据或完整 Trace 提交 Git；
- 正式文档只记录 Case/Run/Trace ID、hash、redacted summary、机械指标和本地 artifact pointer；
- Keychain 仅在用户预授权后由当前产品入口读取既有 DeepSeek credential；不得显示、复制或记录值；
- Stage 3 的 live write/migration 必须另有 backup、stop/restart、hash、integrity/FK、rollback 和 smoke
  合同；本规划不授权。

---

# 12. Git and Worktree Plan

```yaml
planning_branch: codex/v5-main
execution_branch: codex/v5-d
execution_worktree: create_after_user_pre_authorization
push_authorized: false
tag_authorized: false
mainline_merge_authorized: false
```

建议提交边界：

1. Main 上的 calibration/planning docs-only commit；
2. V5-D execution branch startup docs/state commit；
3. 每个 Stage 的 Contract commit；
4. 每个 Stage 一个或少量清晰 implementation/eval commits；
5. Main acceptance docs commit；
6. Stage 3 后由 Main 做 merge preflight、`--no-ff` integration、live-safe closeout；
7. Push/Tag 只有用户授权后进行。

Private case bodies、Raw runs、上游完整仓库和 temp DB 不进入 Git。Merge conflict 触及产品逻辑时返回
V5-D Session，不由 Main 顺手修复。

---

# 13. Program and Startup Documents

本规划轮创建或更新：

- `V5_D_STARTUP_DIRECTION_CALIBRATION.md`：记录 accepted 和三条用户约束；
- `V5_D_VERSION_CHARTER.md`：版本功能/证据/非目标合同；
- `V5_D_STARTUP_AND_EXECUTION_PLAN.md`：全版本操作计划；
- `V5_D_STAGE_0_ENTRY_CALIBRATION_CONTRACT.md`：已授权 Stage 0 合同；
- `V5_PROGRAM_CURRENT_STATE.md`：状态改为 Startup + Stage 0 authorized；
- `V5_PROGRAM_DECISION_LEDGER.md`：记录已接受 calibration 和 planning-only boundary。

本轮不创建 `V5_D_CURRENT_STATE.md`、`V5_D_DECISION_LEDGER.md`、execution worktree/session、Case
manifest、Candidate、Eval repository 或 product code。这些只在后续授权范围内 JIT 创建。

---

# 14. Recommended Execution Pre-authorization

## 14.1 Recommended immediate package: startup + Stage 0 only

用户已批准以下 immediate package：

```yaml
V5_D_execution_pre_authorization:
  accept_charter_and_stage_0_contract: true
  create_codex_v5_d_branch_and_worktree: true
  create_one_persistent_V5_D_version_session: true
  create_minimal_version_state_and_ledger: true
  perform_read_only_startup_audit: true
  freeze_candidate_independent_case_manifest: true
  create_local_isolated_live_db_copy: true
  run_existing_no_skill_runtime: true
  provider: DeepSeek_current_config_only
  keychain_access: existing_credential_read_only_no_value_exposure
  stage_0_valid_discovery_runs: 4
  invalid_replacement_limit: 1_per_discovery_case
  provider_logical_call_cap: 96_total
  provider_input_token_cap: 1000000_total
  provider_output_token_cap: 120000_total
  tool_call_cap: 400_total
  paid_cost_hard_cap_usd: 2
  write_scope: execution_worktree_and_local_isolated_artifacts_only
  live_database_write: false
  product_code_change: false
  upstream_download: false
  candidate_or_skill_creation: false
  active_promotion: false
  push_merge_tag: false
```

该包让 V5-D 得到真实 Entry 证据，同时不预设 Candidate、不污染 held-out，也不把 Stage 0 变成产品
实现。

## 14.2 Current Stage 2 and remaining future authority

用户已在 Stage 1 被 Main 接受后，授权 `V5_D_STAGE_2_FROZEN_PAIRED_EVALUATION_CONTRACT.md`：

- 同一 V5-D Session 可以创建最小 experiment-only Treatment、冻结实验、通过 source gate 后在隔离
  Custodian 下分配 reserve，并完成有界 paired Provider evaluation；
- 普通低风险 treatment plumbing、机械测试与冻结前 fixture 问题由 Version Session 自主修复、复跑；
- held-out 打开后不得修改 Candidate 或 evaluator 并复用同一 held-out；
- Stage 3 human promotion、active/shadow registration、live DB/migration、Push/Tag 仍保留单独明确边界；
- 任何 generic platform、第二 Candidate、材料性 schema/cost/scope、License/data 风险都暂停讨论。

Stage 2 完成后 Main 只做一次有限验收并停止；不得自动进入 Stage 3。

---

# 15. Stop and Escalation Conditions

V5-D Session 可以自主处理 Contract 内普通实现/fixture/runner/测试问题，但遇到以下事项停止：

- Case selection 被 Candidate 假设污染，或 reserve/Gold 泄漏；
- Failure 归因不清、只在一个 task 出现，或 Evidence 不在语料；
- 需要产品代码修改才能完成 Stage 0；
- schema/index/corpus/provider/scaffold identity 漂移；
- exact run/cost cap 将被超过或需要新 Provider/credential；
- License/数据/隐私边界不清；
- 需要 live DB write/migration、不可逆操作、Push/Tag；
- Candidate 要改 Verifier/Split/Promotion/Evidence authority；
- 工作扩张为通用 Harness/Learning Platform、第二项目职责或 Post-V5；
- 多次 invalid/no-progress 只能靠改 Contract 才能继续。

---

# 16. Planned Final Closeout

若 Stage 3 完成，Main 执行一次版本级 closeout：

```text
read-only merge preflight
→ merge accepted codex/v5-d
→ risk-directed + one full no-provider regression
→ backup/live plan if schema changes
→ bounded provider/product smoke only if authorized
→ rollback demonstration
→ Program State/Ledger/Registry/Research Log reconciliation
→ local closeout commit
→ optional user-authorized Push/Tag
```

Portfolio-ready 可以在一个 Candidate 证据闭环形成时达到；Version Complete 还要求 durable lifecycle、
restart/recovery、authority、mainline/live-safe closeout。两者必须在报告中分开声明。

---

# 17. Current Stop Point

```yaml
planning_artifacts_prepared: true
user_execution_pre_authorization_received: true
authorized_scope: completed_startup_stage_0_stage_1_plus_current_stage_2
V5_D_session_created: true
stage_0_started: true
stage_0_status: accepted
stage_0_execution_head: fbf7a0d56816797d0ad481b2381b6d5aba81657c
product_implementation_started: false
provider_runs_performed: true_within_completed_stage_0
candidate_contract_status: accepted_proposed_non_active
stage_1_execution_authorized: closed_completed
stage_2_execution_authorized: true
stage_3_execution_authorized: false
next_action: V5_D_session_executes_frozen_paired_evaluation_and_submits_closeout
```

Stage 1 已完成并由 Main 有限验收接受。用户现授权 Stage 2：创建最小 experiment-only Treatment，在完整
freeze 后先过 D02/D04 source gate，再由隔离 Custodian 分配 sealed reserve 并执行 related/unrelated paired
evaluation。Candidate 仍不得 active/shadow；Stage 3、live DB 与 merge/push/tag 未授权。Stage 2 完成后停止。
