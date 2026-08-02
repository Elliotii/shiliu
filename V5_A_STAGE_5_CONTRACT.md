# 拾流 V5-A Stage 5 Contract（Draft）

```yaml
stage: V5-A Stage 5
title: Product Completion, Trace, and Reliability Evaluation
contract_status: draft_pending_main_review
proposal_authority: Shiliu V5-A Version Session
acceptance_authority: V5 main session
as_of: 2026-08-03
planning_branch: codex/v5-a
planning_head: 26d22cda779086681da69747fce4b97260988646
stage_4_status: accepted_by_v5_main
stage_4_accepted_head: 26d22cda779086681da69747fce4b97260988646
stage_5_implementation_authorized: false
mechanical_product_gate_authorized: false
provider_quality_gate_authorized: false
mainline_integration_authorized: false
live_schema_10_migration_authorized: false
provider_runs_performed: false
live_database_migration_performed: false
stage_5_self_accepted: false
```

本文件是 Stage 5 的目标与验收合同草案，不是实施提交、Provider 运行授权、live
migration 授权或 V5-A 最终验收。内部模块、文件布局、普通技术选择和实现顺序由
V5-A Session 在合同获准后自主决定。

## 1. 唯一使命

把 Stage 1–4 已接受的 durable research kernel、evidence-backed inner loop、outer
goal audit 和 HITL/control plane 收口为用户真正可启动、观察、理解和控制的长期
research 产品路径，并以持久 trace、故障恢复、并发测试、既有产品回归和版本完成
证据证明其边界。

Stage 5 不重新设计研究推理，不把拾流扩张为通用调度、RBAC、多设备协作或复杂
工作流平台。

## 2. 接受基线与 JIT 审计事实

### 2.1 已接受资产

- Stage 1：Task/Goal/Attempt/Checkpoint/Event/Trace/Result/CommandReceipt/
  SideEffect、事务、idempotency、owner lease/epoch fence 与 lineage。
- Stage 2：Task-scoped EvidenceUse、稳定 EvidenceIdentity、append-only validation/
  currentness、provisional synthesis、硬预算与 durable stop。
- Stage 3：server-owned deterministic constraint evaluator、outer audit、compact
  improvement state、targeted continuation 和 parent/child Result lineage。
- Stage 4：server-derived control authority、current pause lineage、InputRequest/
  HumanDecision、interrupt/cancel/resume、unknown SideEffect resolution、retry 和
  isolated branch/replay；主 Session 已接受 `26d22cd`，独立重跑 27 项通过。

### 2.2 当前产品缺口

只读源码审计确认：

- `src/shiliu/web.py` 已有 research create/get/status/trace、inner/outer 与 Stage 4
  control JSON API，但没有用户可见的 research 页面或导航入口；
- kernel `get_task()` 与 control `get_status()` 返回可靠的持久记录和真实
  `allowed_operations`，但尚无面向用户的综合状态、停止原因、证据、引用和 trace
  投影；
- `/search` 与 Fast/Deep `/ask` 已有共享 Evidence/Citation 展示资产，可复用展示
  规则，不能把旧进程内 ask trace 升格为 research authority；
- inner/outer service 的真实 Provider 运行默认 `provider_runs_authorized=False`，
  当前产品路径必须继续 fail closed；
- `Application.__init__()` 会 initialize source schema 10。当前 live DB 是 V5 主
  Session 已迁移的 schema 9，Stage 5 规划与实施不得通过启动 live Application
  隐式迁移。

2026-08-03 只读 live baseline：schema 9、SHA-256
`4f1a27ce8d4a0a62884ac197d0ef035b89fdf723ba51483dd13ba6dd49c4f735`、
94,588,928 bytes、mtime `2026-08-03T02:05:13+0800`、integrity ok、FK 0、
157 videos / 140 completed。schema 9 由 V5 主 Session 迁移；V5-A 未执行 live
migration。

规划期无 Provider 探索测试为 55 passed：Stage 4 control、`/ask` 页面和产品搜索
API；仅既有 Starlette/httpx TestClient warning。

## 3. 冻结的用户旅程

### 3.1 启动与重新进入

用户可以从拾流产品导航进入 Research，提交有界目标和服务端允许的约束。成功
提交必须先产生 durable Task identity 与可重放 receipt，再由受 owner fence 的最小
本地执行路径推进；浏览器断开或 HTTP request 结束不得删除任务或成为任务完成的
前提。

Stage 5 的 mechanical gate 可以用无 Provider deterministic path 证明完整交互。
真实 Provider research 的“开始运行”只在 Gate B 单独授权后开放；未授权时产品必须
清楚显示不可用原因，不能静默降级为伪 Provider 成功。

