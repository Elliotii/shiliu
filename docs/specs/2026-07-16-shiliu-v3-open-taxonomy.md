# 拾流 Shiliu V3.0：开放式个人收藏分类体系发现

## Status

Approved

## Goal

为拾流增加一个独立的、语料级的开放式 Taxonomy Discovery Pipeline。

系统必须在不向发现模型提供人工分类名称的前提下，根据用户真实收藏内容自主发现：

- Content Type；
- 最多两级的稳定 Domain/Subdomain；
- Dynamic Topic；
- Entity；
- 无法可靠分类的内容。

系统通过不可变语料快照、多次独立发现、候选归并、层级校验、全量试分类、单轮结构修正和人工审核，最终发布具有稳定 ID 的 Taxonomy v1。

V3.0 是固定输入输出 Schema、固定阶段和有限模型调用驱动的确定性 Workflow，不是 Agent。

## Context and Current State

### 仓库事实

- 当前项目是本地 Python 模块化单体，版本为 `0.3.0`，见 `pyproject.toml`。
- 应用组装集中在 `src/shiliu/app.py:Application`。
- 当前数据库为 SQLite Schema Version 5，初始化和兼容迁移位于 `src/shiliu/db.py:Database.initialize()`。
- `videos` 保存视频级内容对象，`video_source_memberships` 保存视频与收藏夹的多对多关系。
- 当前 `pipeline_stages` 以 `video_id + stage_name` 为主体，只适合字幕、摘要和精修阶段，不能承载语料级 Taxonomy Run。
- 当前视频 Pipeline 已具备最多三次尝试、`retry_wait`、延迟重试和已完成阶段复用，见 `src/shiliu/pipeline.py:PipelineService`。
- 页面后台任务通过 daemon thread 执行；页面关闭不影响运行，但整个 Web 进程退出后线程不会继续，见 `src/shiliu/web.py:_start_background_sync()`。
- 定时同步通过 launchd 调用 `shiliu sync --scheduled`，见 `src/shiliu/launchd.py`。
- 当前 OpenAI-compatible Provider 使用 `/chat/completions`，以 JSON 解析和 Pydantic 完成结构校验，但未使用统一 strict JSON Schema，也未保存响应 usage，见 `src/shiliu/llm.py:OpenAICompatibleProvider`。
- 当前设置页已经支持 Base URL、API Key、模型、连接测试及 macOS Keychain。
- 当前摘要结构已经包含一句话结论、核心观点、详细总结、实体和可执行事项，定义于 `src/shiliu/domain.py:SummaryResult`。
- 当前摘要和原文使用本地 JSON/Markdown 原子落盘，见 `src/shiliu/artifacts.py:ArtifactStore`。
- 当前测试入口为 `.venv/bin/python -m pytest`，基线结果为 47 个测试通过。
- 2026-07-16 只读数据库审计结果：

```text
2 个收藏夹来源
134 条活跃收藏关系
132 个去重 BVID
68 个已物化视频
60 个已有摘要和整理原文
62 个已有有效简介
66 条收藏关系尚未物化
```

以上数量是审计时快照，不作为未来固定验收数字。

### 已确认的用户决策

- V3 使用独立的语料级 Pipeline，不复用现有 `pipeline_stages`。
- 保持本地单体，不引入微服务。
- 第一批实现只包含阶段 0 和阶段 1。
- Snapshot 冻结所选范围内的全部内容，包括 D 级未物化内容。
- Discovery 默认只使用 A/B/C 级卡片。
- D 级不参与 Discovery，但参加 Trial Assignment。
- Stored Card 保存收藏夹上下文，Discovery View 默认排除收藏夹名称。
- 快照默认只包含所选收藏夹当前仍存在的收藏关系。
- 用户行为字段不影响快照范围，也不得进入 Classification Card。
- 人工 Reference Taxonomy 和 Gold Set 不再阻塞 V3.0。
- 第一次完整真实 Discovery 前必须冻结与生产 Discovery 隔离生成的 Silver Reference v1。
- V3.0 Eval 由 Silver Agreement、reference-free Judge 和 cross-run consistency 共同组成；Silver 不得称为 Gold、Ground Truth 或真实准确率。
- Concept Search 属于 V3.0，但不阻塞最初的无搜索 Baseline。
- 长任务必须提供独立、可恢复的 Runner，不能只依赖 Web daemon thread。
- Token 或成本无法从 Provider 获取时允许保存为 `NULL/unknown`。
- 131 条规模下，人工修改 Taxonomy 后允许全量重新试分类。
- 重型 reference-free 指标和完整四组消融不阻塞基础产品路径。

