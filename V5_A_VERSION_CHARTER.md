# 拾流 V5-A Version Charter（Revised Draft）

```yaml
document_status: pending_final_main_acceptance
version_session: Shiliu V5-A Version Session
proposal_authority: V5-A execution session
acceptance_authority: V5 main session
created_at: 2026-07-30
revised_at: 2026-07-31
main_review_round_1: completed
product_baseline_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
startup_commit: 2feccbccaa288f67071d22460eb220d50b19d871
implementation_authorized: false
product_implementation_started: false
provider_runs_authorized: false
provider_runs_performed: false
```

> 本文件已根据 V5 主 Session 第一轮独立审查修订，现等待最终验收。它不构成自我验收、Stage 开工授权、长期路线变更或 Provider 运行授权。

## 1. 版本使命

V5-A 拟把拾流现有一次性 Fast/Deep 问答能力扩展为一个可持久、可审计、可安全续作的研究任务内核：

1. 用户目标、证据约束、尝试、检查点、事件、结果与副作用拥有稳定且彼此分离的身份。
2. 进程退出、失败、取消、用户中断或重启后，系统能够依据持久事实决定“安全续作、创建新尝试、等待用户、诚实停止”，而不是静默重跑。
3. 内层研究只以可重建、可校验的 transcript/ASR 证据为事实权威。
4. 外层目标审计只决定是否满足约束、是否存在可恢复缺口、下一轮应针对什么缺口；候选答案、自报置信度或模型评价不得成为 verifier/gate 权威。
5. 对任何不确定的外部 in-flight 操作 fail closed；没有幂等性或结果收据时，不自动重放。

## 2. 拟交付的用户可见变化

版本完成时，用户应能创建一个研究任务，看到其目标、当前状态、证据支持程度、尝试与检查点沿革，并在以下场景得到一致行为：

- 正常完成时得到带稳定引用的 `valid_success` 结果。
- 证据不足或预算耗尽时得到可解释的 `valid_partial` / `valid_insufficient`，而不是伪装成成功。
- 有明确、可恢复缺口时只针对该缺口续作，并保留既有有效证据。
- 需要用户判断时进入可持久的等待状态，重启后仍可继续。
- 外部副作用结果不确定时进入显式阻塞状态，未经解析不自动重放。
- 取消、重试、目标修订、分支或回放不会改写既有历史，也不会把新结果错误归入旧尝试。

本轮不交付上述产品变化；本轮只提交研究和契约 Draft。

## 3. 起始事实

### 3.1 已确认产品基线

- 正式产品基线：`483fd46bca1d7141a696fda4b2d1e093a55f209b`。
- V5-A 启动包所在提交：`2feccbccaa288f67071d22460eb220d50b19d871`。
- 执行分支：`codex/v5-a`。
- 当前产品仍只有 `/search`、`/ask` Fast/Deep；没有 `/research` 产品 Runtime。
- 当前 Deep graph 是单次进程内执行，未配置 checkpointer。
- 当前 Ask trace 保存在进程内字典，重启后不可查询。
- 当前数据库 schema version 为 6，没有 Research Task、Goal、Attempt、Checkpoint、Event 或 SideEffect 表。
- V4.1 continuation/H0 是评估 Harness，不是产品 Runtime。

### 3.2 已接受的现场 Baseline Update

2026-07-30 的只读现场核验发现：

- 数据库记录 157 个视频，其中 140 个 `completed`。
- 内容目录存在 155 个 `BV*` artifact 目录；数据库非空且去重后的 `artifact_dir` 也是 155。
- 这与 Program Current State 中记录的 150 个内容目录不同。
- lexical 物理索引为 `shiliu_lexical`，154 eligible videos、154 video units、1479 chunks。
- dense 物理索引为 `shiliu_dense`，model `Qwen/Qwen3-Embedding-0.6B`、1633 units/vectors。
- 产品运行逻辑 corpus identity 为 `shiliu-live-current`；它不是物理索引名称。

