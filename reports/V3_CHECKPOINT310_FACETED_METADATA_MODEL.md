# V3 Checkpoint 3.10：Faceted Metadata Model

## 当前结论

```text
Automatic Gate: FAIL
Main Agent preliminary verdict: FAIL
Independent Reviewer: FAIL
```

四分面 Schema、可恢复 Runner、31 候选拆解、48 条真实赋值和 OR/AND
组合筛选均已完成，但本次候选发现方式没有形成可用的受控词表。失败不是 Domain
路径或标签预算错误，而是拆解器把每个旧候选都强迫填满多个分面，随后把近义成分
逐一保留，导致词表碎片化和组合查询大量为空。

本轮不进入 128 条全量验证、Run B/C、Trial Assignment 或正式 UI。

## 1. Git 冻结和分支

| 项目 | 值 |
|---|---|
| Checkpoint 3.9 基础 Commit | `b65a866a99163294d7e3b5b81f7f8825894186c1` |
| Checkpoint 3.9 标记 | `checkpoint/v3.9-failed` |
| 新分支 | `feat/v3-faceted-metadata` |
| 初始实现 Commit | `e8eb885` |
| 第一轮窄修复 Commit | `ab857c2` |
| 第二轮窄修复 Commit | `3227100` |
| 创建时间 | 2026-07-18（Asia/Shanghai） |

Run #10 和 #11 的历史数据库状态仍分别为 `running` 和 `retry_wait`；Run #12、
#13、#14 为 `completed`。按照冻结要求，没有改写这些状态、Manifest 或私有运行产物。
各 Run Manifest Hash 已记录在 ADR。

## 2. ADR 摘要

ADR：`docs/adr/ADR_V3_FACETED_METADATA_MODEL.md`

废弃假设：一套纯净、扁平的 Content Type 可以同时容纳表达形式、对象类别、使用
情境和目标。

新模型：

1. Domain：核心分类树，复用 Run #12，不重新发现；
2. Presentation Form（内容形式）：核心扁平筛选；
3. Focus Object Type（对象类型）：可空辅助筛选；
4. Use Context（使用场景）：可空辅助筛选。

筛选语义固定为同一分面内 OR、不同分面间 AND；未选择的分面不参与过滤。

## 3. 新旧 Schema

| 版本 | 语义 | 本轮状态 |
|---|---|---|
| `content_type_v1` | 旧复合 Content Type 实验 | deprecated、只读保留 |
| `presentation_form_v1` | 表达、组织或呈现方式 | Spike |
| `focus_object_type_v1` | 对象类别，不含具体名称 | Spike |
| `use_context_v1` | 用户任务或目标 | Spike |
| `faceted-assignment-v1` | 四分面单条赋值 | Spike |

没有把 `content_type_v1` 直接写入新字段，没有数据库破坏性迁移，也没有迁移正式
用户数据。

硬预算：

- Domain：1 条 primary path，最多 2 条 secondary path；
- Form：1 个 primary，最多 1 个 secondary；允许 `unknown/ambiguous`；
- Object Type：0～2；
- Use Context：0～2。

所有超限均产生 Pydantic Validation Error，不静默截断。

## 4. 复用血缘

```text
Snapshot #2
  hash 1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2

Run #12
  Domain Draft（只读，Hash 未变）

Run #14
  31 个 normalized Content Type candidates
  compact_form_view_v1
  historical Candidate Decisions（仅血缘，不作正确性证据）

48-item Profile Manifest
  A/B/C = 22 / 9 / 17
```

未读取 Silver Reference、完整字幕或完整总结。

## 5. 31 个候选拆解

覆盖率为 31/31，Schema 字段完整；但 31/31 全部被判为 compound，31/31 全部
生成 Form、Object Type 和 Use Context，Domain component 为 0，只有 1 个 Entity。
这说明拆解器没有真正使用“可空”边界，而是在机械填满分面。

