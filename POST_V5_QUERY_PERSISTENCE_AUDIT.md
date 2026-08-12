# Shiliu Query / Run / Trace / Evidence Persistence Audit

当前持久化边界并不统一：`/search` 保存检索 Trace，`/ask` 的完整问答主要只存在于进程内存，`/research` 则是完整的 durable workflow。

本文中的“永久保存”指写入 SQLite、能够跨页面刷新和服务重启存在；不代表永不可删除。

| 页面 | Query | run_id / trace_id | Trace | Evidence | Result | Feedback |
|---|---|---|---|---|---|---|
| `/search` | SQLite 保存 | `trace_id` 保存 | 保存精简 Trace | 保存命中 ID/分数，不保存完整展示文本 | 完整结果仅 response | 没有 |
| `/ask` Fast | Ask 层不保存；子搜索 Query 会保存 | Ask `run_id` 仅内存 | Ask Trace 仅内存；子搜索 Trace 保存 | 最终 Citation 仅 response；子检索命中保存 | Answer 仅 response/内存 | 没有 |
| `/ask` Deep | Ask 层不保存；执行过的搜索 Query 会保存 | Ask `run_id` 仅内存 | Agent Trace 仅内存；子搜索 Trace 保存 | 最终 Citation、读过的窗口仅内存；子检索命中保存 | Answer 仅 response/内存 | 没有 |
| `/research` | 保存 | task/goal/attempt/trace/result 等 ID 均保存 | 保存 | 保存完整 evidence identity/use/provenance/validation | 保存状态及回答 artifact | 保存为 event + receipt |

## `/search`

永久保存到 SQLite：

- 原始 Query、normalized Query
- mode、scope、filters、top-k
- `trace_id`
- router 决策、实际执行模式、fallback
- 索引版本、模型版本、各阶段耗时
- lexical/dense 候选数量
- 原始命中的 `unit_id`、rank、score
- Product presentation：
  - 返回的视频 ID
  - 时间窗口起止点
  - jump time
  - chunk IDs
  - chapter title
  - grouping/anchor/chapter 指标

对应表：

- `retrieval_search_traces`
- `retrieval_search_presentations`

不会永久保存：

- 页面返回的完整视频卡片 JSON
- 标题、UP 主、封面等完整结果快照
- `match_excerpt`
- 完整字幕摘录
- chapter summary
- `corpus_context`
- `result_contributions`
- warnings
- 用户当时看到的完整排序页面

这些只在 HTTP response 和当前 DOM 中。之后通过 Trace 能恢复“当时命中了哪些 unit/video/window”，但不能精确恢复当时整份 UI response。

代码位置：

- `src/shiliu/retrieval/orchestrator.py`
- `src/shiliu/retrieval/product_search.py`

另外，Query 和筛选条件会被写入浏览器地址栏，例如 `/search?q=...`。这会进入浏览器导航历史，但不属于 Shiliu 的服务端结果存档。

## `/ask` Fast

Ask 层不会写 SQLite。

仅存在于 Python 进程内存和 HTTP response：

- `ask_run_...` run_id
- Ask 原始 Query 与 Ask mode
- Query Analysis 结果和 rewrites
- Ask 总体 Trace
- Query-analysis usage、answer usage
- 最终 Evidence/Citations
- Answer blocks
- limitations
- termination reason
- repair/stale/context 指标

内存存储为：

```python
self._traces[run_id] = trace
```

服务一旦重启，`GET /api/ask/traces/{run_id}` 就会返回 404。

但 Fast 内部执行的每一次 Search 会生成永久的 Search Trace。因此会持久化：

- 实际送入 retrieval 的每条 Query
- 每次 `search_trace_id`
- 检索计划、过滤条件、索引身份
- 命中 unit ID、rank、score
- Product presentation summary

缺失的关键关联是：

```text
Ask run_id
→ 哪些 child search_trace_id
→ 最终 Answer / Citation
```

这个整体关系只在 Ask 内存 Trace 中。虽然子搜索 Query 留在数据库里，但数据库不会标明“它属于哪个 Ask”。

