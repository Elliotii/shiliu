# 拾流 V3 Retrieval Version Brief

> 文件角色：本文件是主 Session 对 **V3 Retrieval Version Session** 的正式版本授权与边界说明。  
> 本文件负责定义 V3 为什么做、必须完成什么、明确不做什么、如何证明完成，以及什么情况必须升级回主 Session。  
> 具体本地仓库状态、文件结构、数据库 Schema、实现方案与 Codex 执行计划，由 V3 Version Session 在当前项目中核查和维护。

---

# 1. Version Identity

## 1.1 Version Name

```text
Shiliu V3 — Searchable Evidence Library
拾流 V3 —— 可检索、可定位证据的内容库
```

## 1.2 Version Status

```text
Status: Authorized for Version Planning and Implementation
状态：已授权进入版本核查、规划与实现
```

## 1.3 Target Form

V3 的目标是：

```text
Portfolio-grade MVP
作品集级最小完整版本
```

V3 需要形成真实、可演示、可评测、可解释的 Retrieval 闭环，但不追求生产级搜索平台、大规模 Benchmark 或全面产品成熟度。

## 1.4 Timebox

```text
Target Budget: 18–24 effective hours
目标预算：18–24 个有效开发小时

Expected Calendar Time:
约 1.5–2.5 天
```

时间预算包含：

- 本地事实核查；
- 数据与索引设计；
- Codex 实现与返工；
- 基础前端联调；
- 最小 Retrieval Eval；
- 版本文档和 Closeout。

时间预算不包含后续 V3.5 的 Grounded RAG、Notes-to-Action 或 Agent 开发。

---

# 2. Version Mission

V3 的唯一核心任务是：

> **让拾流现有的视频、摘要、字幕和用户笔记能够被准确检索，并能定位到原始字幕的时间戳证据；通过小型离线 Eval 比较关键词、语义和混合检索方案，证明技术选择的实际效果。**

V3 解决的用户问题是：

```text
我记得收藏过某个主题、工具、项目或观点，
但现在无法快速找到对应视频，
也无法定位它在视频中的具体位置。
```

典型示例：

```text
“找出我收藏过的 Harness 相关内容。”

“哪些视频讨论了 Agent Memory 的上下文压缩？”

“最近收藏但还没看的 LangGraph 视频有哪些？”

“哪条视频在什么时间点提到了某个 GitHub 项目？”
```

---

# 3. Product and Career Rationale

## 3.1 Product Rationale

当前拾流已经能够持续摄取并处理内容，但内容主要以独立视频卡片、摘要和笔记存在。随着视频数量增长，用户无法稳定完成：

- 按主题找回内容；
- 按专有名词或项目名定位内容；
- 跨标题和字幕检索语义相关内容；
- 按收藏时间、阅读状态或收藏夹缩小范围；
- 回到视频中的具体证据位置。

因此，Retrieval 是现有内容资产被进一步利用的必要基础。

## 3.2 Career Rationale

V3 应自然展示以下 AI 应用研发能力：

```text
Information Retrieval
信息检索

Lexical Search / BM25
关键词检索 / BM25

Dense Retrieval
稠密语义检索

Hybrid Search
混合检索

Query Understanding
查询理解

Metadata Filtering
元数据过滤

Multi-granularity Chunking
多粒度切分

Timestamp Provenance
时间戳来源追踪

Incremental Indexing
增量索引

Retrieval Eval
检索评测
```

V3 的技术价值不来自简单接入向量数据库，而来自：

- 建立明确 Baseline；
- 根据真实查询比较不同方案；
- 保留证据和时间戳；
- 说明为什么选择当前架构；
- 用 Eval、延迟和失败案例证明取舍。

---

# 4. Confirmed High-level Baseline

主 Session 当前确认以下高层事实：

- 拾流已经具备 B 站收藏夹同步能力；
- 已有官方字幕输入；
- 已有无字幕视频的 ASR 输入；
- 已有字幕整理和结构化摘要；
- 已有本地持久化；
- 已有 Web 浏览界面；
- 已有阅读状态、Mark、归档、忽略、恢复和用户笔记；
- 已有失败状态和部分重试能力；
- 当前没有正式产品化的 Search Service；
- 当前没有正式 Dense Index；
- 当前没有正式 Hybrid Retrieval；
- 当前没有正式 Query Understanding；
- 当前没有产品级字幕 Chunk Retrieval；
- 当前没有正式 Retrieval Eval；
- Taxonomy Research 已经收口；
- Draft A 是冻结研究资产，不是当前产品分类；
- M6 未获得产品授权；
- Taxonomy Research 中的 Workflow、Resume、Reviewer 等资产不自动等于产品级 Task Runtime。

