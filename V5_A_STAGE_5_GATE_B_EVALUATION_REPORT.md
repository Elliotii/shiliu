# 拾流 V5-A Stage 5 Gate B Evaluation Report

```yaml
stage: V5-A Stage 5
gate: B_real_provider_product_quality_evaluation
report_status: submitted_for_main_acceptance
gate_B_self_accepted: false
acceptance_request: partial_accept
formal_run_id: GB-20260803T081500Z-be96740
branch: codex/v5-a
bounded_rework_commit: be96740
entry_manifest_commit: 1a1b52f
provider: deepseek_openai_compatible
base_url: https://api.deepseek.com/v1
model: deepseek-v4-pro
provider_calls_performed: 15
http_attempts: 15
cost_usd: 0.019203539
live_database_migration_performed: false
gate_C_started: false
```

## 1. 结论

正式 Gate B 按冻结用例、模型、角色和预算一次执行，没有调 Prompt/Tool/model/case，也没有
opportunistic rerun。两个必跑用例形成有效评价：

- `GB-G-01` 产生由 3 条 current transcript citation 支撑的 `valid_partial` grounded
  answer；核心的 90% 手工验证、可独立调用后端、确定性断言加 LLM 裁判分层设计均能回到
  `BV1o87764Ebs` 的具体时间段；
- `GB-I-01` 在固定语料无法支持 2027 年三家平台量化事故率时停在
  `valid_insufficient / no_new_evidence`，没有编造数值或 citation。

条件 `GB-H-01` 暴露一个产品完成缺口：Agent 判断“需要先询问用户”，但当前 receipt-bound
Deep Ask 评价路径没有接入 Stage 4 durable InputRequest/HumanDecision/continuation，最终也未
消费固定用户回答。首次 grounded draft 违反 typed insufficient shape；exact 五调用上限阻止
repair transport，结果为 `provider_error`。这不是 Provider auth/network/endpoint/unknown
dispatch 故障，而是产品路径/HITL 接线的质量失败。

此外，三条 evaluation Research Task 都有持久 Provider Action/SideEffect/Event/Receipt，
但没有把 Provider answer 接入 Stage 2 checkpoint/artifact、Stage 3 outer audit 和 terminal
Research Result；Task 因而保持 running。故本报告请求 `partial_accept`：接受两个 mandatory
真实 Provider 产品质量证据与 receipt/cost 证据，不把 Gate B、Stage 5 或 V5-A 宣布完整
完成。

## 2. Entry Gate 与隔离 snapshot

机械返工 `be96740` 先关闭两项主审缺口：

1. actual runtime endpoint/model/role/thinking/effort 在 transport 前 fail-closed 校验，并
   绑定 canonical request、descriptor 与 receipt；
2. 缺失真实 Provider response/operation ID 形成 `unknown + blocked`，不再生成本地伪 ID。

无网络 wiring 定向 14 项、Stage 1–5 联合定向 160 项通过；错误 model/endpoint/thinking 的
transport count 为 0，missing operation ID replay 为 0。五个冻结 blob 均与 Gate A accepted
tree 相同。

运行 root：
`/Users/elliot/Documents/Shiliu-Evaluations/V5-A/Gate-B/GB-20260803T081500Z-be96740/`。

```yaml
source_live_schema: 9
source_live_sha256: eb84e971fad9442866f274c95f424dd3f05b397266ccbe69c1576c28ba66165a
source_live_size_bytes: 94588928
source_live_mtime: 2026-08-03T15:49:52+0800
source_counts: 157_videos / 140_completed / 1633_units / 154_indexed
source_lexical_index: v3-stage1-lexical-v1 / 154_video / 1479_chunk
schema9_safe_copy_sha256: e1e276dfde8194bf3c3282d2014bcbc272b5eea330633049342aeb24329922c3
schema10_pre_run_sha256: bc2ae5410b1bd3d75c415eec0ade6a8d659a8a4da408941c28c198ed64a2a7e0
schema10_post_run_sha256: eb9b7169ef137abb261de472ed7d0fa2e1b28dd2dcb5632f75ac9e9c1d0a71d8
artifact_tree_sha256: f315fc20b45251334ef89d89b75a8d0129722d8febd2c02439a15cb1443c34dc
target_subtitle_sha256: 8e4f3f97af264a9eb1faef65b2cb797bb4616f7fe9e2dc477807244194f19016
eval_integrity: ok
eval_foreign_key_violations: 0
```

SQLite online backup 在 stable window 从只读 schema 9 source 形成；全量 68 MB artifact copy
设为只读，eval DB 中 140 条 completed artifact path 全部指向隔离 root。仅 eval copy 迁移至
schema 10。正式运行后 live DB 的 SHA/size/mtime 仍为上述值，V5-A 未对 live DB 执行
migration 或写入。

## 3. Provider、价格与硬预算

运行前从 DeepSeek 官方价格页再次核验 `deepseek-v4-pro`：cache-hit input
US$0.003625/M、cache-miss input US$0.435/M、output US$0.87/M；官方同时预告峰时 2×。
Entry manifest 继续使用 nominal/reserve/absolute `0.10 / 0.40 / 0.50` 美元边界，文档最坏
17 logical calls 加一次 retry 为 US$0.3549，未超过授权。