## Scope

### V3.0 总体范围

V3.0 包含：

1. Anti-Contamination Contract；
2. 隔离生成的 Silver Reference 和追加式冻结机制；
3. 不可变 Corpus Snapshot；
4. Classification Card；
5. Stored Card 和 Discovery View；
6. A/B/C/D 证据等级；
7. Facet 提取；
8. 单次无搜索 Baseline；
9. Gated Concept Search 和本地 Concept KB；
10. 三次独立开放发现；
11. 候选分类归并；
12. 层级一致性校验；
13. Draft A；
14. 全量分批 Trial Assignment；
15. Taxonomy 诊断；
16. 一轮结构修正；
17. Draft B；
18. 人工审核和发布 Taxonomy v1；
19. Silver Agreement、reference-free Taxonomy Judge 和 cross-run consistency Eval；
20. 可恢复的 CLI Runner。

### 第一批实现范围

第一批实现严格限制为阶段 0/1。

#### 阶段 0

- 防污染契约；
- Runtime/Eval 代码边界；
- Silver Reference Schema；
- Silver Eval Set Schema；
- 空模板；
- 候选视频清单格式；
- Reference Version 和 Hash 规则；
- 防污染审计测试；
- 正式 Discovery 的 Silver Reference 冻结门禁设计。

#### 阶段 1

- 不可变 Corpus Snapshot；
- Classification Card；
- Stored Card；
- Discovery View；
- A/B/C/D 证据等级；
- Discovery Eligible 规则；
- 多收藏夹去重与 membership 聚合；
- 未物化 D 级视频；
- Snapshot/Card Hash；
- Snapshot 预览页面；
- 三至五张真实样例 Card 展示。

第一批实现不得调用 LLM。

## Non-goals

V3.0 明确不包含：

- Agent 或 Agent Harness；
- 对话式分类 Agent；
- BERTopic；
- Embedding 聚类；
- 向量数据库；
- 图数据库或知识图谱；
- 微服务；
- Redis、Celery 或外部任务队列；
- 通用插件系统；
- Engine 注册中心；
- 无限自动修正循环；
- 三级及以上稳定领域树；
- 新视频增量分类；
- confirmed/suggested/conflicted 标签生命周期；
- 用户修正记忆；
- Dynamic Topic 趋势检测；
- Novelty Pool；
- 长期 Taxonomy 自动演化；
- 默认读取收藏夹名称参与 Discovery；
- 将完整字幕批量送入 Discovery；
- 把 Silver Reference 称为 Gold Set、Ground Truth 或真实准确率；
- Silver Evaluator 读取生产 Discovery A/B/C、Consolidation 或 Draft 输出；
- 根据生产 Discovery 结果反向构造 Silver Reference；
- 第一批实现中的 LLM、Search、分类、试分类、发布和 Eval；
- 第一批实现中修改现有视频页面及视频业务数据。

实现不得包含任何被 Non-goals 明确排除的能力。

## Users and Key Flows

### 创建快照

```text
用户进入 Taxonomy 页面
→ 选择一个或多个当前启用的收藏夹
→ 查看内容总数、去重数量和 A/B/C/D 分布
→ 查看 Discovery Eligible 数量
→ 创建不可变 Snapshot
→ 查看 Snapshot Hash 和样例卡片
```

### 正式 Discovery 门禁

```text
Snapshot 已冻结
→ Eval 侧按 Silver Eval Protocol 运行独立 Evaluator A/B/C
→ 初标、独立复核和分歧仲裁
→ 冻结 Silver Reference Version 和 Hash
→ Workflow 才允许开始完整真实 Discovery
```

Facet Schema、Runner 和 10～20 条小样本 Spike 可以在 Silver 冻结前实施；Spike 输出不得成为 Silver Evaluator 的输入。

### 后续长任务