用户可重新打开既有 Task，并看到目标、当前 Goal revision、active Attempt、父子
Task/Attempt lineage、最近 checkpoint、更新时间与是否仍在安全推进。Stage 5 只需
一个本机产品用户和有界任务列表/直接链接，不实现多用户 inbox 或调度队列。

### 3.2 理解状态和结果

产品至少用稳定、用户可理解的投影显示：

- 当前状态：运行、等待用户、blocked/cancel-pending、停止或 terminal；
- 当前 phase、已用预算和硬上限、最近可靠进展、下一项允许操作；
- `answer_status`、`termination_reason`、`failure_class` 三个正交维度，并提供不丢失
  原始 taxonomy 的用户文案；
- 为什么继续、为什么停止、由哪个 checkpoint/decision/constraint observation
  导致；
- 当前 Result 或 provisional artifact，以及明确的 provisional/insufficient/stale
  标记；
- unknown external effect、stale owner、expired input 等不能自动恢复的安全状态。

显示层不得从“页面看起来成功”、citation 数量、candidate/self-confidence 或旧 trace
自行推导 `valid_success`。

### 3.3 Evidence、Citation 与持久 trace

Evidence/Citation 展示必须复用 V4 已接受的 shared renderer 语义，同时以 Stage 2
持久模型为 authority：稳定 EvidenceIdentity、Task/Goal/Attempt-scoped EvidenceUse
及 append-only currentness observation。跨 Task 相同内容可共享 identity，但使用、
provenance、currentness 和结论不得串线。

用户 trace 是 durable Event/Checkpoint/Action/Audit/CommandReceipt/Control lineage
的只读投影，至少能解释：计划与工具动作、evidence 使用、synthesis、outer audit、
continuation、HITL/control、result commit 与失败/停止。进程内 log、一次性 graph、
segment ID 或浏览器状态都不是权威。

默认 trace 只显示理解任务所需的摘要和引用；高级细节可展开。不得泄露 secret、
credential、未受控完整 payload 或无界 transcript；原始 ID 可以复制用于审计，但
不得要求普通用户手工填写 fence token。

### 3.4 最小 HITL 与 operational control

产品仅暴露 Stage 4 `allowed_operations` 当前真实允许的操作：

- 回答当前 clarification/constraint-choice InputRequest；
- interrupt、cancel、resume；
- 对 unknown SideEffect 作服务端 canonical decision 的最小 resolution；
- explicit retry、从明确 source checkpoint 创建 branch/replay child Task。

页面操作必须经 Stage 4 service/API、server-derived principal 和 current
Attempt/checkpoint/control generation 校验。浏览器中的 actor/role/capability、旧页面、
隐藏字段或 URL 参数不能授予权限。成功响应应返回新状态；冲突/过期请求必须 fail
closed、提示刷新且不漂移。双击、刷新和网络重试使用同一 command identity 时 exact
once，不得重复创建 input、effect、child Task 或 Result。

## 4. Product completion 不变量

1. **Durability before presentation**：UI 只投影已提交持久状态；先显示后落库、仅存在
   内存的进度不是完成。
2. **Single mutation path**：所有产品 mutation 都通过 Stage 1–4 service transaction、
   receipt、owner/control fence；UI 不直接写表或重构历史。
3. **Authority preserved**：Evidence Authority、evaluator authority、human authority
   与 worker ownership 各自独立，不因 UI 接线合并。
4. **Current-lineage control**：控制只消费当前 pause/source lineage；历史 interrupt、
   input、checkpoint 或旧 generation 不能授权现在的操作。
5. **No opportunistic rerun**：restart、poll、refresh、replay 和 error handling 不自动
   重跑 tool/Provider/unknown SideEffect。
6. **Honest completion**：产品状态、trace 和版本报告准确区分
   `valid_success|valid_partial|valid_insufficient|not_produced`、termination 和 failure；
   未运行项保持 `not_exercised`，未证明项保持 `unproven`。
7. **Bounded input/output**：目标、约束、用户回答、candidate、trace page 与 evidence
   展示均有服务端长度/数量边界；客户端截断不能代替服务端保护。
8. **Compatibility**：`/search` 和 Fast/Deep `/ask` 的 Evidence/Citation、默认行为和
   failure taxonomy 不因 Research 页面而改变。

## 5. 三道独立 gate

### Gate A — Mechanical Product Wiring / UI / Trace / Reliability

本 Contract 获主 Session 接受后可以单独授权 Gate A。允许范围：

- 最小 Research 产品入口、任务列表/详情、用户状态与 trace 投影；
- 将已接受的 JSON API/service 与 UI 连接，补齐有界 projection API；
- 无 Provider deterministic execution/fixture 和最小本地 cooperative runner；
- Stage 4 当前允许的 HITL/control 交互；
- 必要的 product code、template、CSS/JS、机械测试、fault/restart/concurrency tests；
- 如确有必要，source migration 和临时 DB migration test；不得迁移 live DB。