| ID | 旧候选 | Form | Object Type | Use Context | Domain | Entity | Compound |
|---|---|---|---|---|---|---|---|
| `nct_001` | 学习路径指南 | 分阶段步骤序列 | 学习路径 | 技能学习与职业转型 | — | AI/机器学习 | 是 |
| `nct_002` | 工具介绍 | 介绍性概述 | 软件工具 | 工具选型与上手 | — | — | 是 |
| `nct_003` | 工具使用教程 | 步骤教程 | 软件工具 | 工具学习与操作 | — | — | 是 |
| `nct_004` | 工具推荐 | 列举与简要介绍 | 软件工具/资源 | 工具发现与选择 | — | — | 是 |
| `nct_005` | 工具/框架介绍与对比 | 介绍与对比 | 技术工具/框架 | 技术选型与评估 | — | — | 是 |
| `nct_006` | 工具评测与使用心得 | 评测与心得 | 软件工具 | 工具评估与经验分享 | — | — | 是 |
| `nct_007` | 工具评测与推荐 | 评测与推荐 | 软件工具/插件 | 工具选择与配置 | — | — | 是 |
| `nct_008` | 工具评测对比 | 横向对比评测 | 技术工具/模型 | 技术选型与决策 | — | — | 是 |
| `nct_009` | 开源项目介绍 | 项目介绍 | 开源软件项目 | 项目发现与了解 | — | — | 是 |
| `nct_010` | 开源项目源码解析 | 源码解析 | 开源项目源码 | 技术深入学习 | — | — | 是 |
| `nct_011` | 技术原理深度解读 | 深度解读 | 技术概念/机制 | 技术原理学习 | — | — | 是 |
| `nct_012` | 技术原理解析 | 原理解析 | 技术/算法/架构 | 技术原理学习 | — | — | 是 |
| `nct_013` | 技术对比分析 | 对比分析 | 技术方案/工具/协议 | 技术选型与决策 | — | — | 是 |
| `nct_014` | 技术操作教程 | 操作教程 | 技术任务 | 动手实践与操作 | — | — | 是 |
| `nct_015` | 技术教程 | 步骤化教程 | 技术任务/工具 | 技能学习与操作 | — | — | 是 |
| `nct_016` | 技术教程与操作指南 | 教程与指南 | 技术/工具 | 快速上手与问题解决 | — | — | 是 |
| `nct_017` | 技术观点评论 | 观点评论 | 技术工具/方法/趋势 | 观点形成与决策参考 | — | — | 是 |
| `nct_018` | 概念原理解析 | 原理解析 | 技术概念/算法/设计思想 | 概念理解与学习 | — | — | 是 |
| `nct_019` | 步骤教程 | 步骤教程 | 任务流程 | 动手实践与跟随操作 | — | — | 是 |
| `nct_020` | 知识体系梳理 | 体系化梳理 | 知识体系 | 知识学习与体系构建 | — | — | 是 |
| `nct_021` | 经验分享与建议 | 经验分享与建议 | 个人经验/建议 | 职业发展与学习规划 | — | — | 是 |
| `nct_022` | 行业事件快讯 | 新闻快讯 | 行业事件 | 行业动态追踪 | — | — | 是 |
| `nct_023` | 观点评论 | 观点评论 | 主题观点 | 观点参考与讨论 | — | — | 是 |
| `nct_024` | 论文精读 | 论文精读 | 学术论文 | 学术研究学习 | — | — | 是 |
| `nct_025` | 课程大纲 | 课程大纲 | 课程 | 课程选择与规划 | — | — | 是 |
| `nct_026` | 面试经验 | 经验分享 | 面试经历 | 求职面试准备 | — | — | 是 |
| `nct_027` | 项目复盘 | 复盘总结 | 项目经历 | 经验学习与反思 | — | — | 是 |
| `nct_028` | 项目复盘与经验分享 | 复盘与分享 | 个人实践经历 | 经验学习与借鉴 | — | — | 是 |
| `nct_029` | 项目复盘与经验总结 | 复盘与总结 | 个人实践经历 | 方法论学习与借鉴 | — | — | 是 |
| `nct_030` | 项目复盘与配置分享 | 配置分享 | 项目配置/工作流 | 配置参考与复用 | — | — | 是 |
| `nct_031` | 项目实战复盘 | 实战复盘 | 具体项目 | 项目经验学习 | — | — | 是 |

自动 Gate 识别出 5 个 compound 候选原名被直接复制成 Form：`nct_019`、
`nct_021`、`nct_023`、`nct_024`、`nct_025`。即使名称从其他候选中轻微改写，
大量拆解仍表现为“逐词换名”，而不是跨候选归并。

## 6. 三个词表

| 词表 | 总数 | stable | draft | rejected |
|---|---:|---:|---:|---:|
| Presentation Form | 28 | 3 | 25 | 0 |
| Focus Object Type | 28 | 2 | 26 | 0 |
| Use Context | 29 | 2 | 27 | 0 |

原始响应把 85 个节点全部标为 stable，其中 78 个只有单条内容支持。系统依据冻结规则
进行了显式、逐字段、可审计的状态降级：`stable → draft`；名称、定义、includes、
excludes 和 supporting IDs 均未改变。

主要问题：

- 没有任何 rejected 节点，说明归并器仍倾向全保留；
- Form 同时保留“步骤教程、操作教程、步骤化教程、教程与指南”等近义节点；
- Object 同时保留“软件工具、软件工具/资源、技术工具/框架、技术/工具”等粒度混杂节点；
- Context 同时保留多个“学习、操作、选型、借鉴”近义目标；
- 28 个 Form 全部低于 3 条候选期支持，尚无一个具备充分稳定证据。

