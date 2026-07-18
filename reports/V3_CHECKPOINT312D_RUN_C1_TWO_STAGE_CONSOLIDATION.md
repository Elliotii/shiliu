# V3 Checkpoint 3.12D：Run C1 两阶段 Domain Consolidation

## 结论

Run C1 完成了 `Local Discovery → Normalize → Domain Node Synthesis → Batched Candidate Routing → Deterministic Assembly → Gate`，证明两阶段执行协议能够在不重放已完成批次的前提下实现 44 / 44 Candidate 的完整决策与可恢复落盘。

本 Checkpoint 的正式结论为 **FAIL**，未来 Run C2 **不可执行**。失败原因不是结构化输出、覆盖率或恢复机制，而是冻结 Domain Tree 后仍有 10 / 44（22.7273%）Candidate 需要新领域，其中 4 个 Candidate 具有多条 Evidence，超过 Gate 允许的 `≤ 3 且 ≤ 10%`，并触发系统性未解决边界判定。

本报告不修改 Run C1 Tree，不把 Run B 的 unresolved 当作正确答案，不执行 Cross-run Merge、C2、Draft A 或 Trial Assignment。

## 1. Git 冻结

- Checkpoint 3.12C 基线：`9435094 feat: complete Run B domain evidence contract`
- 冻结 Tag：`checkpoint/v3.12c-run-b-complete`
- Run C1 分支：`feat/v3-domain-consolidation-v2`
- Run C1 执行代码：`a2ff92b feat: add two-stage domain consolidation protocol`
- Tag 与基线分支均已推送远端；Run C1 Manifest 记录执行时工作区 clean。

## 2. Hash Algorithm v2

`sha256-tree v2` 使用以下确定性契约：

- 相对 POSIX 路径按字典序排列；
- 文件内容按原始 bytes 计算 SHA-256，不转换换行；
- 只接受普通文件，遇到符号链接即拒绝；
- 排除 `.DS_Store`、`*.tmp`、`__pycache__/*` 和自引用的 `final-artifact-manifest.json`；
- Manifest 保存每个文件的路径与内容 Hash，再计算 Tree Hash；不同版本算法的 Hash 不得直接比较。

Run C1 最终 Manifest：

| 项目 | 值 |
|---|---:|
| Hash algorithm version | `v2` |
| 文件数 | 76 |
| Tree Hash | `1790e6b48f11cc296ac8e851c178623e293b2f0770c66771751b1448f14a2192` |
| Reviewer 重算 | 与 Manifest 完全一致 |

关键产物 Hash：

| 产物 | SHA-256 |
|---|---|
| Normalized Candidate Table | `917eb091eabe8111e4cf2548ece03a7ee27bb0145e1cb58e5d6c20e18a8b15be` |
| Frozen Domain Tree | `b2c2bdb1bad01ea769d6863af532a7678f0973a2bbc94503f8e13dd8e4909ad8` |
| Complete Candidate Decisions | `5664ba9c5026b86b4de57171f355fa7b099f4d96e56e2717cde68bfb26addbde` |
| Evidence Contract v2 | `7c5c6b6506784e55effac906467432e2f584dd5165d1a56443b3fae7cd5a6148` |
| Quality Gate | `de0cc0807fd00b6f100858d2c88b5f0bac9f0a8874269a49ecc52786ee1a3040` |
| C2 Replication Plan | `c1bcb7ba31a5f4f54e5b1efd0a4e919f4f99a0a674ffb07d18a8e514b8b7eaf5` |

## 3. Semantic Contract 与 Execution Contract

Domain Semantic Contract 继续使用 `domain-semantic-contract-v1`：问题仍是“内容属于什么相对稳定、可长期复用的知识领域？”，最多两级，并继续排除表达形式、使用场景、工具、模型、项目、人物、单篇论文、短期热点和过窄实现细节。

- Semantic Contract canonical hash：`b512b78032b00deef0294235387c6c03680e11a2bbdfa37aa099aaaae730632f`
- Execution Contract：`domain-consolidation-execution-contract-v2`
- 新执行阶段：`domain_node_synthesis`、`batched_candidate_routing`、`coverage_consistency_assembly`

设计意图是与 A/B 相比只改变 Consolidation 的序列化、分批和恢复方式。已确认没有改变 Domain 问题、Local Discovery 语义、Normalize 语义、Snapshot、Eligible IDs 或 Provider 角色；但全局 Consolidation 语义是否等价，仍需结合第 4 节的独立复核结论。Local Schema 沿用 A/B 已冻结的 `domains / topic_hints / ambiguous_ids`，没有为了 C1 单独加入新字段。