上述内容只是高层已知事实。

> 具体项目路径、Git 状态、文件结构、数据库表、字幕时间戳 Schema、笔记存储方式、API、测试、前端结构和可复用代码，必须由 V3 Version Session 通过 Codex 在当前本地仓库中核查。

---

# 5. Required Scope

Required Scope 中的全部能力必须完成并提供验收证据，V3 才能进入 Closeout。

---

## 5.1 Retrieval Data Model

### 5.1.1 Video-level Search Unit

系统必须支持对视频整体内容进行检索。

候选输入包括：

- 标题；
- UP 主；
- 简介；
- 一句话总结；
- 核心观点；
- 完整总结；
- 整理原文；
- 用户笔记；
- 收藏夹；
- 收藏时间；
- 阅读状态。

具体哪些字段合并进入 Video-level Index，由 V3 Version Session 根据本地数据和 Eval 决定。

### 5.1.2 Transcript Chunk-level Search Unit

系统必须支持对字幕片段进行检索，并能返回：

```text
video_id
chunk_id
source_type
start_time
end_time
text
```

Chunk 第一版只需要合理、稳定、可复现，不要求实现理论最优切分。

可接受的第一版策略包括：

```text
字幕时间段聚合
+
字符数或 Token 上限
+
少量 Overlap
```

### 5.1.3 Stable Provenance

每个可检索单元必须能够追溯到原始内容。

至少需要稳定表达：

```text
video_id
chunk_id（Chunk-level）
source_type
start_time（如适用）
end_time（如适用）
source_text
```

### 5.1.4 Index Version and Rebuild

索引必须具备：

- 明确的 Index Version；
- 可重复执行的索引构建或重建方式；
- 新视频进入后的增量更新；
- 视频删除、重新处理或字幕变化后的更新方式；
- 不产生明显重复索引记录。

---

## 5.2 Lexical Retrieval Baseline

必须实现基于 SQLite FTS5 / BM25 或等价轻量方案的关键词检索 Baseline。

Baseline 至少需要证明：

- 专有名词可以被准确查找；
- 项目名、模型名、框架名可以检索；
- 标题、摘要、字幕和笔记中的命中可以返回；
- 支持基础 Metadata Filter；
- 返回命中片段或匹配解释。

FTS5 / BM25 是 V3 Eval 的必要基线，不得直接跳过关键词检索，只展示 Dense Retrieval。

---

## 5.3 Dense Retrieval

必须实现 Dense Retrieval，用于处理：

- 同义表达；
- 语义改写；
- 用户未使用原文关键词的主题查询；
- 中文口语与技术表达之间的差异。

具体实现可选：

```text
FAISS
sqlite-vec
其他适合 local-first 小规模数据的轻量实现
```

但必须通过明确的 Retriever / Index Adapter 隔离具体存储实现，避免业务代码直接依赖单一向量库。

不要求引入：

- Milvus；
- Weaviate；
- Elasticsearch 集群；
- 分布式向量数据库。

---

## 5.4 Hybrid Retrieval

必须实现：

```text
Lexical Retrieval
+
Dense Retrieval
→ Rank Fusion
→ Unified Search Results
```

默认候选融合方式：

```text
RRF
Reciprocal Rank Fusion
倒数排名融合
```

V3 必须能够独立运行并比较：

```text
Lexical
Dense
Hybrid
```

不能只实现 Hybrid 而失去可比较 Baseline。

---

## 5.5 Query Understanding

必须建立一个最小 Query Understanding 层。

至少支持：

### 5.5.1 Semantic Query Extraction

从自然语言中提取用于检索的核心语义查询。

### 5.5.2 Metadata Filter Extraction

根据本地已有 Metadata，至少支持其中适用的若干项：

- 收藏时间；
- 阅读状态；
- 收藏夹；
- UP 主；
- Mark 状态。

### 5.5.3 Retrieval-level Routing

系统应能够判断或允许指定：

```text
Video-level
Transcript Chunk-level
```

### 5.5.4 Query Rewrite

