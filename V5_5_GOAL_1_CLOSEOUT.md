# Shiliu V5.5 Goal 1 Closeout — 可用的长程 Research

> Date: 2026-08-13
> Branch: `codex/v5-5-productization`
> Baseline / rollback point: `f0c704db88f79794c52b3f4f6e6ac77c320470f2`
> Status: COMPLETE

## 1. 最小接入方式

普通 `/research` 的既有 create/run flow 现在由服务器选择 `receipt_bound_provider` 产品执行 profile，并通过现有 background dispatcher 调用 `ReceiptBoundResearchProductOrchestrator`。Provider 结果、EvidenceUse、Citation、SideEffect、CommandReceipt、Checkpoint、Research Result 和 deterministic Outer Audit 都进入原有 durable Research state；没有创建第二套 Research、Planner、Provider service 或后台平台。

Provider 不可用、凭据缺失、模型/价格身份不在已注册安全配置中时，创建请求会明确返回不可用，且不会先留下一个假装能够执行的 durable task；不会静默降级为 no-Provider mechanical Research。

## 2. 关键修改文件

- `src/shiliu/app.py`：组合受限的产品 Provider runtime、可用性检查、角色白名单和已注册价格身份。
- `src/shiliu/web.py`：普通产品入口、后台 Provider dispatch、安全 resume、服务器 retry child task 和异常边界。
- `src/shiliu/research/product_service.py`：server-owned Provider task/profile、冻结预算、Provider-aware projection、诚实失败/unknown 状态。
- `src/shiliu/research/provider_product.py`：执行前验证 durable task 的 Provider authority。
- `src/shiliu/research/provider_wiring.py`：grounded-answer profile 配置与“有 operation id/usage 但无最终正文”的已知失败判定。
- `src/shiliu/research/control_service.py`：HITL 修改目标时保留服务器 Provider authority、receipt 和预算绑定。
- `src/shiliu/templates/research.html`、`src/shiliu/static/research.js`：面向用户的长程 Research 文案、Provider 状态、Citation 下钻和安全 retry。
- `tests/test_v5_a_stage5_gate_b_provider_product.py`、`tests/test_v5_a_stage5_product_completion.py`：产品纵切、安全边界、中断与 replay 回归。

## 3. Server-owned Provider authority

- 客户端 create schema 不接受 execution/authority/evidence-policy 等授权字段；尝试传入会得到 `422`。
- 服务器只在普通“开始研究”产品动作、Provider 安全配置与凭据均有效时创建 Provider task。
- task 的 active goal 持久冻结 `product_execution`、constraint profile、authority、Provider run budget 及其 binding hash；执行器会再次核验这些记录。
- HITL clarify/revise 只能改变用户目标和约束，不能覆盖或升级 Provider authority、receipt policy 或预算。
- run command id 由 task id 在服务器稳定派生；客户端不能通过换 command id 绕过幂等/unknown replay 保护。
- retry 只由服务器创建带 parent lineage 的新 task 和新预算；unknown side effect 不会自动 replay。
- 所有外部调用继续经过已有 receipt、SideEffect、identity、deadline、token/call/cost budget 检查。

## 4. 复用的 V5-A 能力

直接复用了 `ResearchTask / Attempt / Checkpoint`、`ResearchProductService`、`InnerResearchService`、`OuterResearchService`、`ReceiptBoundProviderService`、`ReceiptBoundResearchProductOrchestrator`、`ReceiptBoundDeepResearchExecutor`、Deep Search、grounded answer、EvidenceUse / Citation、SideEffect / CommandReceipt、Provider budget/deadline/cost accounting、durable controls、product projection 和 deterministic Outer Audit。

保持了 Post-V5 真实性语义：Provider answer、Citation 和 kernel `valid_success` 不会自动授予 `objective_verified=true`；failure/waiting/blocked 优先于漂亮答案；raw lineage 不改写；branch/replay 仍要求明确确认。

## 5. 自然真实 Case

每个自然任务只进行了一次正式执行；前两个历史 task 在发现问题后没有为了得到漂亮答案而重跑。

### Case A — 长期记忆的安全设计

- Query：`根据收藏中的视频，Agent 长期记忆应该如何设计才安全？总结关键风险、边界和实践建议，并标出来源。`
- Task：`rtask_dc9e7bc87944f3a35c389bf5a33286cc`
- Outcome：query analysis 和 3 次 agent action 均成功并 receipt-bound；grounded-answer 调用在旧的 thinking-high profile 下耗尽输出上限，历史 task 诚实保持 blocked/unknown，未生成最终 artifact/Outer Audit，也未自动重放。
- Citation / EvidenceUse：7 条当前 EvidenceUse/Citation，覆盖 3 个真实视频来源。
- 观察：搜索取证与问题复杂度相称；即使已有充分证据，未知外部副作用仍优先投影为 blocked，`objective_verified=false`，页面给出检查状态/安全处理的下一步。
- 已入账 Provider cost：成功回执调用合计 `0.003565463`；未知调用不冒充已结算费用。

### Case B — Skill 与长 Prompt 的比较

