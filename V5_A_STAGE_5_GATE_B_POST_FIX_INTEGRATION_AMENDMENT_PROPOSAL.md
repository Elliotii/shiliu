# 拾流 V5-A Gate B Post-fix Integration Validation Amendment Proposal

```yaml
proposal_status: pending_v5_main_written_authorization
proposal_type: bounded_post_fix_integration_validation
original_formal_run: GB-20260803T081500Z-be96740
original_run_must_remain_immutable: true
provider_run_authorized_by_this_document: false
credential_access_authorized_by_this_document: false
gate_C_authorized: false
```

## 1. 为什么不是 opportunistic rerun

原计划的“同一 case 仅一次正式 run”防止看到答案后调参再跑。原 run 已严格执行一次，且
主 Session 已接受为不可覆盖诊断证据；其结果、人工 review 与失败结论不会被修改或替换。

本 proposal 请求的不是重判原算法输出，而是验证一个原 run **从未执行的组合边界**：
`receipt-bound real Provider → Stage 2 checkpoint/artifact → Stage 3 audit/Result or waiting_user
→ Stage 4 current-lineage HumanDecision continuation`。bounded rework 只用 mock/no-network
临时 DB 关闭实现缺口。若获授权，第二次运行应有新的 run identity、独立 root 与明确标签
`post_fix_integration_validation`；报告并列原 run，不合并统计，不宣称原失败消失。

没有修改 Prompt、Tool/Schema、model、case text、expected outcome、retrieval algorithm 或
evaluator authority，也没有依据原答案加入 Case ID/Gold 特判。因此本次请求是一次新的
integration validation，不能用于覆盖原 answer-quality 诊断。

## 2. Exact cases 与产品旅程

使用 `V5_A_STAGE_5_GATE_B_EVALUATION_PLAN.md` 中以下 exact objective、success constraints
和 fixed answer，文本逐字不变：

1. `GB-G-01`（mandatory）：从产品 create/run 入口进入 receipt-bound product
   orchestrator；要求 Stage 2 provider artifact、Stage 3 audit 和 terminal Result 或准确
   bounded partial boundary，不允许 Task 遗留 running。
2. `GB-I-01`（mandatory）：同一路径运行一次；接受 terminal `valid_insufficient` 或带
   current InputRequest 的 `waiting_user`，不自动续跑、不补写未来量化事实。
3. `GB-H-01`（本次 mandatory integration case）：先由既有 deterministic product runner
   对原歧义目标形成 current Stage 3 blocked checkpoint 与 Stage 4 InputRequest，消费计划中
   固定回答一次，产生 goal-revision child Attempt；随后才执行一次 receipt-bound Provider
   product continuation。该顺序不让 case metadata 进入算法，且避免为了提问先付费运行一次。

每 case 仍只执行一次 post-fix integration run。schema、auth、unknown、budget 或 assertion
失败后不得 opportunistic rerun；只能保留失败 manifest 并返回主 Session。

## 3. 冻结 Provider、Prompt 与 evaluator

```yaml
provider: deepseek_openai_compatible
base_url: https://api.deepseek.com/v1
model: deepseek-v4-pro
roles:
  query_analysis: {thinking_enabled: false, reasoning_effort: null, max_output_tokens: 1200}
  agent_action: {thinking_enabled: false, reasoning_effort: null, max_output_tokens: 1200}
  grounded_answer: {thinking_enabled: true, reasoning_effort: high, max_output_tokens: 4096}
outer_evaluator: server_owned_deterministic_only
```

冻结 Git blob 与原计划一致：

```yaml
query_analysis_py: 2eb00bf0553bf4f173b22101351788c96665b7f5
agent_action_py: b93777b6dde1bf834604fe01a6fa0c2f08c5a240
grounded_answer_py: ee23019f255b8772bff5beaf142ed5c0bad37bd0
inner_tools_py: 396e3433254d08117b763e4b91e8daa56dad5172
ask_contracts_py: 4ed333410287d25094f327f1c13bec098b367b02
```

任一 blob、model、endpoint、thinking/effort、case text 或 evaluator authority 不一致时，在
credential access 前停止。

## 4. Snapshot 与新 root