Ask 页面同样把问题写进 `/ask?q=...` 浏览器 URL，因此刷新后输入问题仍可能存在，但 Answer、Citation 和 Ask run_id 不会恢复。

## `/ask` Deep

Deep 与 Fast 的持久化边界基本相同，但丢失的内存内容更多。

只在内存 Trace 中：

- `ask_run_...`
- Agent 每轮 decision
- navigation / transcript search / window read 事件
- open/resolved questions
- visited videos / segments
- repeated-action guard
- budgets、deadlines
- Provider usage
- stale/error observations
- 最终 evidence span 集合
- Answer、Citation、limitations
- Deep termination reason

Deep 中调用 Product Search 的步骤仍会留下永久 Search Trace，但：

- Agent action 不永久保存
- “为何发起这次搜索”不永久保存
- transcript window read 不永久保存
- 子搜索与 Ask run_id 的关系不永久保存
- 最终采用或舍弃哪些 Evidence 不永久保存
- 最终 Answer 不永久保存

底层字幕 artifact 本身仍永久存在；丢失的是“这次 Ask 如何选择和使用它们”。

代码位置：

- `src/shiliu/ask/service.py`
- `src/shiliu/ask/deep/service.py`

## `/research`

`/research` 是真正的 durable runtime。页面刷新、Web 重启甚至中途恢复，都以 SQLite 为准。

永久保存的 Query/目标：

- `task_id`
- objective
- success constraints
- evidence policy
- goal revision
- parent/derived task relationships

永久保存的运行身份：

- `task_id`
- `goal_id`
- `attempt_id`
- `trace_id`
- `checkpoint_id`
- `result_id`
- action ID
- artifact ID
- command ID / receipt ID
- side-effect ID

它没有一个统一叫 `run_id` 的字段；`attempt_id + trace_id` 相当于一次运行身份。

永久保存的 Trace：

- Task/Attempt 状态
- checkpoints 与完整 state payload
- ordered events
- command receipts
- inner actions及其 request/observation/error
- retrieval trace 引用
- side-effect reservation/result
- outer audit
- constraint observations
- continuation decision
- termination metadata

永久保存的 Evidence：

- Evidence identity
- 视频、artifact/version、timeline run
- segment IDs 和时间范围
- quote hash 与 quote preview
- Evidence use
- Retrieval provenance
- Search trace ID、rank、method、index identity
- Current/stale/missing/error validation
- Evidence 与最终 artifact/fact 的关系

永久保存的 Result：

`research_results` 保存：

- answer status
- termination reason
- failure class
- reason detail
- terminal 状态

实际回答内容主要保存在 `research_provisional_artifacts`：

- answer blocks JSON
- limitations JSON
- evidence IDs/use IDs
- validation observation IDs
- generation/validation policy
- artifact hash

如果继续进入 Knowledge Workspace，还会保存：

- Knowledge candidates
- Review decisions
- Grounded facts 与 revisions
- Knowledge artifact revisions
- Topic pages 与 revision history
- WorkspaceRecord immutable history

核心 schema 位于 `src/shiliu/research/schema.py`。

Research Feedback 也会永久保存，但只适用于 Research Knowledge：

- Feedback 内容写为 `research_events`
- 幂等执行记录写为 `research_command_receipts`
- 保存 target、decision、reason、note、principal
- 权限明确为 `advisory_feedback_only`
- 不会因为反馈自动改写知识

实现位于 `src/shiliu/research/product_closeout.py`。

只存在于 Research UI response 的主要是：

- 聚合后的 Product projection
- 各类 count/status summary
- 导航关系和推荐操作
- 当前 loading/polling 状态
- 为页面展示拼装的 explanation

它们通常能由永久记录重新计算，但不会作为一份完整 UI JSON 快照再次保存。

## 总结

当前最重要的持久化边界是：

- Search 可审计，但不能完整重放当时的 UI。
- Ask 的最终问答与顶层 lineage 不可跨服务重启恢复。
- Research 具备完整 durable lineage。