```text
页面创建 Run
→ 触发统一 Runner
→ Runner 读取 taxonomy_stage_runs
→ 跳过已完成且 Hash 有效的阶段
→ 从未完成阶段或批次继续
→ 页面查询运行状态
```

## Behavioral Requirements

### Snapshot 范围

默认输入为：

```text
所选收藏夹
→ 当前 removed_at IS NULL 的收藏关系
→ 按 content_key 去重
```

要求：

- 同一视频存在于多个收藏夹时只生成一张 Card；
- 各收藏夹关系保存在 membership 数组；
- 新收藏内容不进入已冻结 Snapshot；
- 摘要后续精修不修改已冻结 Card；
- 已从所有收藏夹消失的本地视频默认不进入 Snapshot；
- 归档、忽略、Mark 和阅读状态不改变 Snapshot 范围。

统一内容标识：

```text
bilibili:{bvid}:p1
```

### Classification Card 证据等级

```text
A = 标题 + 有效简介 + 有效摘要
B = 标题 + 有效摘要
C = 标题 + 有效简介
D = 只有标题或极少收藏列表元数据
```

空白简介和仅包含 `-` 的简介视为无有效简介。

有效摘要必须来自能通过当前 `SummaryResult` Schema 校验的本地摘要 JSON。损坏或缺失的摘要不得被计为有效摘要。

### Discovery Eligible

默认：

```text
A/B/C → Discovery Eligible
D     → Discovery Excluded
```

D 级仍保留在 Snapshot，后续参加 Trial Assignment，并允许返回 `insufficient_evidence`。

预览必须展示：

- 原始活跃 membership 数；
- 去重后总 Card 数；
- 合并的重复 membership 数；
- A/B/C/D 分布；
- Discovery Eligible 数；
- Discovery Excluded、Trial-only 数。

### Stored Card

Stored Card 可以包含：

- content_key
- video_id，可为空
- 标题
- UP 主
- 简介
- 一句话结论
- 核心观点
- 模型、工具和项目实体
- source_ids
- folder_names
- membership metadata
- evidence_level

不得包含：

- reading_state
- is_marked
- archived_at
- is_ignored
- 人工笔记
- 用户价值判断

### Discovery View

Snapshot 继续冻结完整 `card_json`。正式模型输入使用从冻结 Card 派生、带版本号的
Compact Discovery View；不得为压缩输入而覆盖 Snapshot #2 的既有 Card 或 Hash。

默认紧凑视图按证据等级生成：

- A/B：短 ID、标题、一句话结论、最多 3 条去重核心观点、最多 5 个实体、证据等级；
- A 级不再发送简介；
- C：短 ID、标题、最多 300 字符简介、证据等级；
- D：短 ID、标题、证据等级，只参加 Trial Assignment；
- 默认不发送 UP 主；
- 长 content_key 在调用前映射为 `C001` 一类短 ID，落盘时可逆映射；
- 使用单次声明列结构的紧凑数组/行式协议，不为每张卡重复长 JSON 字段名。

不得包含：

- source_ids
- folder_names
- membership metadata
- 用户行为字段
- Silver Reference
- Silver 标签

Stored Card 和 Discovery View 必须分别生成规范化 JSON 和 SHA-256。

### 分批 Discovery 与恢复

巨型单次 Discovery 只作为对比 Baseline，不作为正式方案扩展。正式候选流程为：

```text
Compact Discovery View
→ 每批 20～32 条局部候选发现
→ 全局候选归并
→ 最多两级 Taxonomy Draft
→ 每批 20～32 条 Trial Assignment
→ Novelty Pool
```

局部批次只发现候选 Content Type、Domain、Dynamic Topic 和 Entity，并输出简短定义与
supporting IDs；不得在局部批次生成最终完整 Taxonomy。全局 Consolidation 只读取局部候选、
定义、支持量与代表短 ID，不重新读取全部原始卡片。

Schema 首次失败后不得重放完整语料。调用必须：

1. 请求前保存 running 审计；
2. 收到模型原始内容后立即落盘；
3. 再执行 JSON 解析、Pydantic 和业务约束校验；
4. 失败时只向独立 JSON Repair 提供 raw response、validation errors 和精简 Schema；
5. 保存 Provider 返回的 usage；Provider 未返回时明确记录为 unknown。