针对口语化、冗长或带上下文条件的查询，生成更适合检索的 Query。

### 5.5.5 Safe Fallback

当 Query Understanding 的模型调用失败、Schema 不合法或超时时：

- 不得阻断基础搜索；
- 应退化为原始 Query + 可确定的过滤条件；
- 应记录 Trace 或错误状态。

Query Understanding 必须使用 Structured Output / 明确 Schema，而不是依赖不可解析的自由文本。

---

## 5.6 Metadata Filtering

搜索至少需要根据本地实际可用字段支持部分组合过滤。

优先候选：

```text
favorite_folder
favorite_time
reading_state
mark_state
creator
```

具体字段必须以本地事实为准。

过滤不能依赖尚未产品化的：

```text
domain_ids
form_ids
object_type_ids
```

---

## 5.7 Timestamp Evidence

Transcript Chunk Search Hit 必须能够：

- 返回字幕原文片段；
- 返回起止时间；
- 返回视频身份；
- 区分字幕来源；
- 提供回到原视频对应时间点的能力或可构造链接；
- 保留检索方法和得分信息。

时间戳证据是 V3 区别于普通视频级向量检索的核心能力。

如果本地事实证明时间戳整体不可用，必须触发 Escalation，不能静默删除该目标。

---

## 5.8 Basic Product Surface

V3 必须在现有 Web 中提供最小可用搜索界面。

至少包括：

- 搜索输入；
- 结果列表；
- Video-level 与 Chunk-level 结果的可理解展示；
- 命中片段；
- 时间戳；
- 基础过滤；
- 无结果状态；
- 错误或降级状态；
- 返回原视频或视频详情页的入口。

不要求：

- 完整搜索产品设计；
- 复杂动效；
- 高级筛选器；
- 面向多用户的权限系统。

---

## 5.9 Minimal Retrieval Eval

必须建立一套小型离线 Query Set。

### 5.9.1 Query Count

```text
Target: 20–30 high-quality queries
目标：20–30 条高质量 Query
```

### 5.9.2 Query Types

至少覆盖：

```text
Exact Entity
精确实体

Semantic Topic
语义主题

Evidence Lookup
证据定位

Temporal Query
时间条件查询

Metadata Filter Query
元数据过滤查询
```

### 5.9.3 Labels

每条 Query 至少标注：

- Relevant Video IDs；
- 对适合的部分 Query 标注 Relevant Chunk IDs。

首版不要求所有 Query 都进行完整 Chunk-level Gold 标注。

### 5.9.4 Compared Systems

至少比较：

```text
FTS5 / BM25
Dense Retrieval
Hybrid Retrieval
```

### 5.9.5 Required Metrics

至少输出：

```text
Recall@10
MRR 或 Hit Rate
P95 Latency
```

可以附加：

- Recall@5；
- nDCG；
- Zero-result Rate；
- Embedding / Provider Cost；
- Index Size。

### 5.9.6 Failure Analysis

Eval 必须记录若干代表性失败：

- BM25 找不到但 Dense 找到；
- Dense 语义相近但误召回；
- Hybrid 没有提升的 Query；
- 时间戳定位不准确；
- Metadata Filter 解析错误；
- ASR 或字幕文本导致的检索问题。

不要求在 V3 中修复所有失败，但必须如实记录。

---

## 5.10 Basic Trace and Test

至少记录或测试：

- Query 原文；
- Query Understanding 结果；
- 检索模式；
-过滤条件；
-返回候选；
-耗时；
-错误或 fallback；
-索引版本。

测试至少覆盖：

- FTS5 Search；
- Dense Search；
- Hybrid Fusion；
- Metadata Filter；
- Chunk Provenance；
- Incremental Index；
- Query Understanding fallback；
- 视频删除或重建后的索引一致性。

---

# 6. Optional Scope

只有同时满足以下条件时，才能进入 Optional Scope：

```text
Required Scope 已全部完成
+
最小 Eval 已运行
+
不存在阻塞性 Bug
+
仍在版本时间预算内
```

Optional Scope 包括：

## 6.1 Chapter-level Retrieval

仅当本地已有章节质量和时间戳映射足够可复用时实现。

不得为了 Chapter-level Retrieval 大规模重构现有 Pipeline。

## 6.2 Reranker Ablation

可以实验：

```text
Hybrid Candidates
→ Reranker
→ Final Results
```