## 4. A/B/C1 可比性审计

运行前的自动 `run-c1-comparability-audit.json` verdict 为 `PASS`：

- Snapshot 相同：Snapshot #2，Hash `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2`；
- Discovery Eligible 相同：128；
- Domain Semantic Contract 相同；
- Local Discovery 与 Normalize 语义相同；
- Provider Contract 相同；
- 唯一预期改变为 Execution Contract，以及由 seed 导致的顺序和批次成员差异；
- Run B Taxonomy、Run B unresolved、Silver Reference、controlled facets 和 folder names 均为禁止输入。

但独立复核发现，这个自动结论不能作为最终可比性证明：代码把 `same_semantic_contract` 直接写为 `True`，没有将 C1 canonical Semantic Contract 与 A/B 冻结语义材料逐字段比较；而 C1 Node Synthesis 又明确加入“Domain 能被多条内容共同支持”等约束，A/B Consolidation Prompt 未明确写出同一规则。因此本报告撤回“已经证明只改变 Execution Contract”的强结论，只保留以下已证事实：Snapshot、Eligible IDs、Local Prompt/Schema、Normalize 与 Provider 配置相同；全局 Consolidation 的语义等价性仍是阻断项，需要新 Checkpoint 审定。

## 5. Run C1 Manifest

| 字段 | 值 |
|---|---|
| Run ID / Label | `23 / C1` |
| Seed | `303` |
| Snapshot | `#2` |
| Eligible Cards | 128 |
| Local batch size | 24 |
| Local batches | 6（24 / 24 / 24 / 24 / 24 / 8） |
| Routing batch size | 12 |
| Routing batches | 4（12 / 12 / 12 / 8） |
| Model | `deepseek-v4-pro` |
| Local / Repair thinking | off |
| Node / Routing thinking | on，`high` |
| Runtime 状态 | `quality_failed` |
| 当前阶段 | `run_c1_quality_gate` |

## 6. Local Discovery 与 Normalize

6 个 Local Batch 均完成且主调用均为 1 次。Batch 4 与 Batch 6 首次响应需要既有 JSON Repair；每批只有一次局部 Repair，原始语料没有重放。Repair 只做结构恢复并记录语义选择 Diff；共记录 2 个语义选择事件，因此 Gate 将其作为 warning，而不是隐藏掉。

Normalize 是纯本地确定性阶段，生成 44 个紧凑 Domain Candidate。每个 Candidate 保留 Candidate ID、名称、定义、supporting / representative IDs、Evidence code、includes / excludes、confidence 与源 Batch 血缘。

## 7. Stage A：Domain Node Synthesis

Stage A 一次性读取完整的 44 条 Normalized Candidate Table，只输出冻结 Domain Nodes，不输出 Candidate Decision，也不使用固定 Top-K。

| 指标 | 结果 |
|---|---:|
| 主调用 | 1 |
| Repair | 0 |
| finish_reason | `stop` |
| 生成节点 | 24 |
| 一级节点 | 7 |
| 最大深度 | 2 |
| Prompt tokens | 4,839 |
| Completion tokens | 14,159 |
| Reasoning tokens | 9,592 |
| Total tokens | 18,998 |
| 耗时 | 191.308 秒 |
| 输出预算占用 | 86.4197%（14,159 / 16,384） |
| 语义 Tree Hash | `1b54b2ff9a6a509190d25bf7dbfc39a92d15912c7747f0b4743dc556a57ab9b7` |

输出没有被截断，但 Completion 预算余量偏低、Reasoning 较高，均被 Gate 记录为非阻断 warning。

## 8. Stage B：Batched Candidate Routing

Routing 读取冻结 Tree 与当前 Candidate Batch，只能输出 Candidate Decision，不能新增、重命名、移动或删除节点。四批均一次主调用完成，无 Repair、无 Tail Completion。

| Batch | Candidates | Prompt | Completion | Reasoning | Total | 秒 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 12 | 5,203 | 4,468 | 2,297 | 9,671 | 62.820 |
| 2 | 12 | 5,254 | 3,977 | 1,892 | 9,231 | 57.348 |
| 3 | 12 | 5,252 | 3,567 | 1,712 | 8,819 | 50.194 |
| 4 | 8 | 4,721 | 3,676 | 2,294 | 8,397 | 63.692 |
| 合计 | 44 | 20,430 | 15,688 | 8,195 | 36,118 | 234.054 |

每批 Audit 在调用前落盘，收到原始响应后立即保存 raw response，再解析；已完成批次在 resume 时不会重放。

## 9. Assembly、Coverage 与血缘

Assembly 是纯本地确定性阶段：

