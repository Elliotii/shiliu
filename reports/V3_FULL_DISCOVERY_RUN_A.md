# V3 Full Discovery Run A

## 验收结论

```text
PASS_WITH_CHANGES
```

Run A 的工程链路已经可靠跑通：Run #12 在不重放 Run #10 十二个 Discovery
调用的前提下，完成了两条候选归一化、Content Type Consolidation、Domain
Consolidation、结构检查和 Quality Gate。自动 Quality Gate 为 PASS，数据库状态与
实际产物一致。

但自动 Gate 存在一项语义盲区：它只能识别名称完全相同的 Domain / Content Type
泄漏，未识别最终 Content Type `Agent 架构与原理` 明显偏向知识领域；
`AI 学习路径与职业规划` 也混合了内容目标和领域语义。因此 Run A 结果可用于验证
Pipeline 和候选收缩，但进入 Run B / C 前应补一项窄范围 Content Type 语义纯度
检查，并决定是否只重跑 Content Type Consolidation。

本轮没有启动 Run B、Run C、Cross-run Merge、Trial Assignment、Diagnosis、
Revision、Silver Eval、UI 或发布。

## 1. 冻结输入与运行血缘

| 项目 | 值 |
|---|---|
| 正式完成 Run | #12 |
| Protocol | `full-discovery-run-a-v3` |
| Engine | `dual-view-discovery-workflow-v10` |
| Snapshot | #2，131 张 Card |
| Discovery Eligible | 128 |
| Trial Assignment Only | 3 |
| A / B / C / D | 76 / 17 / 35 / 3 |
| Snapshot Hash | `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2` |
| Profile Hash | `07a814d37dacf397790c6928f9e4f84768d2eb138a3112152cac383edd7f39ba` |
| Domain View | `classification_profile_v1` |
| Content Type View | `compact_form_view_v1` |
| Seed / Batch Size | 101 / 24 |
| Model | `deepseek-v4-pro` |
| Run #12 Git Commit | `c8c4ab0c890ca215b1373c611a3610a65773bf67` |
| Discovery 复用来源 | Run #10，12 / 12 Stage |
| Content Type Reduce 复用来源 | Run #11，1 / 1 Stage |
| 新模型调用 | 1 次 Domain Consolidation |

Run #12 中十二个 Discovery Stage 和 Content Type Consolidation 的
`attempt_count` 均为 0。`reused-discovery-lineage.json` 保存了每个批次的源 Run、
源 Stage、批次成员、输入/输出 Hash、原始响应/解析结果/Prompt/Audit 文件 Hash、
Provider 合约和验证时间；`reused-consolidation-lineage.json` 对 Content Type
Reduce 保存了同等级证据。

Run #10 没有被修改：仍有 54 个文件；Manifest Hash、数据库 Run Row Hash 和 Stage
Rows Hash 分别保持为：

```text
8af50461d2f1468c1cc51f582c52a27a0bd8d03b8eb2cbba7a1a7c965ab864e9
47e14e4422bd615b73a9d01fef98db8f7ae45c3f4ea1e5afc4d74c8ecb023a01
2b88212126b117a231733ae7371643df38f8941acf85291ae3e6fcc2cbc6c5ae
```

## 2. 调用、Token 与耗时

### 正式结果实际引用的调用

| 阶段 | 来源 | 调用数 | Tokens | Provider 耗时 |
|---|---:|---:|---:|---:|
| Domain Local Discovery | Run #10 | 6 | 19,437 | 100.416 s |
| Content Type Local Discovery | Run #10 | 6 | 28,248 | 111.511 s |
| Content Type Consolidation | Run #11 | 1 | 10,410 | 46.567 s |
| Domain Consolidation | Run #12 | 1 | 25,133 | 280.161 s |
| 合计 | 三个 Run 的已验证产物 | 14 | 83,228 | 538.655 s |

Run #12 自身只新增 25,133 Tokens：5,838 prompt、19,295 completion，其中
13,144 reasoning。Repair 为 0，成功调用的 Retry 为 0。运行从 04:20:38 UTC 到
04:25:18 UTC；本地 Normalize、结构规则和 Gate 均在秒级时间分辨率内完成。

Run #11 还发生过一次未纳入最终结果的失败 Domain 调用：14,029 Tokens、
132.284 秒。它在 8,192 completion 上限内消耗了 8,191 reasoning Tokens，最终正文
为空，`finish_reason=length`。因此总实际历史支出为 97,257 Tokens、670.939 秒；
其中 14,029 Tokens 是失败开销。