`high thinking` 默认用于全局归并、层级检查和单轮结构修正。局部发现、Facet、Assignment
和 JSON Repair 不默认使用 high reasoning effort。

低确定度、`insufficient_evidence` 和疑似 `taxonomy_gap` 进入 Novelty Pool，仅对该小集合
执行补充诊断。V3.0 发布后，新视频只按 Published Taxonomy 增量分类；无法匹配的内容进入
Novelty Pool，达到显式阈值后才允许在后续版本触发局部 Taxonomy Evolution，不自动重跑全量
Discovery。

### 不可变性

- Snapshot 冻结后不允许修改原记录和 Card。
- 相同输入可以复用相同 Snapshot，或生成具有相同内容 Hash 的新 Snapshot；实现必须选择一种明确、可测试的策略。
- 内容发生变化时必须创建新 Snapshot。
- Card 必须保存冻结的 JSON 内容，不能只引用当前 `videos` 或可能被覆盖的摘要文件。

### 隐藏 Silver Reference

目标文件：

```text
eval/private_reference/silver_reference_taxonomy_v1.yaml
eval/private_reference/silver_eval_set_40.jsonl
eval/private_reference/silver_disagreements_v1.jsonl
eval/private_reference/silver_reference_manifest_v1.json
```

要求：

- 内容由与生产 Discovery 隔离的 Silver Evaluator 生成；
- Silver Evaluator 不得读取 Discovery A/B/C、Consolidation、Draft、Assignment 或历史分类讨论；
- 至少执行 Evaluator A 初标、Evaluator B 独立复核和 Evaluator C 分歧仲裁三个独立调用角色；
- 同一 Provider 时仍须使用独立上下文、不同输入排列和不同 Prompt 角色；
- 每次评测调用保存模型、Prompt 版本、参数、输入 Hash、输出和错误；
- 第一次完整真实 Discovery 前必须冻结；
- 冻结时保存 Hash；
- 冻结文件不得静默覆盖；
- 修改必须产生新的 Silver Reference Version；
- Runtime 不得读取该目录；
- Silver Reference 未冻结时，正式完整语料 Discovery 必须拒绝启动；
- 单元测试和少量非真实 Fixture 测试不受该门禁限制。

Silver Eval Set 目标为约 40 条，优先覆盖 16 条高证据清晰样本、10 条高证据跨领域样本、6 条 C 级样本、5 条边界或易混淆样本和 3 条 D 级/信息不足/失效/离题样本；真实语料不足时允许微调，但必须保存选择理由。

Silver 指标只能命名为 Silver Agreement 或 Silver Acceptance，不得解释为真实准确率。人工满意率和 Human Modification Rate 在 V3.0 自动评测中固定报告为 `not_evaluated`。

### Reference-free Taxonomy Judge

Judge 独立读取冻结 Taxonomy、节点定义、局部子树和代表视频，按节点或局部子树检查：父子关系、兄弟重叠、粒度一致性、类型混用、定义清晰度、代表视频支持度、过宽、过细和空节点。Judge 只生成评测报告，不得修改生产 Draft。

基础指标包括：

- Silver Content-Type Agreement；
- Silver Primary-Domain Agreement；
- Silver Subdomain Acceptance；
- Cross-run Taxonomy Stability；
- Assignment Consistency；
- Parent-Child Adequacy；
- Sibling Coherence；
- Granularity Balance；
- Entity Leakage；
- Coverage；
- Rejection Distribution。

### Stage 2A：Facet Extraction Spike

- 定义只提取事实的 Facet Schema；
- Facet 包含 main_subject、content_goal、technical_aspects、usage_context、candidate_topics 和 candidate_entities；
- Facet Extractor 不得创建正式分类名称或稳定 Taxonomy 节点；
- 在 Snapshot #2 的 Discovery Eligible 卡片中选取 10～20 条运行 Spike；
- 保存模型、Prompt 版本、参数、输入顺序、输入/输出 Hash、原始结构化输出和失败；
- Spike 用于验证 Schema、Prompt 和上下文体积，不视为完整生产 Facet 阶段。

### Stage 2B：Batched Discovery Spike