## 7. 48 条真实赋值

样本证据分布：A/B/C = 22/9/17。

| 指标 | 结果 |
|---|---:|
| 完整赋值 | 48 / 48 |
| Form assigned | 44 |
| Form unknown | 4 |
| Form secondary | 0 |
| Object 空值 | 4（8.33%） |
| Object 平均标签 | 0.917 |
| Context 空值 | 17（35.42%） |
| Context 平均标签 | 0.646 |
| Context low-confidence 内容 | 0 |
| Novelty Pool | 0 |
| 平均总标签 | 3.479 |

每条实际 Object/Context 最大值均为 1，没有超出 2；Domain secondary path 最大为 2，
没有标签预算违规。总标签分布为：4 个标签 31 条、3 个标签 13 条、仅 Domain 1 个
标签 4 条。

Form 使用高度集中：`pf_17 观点评论` 被分给 14/48 条，而 9 个 Form 只有 1～2 条。
Object 主要集中在 `fo_09 技术概念/机制`（9 条）、`fo_02 软件工具`（8 条）和
`fo_15 技术工具/方法/趋势`（6 条）。Context 有 17 条为空，符合“允许为空”，但其余
标签仍主要落在大量 draft 节点上。

## 8. 组合筛选模拟

筛选使用真实 48 条赋值，规则为同分面 OR、跨分面 AND。

| 指标 | 结果 |
|---|---:|
| 有支持的单标签 | 64 |
| 单标签结果中位数 | 2 |
| 单标签 singleton | 24 |
| 两分面组合 | 783 |
| 两分面空结果 | 633（80.84%） |
| 两分面 singleton | 111（14.18%） |
| 两分面结果中位数 | 0 |
| 两分面最大结果 | 9 |
| 高度共同出现的跨分面关系 | 141 |

报告产物还保存了 Domain+Form、Domain+Object、Form+Context、三分面和四分面的真实
示例，以及空、过窄组合。高空结果和 141 组完全覆盖关系说明多个辅助标签只是重复
表达同一旧候选，未提供足够正交的信息增益。

## 9. 自动 Gate

```text
FAIL
```

Blocking：

- `compound_candidate_copied_to_form`：5 个候选。

Warnings：

- `low_support_presentation_form`：28 个；
- `many_empty_filter_combinations`：80.84%；
- `facet_vocabulary_inflation`：28/28/29。

其他确认：

- 31 候选覆盖率 100%；
- Entity → Object Type 精确泄漏计数 0；
- Object Type 与冻结 Domain 同名计数 0；
- Use Context 未强制填满，空值率 35.42%；
- Domain Draft Hash 未改变；
- Runtime 输入不包含 Silver Reference；
- Schema 没有静默截断。

自动 Gate 仍偏保守：它只对精确同名泄漏做阻塞，不能充分识别近义换名、粒度混杂和
跨分面信息重复。因此最终判断不能只依赖 Gate。

## 10. 两轮窄修复与恢复

### Run #15

- 完成 31 候选拆解；主响应两个格式错误，经一次独立 Repair 修复；
- 词表原响应分别输出 28/28/29 个节点；
- 旧 Schema 每分面固定 `max_length=20`，构成隐形 Top-K；
- 中断正在进行的 Repair，保留原响应，不删除节点。

### 第一轮窄修复：Run #16

- 将词表容量改为由 31 个源候选推导的结构上限：Form 31、Object/Context 62；
- 零调用复用拆解，直接解析 Run #15 的原始词表响应；
- 78 个单支持 stable 节点通过逐字段审计降为 draft；
- Assignment Batch 1 主响应和 Repair 只有同一证据字符串超过 180 字符的问题。

### 第二轮窄修复：Run #17

- Evidence 技术容量放宽至 500，不截断文本；
- 零调用复用拆解、词表和 Run #16 Batch 1 Repair 原响应；
- 只调用 Batch 2～4，三批均一次通过；
- 完成筛选模拟和 Gate。

两轮修复均没有重新定义四分面、修改 Domain、删除候选或重跑 128 条。附件允许的两轮
窄修复额度已经用完。

## 11. Token、耗时、Repair 和 Retry

| 调用 | Prompt Tokens | Completion Tokens | Total Tokens | Provider 秒 | 结果 |
|---|---:|---:|---:|---:|---|
| Run #15 Decomposition | 21,838 | 11,877 | 33,715 | 78.466 | 进入 Repair |
| Run #15 Decomposition Repair | 12,224 | 11,817 | 24,041 | 73.757 | 完成 |
| Run #15 Vocabulary | 9,438 | 14,216 | 23,654 | 94.186 | 原响应保留 |
| Run #15 Vocabulary Repair | unknown | unknown | unknown | unknown | 主动中断，不采用 |
| Run #16 Assignment B1 | 12,825 | 6,368 | 19,193 | 40.975 | 进入 Repair |
| Run #16 Assignment B1 Repair | 6,915 | 6,347 | 13,262 | 41.796 | 格式仍超长，原响应后续复用 |
| Run #17 Assignment B2 | 12,807 | 5,081 | 17,888 | 34.436 | 完成 |
| Run #17 Assignment B3 | 12,803 | 4,439 | 17,242 | 30.362 | 完成 |
| Run #17 Assignment B4 | 12,516 | 4,846 | 17,362 | 34.482 | 完成 |