新的冻结预算不是另一个固定 48/Top-K：

```text
max_tokens = round_up(
  clamp(8192 + normalized_candidate_count * 256, 16384, 24576),
  1024
)
```

42 个 Domain 候选得到 19,456 上限。成功响应使用 19,295 completion Tokens，只余
161 Tokens，证明原 8,192 限制确实不足。策略、参数和实际预算均冻结在 Run #12
Manifest 中。

## 3. Content Type 候选收缩

| Batch | Cards | 局部候选 | Ambiguous IDs |
|---:|---:|---:|---:|
| 1 | 24 | 8 | 2 |
| 2 | 24 | 8 | 2 |
| 3 | 24 | 8 | 9 |
| 4 | 24 | 8 | 7 |
| 5 | 24 | 8 | 5 |
| 6 | 8 | 6 | 0 |

```text
局部原始候选：46
确定性 Normalize：45
Consolidation 最终节点：8
候选决策：kept 1，merged_into 44，删除 0，降级 0
Merge Ratio（相对原始）：82.61%
Merge Ratio（相对 Normalize）：82.22%
达到每批 8 个上限：5 / 6 Batch
```

| 最终 Content Type | supporting IDs 数 |
|---|---:|
| Agent 架构与原理 | 4 |
| AI 学习路径与职业规划 | 14 |
| AI 工具评测与对比 | 9 |
| 实操教程与项目实战 | 21 |
| 技术原理解析与深度分析 | 13 |
| 经验心得与观点分享 | 18 |
| 工具与框架介绍 | 13 |
| 方法论与自动化实践 | 14 |

45 个 Normalize 候选全部拥有一条 Candidate Decision，没有候选节点级静默丢弃或
Top-K。
最终节点 supporting IDs 的并集覆盖 90 / 128 张 Discovery Card；这不是 Trial
Assignment Coverage，因为 Reduce 只保存代表性支持，不负责给全量内容分类。

数量收缩本身合理，但语义纯度不足：`Agent 架构与原理` 是明显的 Domain 表达；
`AI 学习路径与职业规划` 更接近目标/领域组合；`工具与框架介绍` 与“形式”和“对象”
的边界也需要复核。模型把 45 个候选全部归入 8 个节点，没有使用
`removed_as_domain/entity/topic/unsupported`，说明 Reduce 的拒绝能力没有在真实
结果中得到验证。

## 4. Domain 候选收缩

| Batch | Cards | 局部 Domain | Topic hints | Ambiguous IDs |
|---:|---:|---:|---:|---:|
| 1 | 24 | 8 | 5 | 6 |
| 2 | 24 | 8 | 5 | 4 |
| 3 | 24 | 7 | 3 | 4 |
| 4 | 24 | 7 | 2 | 3 |
| 5 | 24 | 8 | 3 | 6 |
| 6 | 8 | 5 | 2 | 1 |

```text
局部原始候选：43
确定性 Normalize：42 Domain + 20 Topic hints
Consolidation：7 个一级 Domain + 9 个二级 Domain
候选决策：merged_into 42，删除 0，降级 0
Merge Ratio（相对原始、按全部最终 Domain 节点）：62.79%
Merge Ratio（相对 Normalize）：61.90%
达到每批 8 个上限：3 / 6 Batch
```

| 一级 Domain | 一级支持数 | 二级 Domain（支持数） |
|---|---:|---|
| AI Agent 系统与工程 | 31 | Agent 架构与工程化 (16)；Agent 记忆与上下文管理 (6)；Agent 测试与验证 (3)；多代理协作系统 (3)；人机交互与系统集成 (5) |
| AI 辅助开发与交互 | 22 | AI 编程工具与开发工作流 (16)；AI 交互与提示工程 (5) |
| 检索增强生成 (RAG) | 6 | 无 |
| 大模型优化与工程 | 8 | 无 |
| AI 应用与内容生成 | 4 | 无 |
| 职业发展与面试 | 11 | 职业路径与技能发展 (5)；面试与求职准备 (6) |
| 软件工程基础 | 10 | 无 |

42 个候选全部可追溯到最终一级或二级节点，没有候选节点级隐性截断。Domain supporting IDs
并集为 84 / 128，同样只是候选证据覆盖，不是 Trial Assignment Coverage。

## 5. 自动 Quality Gate

自动 Gate 结果：

```text
passed: true
blocking_issues: 0
warnings: 3
recommended_next_stage: run_b
```

已确认指标：