- 在 Snapshot #2 上派生 versioned Compact Discovery View，不修改冻结数据；
- 先用 48 条、每批 24 条验证两批局部候选与一次全局归并；
- D 级即使不参与候选发现，仍加入 Trial Assignment；
- 保存短 ID 映射、每批 Prompt、请求前审计、原始响应、解析结果、Repair 和 usage；
- 比较巨型 Baseline 与分批方案的输入规模、耗时、失败恢复粒度和结果结构；
- Spike 产物不得写入生产 Taxonomy 表或读取 `eval/private_reference/`；
- 参数确认后才进入完整 Discovery A/B/C 和正式可恢复 Runner。

### Checkpoint 2：Quality Gate 与最小 Run/Resume

在重新运行 48 条回归前，先落实：

- Content Type 使用独立候选结构，明确表达形式与知识领域的区别；
- 稳定节点包含临时 ID、name、definition、includes、excludes、supporting IDs、
  representative IDs、parent ID 和 node type；
- 局部 Domain 候选明确 primary/subdomain、parent hint 和长期稳定性依据；
- Consolidation 不再把“跨批出现”作为二级领域的硬性必要条件；
- 独立 Hierarchy Validator 只生成问题，不修改 Draft；
- 确定性 Quality Gate 保存 passed、blocking issues、warnings、retry stage 和指标；
- 缺失 Content Type 时只运行 Content Type Recovery，不重跑其他局部候选维度；
- Quality Gate 失败只重置指定阶段及其下游，已完成局部 Batch 保持 completed；
- `taxonomy_runs` 和 `taxonomy_stage_runs` 成为状态来源，Web/CLI 不是唯一状态；
- 已落盘原始响应在恢复时先解析；结构失败只恢复 JSON Repair，不重放语料调用。

最小 CLI：

```text
shiliu taxonomy create-run --snapshot-id 2 --limit 48 --batch-size 24
shiliu taxonomy run <run_id>
shiliu taxonomy resume <run_id>
shiliu taxonomy status <run_id>
```

正式 A/B/C 必须使用 discovery-only Run；A/B/C 内不运行全量 Trial Assignment。

### 后续 Concept Search

Search 只允许解析：

```text
这个实体、项目、模型、工具或论文是什么
```

Search 不得回答：

```text
它应该属于哪个分类
应该新建什么分类
应该如何修改 Taxonomy
```

Search 失败不得阻塞整个 Run。

### 后续结构约束

- Content Type、Domain、Dynamic Topic、Entity 必须分离；
- 稳定领域最多两级；
- 允许拒绝分类；
- 自动结构修正只允许一轮；
- 发布前所有结果均为 Draft；
- 发布时才生成稳定 Taxonomy ID。

## Proposed Approach

### 模块边界

建议新增独立包：

```text
src/shiliu/taxonomy/
```

职责包括：

- 语料构建；
- Snapshot 持久化；
- Workflow 状态；
- 后续 Discovery 和 Assignment Engine；
- 可恢复 Runner。

隐藏评测位于不可被 Runtime 导入的独立目录：

```text
eval/
```

### 第一阶段数据表

第一阶段只允许创建：

- `taxonomy_corpus_snapshots`
- `taxonomy_classification_cards`
- `taxonomy_runs`
- `taxonomy_stage_runs`

Snapshot Card 直接保存完整 `stored_card_json` 和 `discovery_view_json`，暂不建设通用内容版本系统。

### 后续输出存储

大型阶段输出使用本地 JSON 资产和 Hash；SQLite 保存索引、状态、元数据及文件位置。不得把所有大型 Discovery 输出强制塞入数据库字段。

### Provider 复用

后续模型调用默认复用现有：

- OpenAI-compatible Base URL；
- Keychain API Key；
- 正式摘要模型；
- Pydantic 校验；
- PipelineError 分类。

Provider 后续可以扩展调用 usage 返回值，但不得为了 V3 重写现有字幕和摘要调用路径。

## Alternatives Considered

### 复用 `pipeline_stages`

未采用。现有表强制依赖 `video_id`，V3 的主体是 Corpus/Run/Batch。

### 建立完整内容版本系统

第一阶段未采用。直接冻结 `card_json + hash` 已能保证可复现性，复杂内容版本系统当前没有必要。

### 默认把收藏夹名称提供给模型

未采用。收藏夹名称可能包含用户人工分类语义，污染开放发现。

