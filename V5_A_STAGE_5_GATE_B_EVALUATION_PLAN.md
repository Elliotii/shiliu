# 拾流 V5-A Stage 5 Gate B Evaluation Plan

```yaml
stage: V5-A Stage 5
gate: B_real_provider_product_quality_evaluation
plan_review: accepted_with_bounded_docs_rework
plan_status: bounded_docs_rework_completed_pending_main_review
proposal_authority: Shiliu V5-A Version Session
acceptance_authority: V5 main session
as_of: 2026-08-03
branch: codex/v5-a
planning_baseline: a09d7c2958a90cffebd43e5c27e6e4d68f13100a
gate_A_status: accepted_by_v5_main
gate_A_accepted_head: a09d7c2958a90cffebd43e5c27e6e4d68f13100a
provider_run_authorized: false
credentials_accessed: false
provider_calls_performed: 0
live_database_migration_performed: false
gate_C_authorized: false
```

## 1. 唯一目的与非目标

Gate B 只验证：已经接受的 Gate A 长期 Research 产品路径，在一个明确、有限、可计费
且可审计的真实 Provider 组合下，能否产生代表性的 grounded answer，并能在证据不足
或目标不明确时诚实停在 partial/insufficient/waiting_user。

Gate B 不重新设计 Stage 1–5，不为评价数据增加 Case ID/hidden Gold 特判，不修改研究
算法来迎合用例，不放宽 Evidence、evaluator、ownership 或 HITL authority，也不开始
Gate C、live migration、主线集成或新的长期知识晋升。

本计划获接受仍不构成 Provider 运行授权。只有用户/V5 主 Session 对 exact cases、预算、
费用、凭据读取方式、最小 Provider wiring 和运行目录作书面确认后，才可开始任何接线或
真实调用。

## 2. JIT 只读核验事实与运行前技术前置

### 2.1 当前 fail-closed 状态

- `Application.research_inner` 与 `research_outer` 均固定
  `provider_runs_authorized=False`。
- inner `execution_mode="provider"` 在 flag 未授权时拒绝；即便只打开 flag，当前仍会因
  “Provider wiring 只可经 SideEffect protocol 调用；当前入口未启用”而拒绝。
- outer provider candidate 同样要求绑定获授权的 SideEffect receipt，当前入口未接线。
- Gate A product runner 当前只执行 `deterministic_no_provider`。

因此 Gate B 运行前需要一个独立、最小、可审查的技术前置：把既有
`query_analysis / agent_action / grounded_answer` structured provider 调用绑定到 Stage 1
SideEffect reserve/in_flight/receipt、owner fence、budget ledger 和 durable action/trace。
该前置不得改变 Prompt、Tool Contract、Evidence validator 或 outer evaluator；outer
constraint gate 默认继续使用已接受的 server deterministic authority。若主 Session 不
授权这项最小 wiring，Gate B 保持 `blocked_not_runnable`，不得绕过 durable protocol 直接
调用 Provider。

### 2.2 已核验的非秘密 Provider 配置

只读、白名单字段核验结果：

```yaml
provider_protocol: OpenAI-compatible chat/completions
base_url: https://api.deepseek.com/v1
default_model: deepseek-v4-pro
fast_transcript_model: deepseek-v4-flash
formal_transcript_model: deepseek-v4-flash
formal_summary_model: deepseek-v4-pro
formal_reasoning_effort: high
```

本轮未读取 `api_key_ref` 值、未调用 `load_api_key()`、未访问 Keychain、未发网络请求。

## 3. 冻结的代表性用例

所有用例只把下列 objective/constraints 作为普通产品输入；代码、Prompt、retrieval 和
evaluator 不接收 case name、expected outcome 或人工评分答案。人工 reviewer 只在 run
结束后看 manifest、Result、EvidenceUse/Citation、Audit 和 trace。

### GB-G-01 — grounded answer（必跑）

**Objective（exact）**：

> 基于当前固定收藏中的字幕证据，解释为什么把 AI Agent 后端改造成可独立调用的接口，
> 并建立“确定性断言 + LLM 裁判”的分层回归体系，能够减少手工验证；请引用来源，区分
> 视频作者的主张与基于证据的推论，并说明局限。