V5 主 Session 已于 2026-07-31 独立只读复核并接受该 baseline update，同时确认 schema 6、157 videos、140 completed、155 distinct artifact directories、lexical 154/1479 与 dense 1633。V5-A 仍不直接修改 Program Current State；正式 Program 文件更新由主 Session 执行。

## 4. 冻结不变量

以下约束在 V5-A 内不得由执行 Session 自行放宽：

1. transcript/ASR artifact 是事实权威；摘要、导航片段、模型记忆和候选答案不是事实权威。
2. 引用必须绑定 `source_artifact_id`、`source_version`、timeline 与有序 segment identity，并可重建、可再校验。
3. Evidence 与 display/navigation 分离；导航结果默认不得获得 citation authority。
4. `/search` 与 `/ask` Fast/Deep 现有语义保持兼容，除非 V5 主 Session 明确接受变更。
5. Fast/Deep 的证据 grounding 与 finalization contract 保持共享。
6. DecisionView 是对模型的有界投影，不是完整 Runtime state，也不能替代持久任务状态。
7. answer/outcome status、termination reason 与 failure class 必须正交持久；`valid_success` / `valid_partial` / `valid_insufficient`、实现失败、Provider failure、产品质量失败、评估基础设施无效必须可无损派生。
8. 不允许 opportunistic rerun 掩盖失败。
9. 候选答案、self-confidence、critic 或 model-as-judge 不能成为最终 verifier/gate。
10. ResearchTask、Goal、Attempt、Checkpoint、Event、Trace、Result、CommandReceipt、SideEffectRecord 身份和语义必须分离。
11. retry、resume、goal revision、branch、replay 必须保留 lineage，不覆盖旧历史。
12. 不确定 external in-flight 操作一律 fail closed；没有确认收据不得自动重放。
13. Stage 1 就必须建立 single-active-owner lease/epoch fence、CommandReceipt、Task-scoped SideEffect 幂等性与 in-flight safety，不能推迟到“可靠性收尾”。
14. V5-A 不自行修改长期路线，不自行宣布 Adoption 或验收。

## 5. 拟议 Stage 序列与依赖

本序列依据已核验的技术依赖提出，不机械继承旧 G1–G4 编号。V5 主 Session 第一轮审查已接受该五 Stage 依赖方向；整体 Charter 与各 Stage 仍须分别最终验收。

### Stage 1 — Durable Task Kernel and Safety Envelope

先建立持久身份、Task/Attempt/Result 终态语义、检查点 lineage、single-active-owner lease/epoch、CAS/mutation guard、CommandReceipt、事件账本和 SideEffectRecord。没有这层，后续循环、HITL、分支和重放都无法证明安全。

### Stage 2 — Evidence-backed Inner Research Loop

在 Stage 1 的持久任务语义上复用 V4 稳定 Evidence/Citation、共享 finalization、预算与受控搜索，把“研究一步”变成可检查点化、可重建证据的内层循环。是否以及如何接线 Provider、允许哪些 Provider 运行，将由 Stage 2 Contract 单独决定。

### Stage 3 — Outer Goal Audit and Recursive Continuation

在已有可信结果和 compact improvement state 上做外层约束审计。只有可恢复且有新的 targeted objective 时续作；无进展、预算耗尽、不可恢复缺口或证据不足时诚实停止。Stage 3 的 Provider 接线、审计运行和预算范围同样由 Stage 3 Contract 单独决定。

### Stage 4 — HITL and Operational Control

加入持久 user input/interrupt、取消、等待、人工解析不确定副作用、重试、branch/replay 和跨进程控制。所有操作必须服从 Stage 1 的 lineage 与 mutation guard。

### Stage 5 — Product Completion, Trace, and Reliability Evaluation