只有 Eval 显示明确增益，才建议保留为正式能力。

## 6.3 Search-result Clustering

可以针对单次搜索结果做临时聚类与 LLM 主题命名。

不得将其升级为正式 Taxonomy。

## 6.4 Dynamic Topics Experiment

可以对收藏夹或时间窗口生成临时主题。

仅作为实验资产，不要求永久 Assignment、节点生命周期或全量迁移。

## 6.5 Simple Related Content

可以复用 Dense Similarity 或 Hybrid Signal 提供简单关联内容。

不得扩张为完整推荐系统。

---

# 7. Explicit Out of Scope

以下内容不属于 V3，除非主 Session重新授权。

## 7.1 Product Features

- Grounded QA / 生成式 RAG 回答；
- 跨视频综合报告；
- Notes-to-Action；
- 学习清单；
- GitHub 项目 Review；
- Reminder；
- 个性化推荐系统；
- 完整内容关系图；
- 思维导图。

## 7.2 Agent Features

- Agent；
- Planning / Replanning；
- Tool Registry；
- Agent Task Runtime；
- Multi-Agent；
- Reviewer Subagent；
- Agent Memory；
- MCP。

## 7.3 Taxonomy

- 恢复 M6；
- Draft B；
- 131 条全量 Assignment；
- 正式 Domain Taxonomy；
- 分类树发布；
- 分类节点生命周期；
- 为检索强制加入 Domain / Form / Object 等完整分类字段。

## 7.4 Infrastructure

- Milvus；
- Weaviate；
- Elasticsearch 集群；
- Neo4j；
- GraphRAG；
- Redis 队列；
- Kafka；
- Kubernetes；
- 分布式系统；
- 多租户；
- 高并发平台。

## 7.5 Unrelated Refactoring

- 全仓代码整理；
- 与 V3 无关的前端重写；
- 通用 Search Framework；
- 通用 Agent Framework；
- 为未来版本提前搭建完整基础设施；
- ASR 专项术语纠错系统；
- 与 Retrieval 无直接关系的 Provider 重构。

---

# 8. Cross-version Constraints

V3 需要为后续版本保留最小兼容性，但不得为了未来进行过度设计。

## 8.1 Evidence Compatibility

Search Hit 应尽量稳定表达：

```text
video_id
chunk_id
source_type
start_time
end_time
text
score
retrieval_method
index_version
```

这些字段未来可以被 V3.5 Evidence Bundle 和 V4 Agent Tool 复用。

V3 不需要现在设计完整 Evidence Bundle 或 Agent Tool Schema。

## 8.2 Incremental Compatibility

V3 必须支持或清楚定义：

- 新视频的增量索引；
- 视频删除后的索引清理；
- 字幕重新生成后的受影响 Chunk 重建；
- 摘要或笔记变化后的更新；
- 索引版本变化后的重建方式。

## 8.3 Local-first Boundary

- 主数据库优先继续使用 SQLite；
- 不引入需要独立集群维护的基础设施；
- 向量实现通过 Adapter 隔离；
- 能够在单用户本地环境中运行和重建。

## 8.4 Taxonomy Independence

Retrieval 必须在没有正式 Taxonomy 的情况下成立。

可以使用：

- 视频 Metadata；
-用户状态；
-收藏夹；
-UP 主；
-Entity Alias；
-用户明确标签。

不能依赖：

- Draft A；
-未发布 Domain；
-未完成的 Controlled Facets；
-全量分类 Assignment。

## 8.5 V3.5 Compatibility

V3 的结果应能够支持后续：

```text
Grounded Answer
Related Content
Notes-to-Action
Evidence-linked Artifact
```

但 V3 不实现这些功能。

## 8.6 V4 Compatibility

未来 Agent 应能够把 Search 作为工具使用。

因此 V3 Search 接口应尽量：

- 输入输出结构明确；
-错误状态可识别；
-结果来源可追踪；
-支持限制 Top-K；
-支持基础过滤；
-不要求调用前端逻辑。

但不要求现在建设 Agent Tool Registry。

---

# 9. Local State Discovery Requirement

V3 Version Session 是本版本本地项目状态的直接负责人。

实现前必须通过 Codex 完成一次：

```text
Read-only Local Discovery
只读本地核查
```

## 9.1 Time Budget

```text
30–60 minutes
最多一个 Codex 集中核查轮次
```