- expected Candidate IDs = actual Candidate IDs；
- 44 个 Candidate 恰好各有一条 Decision；
- 缺失、多余、重复、非法 action / target 均会拒绝；
- 结果覆盖率 44 / 44 = 100%；
- 每条 Decision 保存 routing batch、attempt 与 raw response Hash；
- `source_candidate_ids`、`evidence_pool_ids` 和 `source_batch_ids` 从 Candidate 与 Decision 派生；
- 本阶段不生成视频 Assignment。

恢复后的只读核验显示所有 Provider Stage 的 `attempt_count` 仍为 1，原始响应 Hash 与时间不变；重新执行 resume 只重建 Gate / Manifest，没有新 Provider 调用。

## 10. Evidence Contract v2 与 Parent/Child v2

24 个节点统一输出 `domain-evidence-contract-v2`，并保留：

- model-selected evidence；
- representative evidence；
- 由全部 source candidates 派生的 evidence pool；
- canonical / display includes 与 excludes；
- source candidate / batch / run / stage / attempt 血缘。

Parent/Child v2 的 blocking 与 warning 均为空。校验采用“概念范围必须为父级的更具体子集”，但不错误要求子节点 Evidence 必须是父节点模型选择 Evidence 的子集。

Gate 另外发现 11 个节点的 Evidence Pool 不超过 2 条，这是需要后续关注的非阻断风险，不代表血缘缺失。

## 11. unresolved 与 Run C1 Gate

| 指标 | 值 |
|---|---:|
| Candidate 总数 | 44 |
| unresolved | 10 |
| unresolved 比例 | 22.7273% |
| 多 Evidence unresolved | 4 |
| High-confidence unresolved | 0 |
| 涉及独立 supporting IDs | 14 |

未解决 Candidate：`AI基础设施`、`AI游戏技术`、`AI生成UI与设计自动化`、`AI科研加速`、`人机交互与内容提取`、`人机协同与创造力增强`、`大模型学习与微调（学习路径）`、`机器学习教育`、`算法优化与双指针技巧`、`终端与命令行`。

Gate blocking：

1. `unresolved_boundary_exceeded`：10 条、22.7273%，同时超过数量和比例门禁；
2. `systematic_unresolved_gap`：4 个 unresolved 具有多条 Evidence，不是孤立单卡噪声。

因此 Gate 状态为 **FAIL**。这些 Candidate 没有被强行归类，也没有在冻结 Tree 上偷偷新建节点。

## 12. Run B unresolved 的封存后对照

此对照只在 C1 完成并封存后进行，没有进入 C1 Prompt、Tree、Decision 或 Gate，也不用于修改 C1。

| Run B unresolved | C1 独立候选路径 | C1 结果 |
|---|---|---|
| `语音交互系统`（C016） | C1 Local/Normalize 将 C016 纳入 `AI Agent系统` 的 Evidence | 合入较宽的 `c1_d_01 AI Agent 系统与工程`，没有保留同名概念 |
| `间隔重复系统`（C126） | C1 形成 `nc_021 个人知识管理与复习系统`（C070、C126） | `downgrade_to_entity`，判断为具体系统而非稳定 Domain |

这表明两次执行对边界的处理不同，但不能据此认定任一结果是“正确答案”。C1 另有 10 个自身产生的 unresolved，仍须按 C1 Gate 独立失败。

## 13. Token、耗时与 Repair 成本

下表包含主调用和两次 Local JSON Repair；Reasoning token 已包含在 Completion token 中，因此 Total 只按 Prompt + Completion 计算。

| Stage | 调用数 | Prompt | Completion | Reasoning（Completion 子集） | Total | 秒 |
|---|---:|---:|---:|---:|---:|---:|
| Local Discovery（含 2 Repair） | 8 | 15,399 | 9,695 | 0 | 25,094 | 118.226 |
| Node Synthesis | 1 | 4,839 | 14,159 | 9,592 | 18,998 | 191.308 |
| Candidate Routing | 4 | 20,430 | 15,688 | 8,195 | 36,118 | 234.054 |
| 总计 | 13 | 40,668 | 39,542 | 17,787 | 80,210 | 543.588 |

两次 Repair 合计 3,161 Prompt + 2,148 Completion = 5,309 tokens、21.612 秒。没有 Routing Repair、Tail Completion 或 Node Repair。Normalizer、Assembly、Evidence Adapter、Gate、Manifest 和 resume 审计均为本地操作，不调用 Provider。

## 14. C2 Replication Plan

