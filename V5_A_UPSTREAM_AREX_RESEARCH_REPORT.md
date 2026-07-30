# V5-A 有界上游研究报告：AREX

```yaml
report_status: accepted
revised_at: 2026-07-31
main_review_round_1: evidence_boundary_confirmed
accepted_at: 2026-07-31T01:08:24+08:00
acceptance_record: V5_A_STARTUP_MAIN_REVIEW_AND_STAGE_1_AUTHORIZATION.md
registry_id: arex_paper
paper_title: "AREX: Towards a Recursively Self-Improving Agent for Deep Research"
paper_version: arXiv:2607.21461v2
paper_submitted: 2026-07-23
paper_v2_date: 2026-07-24
official_project: https://vectorspacelab.github.io/arex-model/
official_model_repository: https://huggingface.co/BAAI/AREX-Turbo
official_repository_commit: 129812742df4a5de27980ed07bda78d9d27c7370
paper_license: arXiv_perpetual_non_exclusive_license
repository_license: Apache-2.0
paper_reviewed: true
official_source_reviewed: limited_inference_subset
tests_reviewed: false
tests_executed: false
weights_downloaded: false
provider_runs_performed: false
adoption_status: adopted
adoption_type: training_independent_patterns_only
usage_level: design_reference
role: recursive_research_design_reference
qualifier: no_model_no_weights_no_prompt_no_code_no_confidence_gate_stage_1_excluded
implementation_authorized: false
```

## 1. Shiliu Problem

AREX 与 V5-A 的相关问题不是“是否采用一个训练好的研究模型”，而是：

- 如何把一次研究拆成内层研究与外层约束审计。
- 当结果未满足目标时，如何只针对具体缺口 follow up。
- 如何压缩保存有效发现、被拒候选、未满足约束、有效性风险和下一步，而不丢失审计语义。
- 在多轮递归中何时停止并诚实报告不足。

本研究只考虑可脱离训练和特定模型的协议模式。

## 2. Official Evidence

### Paper

- arXiv abstract：`https://arxiv.org/abs/2607.21461`
- 固定 HTML v2：`https://arxiv.org/html/2607.21461v2`
- 标题：*AREX: Towards a Recursively Self-Improving Agent for Deep Research*
- 作者主体：AREX Team / Beijing Academy of Artificial Intelligence
- v1 提交：2026-07-23
- v2：2026-07-24

论文页面使用 arXiv perpetual non-exclusive license。该许可不是软件代码许可。

### Official project and code availability

- Project：`https://vectorspacelab.github.io/arex-model/`
- Hugging Face：`https://huggingface.co/BAAI/AREX-Turbo`
- 固定 commit：`129812742df4a5de27980ed07bda78d9d27c7370`
- Commit time：2026-07-24T03:19:13Z
- Commit subject：`Add files using upload-large-folder tool`
- Repository License：Apache-2.0

为核验官方代码可用性，只对官方模型仓库进行了不下载权重的稀疏读取。没有把代码复制进产品，也没有运行模型。

## 3. Inspected Official Source

固定提交中实际审阅：

| 文件 | 内容 |
| --- | --- |
| `inference/README.md` | OpenAI-compatible endpoint 使用说明、模型服务与 action 输出示例 |
| `inference/inference.py` | 单次生成下一 action 的最小客户端 |
| `inference/prompts.py` | search、Google Scholar、visit、update_context、finish tool schemas 与 BrowseComp prompts |
| `README.md` / model card | 模型说明、License 与 artifact 指针 |
| `LICENSE` | Apache-2.0 正文 |

官方仓库提供的是最小推理入口与 prompts：

- `inference.py` 构造一次 OpenAI-compatible chat completion，并打印模型的下一 action。
- 真正的工具执行、history 回填、多步 inner loop、outer audit、Restart/Refine orchestration 均留给调用方。
- 仓库树中没有本论文完整训练管线、训练数据、outer-loop orchestrator、完整 evaluation harness 或测试。

因此本报告不能把“README 提及公开 evaluation code”升级为“完整系统已开源/可复现”。

## 4. Verified Paper Method

### 4.1 Discovery–verification asymmetry

论文把 deep research 的困难描述为：

- discovery 容易找到很多候选信息；
- verification 更难，需要检查候选是否真正满足复杂约束。

这与拾流的 Evidence/Citation 治理一致：搜索到片段不等于已验证结论，候选答案也不等于满足目标。

### 4.2 Inner Research

inner loop 维护紧凑研究状态并执行：

- search/browse 类 action
- `update_context`
- `finish`