### D 级参与 Discovery

未采用。低证据内容可能显著影响分类命名和结构，但仍保留用于 Trial Assignment。

### Search 先于 Baseline

未采用。先通过无搜索 Baseline 观察真实陌生实体问题，再实现门控搜索。

### Web daemon thread 作为唯一执行方式

未采用。它不能跨进程退出恢复。

## Data / API / Tool / Interface Changes

### 第一阶段数据库

新增四张 Taxonomy 表，不修改现有视频业务字段语义。

### 第一阶段页面

新增独立 Taxonomy 入口，预期能力：

- 选择收藏夹；
- 预览统计；
- 创建 Snapshot；
- 查看 Snapshot；
- 查看样例 Stored Card 与 Discovery View。

具体 URL 命名属于实现细节，但不得覆盖现有首页或设置页功能。

### 后续 CLI

后续必须提供语义等价于：

```bash
shiliu taxonomy run <run_id>
shiliu taxonomy resume <run_id>
shiliu taxonomy status <run_id>
```

第一阶段可以只保留命令边界，不要求实现不存在的 Discovery Runner。

### 隐藏 Eval 文件

实际 Silver Reference、Silver Eval Set、分歧和调用审计默认不进入源码发布包。可提交 Protocol、Schema、模板和生成器；实际冻结产物保留在本地私有目录。

## Technical Constraints

- Python 3.10+；
- SQLite；
- FastAPI；
- Pydantic；
- OpenAI-compatible API；
- 本地文件系统；
- macOS Keychain；
- 继续只监听 `127.0.0.1`；
- 第一阶段不新增第三方依赖；
- 所有 JSON Hash 使用稳定字段排序和固定编码；
- Snapshot/Card 创建不得调用网络；
- Snapshot/Card 创建不得调用 LLM；
- Runtime 不得读取隐藏 Eval 目录；Eval 可以读取冻结 Snapshot，但不得读取生产 Discovery 输出；
- 新数据库迁移必须兼容现有 Schema Version 5 数据；
- 现有字幕、ASR、同步、阅读、Mark、归档、忽略和笔记行为必须保持不变。

## Change Boundary

### 第一阶段允许修改

- `src/shiliu/db.py`：增加兼容迁移和四张 Taxonomy 表；
- `src/shiliu/app.py`：组装 Corpus/Snapshot 服务；
- 新增 `src/shiliu/taxonomy/`：仅限阶段 0/1 领域模型、Repository 和 Corpus 服务；
- `src/shiliu/web.py`：增加 Snapshot 预览和创建接口；
- `src/shiliu/templates/`：增加独立 Taxonomy 页面；
- `src/shiliu/static/`：增加该页面所需最小交互和样式；
- `eval/`：Schema、模板、契约和非运行时代码；
- `tests/`：Snapshot、Card、隔离和页面测试；
- `docs/specs/`：保存批准后的本 Spec。

### 默认不得修改

- 视频字幕和摘要 Prompt；
- `PipelineService` 核心执行逻辑；
- `SyncService`；
- Paraformer ASR；
- BilibiliAdapter；
- 阅读状态、Mark、归档、忽略和笔记语义；
- launchd 定时规则；
- 现有视频卡片展示结构；
- 当前摘要 JSON Schema。

### 需要再次批准的边界跨越

- 新增第三方依赖；
- 修改现有 `videos` 业务字段语义；
- 修改现有视频 Pipeline；
- 修改同步或 launchd 调度；
- 新建外部服务或任务队列；
- 改变现有 OpenAI-compatible 配置格式；
- 第一阶段提前实现 LLM、Search、分类或发布；
- 将隐藏 Reference 暴露给 Runtime。

## Complexity Budget

第一阶段复杂度上限：

- 一个新的 `taxonomy` 包；
- 四张新表；
- 一个 Corpus/Snapshot Service；
- 一个 Repository；
- 少量 Pydantic Schema；
- 一个独立预览页面；
- 不超过现有单体架构能力的本地实现。

第一阶段禁止：

- 通用 Workflow Framework；
- 插件注册系统；
- 任务队列；
- 新数据库；
- 新服务；
- 新 Provider SDK；
- 为未来 BERTopic/Embedding 预建实现；
- 为每个未来阶段预建独立 Service 或 Protocol；
- 与当前需求无关的重构。

