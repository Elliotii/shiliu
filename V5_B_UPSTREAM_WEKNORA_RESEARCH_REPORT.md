# 拾流 V5-B 上游 WeKnora 固定提交研究报告

```yaml
document_status: draft_for_v5_main_review
research_priority: bounded_P1
research_session: Shiliu V5-B Version Session
researched_at: 2026-08-04
official_repository: https://github.com/Tencent/WeKnora
pinned_commit: fcc4cd6a9f29a94818e481b3a604f44ce51c55e2
nearest_current_release_reviewed: v0.7.1@c64a48647cd6f7eb8b0fb020b2e8fec74ee375fb
license: MIT_with_listed_third_party_components
source_audit_completed: true
tests_reviewed: true
bounded_test_execution: 2_passed
provider_runs_performed: false
implementation_authorized: false
```

## 1. 结论先行

WeKnora 对 V5-B 的价值集中在 Topic Page 产品形态、页面版本、持久异步队列、重启恢复、链接浏览和 review UI。它不应成为拾流的 RAG/Connector/企业知识平台底座。

建议采用边界：

- `product_or_behavior_reference`：目录化 Topic Page、页面关系、历史/差异/回退、问题提示和 pending 状态；
- `reimplement_pattern`：页面乐观锁、更新与旧版本快照同事务、回退即新版本、持久 pending operation、去重键、失败计数、dead letter、启动恢复；
- `test_reference`：version conflict rollback、revision retention、stale claim recovery、dedup-key affinity、poll transition；
- `reject`：tenant/RBAC/Connector、通用 RAG 平台、GraphRAG 默认、Redis 活跃标记作为权威、对 index rebuild 失败仅记录日志后删除 pending row。

拾流仍必须把 Fact → Evidence 的逐 claim lineage 作为页面权威；WeKnora 的 document/source refs、普通 Markdown links 和 Wiki Page 不能替代 V5-A Stable Citation。

## 2. 固定身份、维护与 License

### 2.1 仓库身份

- 官方仓库：<https://github.com/Tencent/WeKnora>
- 官方 Remote：`https://github.com/Tencent/WeKnora.git`
- 固定 Commit：`fcc4cd6a9f29a94818e481b3a604f44ce51c55e2`
- Commit 时间：`2026-08-04T04:35:23Z`；主题：`fix(frontend): announce RAG wait status from a persistent live region`。
- 研究时官方 `main` / `HEAD` 指向该 Commit。
- 同时核验最近正式 Release `v0.7.1`：`c64a48647cd6f7eb8b0fb020b2e8fec74ee375fb`。本报告固定更新的 `main`，因为 Wiki queue/revision/recovery 相关实现继续在 release 后演进；不把 release tag 与本报告 Commit 混写。
- 临时稀疏检出位于产品树外，Detached HEAD 固定到上述 Commit；未 bulk-vendor。

### 2.2 License 边界

- 根 `LICENSE` 声明主项目 MIT，Copyright 2025 Tencent。
- 同一文件列出第三方组件及各自条款，包括 Apache-2.0、BSD、MIT/MIT-CMU、Python-2.0 等。
- 本轮审阅的 Go/Vue/Wiki 源码按主项目 MIT 处理，但没有复制代码或组件，因此不引入其依赖/第三方 License 面。
- 若未来复制 UI、测试或 Go 实现，必须做目标文件与依赖级复核；本报告只建议独立重实现。

## 3. 研究深度

| 项目 | 深度 | 状态 |
| --- | --- | --- |
| README、Release、License | 官方文档 | `verified` |
| Remote、HEAD、Commit、clean detached checkout | Git | `verified` |
| WikiPage / Revision / queue migrations | 类型与 DDL | `source_reviewed` |
| page create/update/revert/delete/link/stats | service/repository | `source_reviewed` |
| ingest/finalize/retry/dead-letter/recovery | service/repository/container | `source_reviewed` |
| WikiBrowser/revision/status refresh/API | Vue/TypeScript | `source_reviewed` |
| Go 与前端相关测试 | 测试源码 | `source_reviewed` |
| `wikiStatusRefresh.test.ts` | Node 无 Provider 执行 | `2_passed` |
| Go Wiki/queue 测试 | 未安装/未编译整仓 | `not_executed` |
| Provider/LLM Wiki generation | 未运行 | `not_exercised` |

## 4. Topic Page / Auto-Wiki 产品形态

`internal/types/wiki_page.go` 定义：

- PageType：`summary/entity/concept/index/synthesis/comparison`；
- PageStatus：`draft/published/archived`；
- 页面：slug、title、Markdown content、summary、aliases、folder/category/wiki path、depth/order；
- 来源：`SourceRefs`（文档级）与 `ChunkRefs`（chunk UUID）；
- 关系：`InLinks` / `OutLinks`；
- 版本：`Version`、`LastEditSource`（pipeline/agent/user/revert）、`LastEditorID`；
- revision：旧版本不可变快照，带 source/editor/version；
- optimistic update：请求携带期望 Version。