`finish` 产生答案、evidence/document identities 和 `[0,100]` confidence。Compact state 保存：

- 已验证 findings 及 source IDs
- 当前 candidates
- rejected candidates
- unresolved constraints
- validity concerns
- next plan

适合拾流迁移的是这种“把可复用有效发现和未解决约束分开”的状态形状，不是 confidence gate。

### 4.3 Outer Constraint Audit

outer layer 接收内层结果和 terminal state：

- confidence 达到 threshold：Accept
- 可恢复：Refine，保留 progress、记录 issues，并给出 targeted next objective
- 不可恢复：Restart from original
- 达到 outer operation 上限仍未过阈值：返回已完成结果中 confidence 最高者

论文评估配置允许最多 300 inner turns 与 5 次 outer operations。

### 4.4 Training dependence

AREX 的完整能力不是纯 orchestration 结果。论文包含：

- synthetic task construction
- teacher trajectories
- multi-stage midtraining
- key-step supervision
- step-aware reinforcement learning

key-step annotations 属于训练/离线监督，不是运行时可直接取得的 deterministic verifier。拾流不能假设换一个 loop 就会获得论文中的模型行为。

## 5. Paper / Code Limitations

论文没有单列完整的“Limitations”章节。以下限制分为直接事实与基于方法的工程推断。

### 直接可见

- 接受门依赖模型生成的 confidence threshold。
- 最多可使用 300 inner turns × 5 outer operations，成本上界很高。
- 超过外层预算后选择“最高 confidence 的已完成答案”，而不是强制输出 explicit insufficient。
- 公开官方仓库没有完整 outer loop、tool executor、训练管线或测试。
- 官方推理样例只演示生成下一 action，不证明端到端递归行为。

### 对拾流的工程推断

- 模型可能对错误答案高置信，因此 confidence 不能替代 stable evidence/citation validator。
- “Restart”若按字面丢弃历史，会破坏拾流要求的 Goal/Attempt/Checkpoint lineage；拾流只能创建新 Attempt，不能删除旧轨迹。
- 300×5 的策略必须被拾流预算、Provider 成本与 no-progress gate 大幅约束。
- 论文未处理产品级 crash recovery、HITL、并发 mutation、cancel 或 external SideEffect ambiguity。
- 模型训练带来的 improvement 不能视为 Shiliu 现有模型可继承事实。

## 6. Transferable Patterns

### 6.1 Inner Research

把一次研究限定为：

- 当前 Goal revision 的一组显式约束；
- 受预算控制的搜索/读取；
- 可重建的 transcript evidence；
- 一个 compact improvement state；
- 明确 result classification。

拾流必须用 V4 Evidence/Citation contract 替代 AREX 的一般 document ID/自由文本 evidence summary。

### 6.2 Outer Constraint Audit

外层审计应逐条检查：

- 哪些 success constraints 已由稳定证据满足；
- 哪些缺失；
- 哪些证据冲突或版本失效；
- 当前结果是 `valid_success`、`partial` 还是 `insufficient`；
- 缺口是否可恢复。

外层可以由模型提出候选 audit，但最终 gate 必须由确定性证据/约束验证与 Runtime 安全规则决定。

### 6.3 Targeted Follow-up

只有同时满足以下条件才 continuation：

- 有具体 unresolved constraint；
- 下一步 query/tool objective 与缺口直接相关；
- 当前 lineage 和 checkpoint 可安全继续；
- 没有 unresolved unknown side effect；
- 预算仍允许；
- 与上一轮相比存在可定义的新 progress delta。

### 6.4 Compact Improvement State

建议拾流 compact state 包含：

- verified evidence references
- satisfied constraint IDs
- unresolved constraint IDs
- rejected candidate + rejection reason
- conflict/validity flags
- blocker
- next targeted objective
- budget usage
- parent checkpoint / attempt identity

它是持久 Runtime state 的有界部分，不是事实权威，也不能覆盖完整 Event/Trace。

## 7. Explicit Rejections

- 不采用 AREX-Turbo/Base 模型或权重。
- 不复制官方 prompts 或 tool schemas。
- 不新增官方仓库依赖。
- 不使用 self-confidence threshold 作为完成门。
- 不继承 prompt 中“问题保证有正确答案、不要放弃”的假设。
- 不在预算耗尽时自动选择最高置信结果并标 success。
- 不让 Restart 删除或覆盖旧 Attempt/Checkpoint。
- 不把论文 benchmark improvement 当作拾流产品质量证据。

## 8. Main Review Decision / Adoption Boundary