只在 Entry Gate 全部 pass 后调用一次既有 `load_api_key(config.api_key_ref)` 路径；manifest
只保存 reference SHA-256，不保存完整 reference 或 secret。没有输出、日志或异常包含 key。

| Role | Logical / HTTP | Input | Cache hit | Output | Cost USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| query_analysis | 3 / 3 | 388 | 0 | 428 | 0.000541140 |
| agent_action | 9 / 9 | 25,087 | 5,248 | 1,539 | 0.009987919 |
| grounded_answer | 3 / 3 | 10,462 | 640 | 5,057 | 0.008674480 |
| **Total** | **15 / 15** | **35,937** | **5,888** | **7,024** | **0.019203539** |

总 wall time 169.882 秒。所有 case、总 logical/HTTP/time/cost 均低于冻结上限；没有 transport
retry，没有费用重置或 active reservation 遗留。

## 4. Case 结果与人工 rubric

| Case | Outcome | Calls | Cost | Human review |
| --- | --- | ---: | ---: | --- |
| GB-G-01 | valid_partial / answer_ready | 5 | 0.008393122 | valid evaluation；grounding pass with minor source/inference-label limitation |
| GB-I-01 | valid_insufficient / no_new_evidence | 5 | 0.005343076 | valid evaluation；honest stop pass |
| GB-H-01 | valid_insufficient / provider_error | 5 | 0.005467341 | product-quality failure；durable HITL 未接线 |

逐 case 的 `request.json`、`result.json`、`trace_projection.json`、
`research_task_trace.json`、`evidence_citations.json`、`usage_cost.jsonl` 与
`human_review.json` 位于 formal root。没有隐藏 Gold、Case ID 算法特判或测试专用 Prompt。

### 4.1 GB-G-01

两个 answer block 绑定 3 个 typed citation；citation 都来自固定 source version
`087e661…`，具有 BVID、timeline、segment、时间戳与 jump URL。人工核验 quote 对 90% 手工
测试、UI/接口改造、两层裁判和闭环回归均有直接支持。答案明确列出单视频范围、架构细节
不足、LLM 裁判不确定性和 context truncation；因此 `valid_partial` 准确。轻微问题是正文
保留 `[1]/[2]/[3]` 装饰编号，且“来源主张/系统推论”的标签不够显式。

### 4.2 GB-I-01

导航与 transcript search 没找到目标量化数据。最终 answer block 与 citation 均为空，限制
准确描述证据缺口和 no-new-evidence stop；没有将无关 Evidence presence 当成支持，也没有
用模型常识补齐未来数值。

### 4.3 GB-H-01

Agent 第三轮明确输出“需要先询问用户澄清目标”，说明模型识别了歧义；但 Agent action
schema/运行路径只能 finish，未打开 durable InputRequest。固定用户回答从未进入 current
Attempt/checkpoint/control-generation lineage。首次 answer 的 `insufficient` 同时带 blocks，
被 deterministic validator 拒绝；下一 repair 在 transport 前被五调用 hard cap 拒绝。
这是有效发现，不允许 rerun 掩盖。

## 5. Receipt、Trace 与恢复证据

- 15 条 `structured_provider_call` SideEffect 全部 `succeeded`；15 条都有真实
  `provider_operation_id`、receipt hash 与 result reference；
- role/endpoint/model/thinking/effort、canonical request hash、usage、cost、output hash 与
  receipt 在持久 Action/Event/CommandReceipt 中可对应；
- `unknown|in_flight|reserved` 数量为 0，transport retry 为 0；
- formal run 没有 crash/restart/takeover，因此真实 Provider restart/recovery 为
  `not_exercised`；对应 deterministic/mocked restart、replay、owner/control fence 与 unknown
  fail-closed 证据来自 Entry suite；
- 三个 Task 都停在 `running / state_version=17`，这准确暴露 Provider answer 尚未被提交为
  Stage 2/3/5 product checkpoint/result，而不是伪造 terminal success。

## 6. 失败分类、未证明项与请求

```yaml
mandatory_cases_eval_disposition: valid_evaluation
mandatory_product_quality: pass_with_limitations
conditional_HITL_eval_disposition: product_quality_failure
implementation_failure: none_observed_in_receipt_transport_path
provider_failure: none
evaluation_invalid_run: false
infrastructure_invalid_run: false
unknown_side_effects: 0
outer_audit: not_exercised
real_provider_restart_recovery: not_exercised
gate_B_acceptance_request: partial_accept
gate_B_self_accepted: false
stage_5_complete: false
v5_A_complete: false
gate_C_started: false
```

请求 V5 主 Session：

1. 接受 `GB-G-01` 与 `GB-I-01` 作为获批 DeepSeek 组合下的代表性真实 Provider 质量证据；
2. 接受 actual identity、operation ID、receipt/usage/cost 和硬预算证据；
3. 对完整 Gate B 作 `partial_accept`，保留两项材料性缺口：Provider answer 到 durable
   Stage 2/3 terminal product path 的接线，以及 Stage 4 HITL 在该 Provider 产品路径中的
   实际消费；
4. 不授权 V5-A 启动 Gate C。Gate C 的 owner 仍为 V5 主 Session。

保持 `not_exercised`：DeepSeek Flash、其他 Provider/model/role、Provider outer evaluator、
真实 crash/restart、live schema 10 migration、mainline integration 与 Gate C smoke。