这一形态证明 Topic Page 应是稳定身份 + 可见版本 + 来源 + 关系 + review 状态，而不是每次打开即时生成的 Markdown blob。拾流要进一步收紧：PageRevision 必须保存引用的 ArtifactRevision/FactRevision ID；ChunkRef 不能替代 EvidenceIdentity + EvidenceUse + Validation。

## 5. 页面更新、版本与回退

### 5.1 原子 revision

`internal/application/repository/wiki_page.go` 的 `UpdateWithRevision` 在同一数据库事务中：

1. 以 `(page_id, version)` 唯一键写入被替换版本快照，冲突时 do-nothing；
2. 用 `WHERE id=? AND version=?` 更新页面；
3. 只有成功更新才把 version 加一；冲突/失败会恢复调用者对象中的旧 version。

该事务解决“快照存在但页面仍是旧版本”的幽灵历史，适合 V5-B 独立重实现。

### 5.2 visible change 与 metadata change 分离

`wiki_page.go` service 只在 title/content/summary/type/status/aliases 等用户可见字段变化时创建 revision 并 bump version；source refs、link rebuild 等 bookkeeping 使用 metadata update，不制造虚假内容版本。

V5-B 应采用该区分，但 EvidenceValidation/stale/conflict 观察仍应追加独立事件，不把 currentness 变化静默藏进 metadata。

### 5.3 Revert

`RevertPageToVersion` 把历史内容作为一次普通新 edit 应用：先快照当前版本，version 继续递增，重新解析 links，`LastEditSource=revert`。它不倒转 placement/source refs。

“回退即新版本，而不是抹去历史”直接适用于 Topic Page 与 ResearchArtifact。

### 5.4 Retention 与 Delete 风险

WeKnora 对 pipeline revision 有 soft cap 50、所有 revision hard cap 200；手工/agent/revert 优先保留到 hard cap。页面 soft delete 后会硬删 revision 历史。拾流 Stage 1 不采用这种删除语义：review/correction lineage 应保留，未来 retention 需另立 Contract。

## 6. 异步 generation/update/rebuild 状态

### 6.1 持久 pending operation

`000041_task_queue_and_wiki_indexes` migration 与 `repository/task_queue.go` 建立 `task_pending_ops`：

- `task_type/scope/scope_id/op/dedup_key/payload`；
- `fail_count/enqueued_at/claimed_at`；
- claim/peek/release/delete/pending count；
- 非 SQLite 模式使用 `FOR UPDATE SKIP LOCKED`，并允许 stale claim 回收；
- `task_dead_letters` 保留耗尽重试的失败记录。

`wiki_ingest.go` 先持久化 pending row，再 enqueue 临时 trigger。相同 knowledge 的 re-ingest 通过 dedup 约束折叠；trigger 丢失不等于 operation 丢失。

### 6.2 启动恢复

`internal/container/recover_pending_wiki_tasks.go` 启动时：

- 清除已删除 KB 的孤儿队列，核验失败则 fail closed；
- 对 durable pending 的 ingest/finalize lane 各重建一个 trigger；
- duplicate trigger 被视为无害，ingest claim disjoint rows，finalize 使用 per-KB TaskID 合并。

这是“durable intent + ephemeral wakeup”模式，适合后续 V5-B update/rebuild；Stage 1 只需先建立 durable BuildRun/receipt，不必引入 asynq/Redis/通用队列平台。

### 6.3 Retry / dead letter / finalize

Wiki ingest 对行递增 `fail_count`；预算内 release claim，超限后写 dead letter 并移除 pending row。finalize lane 将 index intro rebuild、dead-link cleanup、cross-link injection 和 folder prune 合并；folder prune 会等待 ingest lane 排空。

关键拒绝项：`ProcessWikiFinalize` 对 index rebuild 失败只记录日志，随后仍 drain 该 finalize row，以免无限重做。对通用 Wiki 可能是性能/收敛权衡，但对拾流 Evidence-backed Page 不可接受；如果 rebuild 影响当前页面权威，必须持久化 `failed/retryable/needs_user`，不得表示成功。

## 7. 可观察性

`GetStats` 暴露 total pages、type counts、links、orphans、recent updates、pending tasks、pending issues 与 `is_active`。其中 pending task 来自持久队列；`is_active` 是 Redis 短期 flag，源码明确不把它当 durable state。

V5-B 采用：

- durable BuildRun status/error/attempt/receipt 是权威；
- pending count、最近变化、stale/conflict/issue count 是用户投影；
- polling/SSE/live region 只改善体验，不授予状态权威；
- active worker 消失时由 lease/claim/recovery 推导，而不是依赖布尔缓存。

## 8. 页面关系与浏览

`WikiPageService` 从 Markdown 解析 OutLinks，更新目标 InLinks；`RebuildLinks` 可全量重算双向 links，并作为 metadata-only update。Graph API 支持 overview/ego、depth/type/limit 和 truncated metadata，避免向浏览器发送全图。

前端 `WikiBrowser.vue` 提供目录、搜索、图视图、page drawer、issue badge、contradictory/out-of-date 提示；API 支持 pages/folders/index/graph/stats/search/issues/rebuild-links。