完成产品入口和可见状态、持久 trace、恢复/并发/故障注入测试、真实产品质量评估及回归验证。Stage 5 负责收口而不是机械推迟所有 Provider 验证；Stage 2/3 可以在其 Contract 明确且另获运行授权后进行相应 Provider 验证。任何真实 Provider 运行始终需要单独授权，不能因本 Charter 或某个 Stage Contract 被接受而自动获权。

## 6. 正式版本目标

### G-A：Durable identity and lineage

- 每个 Task、Goal revision、Attempt、Checkpoint、Event、Trace、Result、CommandReceipt、SideEffectRecord 有稳定 ID。
- parent、retry、resume、branch、replay 与 goal revision 关系可查询且不可被覆盖。
- terminal Task 不可复活；后续 retry/revision 创建带 `parent_task_id` 的 child Task。
- 进程重启后能从数据库事实恢复，而不是依赖进程内对象。

### G-B：Safety and mutation correctness

- 所有状态变更有 expected version/checkpoint guard。
- 所有 mutation、checkpoint/result commit 与 SideEffect reserve/receipt 校验 current owner lease/epoch。
- 重复命令幂等；并发旧写入被拒绝。
- 外部调用前持久化 reservation/in-flight；崩溃后的未知状态显式阻塞。
- cancel、retry、resume 与 goal edit 不会静默重放或串线。

### G-C：Evidence-backed inner loop

- 每项支持性结论可追溯到稳定 transcript evidence。
- compact state 只保存可验证发现、缺口、拒绝候选、约束和下一步，不把自由文本记忆提升为事实。
- inner loop 在预算、重复、无新证据和 provider failure 下产生准确终止分类。
- answer status、termination reason 与 failure class 分开记录。

### G-D：Outer constraint audit and continuation

- 目标满足判定基于显式约束和证据验证，不基于自报 confidence。
- continuation 必须指向具体 unresolved constraint，并产生可观察 progress delta。
- 反复相同 blocker/无新有效证据达到阈值后停止。

### G-E：HITL and operational control

- 用户输入、中断、取消和等待状态持久化。
- 重启后仍能恢复到同一语义位置。
- 人工解析未知副作用必须成为显式事件，保留原始不确定事实。

### G-F：Product and evaluation closure

- 产品状态、结果和 trace 可被用户理解。
- 机械测试、故障注入、恢复测试、证据/引用回归和获批 Provider 评估分别报告。
- 所有失败按治理 taxonomy 分类；未执行项标记 `not_exercised` 或 `unproven`。

## 7. 非目标

- 不把 DeerFlow、AREX 或其他上游直接复制进产品。
- 不把 LangGraph chat thread/checkpoint 自动等同于拾流 ResearchTask 模型。
- 不在 V5-A 训练、微调或采用新模型。
- 不让导航结果、模型摘要、candidate answer 或 confidence 获得事实权威。
- 不在未获批前修改现有 Prompt、Tool Contract、正式测试、Migration 或 UI。
- 不把 V4.1 Harness checkpoint 文件升级为产品数据库方案。
- 不实现跨设备协作、多租户调度或通用工作流平台。
- 不改变 V5-B/C/D 边界或长期路线。

## 8. 已核验上游与采用边界

| 上游 | 本轮状态 | 可考虑的模式 | 明确不采用 |
| --- | --- | --- | --- |
| DeerFlow | 主 Session 已确认固定提交/MIT 与报告证据边界，并接受为 `pattern_only_reimplementation` 的设计/测试参考；未执行其测试 | typed blocker、continuation gate、durable receipt、expected-checkpoint guard、lineage traversal、idempotent cancel、lease/orphan fencing 的独立重实现 | 整体依赖/复制；源码/Prompt；chat thread 等同 Task；默认 memory checkpointer；可见文本 hash 等同语义进展；模型 verifier；cap 后仍算 success |
| AREX | 主 Session 已确认论文 v2/官方最小推理仓库证据边界，并接受为 `training_independent_patterns_only` 设计参考 | 可脱离训练的 Inner Research、Outer Constraint Audit、Targeted Follow-up、Compact Improvement State；Stage 1 不实现 | 模型/权重/Prompt/代码；self-confidence gate；“保证有答案、不得放弃”；无显式不足结果的最高置信度回退 |
| youtu_agent | Deferred | 无 | 本轮不 Clone、不深研、不形成采用结论 |