- invalid supporting IDs：0；
- Entity Leakage into Domain：0；
- Content Type Leakage into Domain：0；
- Domain Leakage into Content Type（仅名称精确匹配规则）：0；
- Entity Leakage into Content Type：0；
- 一级 / 二级 Domain：7 / 9；
- Content Type：8；
- 过宽一级 Domain：0；
- 丢失全部 Content Type 候选的 Batch：0。

三个 Warning：

1. 15 个 Domain 节点使用了与局部候选不完全同名的新名称，需要语义审计；
2. 20 / 35 张 C 级 Card 在局部 Content Type 发现中被标记 ambiguous（57.14%）；
3. 5 / 6 个 Content Type Batch 达到候选上限。

结构规则没有产生需模型复核的高重叠 sibling pair，因此
`local_validation_unit_count=0`，未额外调用 Validator。这是规则结果，不应表述为
模型已逐节点审查。

自动 PASS 不等于最终产品验收 PASS。当前泄漏检查使用规范化后的名称等值匹配，
无法识别语义近似或重新命名后的维度混用；这正是本报告将最终结论降为
`PASS_WITH_CHANGES` 的原因。

## 6. 工程修复

本轮完成：

1. 中间候选容量改为 `source_batch_count × per_batch_schema_limit`，取消 Normalize
   前的固定 24 和 Topic 16 截断；
2. Candidate Decision Schema 要求覆盖全部 Normalize 候选，并验证目标节点；
3. Run / Stage 异常路径写入 failed 或 retry_wait，并保存失败阶段、时间、错误、
   可重试性、完成/未完成 Stage 和复用资格；
4. 对 Run #10 十二个 Discovery Stage 实施严格跨 Run 复用；
5. 对 Run #11 已完成的 Content Type Consolidation 实施同等级严格复用；
6. Domain Consolidation 输出预算按候选数计算并冻结；
7. 补充容量、异常状态、Resume、产物血缘、旧 Manifest 预算缺省值和预算边界测试。

全量测试结果：137 passed；另有一条现存 Starlette / httpx deprecation warning。

与原计划的偏差只有一次必要的第二轮最小修复：Run #11 证明 high-thinking Domain
Consolidation 的 8,192 输出预算不足，因此创建 Run #12，并只新调用受影响的 Domain
Consolidation。没有修改 Snapshot、双视图、局部 Discovery Prompt 或分类对象定义。

## 7. 进入 Run B / C 前的窄范围修改

1. 增加独立的 Content Type 语义纯度检查，不能只做最终名称精确匹配；
2. 明确标记 `Agent 架构与原理` 等节点是否应
   `removed_as_domain`，必要时只重跑 Content Type Consolidation；
3. 取消输出 Schema 的静默字段截断，或把截断记录为明确的校验错误/审计事件；
   本次原始 `软件工程基础.includes` 从 6 条静默变为 5 条；
4. 对 57.14% 的 C 级局部 Content Type ambiguity 和 5 / 6 Batch 饱和保留警告，
   不在本轮修改局部 Prompt；
5. 在 Run B / C 之前确认 high-thinking Reduce 的 24,576 技术上限是否给最坏候选
   数留下足够保险；本轮 19,456 仅余 161 Tokens。

本轮已经使用两次允许的最小修复（候选容量/状态/复用，以及 Domain Reduce 预算），
因此按约束停止，不再自行发起第三轮模型修复。

## 8. 独立只读复核

Reviewer 结论：

```text
PASS_WITH_CONCERNS
```

Reviewer 独立复现了候选数量、Token/时间、12 个 Discovery Stage 与 1 个 Content
Type Reduce 的零调用复用血缘、Run #10 四项冻结 Hash、失败状态和自动 Gate PASS。
它执行了 25 个定向测试，全部通过。

Reviewer 同意主报告对 Content Type 语义泄漏的判断，并额外发现字段级静默截断：
`TopLevelDomainNode` 的 `mode="before"` validator 把原始
`软件工程基础.includes` 从 6 条截成 5 条。这不影响 42/45 候选决策的完整性，
但必须在 B/C 前改为明确校验或可审计事件。

主 Agent 接受 Reviewer 的全部 Required Fixes，没有未解决的结论分歧。完整复核见
`reports/V3_RUN_A_INDEPENDENT_REVIEW.md`。

## 9. 停止位置

```text
Run A 工程 Pipeline：完成
自动 Quality Gate：PASS
主 Agent 技术验收：PASS_WITH_CHANGES
独立只读 Reviewer：PASS_WITH_CONCERNS，Required Fixes 已接受
禁止阶段：B / C / Merge / Assignment / Diagnosis / Revision 均未启动
```