**Success constraints（exact）**：

1. 至少绑定 2 个 current、可跳转的字幕 EvidenceUse；
2. 每个核心事实性结论都有 citation，且 citation quote 语义支持该结论；
3. 明确区分来源主张、系统推论和未证明项。

预期接受范围为 `valid_success` 或有明确限制的 `valid_partial`；不能仅凭 citation 数量
判成功。主要现实来源候选是 `BV1o87764Ebs`，但 retrieval 不被强制限定到该视频。

### GB-I-01 — insufficient / waiting_user（必跑）

**Objective（exact）**：

> 基于当前固定收藏语料，比较 2027 年 MCP 生产事故在 OpenAI、Anthropic、Google 三家
> 平台的公开量化失败率，并给出每个平台的当前字幕证据；如果当前 corpus 无法支持，
> 请准确说明缺口并停止，不要用常识或推测补齐。

**Success constraints（exact）**：

1. 每个平台的量化失败率都必须绑定 current EvidenceUse；
2. 缺任一平台或缺可验证数值时，不得产出 `valid_success`；
3. 不能把未来推测、模型常识或 citation presence 当成来源事实。

可接受结果为 `valid_insufficient`、有明确缺口的 `valid_partial`，或因需用户修改目标而
`waiting_user`；编造数值、伪 citation 或 terminal `valid_success` 为产品质量失败。

### GB-H-01 — 最小 HITL/continuation（条件用例）

只有 GB-G-01 与 GB-I-01 都未自然触发 waiting_user/HITL，且书面授权明确包含本用例时
才运行。

**Objective（exact）**：

> 基于当前固定收藏，为拾流长期 Research 的回归测试安排前三项优先级；如果“优先”
> 无法从目标判断是更重视可靠性还是迭代速度，请先询问用户，再继续一次。

固定一次用户回答：

> 可靠性优先；未知外部副作用不得自动重放。

只允许一个 InputRequest、一次 HumanDecision 和最多一次 targeted continuation。不得
因固定回答改写 evaluator 或跳过 current pause lineage。

## 4. Corpus / Evidence snapshot 与隔离

规划时观察到的材料性 baseline（用于审查 snapshot 形成流程，不是永久授权 SHA）：

```yaml
source_live_db_schema: 9
source_live_db_sha256: 8e98b39b4c34ef034b170374616a14796bb74425a5c88a59dbc4c28efb4a37e7
source_live_db_size_bytes: 94588928
source_live_db_mtime: 2026-08-03T04:09:35+0800
source_live_db_last_sync_run: 353
source_live_db_last_sync_status: completed_with_errors
videos: 157
completed_videos: 140
retrieval_units: 1633
indexed_videos: 154
grounded_source_id: BV1o87764Ebs
grounded_source_artifact_sha256: 8e4f3f97af264a9eb1faef65b2cb797bb4616f7fe9e2dc477807244194f19016
retrieval_index_version: v3-stage1-lexical-v1
```

外部 scheduled sync run 353 在规划期间改变了 live SHA/mtime，但 schema、corpus/
retrieval counts、index identity 和目标 artifact hash 未变；V5-A 未触发或干预该 sync。
该事实证明 live SHA 不是永久授权身份。

运行获权后必须：

1. 在 stable window 记录 live SHA/mtime，并用 SQLite online backup/等价 SQLite-safe
   copy 建立 eval DB；随后对 eval copy 做 integrity/FK、行数和 source identity 核验，
   冻结 **eval copy 精确 SHA**；
2. 把用例所需 artifact 复制到独立 eval root，记录 source/copy SHA；
3. 只对 eval copy 执行必要 source schema 10 migration/preflight，绝不初始化 live
   `Application`；
4. eval runtime 的 Task/Trace/Result/Receipt 只写 eval DB；原 corpus/artifact copy 设为
   只读；
5. manifest 同时记录 source live observation 与获授权 eval copy identity，并固定每个
   EvidenceIdentity 的 source version、artifact hash、timeline、EvidenceUse 与 validation
   observation。