`run-c2-replication-plan-v1` 已冻结未来 C2 的 Semantic / Execution / Evidence / Hash / Gate 版本、Provider、Model、thinking、Schema Hash、Prompt Version、Normalize 版本和两个 Batch Size。未来只允许改变 seed、卡片和 Candidate 顺序、对应批次成员、run_id 与 timestamps。

独立复核同时确认该计划仍不完整：它没有锁定 Node Synthesis 与 Candidate Routing 的实际 Prompt Template Hash。仅锁 Prompt Version 无法阻止“模板代码改变但版本号未更新”的静默漂移，因此即使 Gate 没有失败，当前计划也不足以批准精确复制。

当前 `replication_eligible=false`。任何语义 Prompt、Schema 或 Contract 修改都必须进入新协议版本，不能直接冒充 C2 复制实验。

## 15. 测试

Checkpoint 新增测试覆盖：

- Hash v2 的版本、排序、排除、raw bytes、symlink 拒绝与可复算；
- Semantic canonical hash 与 Execution Contract 分离；
- Node Synthesis 完整 Candidate Table、无固定 Top-K、无 Decision、最多两级、Evidence 可追踪；
- Routing 确定性 Batch、精确覆盖、合法 action / target、冻结 Tree；
- Assembly 100% 覆盖和 Decision 血缘；
- Evidence Pool 与 source batch 派生；
- C2 Replication Plan 锁定字段与 Gate 资格。

全量测试：`243 passed`。唯一输出为既有的 Starlette / httpx deprecation warning，不影响结果。

## 16. 独立只读 Reviewer

Reviewer 在报告完成后执行，只允许读取代码、数据库元数据、Run C1 产物与本报告；不得修改代码或数据库、调用 Provider、读取 Silver、把 Run B unresolved 当成正确答案、接受自动 Gate 代替复核，或执行 Cross-run Merge。

Reviewer verdict：**FAIL**；Replication Eligibility：**FALSE**。

### Evidence

- 3.12C Tag 正确指向 `9435094`；Hash v2 的 76 个文件、Tree Hash 和六个关键资产 Hash 均可独立复算；
- Snapshot、Eligible IDs、Local Prompt/Schema、Normalize 和 Provider 配置与 A/B 相同；
- Node Prompt 包含 `nc_001–nc_044`，Node 输出只有 24 个节点，没有 Candidate Decision；
- 四个 Routing Prompt 的 Frozen Tree 与落盘 Tree 逐字段一致，输出只有 Decision；
- 44 个 Candidate 各有且仅有一条 Decision，Coverage 100%，血缘完整；
- Repair 只发生在 Local Batch 4、6；Node / Routing 无 Repair 或 Tail；
- 24 个 Evidence Contract v2 节点的版本、统计、来源和派生 Hash 一致；
- 10 个 unresolved 没有被强行归类；Run B unresolved 没有进入模型输入；
- DB 状态、12 个 Stage 的 attempt count，以及 80,210 tokens / 17,787 reasoning / 543.588 秒均可复现。

### Blocking Findings

1. 10 / 44 unresolved（22.7273%），其中 4 个为多 Evidence、共涉及 14 个 supporting IDs，构成系统性边界缺口；
2. `same_semantic_contract=True` 是硬编码，未与 A/B 冻结语义材料比较；
3. C1 新增了 A/B Consolidation Prompt 未明确写出的语义规则，所以“只改变 Execution Contract”尚未成立；
4. C2 Plan 缺少 Node / Routing Prompt Template Hash，无法防止模板静默漂移。

### Non-blocking Concerns

- Node Completion 预算占用 86.4197%，Reasoning 9,592 tokens；
- 11 个节点的 Evidence Pool 不超过两条；
- 两次 Local Repair 产生了显式语义选择记录。

### Required Fixes

- 禁止执行 C2；
- 新 Checkpoint 先审定 C1 新语义规则与 A/B 原语义的差异，移除硬编码可比性结论；
- 若调整 Semantic Contract、Node Prompt 或 Tree 规则，必须升级为 v2.1 并作为新实验，不能冒充 C2；
- 后续复制计划锁定 Node 与 Routing Prompt Template Hash；
- 保持 C1 原始 Tree、Decision、DB 状态和失败结果不变。

## 17. 最终判定

```text
Checkpoint 3.12D: FAIL
Run C1 execution completeness: PASS
Run C1 candidate coverage: PASS (44/44)
Run C1 quality gate: FAIL
C1 semantic comparability: NOT PROVEN
C2 Replication Eligibility: FALSE
```

下一步不能直接运行 C2。若要继续，必须先由新的 Checkpoint 明确决定如何处理系统性 unresolved 边界；任何语义调整都需要新协议版本，不能回写或静默修改已冻结的 Run C1。