## 9.2 Required Checks

只核查与 V3 直接相关的事实：

1. 当前项目路径、Git 分支、未提交修改；
2. 启动、测试和数据库位置；
3. 视频、字幕、ASR、摘要、章节和笔记的真实 Schema；
4. 字幕时间戳是否存在及保存粒度；
5. Video ID、Subtitle ID、Note ID 的稳定性；
6. 当前 API 与前端结构；
7. 当前是否已有任何 Search / Index 基础；
8. 新视频处理完成后的可挂载点；
9. 视频删除、忽略和重新处理流程；
10. 可复用的 Trace、Retry、Resume、Eval 资产；
11. Taxonomy Research 代码与产品代码的边界；
12. 会阻塞 V3 或显著影响 V3.5 / V4 的技术债。

## 9.3 Not Required

本地核查不得扩张为：

- 全仓源码审计；
- 全部技术债清理；
- ASR 质量研究；
- Taxonomy 历史复盘；
- 完整后续 Agent 数据模型设计；
- 无关前端体验分析；
- 生产级安全或性能审计。

## 9.4 Local Truth Rule

代码和运行事实的优先级为：

```text
Current repository, database, tests and runtime evidence
当前仓库、数据库、测试和运行证据
>
Old capability documents
旧能力文档
>
Main Session's high-level assumptions
主 Session 高层假设
```

如果本地事实与本 Brief 的 Mission、Required Scope 或跨版本约束发生实质冲突，必须触发 Escalation。

---

# 10. Acceptance Evidence

V3 Version Session 声明版本完成时，必须提供以下证据。

## 10.1 Functional Demonstrations

至少提供以下可复现示例：

1. 一个精确实体或专有名词查询；
2. 一个语义改写查询；
3. 一个带时间或阅读状态过滤的查询；
4. 一个字幕 Chunk 时间戳定位；
5. 一个新增视频或内容变化后的增量索引；
6. 一个 Query Understanding 失败后的 fallback；
7. 一个无结果或证据不足的正常状态。

## 10.2 Eval Table

至少提供：

| System | Recall@10 | MRR / Hit Rate | P95 Latency | Notes |
|---|---:|---:|---:|---|
| FTS5 / BM25 |  |  |  |  |
| Dense |  |  |  |  |
| Hybrid |  |  |  |  |

如果加入 Reranker，单独作为 Optional 方案列出。

## 10.3 Failure Cases

至少记录 3–5 个有代表性的失败案例，包含：

- Query；
-预期结果；
-实际结果；
-失败原因；
-是否在 V3 修复；
-后续建议。

## 10.4 Engineering Evidence

至少提供：

- 关键模块与职责；
-数据库 Migration 或初始化方式；
-索引构建 / 重建命令；
-增量索引触发方式；
-自动测试结果；
-搜索 API 或 Service 接口；
-错误与 fallback 行为；
-当前已知限制。

## 10.5 Product Evidence

至少提供：

- 搜索 UI 截图或演示；
-搜索结果；
-字幕证据；
-时间戳回源；
-过滤功能。

## 10.6 Closeout

必须生成：

```text
V3_CLOSEOUT.md
```

其中明确区分：

```text
Delivered
实际交付

Not Delivered
未交付

Degraded
降级实现

Deferred
推迟

Rejected
拒绝
```

版本 Session 可以声明 Engineering Complete，但最终是否 Accepted，由主 Session审阅决定。

---

# 11. Escalation Conditions

出现以下任一情况时，V3 Version Session 必须暂停受影响部分，并返回主 Session 讨论。

## 11.1 Core Evidence Risk

- 本地没有可用字幕时间戳；
- 时间戳只能通过大规模重新处理才能获得；
- 证据定位无法达到最小可用程度；
- 原始字幕与视频身份无法稳定关联。

## 11.2 Architecture Risk

- Chunk 数据模型要求大规模重写现有 Pipeline；
- 必须更换主数据库；
- 必须引入重型搜索基础设施；
- Search Schema 会显著阻碍 V3.5 Evidence 或 V4 Agent；
- 现有研究代码与产品代码冲突严重。

## 11.3 Eval Risk

- Dense Retrieval 在代表性 Query 上无明显价值；
- Hybrid 不优于 Baseline；
- Eval 结果不足以支持保留某项核心技术；
- Query Set 构建成本明显超出版本预算。