V5-B Stage 1 只采用小范围关系：显式 page-to-page links、fact-shared related pages 和 backlinks；不采用通用知识图谱、图推理或 GraphRAG。关系是导航/组织，不是 Citation。

## 9. 用户 review / revision UI 模式

`WikiRevisionDrawer.vue` 的有效模式包括：

- 当前版本与历史版本同列，显示 edit source/time；
- 历史详情按需加载，可看 line diff 或 raw body；
- revert 有确认，完成后保持 drawer 打开并刷新历史；
- overlapping detail requests 用单调 request sequence 防止旧响应覆盖新选择；
- 分页加载时按 version 去重，抵抗打开期间新增 revision。

这是高价值 `product_or_behavior_reference`，但 V5-B UI 还必须显示 Fact/Evidence currentness、用户决定、冲突/限制和字幕时间戳下钻。

## 10. 测试证据

### 10.1 已执行

用固定 Commit 的官方文件直接运行：

```text
node --test frontend/src/views/knowledge/wikiStatusRefresh.test.ts
2 tests, 2 pass, 0 fail
```

证明纯函数只在 document 从 in-flight 离开时请求 Wiki status refresh，普通 pending→processing 轮询不会重复刷新。它只验证 UI refresh predicate，不证明 queue/rebuild 正确性。

### 10.2 已审阅、未执行

- `repository/wiki_page_test.go`：SQLite revision DDL、optimistic conflict、失败恢复 version、retention；
- `service/wiki_page_revision_test.go`：snapshot、metadata no bump、revert creates new version；
- `repository/task_queue_test.go`：dedup、scoped pending count、claim affinity、fresh/stale claim、release、dead letter；
- `service/wiki_ingest_retry_test.go`：permanent/transient retry 分类；
- `service/wiki_folder_prune_finalize_test.go`：pending ingest 时保留 durable prune row；
- `container/reset_pending_tasks_test.go`：启动恢复 trigger 与 stuck state；
- `knowledge_post_process_wiki_enqueue_test.go`：trigger retry 不重复追加 pending operation。

Go 测试没有在本 Session 编译/执行；没有下载整套 Go/前端依赖。测试存在不等于测试通过。

## 11. Adoption Matrix

| 机制 | 决定建议 | 说明 |
| --- | --- | --- |
| stable TopicPage + typed page + folder/browser | `product_or_behavior_reference` | 收窄为个人收藏库 Topic workspace |
| optimistic version + atomic superseded snapshot | `reimplement_pattern + test_reference` | Stage 1 页面/Artifact 版本核心 |
| revert as fresh version | `reimplement_pattern` | 保留 correction lineage |
| durable pending row + ephemeral trigger + startup recovery | `reimplement_pattern` | Stage 2+ async refresh；不引入其平台 |
| dedup/fail count/dead letter/stale claim tests | `test_reference` | 转译为 SQLite/既有 receipt/fence |
| pending/issues/recent updates/revision diff | `product_or_behavior_reference` | 用户可观察性 |
| bounded overview/ego link browsing | `product_reference_later` | 关系只作导航；Stage 1 保持小范围 |
| tenant/RBAC/Connector/general RAG platform | `reject` | 企业平台过度范围 |
| GraphRAG/知识图谱默认依赖 | `reject` | 非 V5-B 默认架构 |
| Redis active flag 作为权威 | `reject` | 非 durable |
| finalize rebuild failure log-and-drain | `reject` | 会把未收敛误投影为完成 |
| page soft delete + revision hard delete | `reject_for_stage_1` | 破坏审计/用户 correction |
| 源码/组件复制 | `not_authorized` | 独立重实现足够，避免第三方依赖面 |

## 12. 未证明项与风险

- 未运行 Go repository/service/container 测试或完整前端测试。
- 未运行 Wiki LLM generation、index rebuild、cross-link injection 或任何 Provider。
- 未证明大规模 Wiki 性能、队列在生产 Redis/Postgres 下的行为。
- WeKnora `SourceRefs/ChunkRefs` 不等于拾流的 Transcript Evidence lineage。
- main Commit 新于最近 release；未来实现前若上游已变化，只有在本 Stage 机制不清时才需要 bounded JIT refresh，不追逐每次更新。

## 13. 请求 V5 Main 决定

请 V5 Main 有限审查并决定是否接受：

1. 将 WeKnora 固定为 `fcc4cd6a9f29a94818e481b3a604f44ce51c55e2` 的 bounded P1 证据；
2. 接受页面 version/revision、durable operation/recovery 和 UI review pattern 的独立重实现/测试参考；
3. 拒绝企业平台、通用 RAG、GraphRAG 默认、Redis active authority、log-and-drain rebuild failure；
4. Stage 1 不引入 WeKnora 依赖或通用异步平台，只铺设持久 BuildRun 与页面 revision；完整 async refresh 放入后续 Stage Contract。

上述请求不构成 Charter、Stage 1 或实现授权。