```yaml
upstream_id: arex_paper
decision_status: accepted
main_review_round_1_decision: training_independent_patterns_only_reference
patterns:
  - inner_research
  - outer_constraint_audit
  - targeted_follow_up
  - compact_improvement_state
model_adoption: false
weights_adoption: false
prompt_copy: false
code_copy: false
direct_dependency: false
implementation_authorized: false
stage_1_implementation: prohibited
required_shiliu_overrides:
  - stable_transcript_evidence_and_citation_validation
  - deterministic_constraint_gate
  - durable_task_attempt_checkpoint_lineage
  - explicit_partial_and_insufficient
  - bounded_budget_and_semantic_no_progress
  - unknown_external_in_flight_fail_closed
```

V5 主 Session 第一轮独立审查已确认该 reference-only 边界：不采用模型、权重、Prompt、代码或 confidence gate，Stage 1 不实现 AREX 模式。任何未来独立重实现仍需对应 Stage Contract 授权。

## 9. Registry Update（主 Session 已执行）

主 Session 已更新 `arex_paper` 条目，并将论文许可与代码许可分开记录：

```yaml
source_last_checked: 2026-07-31
paper:
  arxiv_id: "2607.21461"
  version: v2
  url: https://arxiv.org/html/2607.21461v2
  license: arXiv perpetual non-exclusive license
official_artifacts:
  project_url: https://vectorspacelab.github.io/arex-model/
  repository: https://huggingface.co/BAAI/AREX-Turbo
  pinned_commit: 129812742df4a5de27980ed07bda78d9d27c7370
  license: Apache-2.0
review_evidence:
  paper_reviewed: true
  official_source_reviewed: limited_inference_subset
  complete_outer_loop_available: false
  training_pipeline_available: false
  tests_available: false
  tests_executed: false
  weights_downloaded: false
  provider_run: false
adoption_status: adopted
adoption_type: training_independent_patterns_only
usage_level: design_reference
role: recursive_research_design_reference
qualifier: no_model_no_weights_no_prompt_no_code_no_confidence_gate_stage_1_excluded
adoption_boundary:
  model: rejected
  weights: rejected
  prompt_copy: rejected
  code_copy: rejected
  confidence_gate: rejected
stage_1_implementation: prohibited
implementation_authorized: false
```

`adoption_status` 已使用 Program Registry 允许枚举；其受限含义由 `adoption_type`、`usage_level`、`role`、`qualifier`、`stage_1_implementation` 与 `implementation_authorized` 共同表达。

## 10. Research Log Update（主 Session 已执行）

主 Session 已追加权威事件 `UR-20260731-016`；以下是报告阶段保留的摘要记录：

```json
{"timestamp":"2026-07-31","session":"V5 main session","upstream_id":"arex_paper","event_type":"main_review_reference_boundary_confirmed","paper":"arXiv:2607.21461v2","paper_license":"arXiv perpetual non-exclusive license","official_repository":"https://huggingface.co/BAAI/AREX-Turbo","commit":"129812742df4a5de27980ed07bda78d9d27c7370","repository_license":"Apache-2.0","paper_reviewed":true,"official_source_reviewed":"limited_inference_subset","tests_reviewed":false,"tests_executed":false,"weights_downloaded":false,"provider_runs":false,"outcome":"training_independent_patterns_only_design_reference","model_adopted":false,"prompt_copied":false,"code_copied":false,"confidence_gate_adopted":false,"stage_1_implementation":false,"implementation_authorized":false}
```

## 11. Evidence Classification

| 证据项 | 分类 |
| --- | --- |
| arXiv v2 方法 | paper_reviewed |
| arXiv 论文许可 | verified |
| 官方项目/HF repository identity | verified |
| 固定 repository commit | verified |
| Apache-2.0 | verified |
| `inference.py` / prompts / README | limited_source_reviewed |
| 完整 outer loop | unavailable_not_reviewed |
| 训练 pipeline/data | unavailable_not_reviewed |
| 官方测试 | unavailable_not_reviewed |
| 模型权重 | not_downloaded |
| Provider / model behavior | not_exercised |
| 论文效果向拾流的迁移 | unproven |

## 12. 主 Session 接受结果

主 Session 已接受 `training_independent_patterns_only` Adoption Proposal、分离的论文/代码许可记录和 `limited_inference_subset` 证据分类。若官方未来发布完整 outer loop、训练管线或测试，将在相关 Stage 前形成新的有界研究 Episode；该动作不属于 Stage 1。

```yaml
research_report_status: accepted
adoption_decision_status: accepted
implementation_authorized: false
provider_runs_performed: false
```