原 root
`/Users/elliot/Documents/Shiliu-Evaluations/V5-A/Gate-B/GB-20260803T081500Z-be96740/`
保持只读、不可覆盖。获授权后在同级创建全新
`GB-<timestamp>-<rework_commit>-postfix/`。

为保持 corpus/evidence 完全可比，不从届时可变 live DB 重新抽样：

1. 只读复制原 root 的 `eval.schema9.snapshot.db`（SHA-256
   `e1e276dfde8194bf3c3282d2014bcbc272b5eea330633049342aeb24329922c3`）到新 root；
2. 在新 copy 上执行临时 schema 10 migration/preflight，冻结新 eval DB 精确 SHA；
3. 只读复制原隔离 artifact tree，要求 tree SHA-256 继续为
   `f315fc20b45251334ef89d89b75a8d0129722d8febd2c02439a15cb1443c34dc`，目标字幕 SHA
   继续为 `8e4f3f97af264a9eb1faef65b2cb797bb4616f7fe9e2dc477807244194f19016`；
4. 核验 schema/corpus/index/material baseline 仍为 157 videos、140 completed、1633 units、
   154 indexed、lexical `v3-stage1-lexical-v1`；
5. 新 Task/Receipt/Result 只写新 eval DB，live DB 不读取为运行状态源、更不迁移。

任一 hash/material baseline 不一致则 call count 保持 0 并停止。

## 5. 调用、token、费用与时间硬上限

沿用原计划边界，不因返工放大费用：

| Case | Provider continuation | logical calls cap | HTTP attempts cap | input/output cap | wall time |
| --- | ---: | ---: | ---: | ---: | ---: |
| GB-G-01 | 1 | 7 | 14 | 60,000 / 14,192 | 12 min |
| GB-I-01 | 0 | 5 | 10 | 40,000 / 8,896 | 10 min |
| GB-H-01 | 1（fixed answer 后） | 5 | 10 | 40,000 / 8,896 | 12 min |
| **Total** | — | **17** | **34** | **140,000 / 31,984** | **34 min** |

```yaml
nominal_cost_usd: 0.10
reserve_stop_usd: 0.40
absolute_max_cost_usd: 0.50
```

首次调用前重新从官方 price table 冻结运行时价格并按原严格公式重算；最坏预留超过
US$0.50 则不访问 credential、不调用 Provider。restart 不重置 ledger；pre-call reservation
不得跨过 absolute cap。

## 6. Entry Gate、停止条件与输出

书面授权后仍须重新执行机械 Entry Gate：rework commit/clean tree、167 项 Stage 1–5 联合
定向、五个 blob、fresh eval SHA/artifact identity、receipt reserve→in_flight→receipt、
restart/replay/unknown/fence/cost cap 全部 pass。Entry Gate 任一失败，credential/provider
count 保持 0。

运行中立即停止且不重跑：

- credential/auth/model/endpoint/thinking identity 异常；
- unknown/unreconciled SideEffect、stale owner/state/checkpoint/control generation；
- 需要修改 Prompt、Tool/Schema、model、case 或 evaluator；
- logical/HTTP/token/time/reserve/absolute cost 任一上限达到；
- H 的 InputRequest 不是 current lineage、HumanDecision 非 exact-once，或 fixed answer 未被
  child Attempt 消费；
- G/I 结束后仍为无 checkpoint/audit/result-or-input 的 running Task；
- eval infrastructure invalid 或原 root 出现任何写入。

新 root 输出独立 manifest、每 case product projection、Stage 2 artifact/currentness、Stage 3
audit/Result、Stage 4 input/decision lineage、Provider receipt/usage/cost、human rubric 与
Gate B post-fix report。报告必须并列引用原 run，明确它仍是第一次 answer-quality 与缺口
诊断，不合并或覆盖。

## 7. 请求决定

请求 V5 主 Session 选择：

```yaml
postfix_integration_validation: authorize | rework | pause | reject
credential_scope: existing_llm_keychain_reference_once_after_entry_gate
provider_scope: exact_three_cases_and_caps_only
live_migration: forbidden
gate_C: forbidden_for_v5_a_session
```

在收到 `authorize` 的书面决定前，V5-A 停止于 mock/no-network rework 证据，不访问
Keychain/credential，不创建新 formal root，不再次调用 Provider。