- Query：`收藏中的内容如何区分 Skill 与长 Prompt？比较它们的关键差异、适用场景、维护成本和常见误区，并给出有来源的判断建议。`
- Task：`rtask_13f7b3b151e176677f6c79a6d44a58a6`
- Outcome：query analysis 和 3 次 agent action 成功且有回执；旧 grounded-answer profile 同样在输出上限处留下 unknown side effect，因此任务诚实 blocked，没有伪造最终 answer/audit，也没有安全边界外的 replay。
- Citation / EvidenceUse：7 条当前 EvidenceUse/Citation，覆盖 3 个来源视频。
- 观察：多方面比较确实触发多步检索；有 Provider 输出或证据不等于用户目标已验证完成。
- 已入账 Provider cost：成功回执调用合计 `0.003336392`；未知调用未被错误计为确定结果。

### Case C — Skill 为什么不只是更长的 Prompt

- Query：`根据收藏中的相关字幕，用两到三点说明 Skill 为什么不只是更长的 Prompt，并标出来源。`
- Task：`rtask_c9a09e60bcab6ffb30bc29baa226bae4`
- Outcome：通过普通 Web 入口完整成功；query analysis、3 次 agent action、grounded answer 共 5 次 Provider 调用全部 receipt-bound 成功，产生 3 个 grounded answer blocks、1 个 durable result 和 1 个 deterministic Outer Audit。
- Citation / EvidenceUse：8 条当前 EvidenceUse/Citation，覆盖 3 个来源视频；在真实 `/research` UI 中验证了来源标题、时间范围、摘录及 Bilibili 时间跳转链接，Citation `[8]` 可下钻。
- 观察：产品状态为“已有有证据研究结果，目标尚未验证完成”；kernel 为 `valid_success / answer_ready`，但没有注册自然语言 objective evaluator，因此仍正确保持 `objective_verified=false`。
- Provider cost：5 次成功调用合计 `0.003060341`。

## 6. Focused / affected regression

最终运行：

```text
PYTHONPATH=src <shared-venv>/bin/python -m pytest \
  tests/test_v5_a_stage4_operational_control.py \
  tests/test_v5_a_stage5_gate_b_provider_wiring.py \
  tests/test_v5_a_stage5_gate_b_provider_product.py \
  tests/test_v5_a_stage5_product_completion.py \
  tests/test_boundaries_and_web.py \
  tests/test_post_v5_execution_persistence.py

91 passed, 1 existing Starlette/httpx deprecation warning
```

另完成 `python -m compileall -q src tests` 与 `git diff --check`。按 Charter 未提前运行完整 1800+ deterministic suite；该 suite 留给 V5.5 Final Gate。

## 7. Bounded correction

使用了唯一一次 bounded correction。两个复杂自然 Case 暴露出 grounded-answer 的 thinking-high 输出会在 4096 token 上限前耗尽预算，并且旧判定把“已有 provider response id 与 accountable usage、但没有最终正文”的响应误归为完全 unknown。

修正保持在既有架构内：产品 grounded-answer profile 改为 thinking disabled；有 operation id 与 usage 的无正文响应按已知 Provider failure 收口；真正 in-flight/无 operation id 的副作用仍保持 unknown、blocked 且禁止自动 replay。Case C 在修正后一次验证成功。没有继续调 Prompt、重跑 A/B 或扩张 Retrieval/Provider 架构。

## 8. Remaining limitations

- Web 仍使用 FastAPI `BackgroundTasks`，没有跨进程自动重调度、独立 Worker/Queue；durable state 可保留并支持安全人工继续。
- unknown Provider side effect 必须先确认/解决，不能自动 replay。
- A/B 是不可改写的历史 blocked 记录；修正后的成功由独立自然 Case C 验证。
- Case C 的 evidence set 覆盖 3 个来源，但每个答案 block 的直接引用集中在单个 Citation id；多来源综合稳定性尚未证明，不属于本 Goal 的强制成功条件。
- 产品 Provider 当前仅开放已注册并可核验价格/身份的 DeepSeek `deepseek-v4-pro` 配置；其他 Provider/模型需先注册相应身份和价格策略。
- 未注册权威 objective evaluator 的自然语言任务，即使有 grounded result，也继续保持 `objective_verified=false`。

## 9. Checkpoint / HEAD

- Branch：`codex/v5-5-productization`
- Baseline / rollback point：`f0c704db88f79794c52b3f4f6e6ac77c320470f2`
- Goal 1 checkpoint / final HEAD：包含本 closeout 的 branch tip；精确 immutable SHA 在提交后的交付信息中记录。Git commit 无法在自身内容中预写自己的最终 SHA。

## 10. Completion conditions

- [x] 普通 Web Research 能发起 server-authorized Provider Research。
- [x] Provider dispatch 继续经过 receipt / budget / SideEffect 控制。
- [x] 复用现有 Deep / grounded answer / EvidenceUse / Citation。
- [x] Provider result 正确进入 durable Research state。
- [x] deterministic Outer Audit 继续工作。
- [x] Provider-aware projection 与 no-Provider 语义明确区分。
- [x] failure / waiting / blocked 诚实展示。
- [x] 中断后 durable state 不丢，并有安全继续路径；unknown 不自动 replay。
- [x] 3 个自然 Case 已执行并记录。
- [x] focused / affected regressions 通过。
- [x] 未引入本 Goal 禁止的新架构。

Goal 1 completion conditions 已满足。后续 Goal 未在本次工作中启动。