最小 runner 只负责本机有界 claim/continue、lease renewal 与安全停止；SQLite Task
状态仍是权威。不得演化为任务优先级、cron、分布式 queue、autoscaling、通用 job
编排或多租户平台。

Gate A 不授权真实 Provider、凭据访问、Provider Prompt/model/Tool Contract 改动、
live migration、Merge/Push/Tag。机械 gate 可被独立验收，但不等于真实产品质量通过。

### Gate B — Real Provider and Product-quality Evaluation

任何真实 Provider 调用都必须由用户/V5 主 Session 另行书面授权。授权包必须在运行
前冻结：

- exact use cases 与 corpus/evidence snapshot 身份；
- Provider/model/role 组合和是否允许任何 Prompt/Tool Contract 变更；
- 最大 case 数、每 case continuation/action/token/time 上限、总调用数和最大费用；
- credentials 的允许读取方式；禁止输出或记录 secret 值；
- success/partial/insufficient、citation correctness、outer audit、HITL、latency/cost
  与恢复的评价 rubric；
- 运行数据库/输出位置、是否隔离于 live DB、停止条件和失败 taxonomy；
- 人工 review、报告格式以及哪些组合保持 `not_exercised`。

未获得该授权时，Provider path 必须保持 fail closed，测试不得读取 Keychain 或凭据。
Gate B 结果不得改写 mechanical 证据；机械通过也不能替代质量评价。V5 主 Session
可以在最终验收中明确接受某些组合为 `not_exercised`，V5-A 不自行豁免。

### Gate C — Mainline Integration and Live Schema Migration

Gate C 只在 V5-A version evidence 完成并经主 Session 决定后执行，且拆分决定：

- V5-A commits 如何进入 `codex/v5-main`；
- source schema 10（或届时获准版本）是否、何时迁移 live DB；
- migration preflight、备份、磁盘空间、完整性/FK、stable fingerprint、postflight、
  rollback/recovery 与 scheduled sync 协调；
- 集成后 product smoke 是否允许触发 Provider。

Contract/Stage 5 Gate A 接受不自动授权 Merge、Push、Tag 或 live migration。由于
`Application.__init__()` 会 initialize schema，Gate C 前所有测试必须继续使用临时
DB，live 检查只能使用不会初始化应用的 immutable/read-only 方式。

## 6. Gate A 用户可见完成条件

Gate A 只有同时满足以下条件才可提交验收：

1. 用户能从产品导航创建有界 Research Task，获得稳定链接，断开/刷新/应用重启后
   能重新找到并观察同一 Task。
2. 至少一条无 Provider deterministic journey 从 create → durable execution →
   evidence/citation → provisional/outer decision → terminal 或准确 bounded stop 全程
   可见，且每个继续/停止原因可追溯到持久记录。
3. waiting_user、interrupt/resume、cancel/cancel-pending、unknown resolution、retry、
   branch/replay 均有最小且不会越权的产品交互；产品只显示当前真实允许操作。
4. Result/provisional artifact、EvidenceUse/citation/currentness 与 constraint/audit
   observation 清楚分层；stale/insufficient 不伪装成 success。
5. 重启、lease takeover、stale page、重复 submit、并发 command、fault rollback 后，
   UI 与 API 收敛到同一 durable truth，没有重复副作用、孤儿 lineage 或虚假进度。
6. `/search`、Fast/Deep `/ask` 和 Evidence/Citation 回归通过；Provider logical/
   transport calls 为 0。
7. 基本 accessibility 与 operational usability 通过：键盘可操作、状态不只依赖颜色、
   loading/error/empty/terminal 状态明确、破坏性控制要求确认。
8. Implementation Report 给出 Contract 矩阵、commits/diff、测试与故障证据、live DB
   稳定指纹、warnings、`not_exercised`、`unproven`；不自我接受 Stage 5/V5-A。

## 7. Gate A 定向验收矩阵

| 维度 | 必须证明的路径 |
| --- | --- |
| Product entry | create validation、stable link、list/open、refresh/restart、empty/error |
| Status projection | running/waiting/blocked/terminal、三维结果 taxonomy、budget/phase/reason |
| Trace | durable ordering、checkpoint/decision cause、pagination/bounds、no secret/raw overflow |
| Evidence/Citation | current/stale/insufficient、cross-Task isolation、shared renderer consistency |
| Control | current input、interrupt/resume、cancel、unknown resolution、allowed operations |
| Derivation | retry/branch/replay child lineage、source/sibling immutable、source checkpoint visible |
| Idempotency | double click、network replay、payload mismatch、stale state/generation fail closed |
| Recovery | process restart、expired lease/takeover、mid-transaction crash、runner/poll reconnect |
| Concurrency | two workers/clients single winner、terminal race、input/control/resolution race |
| Compatibility | Stage 1–4 joint tests、`/search`、Fast/Deep `/ask`、Evidence/Citation |
| Boundary | Provider/credential access 0、live DB mutation 0、Prompt/Tool Contract unchanged |