任何新增抽象必须由当前阶段至少两个真实调用方证明必要。

## Error Handling and Recovery

### 第一阶段

- 未选择收藏夹：拒绝创建 Snapshot。
- 收藏夹不存在或未启用：返回明确错误。
- Snapshot 中没有活跃内容：允许预览零结果，但创建前应要求用户确认或拒绝创建；具体策略需在实施前固定。
- 摘要文件缺失或校验失败：降级为不含摘要的证据等级，不修改原视频状态。
- 单条异常数据不得导致原视频数据被修改。
- Snapshot/Card 落盘必须在事务内完成；失败不得留下半冻结 Snapshot。
- Hash 计算失败或序列化失败时不得标记 Snapshot 成功。
- 迁移失败时保留现有数据库备份，不继续创建 Snapshot。

### 后续 Runner

- 已完成且输出 Hash 有效的阶段不重跑；
- 输出文件缺失或 Hash 不匹配时不得盲目标记完成；
- retryable 错误进入有限重试；
- 非 retryable 错误进入人工处理；
- 进程退出后通过 `resume` 恢复；
- 不允许无限重试或无限自动修正。

## Acceptance Criteria

### 阶段 0

- 存在明确的 Anti-Contamination Contract。
- 存在 Silver Reference Taxonomy、Silver Eval Set、分歧和 Manifest Schema/模板。
- Runtime 代码不导入 Eval 路径。
- 未冻结 Silver Reference 时，正式完整语料 Discovery 不能启动。
- 冻结 Silver Reference 保存 Version 和 Hash，且不可静默覆盖。
- 防污染测试能够检查 Discovery 输入不含 Silver 数据，Silver 输入不含生产 Discovery 数据。

### 阶段 1

- 数据库通过兼容迁移新增且只新增四张 Taxonomy 表。
- 用户可以选择当前启用的收藏夹并预览 Snapshot。
- 预览展示 membership 总数、去重 Card 数、重复合并数、A/B/C/D 和 Discovery Eligible 数。
- Snapshot 只包含所选收藏夹中当前未移除的 membership。
- 相同视频的多个 membership 合并为一个 Card。
- 未物化视频以 D 级 Card 进入 Snapshot。
- D 级不进入默认 Discovery Corpus，但标记为后续 Trial Assignment 参与者。
- Stored Card 保存收藏夹上下文。
- Discovery View 不包含收藏夹名称和 membership metadata。
- Card 不包含阅读、Mark、归档、忽略和人工笔记字段。
- Stored Card、Discovery View 和 Snapshot 均具有可重复计算的 Hash。
- Snapshot 冻结后，修改视频或摘要不能改变旧 Snapshot。
- 第一阶段没有任何 LLM 或 Search 调用。
- 现有视频业务数据和页面行为不变。
- 验收报告包含三至五张真实 Card 及对应 Discovery View。
- 验收报告包含当时真实 A/B/C/D 和 Discovery Eligible 数量。
- 全部现有测试和新增测试通过。
- 实现不包含 Non-goals 明确排除的能力。

### V3.0 后续总体标准

- Discovery 模型未看到人工分类名称。
- Discovery 模型未看到 Silver 分类名称或 Silver 标签。
- Discovery 输入基于不可变 Snapshot。
- Content Type、Domain、Topic、Entity 分离。
- 稳定 Domain 最多两级。
- 完成三次独立 Discovery。
- 能归并语义相同但名称不同的节点。
- 有独立层级校验。
- Draft A 能进行全量 Trial Assignment。
- 支持四类拒绝原因。
- 只执行一轮自动结构修正。
- Search 只解析概念，不决定分类。
- 用户确认前不发布。
- 发布后产生稳定 Taxonomy ID。
- 长任务可从阶段或批次恢复。
- Silver Agreement 不被表述为真实准确率，人工满意率和 Human Modification Rate 标记为 `not_evaluated`。

## Verification Plan

### 已知命令

运行全部测试：

```bash
.venv/bin/python -m pytest
```

检查工作区：

```bash
git status --short
git diff --check
```

检查数据库 Schema：