授权的是上述 snapshot **形成流程**和材料性 baseline。只有 schema、videos/completed/
retrieval/indexed counts、index version/identity、目标 source/artifact identity/hash 任一
变化才停止并请求决定。仅 live DB SHA/mtime 或不改变这些字段的 scheduled-sync 变化，
在 manifest 更新 observation 后继续形成 eval copy，不重新申请授权。

拟议 eval root：
`/Users/elliot/Documents/Shiliu-Evaluations/V5-A/Gate-B/<run_id>/`。它不得与 live state
dir、live DB 或正式 content tree 重合。

## 5. Provider / model / role 与 Prompt/Tool freeze

本轮唯一候选组合：

| Role | Provider / model | thinking | 单调用 output 上限 | timeout | 用途 |
| --- | --- | --- | ---: | ---: | --- |
| `query_analysis` | DeepSeek OpenAI-compatible / `deepseek-v4-pro` | disabled | 1,200 tokens | 180s | 解析目标与检索意图 |
| `agent_action` | 同上 | disabled | 1,200 tokens | 180s | 选择一个有界研究动作 |
| `grounded_answer` | 同上 | enabled, effort `high` | 4,096 tokens | 180s | grounded synthesis；最多一次既有 repair |

outer constraint audit 继续由 server-owned deterministic evaluator 决定；本 Gate 不创建
新的 Provider evaluator authority。

Prompt、response schema、Tool Contract 和 model 均默认不变，冻结到 Gate A accepted
tree。关键 Git blob：

```yaml
query_analysis_py: 2eb00bf0553bf4f173b22101351788c96665b7f5
agent_action_py: b93777b6dde1bf834604fe01a6fa0c2f08c5a240
grounded_answer_py: ee23019f255b8772bff5beaf142ed5c0bad37bd0
inner_tools_py: 396e3433254d08117b763e4b91e8daa56dad5172
ask_contracts_py: 4ed333410287d25094f327f1c13bec098b367b02
```

若最小 durable wiring 无法在这些 Prompt/Tool/Schema blob 不变的情况下完成，必须停止并
把具体差异作为新的主 Session 决定，不能先改后报。

## 6. 首次付费调用前机械 Entry Gate

V5-A Session 在任何 credential access 或 Provider call 前必须逐项执行并把结果写入
entry-gate manifest；这不是 Gate B 最终自我验收：

1. minimal receipt-bound Provider wiring 已形成独立 commit，working tree clean；
2. 无网络/mock tests 实际证明 SideEffect `reserve → in_flight → receipt`、owner fence、
   usage/cost 原子记账、restart 后 budget 不重置、unknown fail closed、command replay 不
   产生第二次 logical/transport call；
3. Prompt/Tool/Schema blob 与 Gate A accepted tree 完全一致；
4. SQLite-safe eval DB copy 已建立，schema 10 migration/preflight、integrity/FK、材料性
   baseline、eval copy SHA、artifact SHA、manifest 与 price table 均已冻结；
5. case/budget/cost/credential authorization 与本计划完全匹配，provider call meter 从 0
   开始且可在调用前预留最坏费用。

任一项失败：Entry Gate 为 `fail_closed`，不得访问 `api_key_ref`、不得调用 Keychain，
Provider logical/transport call count 必须保持 0。V5-A 可按清单自行执行并记录机械 Gate，
无需主 Session 再做完整 wiring diff 审阅；但不能据此自我接受 Gate B 最终质量结果。

## 7. 硬预算、官方 price table 与停止条件

| Case | continuation | research actions | logical calls：QA/Action/Answer | input/output token cap | wall time |
| --- | ---: | ---: | ---: | ---: | ---: |
| GB-G-01 | 1 | 8 | 1 / 4 / 2 = 7 | 60,000 / 14,192 | 12 min |
| GB-I-01 | 0 | 6 | 1 / 3 / 1 = 5 | 40,000 / 8,896 | 10 min |
| GB-H-01（条件） | 1 | 6 | 1 / 3 / 1 = 5 | 40,000 / 8,896 | 12 min |