这类结果不能为了完成计划被美化或忽略。

## 11.4 Timebox Risk

- V3 核心预计超过 24 个有效小时；
- 单个问题已投入约 6–8 小时仍无稳定方案；
- 返工已经威胁 Required Scope 的完成；
- Optional Scope 开始挤占 Required Scope 和 Eval。

## 11.5 Scope Risk

- Codex 或 Version Session 建议恢复完整 Taxonomy；
-建议提前实现 Agent、Memory、MCP 或 Multi-Agent；
-建议将 V3 改造成通用知识库或通用搜索框架；
-建议进行与 V3 无关的大型重构；
-本地事实要求实质改变 Version Mission。

## 11.6 Product-direction Risk

- Retrieval 被证明不是当前数据的合理能力；
-为了保留某技术必须制造不自然的用户需求；
-某项实现主要服务技术名词，而缺少功能、Eval 或演示闭环。

一般安装问题、局部 Bug、文件命名、普通 Schema 字段和版本内部实现顺序不需要升级。

---

# 12. Stop Boundary

当以下条件全部满足时：

```text
Required Scope completed
+
Minimal Retrieval Eval completed
+
Core tests passing
+
Known limitations documented
+
V3_CLOSEOUT.md generated
```

V3 Version Session 必须：

1. 停止继续扩张；
2. 不直接开始 V3.5；
3. 不自动实现 Optional 长尾功能；
4. 将 Closeout 带回主 Session；
5. 等待主 Session 判断 V3 是否 Accepted，以及下一版本的正式 Mission。

即使 V3 提前完成，后续时间也优先用于：

- 修复阻塞性问题；
- 补充 Eval；
- 整理失败案例；
- 提升可复现性；
- 完成 Closeout。

不得擅自进入 Agent、Memory 或完整 RAG。

---

# 13. Expected V3 Deliverable

V3 完成后的拾流应能够被准确描述为：

> **一个支持 Video-level 与 Transcript Chunk-level 检索的本地视频内容库，通过 FTS5/BM25、Dense Retrieval 和 RRF Hybrid Search 查找标题、摘要、字幕与用户笔记，并返回带时间戳和来源追踪的证据；系统通过小型人工 Query Set 对不同检索方案进行离线评测，并支持增量索引、Metadata Filter、Query Understanding 和安全降级。**

V3 不应被描述为：

- 完整知识 Agent；
- 完整个人知识库；
- 完整 Taxonomy；
- 高级推荐系统；
- 生产级搜索平台；
- Multi-Agent 系统；
- 完整 Memory 系统。

---

# 14. Version Decision Summary

## Accepted

- V3 主线是 Retrieval 与 Evidence；
- FTS5 / BM25 是必要 Baseline；
- Dense Retrieval 和 Hybrid 必须可独立比较；
- 时间戳 Provenance 是核心差异化；
- Query Understanding 和 Metadata Filter 进入 Required；
- 最小 Retrieval Eval 进入 Required；
- V3 采用 local-first 轻量架构；
- V3 必须独立于正式 Taxonomy；
- V3 结束后先 Closeout，再决定 V3.5。

## Optional

- Chapter-level Retrieval；
- Reranker；
- Search-result Clustering；
- Dynamic Topics 实验；
- Simple Related Content。

## Deferred

- Grounded RAG；
- Notes-to-Action；
- Agent；
- Memory；
- Task Runtime；
- Multi-Agent；
- MCP；
-思维导图；
-完整 Related Ranking。

## Rejected for V3

- 恢复完整 Taxonomy；
- 全量分类 Assignment；
- 重型向量基础设施；
- GraphRAG；
- 通用 Search Framework；
- ASR 专项纠错；
- 与 Retrieval 无关的大型重构。

---

# 15. Authority Reminder

本文件由主 Session 提供，是 V3 产品目标和范围的当前权威来源。

```text
Main Session
决定为什么做、做什么、做到哪里，以及跨版本边界

V3 Version Session
掌握当前本地事实、制定版本内部方案、监管 Codex、完成验收

Codex
读取和修改仓库、运行测试、提供代码与运行证据
```

V3 Version Session 可以根据本地情况调整实现细节和顺序，但不能自行改变本文件的 Mission、Required Scope、Out of Scope、Stop Boundary 和跨版本方向。

Codex 可以提出建议，但建议默认只记录，不自动成为产品需求或架构决定。