已返回 usage 的调用合计：

```text
Prompt Tokens      101,366
Completion Tokens   64,991
Total Tokens       166,357
Provider seconds   428.460
Known responses      8
Interrupted request  1（Provider 未返回 usage）
Reasoning tokens      0
```

Run #17 自身新增调用只有 B2～B4，共 52,492 Tokens、99.280 秒。所有已完成阶段均可
恢复；Run #15/#16 原样保留为诊断历史，没有伪装成成功 Run。

## 12. 测试

实现覆盖：

- 旧字段与新字段版本隔离；
- compound 候选多分面拆解；
- Form/Object/Context 路由；
- Entity → Object Type Gate；
- Context 可空；
- 标签预算和无静默截断；
- stable/draft/rejected 约束；
- 单支持 stable 的可审计降级；
- Domain Hash 不可变；
- Runtime/Silver 隔离；
- 同分面 OR、跨分面 AND；
- Reviewer Bundle 输入边界；
- 窄恢复与原响应复用。

当前全量结果：

```text
172 passed
1 existing Starlette/httpx deprecation warning
```

## 13. 独立 Reviewer

```text
FAIL
```

Reviewer 只读取 ADR、报告、代码、测试、Run #17 派生产物和 Reviewer Bundle；没有
修改代码/数据库、调用 Provider、读取 Silver，或把历史 Candidate Decision 当作
正确性证据。

### Evidence

- `checkpoint/v3.9-failed` 与 `b65a866` 一致，新分支是该 Commit 的后代；
- ADR 准确废弃单一 Content Type 假设；
- 四个分面在工程 Schema 中确实分离，只有 Domain 保持两级树；
- 没有真实标签名称硬编码或隐形产品 Top-K；31/62/62 是源候选推导容量；
- 标签预算严格执行，Use Context 在 17/48 条中为空；
- 组合筛选来自真实 48 条赋值；783/633/111 等数字可复现；
- 报告 Token 和耗时与 Run #15/#16/#17 Audit 求和一致。

### Blocking Findings

1. 31/31 候选同时生成 Form/Object/Context，且 unresolved、discarded 均为 0，属于
   机械填满而非真实语义拆解；
2. 31 个来源扩张成 85 个节点，78 个只有单条支持、rejected 为 0，缺少全局归并；
3. Object Type 混入学习路径、任务流程、知识体系、主题观点、个人经验等非对象概念，
   多个斜杠节点还混合对象、方法、趋势和协议；
4. 只有 `pf_17 观点评论` 显示较强跨域复用，且它占 14/48；其余 Form 尚未证明
   兄弟边界和长期价值；
5. 80.84% 两分面组合为空，141 组跨分面完全共现，四分面没有足够正交信息增益；
6. 问题发生在候选拆解和词表归并层，扩大到 128 条只会放大碎片化与成本。

### Non-blocking Concerns

- 自动 Gate 的精确同名检查不能识别近义换名、斜杠混合和粒度不一致；
- Entity 泄漏检查面偏窄，因为拆解器只提取了 1 个 Entity；
- `stable` 的最低硬条件仍偏弱，跨 Domain/Object 目前主要形成 warning；
- 分支封存和推送由主 Agent 在 Reviewer 完成后执行。

### Required Fixes

Reviewer 建议未来另立、经用户批准的新 Checkpoint：停止逐候选机械拆分，改为跨候选
全局归并，并允许大量 null/discarded/rejected；为三个词表增加兄弟边界、粒度、
singleton/rejected、膨胀率和跨分面可预测性检查；修复后只重跑相同 36～48 条样本。

这些不属于本轮允许的两次窄修复，当前不执行。

## 14. 当前停止位置

主 Agent、自动 Gate 和独立 Reviewer 的一致结论为：

```text
FAIL
```

四分面数据结构和查询语义本身可以实现，但“从 31 个旧复合候选直接拆解并逐成分建
词表”的算法没有产生可用元数据：它强迫填满三个新分面、几乎不拒绝、保留大量近义
节点，并使 80.84% 的两分面组合为空。

因此当前架构不具备进入 128 条全量验证或 Run B/C 的条件。本轮完成独立复核、报告
封存、提交和推送后停止。