上述第一轮主 Session 采用决定只确定设计/测试参考边界，不授予任何 Stage 实现权限；实现权限只能来自相应 Stage Contract 的明确授权。

## 9. Baseline、风险与证据规则

### Baseline

- Git、代码和测试以本文件 3.1 所列提交关系为准。
- DB/Index/Corpus 使用主 Session 于 2026-07-31 独立复核并接受的只读现场事实；不执行 Migration。
- Provider 配置只核验字段存在性，不读取 secret 值，不访问 Keychain，不发请求。

### 主要风险

1. 把 checkpoint persistence 误当作完整任务语义。
2. 在 external call 与状态提交之间崩溃，导致重复副作用。
3. goal edit、cancel、continuation 并发覆盖。
4. 用文字变化代替有效证据进展。
5. 模型自评错误地通过完成门。
6. 复用 V4.1 Harness 时继承不完整 provider identity 或不可恢复 private draft。
7. 运行态 corpus 漂移使固定评估不可复现。

### 证据要求

- 设计事实必须指向本地文件、符号、测试或固定上游提交。
- 文档阅读、源码审阅、测试审阅、测试执行和 Provider 运行分别标记。
- 下载不等于采用，测试存在不等于测试执行。
- “未证明”必须显式记录，不以推断补齐。

## 10. Version 完成条件（须由 V5 主 Session 验收）

只有同时满足以下条件，V5 主 Session 才可考虑正式接受 V5-A：

1. 五个 Stage 均有被接受的 Contract 和完成报告。
2. Task/Goal/Attempt/Checkpoint/Event/Trace/Result/CommandReceipt/SideEffectRecord 语义及数据库 lineage 有机械证据。
3. crash、restart、duplicate/payload mismatch、ownership takeover、stale owner/writer、unknown in-flight、terminal child Task、cancel、goal revision、branch/replay 均有故障测试。
4. Evidence/Citation 不变量与 Fast/Deep 回归通过。
5. outer audit 不依赖 candidate/self-confidence 作为 verifier。
6. 产品可见状态与持久 trace 能解释每次继续或停止的原因。
7. 获批范围内的 Provider 评估单独报告，未运行的组合保持 `not_exercised`。
8. Program Current State、Decision Ledger、Registry 与 Research Log 由 V5 主 Session 更新。

## 11. 暂停与升级条件

遇到以下任一条件必须暂停并请求主 Session 决定：

- 需要修改冻结不变量或长期路线。
- 需要引入正式上游依赖、复制上游代码或采用新模型。
- 需要执行 live DB migration、Provider、付费服务或读取凭据。
- baseline 漂移会改变 Contract 或成功标准。
- 无法证明 external in-flight 的唯一性或安全解析路径。
- 新 UI/Tool Contract/Prompt 变更超出已接受 Stage。
- 需要 V5-B/C/D 协调或跨版本授权。

## 12. 请求 V5 主 Session 的决定

1. 最终接受、继续修订或拒绝本 Revised Charter。
2. 最终审阅 `V5_A_STAGE_1_CONTRACT.md` 的状态模型、ownership fence、CommandReceipt、SideEffect 与测试要求。
3. 决定是否在最终接受 Stage 1 Contract 后另行授权 Stage 1 产品实施。

```yaml
charter_status: pending_final_main_acceptance
stage_1_contract_status: pending_final_main_acceptance
product_implementation_started: false
provider_runs_performed: false
next_action: main_session_final_document_review
```