```bash
sqlite3 <database> '.schema taxonomy_corpus_snapshots'
sqlite3 <database> '.schema taxonomy_classification_cards'
sqlite3 <database> '.schema taxonomy_runs'
sqlite3 <database> '.schema taxonomy_stage_runs'
```

### 第一阶段拟新增自动测试

- Schema Version 5 升级后现有数据保持不变；
- Snapshot 只读取活跃 membership；
- 已从所有收藏夹移除的内容不进入 Snapshot；
- 多收藏夹同 BVID 合并；
- 未物化视频生成 D 级 Card；
- A/B/C/D 计算；
- `-` 不算有效简介；
- D 级不属于 Discovery Eligible；
- Stored Card 包含 folder context；
- Discovery View 不包含 folder context；
- 用户状态和笔记不泄漏；
- Snapshot 冻结后保持不变；
- 相同输入 Hash 可复现；
- 摘要损坏时安全降级；
- Snapshot 创建不调用 Provider；
- Runtime 不导入 Eval；
- 页面预览和冻结接口测试。

### 手工验收证据

- 当前真实收藏夹统计截图或 JSON；
- 三至五张真实 Stored Card；
- 相同 Card 的 Discovery View；
- 字段差异说明；
- Snapshot Hash；
- Silver Eval Protocol、冻结 Manifest 和防污染契约；
- 全部测试结果。

## Risks

- 当前未物化内容较多，D 级比例可能较高。
- 摘要文件以当前活动版本指针读取，必须复制进 Card 才能保证冻结。
- 收藏夹名称可能携带人工分类语义，若错误进入 Discovery 会造成污染。
- Hidden Eval 的“不可读取”主要依靠代码和依赖边界，不能等同于操作系统级文件权限隔离。
- 任意 OpenAI-compatible Provider 对 strict JSON Schema 和 usage 的支持不同。
- 完整摘要和字幕体积较大，后续 Discovery 必须使用紧凑视图。
- Web daemon thread 无法跨应用进程退出继续，后续必须落实 Runner。
- 当前数据库采用集中式 `Database` 类，V3 Repository 必须避免继续扩大该类职责。

## Assumptions

- 第一阶段新增独立 `/taxonomy` 或语义等价页面，不把 Snapshot 操作塞入现有首页卡片。
- Snapshot 中的内容顺序只用于复现和 Hash，不代表正式分类顺序。
- 未物化视频可以使用 membership 中已有标题和 UP 主形成 D 级 Card。
- 现有摘要 JSON 通过 `SummaryResult` 校验后可作为有效摘要。
- 实际隐藏 Silver 文件默认不提交到 Git；Protocol、Schema 和空模板可以提交。
- 第一阶段不要求实现真正的 `taxonomy run/resume`，但数据库结构不得妨碍后续增加 Runner。

## Open Questions

- 阶段 3 使用哪一种 Search API，需在无搜索 Baseline 后另行确认。

阶段 0/1 的下列行为已于 2026-07-16 追加确认：

- 零内容 Snapshot 拒绝创建；
- 相同内容 Hash 复用已有 Snapshot；
- 页面默认不勾选收藏夹，由用户明确选择。
- `paused` 来源可以使用本地已保存的活跃 membership 创建 Snapshot，但不得因此恢复同步或访问 B 站。

## Stop and Escalation Conditions

后续实现遇到以下情况必须停止并请求用户决定：

- 需要新增第三方依赖；
- 需要改变现有视频数据或处理状态语义；
- 需要修改字幕、摘要、ASR、同步或 launchd；
- 第一阶段需要调用 LLM 或网络才能完成；
- 发现当前 membership 数据不足以生成稳定 `content_key`；
- 无法在不读取用户行为字段的情况下生成 Card；
- Silver/Runtime/Discovery 隔离无法通过测试；
- 数据库迁移存在丢失或覆盖现有数据的风险；
- Snapshot 无法做到事务性冻结；
- 需要建设通用任务队列或 Workflow Framework；
- 需要将 folder_names 提供给生产 Discovery；
- 实际复杂度明显超过 Complexity Budget；
- 任一 Acceptance Criterion 无法满足；
- 继续工作会跨越 Change Boundary；
- 出现需要用户接受的新产品取舍。

## Approval

用户于 2026-07-16 明确批准本 Task Spec。