- 必跑总上限：12 logical calls、100,000 input、23,088 output、22 分钟；
- 含条件用例总上限：17 logical calls、140,000 input、31,984 output、34 分钟；
- transport retry：每 logical call 最多 1 次；HTTP attempt 上限分别为 24 / 34；

运行 manifest 必须从 [DeepSeek 官方 Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
冻结当时价目。本次 2026-08-03 只读核验值为：

```yaml
currency: USD
unit: per_1m_tokens
model: deepseek-v4-pro
input_cache_hit: 0.003625
input_cache_miss: 0.435
output: 0.87
announced_peak_multiplier_safety_factor: 2.0
nominal_cost_usd: 0.10
reserve_stop_usd: 0.40
absolute_max_cost_usd: 0.50
```

严格公式：单次费用 = `cache_hit_input × 0.003625 / 1M + cache_miss_input ×
0.435 / 1M + output × 0.87 / 1M`。全部三 case、cache miss、无 retry 的文档上限约
US$0.0887；再按官方预告峰时 2×及每 logical call 最多一次 transport retry 预留，约
US$0.3549。故 nominal 取 US$0.10，预留达到 US$0.40 时不得开始下一调用，绝对上限
US$0.50。若运行时官方价变动，先更新 manifest 并重算；重算仍不超过 US$0.50 才可经
Entry Gate 继续，否则停止请求新授权。无法在调用前可靠计价则标为
`evaluation_invalid_run` 且 Provider call count 保持 0；
- 任何 case 达到 action/continuation/token/time/cost 任一上限，必须 durable stop 为
  `budget_exhausted`，不得 opportunistic rerun；
- auth、余额、forbidden、model-not-found、schema、deadline 或持续 network error 立即停止
  当前 case；unknown SideEffect 必须人工 resolution，禁止自动重放；
- 同一 case 只允许一次正式 run。只有 eval infrastructure 在首个 Provider call 前失败，
  且 manifest 证明调用数为 0，才可在新 run_id 下重试。

## 8. Credentials 拟议方式（本轮未执行）

获书面授权后只使用现有 `load_api_key(config.api_key_ref)` / macOS Keychain 路径，在 eval
process 内短暂取得 key。禁止 CLI 参数、环境回显、日志、manifest、trace、exception 或
截图包含 secret。manifest 只记录 `credential_source=existing_keychain_reference`、是否
成功和 reference hash；不记录 key 或完整 reference。

运行前必须再次得到对“允许访问现有 LLM Keychain reference”的明确授权。本规划轮没有
读取 reference 值或 secret，也没有访问 Keychain。

## 9. 评价 rubric 与失败分类

每个 case 由一名人工 reviewer 按 manifest 中预先冻结的 rubric 复核：

| 维度 | 通过标准 |
| --- | --- |
| Result taxonomy | answer status、termination reason、failure class 正交且与实际停止一致 |
| Evidence/Citation | 每个事实性 claim 可追到 current EvidenceUse；quote/timestamp/source version 正确；无跨 Task/Attempt 串线 |
| Grounding quality | citation 语义支持 claim；不把 citation presence 当 entailment；推论与来源主张分离 |
| Outer audit | deterministic evaluator/audit observation 与 Result 一致；不足约束不得被 Provider/candidate 自授 satisfied |
| HITL | 只消费 current Input/checkpoint/generation；回答 exact-once；历史输入不授权新暂停 |
| Trace | Provider SideEffect、logical/transport attempt、usage、checkpoint、audit、stop/result 可解释且无 secret |
| Reliability | replay 不重复计费；restart/receipt 后恢复；unknown 不自动重放；预算重启不重置 |
| Latency/cost | 每 role、case 和总量均在冻结上限内，费用可由 usage 与冻结 price table 重算 |

分别记录：

- Program outcome：`valid_success|valid_partial|valid_insufficient|not_produced`；
- termination reason 与 `none|implementation_failure|provider_failure|...`；
- eval disposition：`valid_evaluation | product_quality_failure |
  evaluation_invalid_run | infrastructure_invalid_run`。

代码异常/transaction/fence bug 为 implementation failure；auth/network/model/schema/timeout
为 provider failure；运行有效但答案、citation、audit 或诚实停止未达 rubric 为 product
quality failure；snapshot/manifest/usage meter/price table/runner isolation 失效分别为 eval
或 infrastructure invalid run。不得把这些维度压入一个 classification。

## 10. 输出、manifest、记账与报告

每个 run root 只包含有界、去敏输出：

```text
manifest.json
cases/<case_name>/request.json
cases/<case_name>/result.json
cases/<case_name>/trace_projection.json
cases/<case_name>/evidence_citations.json
cases/<case_name>/usage_cost.jsonl
cases/<case_name>/human_review.json
eval.db
V5_A_STAGE_5_GATE_B_EVALUATION_REPORT.md
```

`manifest.json` 冻结 git commit、source/eval DB SHA、artifact/index identity、case exact text、
Provider/model/role、Prompt/Tool blob、预算、price table、credential source kind、run start/end、
logical/transport call count、费用、Result/Trace/Receipt IDs 和所有未执行组合。JSONL 每个
attempt append-only 记录 role、request hash、SideEffect ID、receipt/result reference、token
usage、latency、retry、cost 和 outcome；不记录 Prompt 全文、Provider reasoning 或 secret。

人工 review 必须逐 claim/citation 记录 `pass|fail|not_applicable` 与简短理由。最终报告按
case 汇总产品质量、失败分类、预算、恢复、warnings、`not_exercised` 和是否建议 Gate B
`accept / partial_accept / rework / pause / reject`；不得据此宣布 Gate C 或 V5-A 完成。

## 11. 保持 `not_exercised` 的组合

- `deepseek-v4-flash` 的 research roles 与 transcript/ASR roles；
- 除 `deepseek-v4-pro` 外的所有模型、除当前 DeepSeek endpoint 外的 Provider；
- Provider-owned outer evaluator/candidate authority；
- 多 Provider 比较、ensemble、confidence gate、训练/微调；
- 未获书面授权时的 GB-H-01；
- live DB、正式 scheduler、Gate C integration smoke、真实 external mutation tools；
- Prompt/Tool Contract/model variants。

## 12. 主 Session 待决定项与授权模板

主 Session 只需决定以下少量边界：

1. 是否接受 GB-G-01、GB-I-01 exact text，并是否包含条件 GB-H-01；
2. 是否接受 DeepSeek / `deepseek-v4-pro` / 三 role 单一组合；
3. 是否授权单独实现最小 receipt-bound Provider wiring，且 Prompt/Tool blobs 必须不变；
4. 是否接受 12（或含 HITL 17）logical calls、US$0.10 nominal、US$0.40 reserve stop、
   US$0.50 absolute max 和 34 分钟硬上限；
5. 是否授权运行时访问 existing LLM Keychain reference；
6. 是否接受 eval root 和 snapshot copy/migration/isolation 方案。

计划接受后仍必须等待一条明确书面授权，至少包含：

```yaml
gate_B_provider_run_authorized: true|false
authorized_cases: [GB-G-01, GB-I-01] # 可选 GB-H-01
authorized_provider: deepseek_openai_compatible
authorized_model: deepseek-v4-pro
authorized_roles: [query_analysis, agent_action, grounded_answer]
max_logical_calls: 12 # 含 HITL 时 17
nominal_cost_usd: 0.10
reserve_stop_usd: 0.40
absolute_max_cost_usd: 0.50
credential_access: existing_keychain_reference_allowed|forbidden
minimal_provider_wiring_authorized: true|false
evaluation_root_authorized: true|false
```

在该授权到达前停止于：

```yaml
gate_A_status: accepted_by_v5_main
gate_B_plan_review: accepted_with_bounded_docs_rework
gate_B_plan_status: bounded_docs_rework_completed_pending_main_review
gate_B_provider_run_authorized: false
provider_calls_performed: 0
credentials_accessed: false
live_database_migration_performed: false
gate_C_authorized: false
next_action: V5_main_session_gate_B_bounded_docs_rework_review
```