至少包含 service、public API 和 browser-facing page/DOM 三层对抗测试。race/fault 必须
实际触发，不能只验证 helper 存在；multiprocess 能力在本机可稳定执行时至少覆盖
claim/takeover 或 control CAS。完整默认无 Provider suite 必须运行。

## 8. V5-A version completion evidence

Stage 5 最终报告应提供一个精简、可机器核对的 completion manifest 或等价结构，包含：

- Charter 五个 Stage 的 Contract/acceptance/implementation commits；
- source/live schema、migration actor、migration 是否执行；
- 用户旅程与 Contract 矩阵映射到测试/证据；
- mechanical、Provider quality、integration/live migration 三 gate 的独立状态；
- Provider case/model/call/cost（仅在获批运行时）或明确 `not_exercised`；
- live baseline 与稳定窗口指纹、完整性/FK、corpus counts；
- 已知 warnings、失败、deferred、unproven 与版本遗留风险；
- V5-A 请求主 Session 的 `accept / partial_accept / rework / pause / reject`。

文档或 UI 演示不能替代源码/测试执行，单次 happy path 不能替代 restart/race/fault，
测试存在不能写成测试已运行。

## 9. 非目标与禁止范围

- 通用 scheduler/queue、优先级/cron/autoscaling、RBAC/SSO、组织/多租户；
- 多设备实时协作、通知中心、复杂 workflow builder 或通用 JSON Schema 平台；
- 新的研究推理 Stage、outer evaluator authority 放宽、confidence gate；
- 自动重放 unknown external effect 或绕过 owner/control fence；
- 复制 DeerFlow/AREX 代码、Prompt、模型、权重或添加其依赖；
- 未单独授权的 Provider、费用、凭据/Keychain、Prompt/model/Tool Contract；
- 未单独授权的 live migration、Merge、Push、Tag 或 Program 权威文件修改。

## 10. 风险、未证明项与暂停条件

当前仍为 `not_exercised` 或 `unproven`：真实 Provider 产品质量/成本/延迟、网络调用
cooperative cancellation 与 reconciliation、真实 SIGKILL/断电、多主机长期 lease
soak、production-scale retention/performance、正式认证/RBAC、跨设备协作、live
schema 10 migration/rollback、主线集成和跨版本长期 replay。

出现以下任一材料情况必须暂停并提交事实、选项与建议：

- 产品入口必须绕开 durable receipt/fence 才能运行；
- UI 需要把 citation presence、candidate 或 human confidence 当 semantic verifier；
- unknown effect 只能靠自动重放恢复；
- 需要通用 scheduler/RBAC/多设备/复杂 workflow 才能满足最小旅程；
- 需要真实 Provider、凭据、Prompt/model/Tool Contract 或 live migration；
- schema/data/License 发生材料变化，或 current live baseline 与只读事实冲突；
- Gate A 无法把机械能力和产品质量声明清楚分离。

## 11. JIT 实施计划

Contract 获接受并明确 Gate A 授权后，V5-A 自主按依赖推进：

1. 冻结用户状态/trace/evidence projection 与有界 product command DTO；
2. 接入稳定 Research 入口、列表/详情和无 Provider durable execution trigger；
3. 复用 Evidence/Citation renderer，完成 user-readable state/result/trace；
4. 接入 current Stage 4 HITL/control/derivation interactions；
5. 关闭 stale/replay/restart/race/fault 与 accessibility/error-state 测试；
6. 运行 Stage 1–5 联合、`/search`、Fast/Deep `/ask` 与默认无 Provider 回归；
7. 提交 Implementation Report 与 version completion evidence，停止等待 Gate A 验收；
8. 只有收到单独授权后才执行 Gate B；Gate C 始终由主 Session 另行决定。

该顺序不是对内部 commits、模块或普通实现选择的逐项审批。

## 12. 当前停止点

```yaml
stage_4_status: accepted_by_v5_main
stage_5_contract_status: draft_pending_main_review
stage_5_implementation_authorized: false
stage_5_implementation_started: false
mechanical_product_gate_authorized: false
provider_quality_gate_authorized: false
mainline_integration_authorized: false
live_schema_10_migration_authorized: false
provider_runs_performed: false
live_database_migration_performed: false
next_action: V5_main_session_stage_5_contract_goal_boundary_review
```
