# 拾流 V5-B 上游 DeepTutor 固定提交研究报告

```yaml
document_status: draft_for_v5_main_review
research_priority: P0
research_session: Shiliu V5-B Version Session
researched_at: 2026-08-04
official_repository: https://github.com/HKUDS/DeepTutor
pinned_commit: 44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8
pinned_tag: v1.5.8
license: Apache-2.0
source_audit_completed: true
tests_reviewed: true
upstream_tests_executed: false
provider_runs_performed: false
implementation_authorized: false
```

## 1. 结论先行

DeepTutor 对 V5-B 最有价值的不是可直接搬入拾流的 Memory Runtime，而是五组可独立重实现的机制：

1. 可见的 L1/L2/L3 分层和稳定条目 ID；
2. 每次 Add/Edit 必须携带来源引用的 fail-closed 写入约束；
3. 一批变更先完整校验、再原子应用的 preview/apply 模式；
4. 通过已见 ID 集合进行增量汇总，而不是只依赖文件 mtime；
5. 用户可显式修正、运行可观察、更新可取消/预览/撤销的产品形态。

但其权威模型不能直接成为拾流设计：DeepTutor L1 是可删除的 JSONL 行为 Trace；L2/L3 是可覆盖 Markdown；Delete 会物理移除条目；运行、锁、事件游标和 Undo 主要驻留进程内；L3 引用只到 surface，不能证明 claim-level lineage。拾流应采用 `reimplement_pattern + test_reference + product_or_behavior_reference`，不复制源码、不引入依赖，也不把 DeepTutor 个性化学习事实当作 Grounded Fact。

## 2. 固定身份、维护与 License

### 2.1 仓库身份

- 官方仓库：<https://github.com/HKUDS/DeepTutor>
- 官方 Remote：`https://github.com/HKUDS/DeepTutor.git`
- 固定 Commit：`44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8`
- 该 Commit 是 annotated tag `v1.5.8` 的 peeled commit。
- Commit 时间：`2026-08-02T13:23:45+08:00`；主题：`release: v1.5.8`。
- 研究时官方 `main` / `HEAD` 指向该 Commit；官方 Release 页面也把 `v1.5.8` 标为当前发布版本。
- 临时稀疏检出位于产品树外，Detached HEAD 固定到上述 Commit；未把任何上游文件 vendoring 到拾流。

### 2.2 License 与第三方边界

- 根 `LICENSE` 是 Apache License 2.0。
- `THIRD_PARTY_NOTICES.md` 在该 Commit 记录 CSSwitch（MIT）设计概念用于 Codex OAuth；本报告研究的 Memory 文件不属于该 OAuth 范围。
- 本轮不复制代码、Prompt、样式或测试，因此不产生 Apache NOTICE/修改标记的交付面。
- 若未来主 Session 改为复制或派生，必须重新确认所复制文件的版权头、保留 Apache-2.0 文本/NOTICE，并标注修改；本报告不授权该动作。

## 3. 研究深度与证据等级

| 项目 | 深度 | 状态 |
| --- | --- | --- |
| 官方 README、Release、License、第三方声明 | 文档核验 | `verified` |
| 固定 Commit、Remote、Tag、clean detached checkout | Git 核验 | `verified` |
| L1/L2/L3 路径、对象、读写更新删除 | 源码符号审阅 | `verified_at_pinned_commit` |
| 增量汇总、引用、运行状态、用户 correction | 源码符号审阅 | `verified_at_pinned_commit` |
| 相关单元测试 | 测试源码审阅 | `source_reviewed` |
| 六个 Memory 测试文件执行 | 有界尝试 | `not_executed_collection_blocked` |
| Provider/LLM 行为 | 未运行 | `not_exercised` |

测试执行尝试选取 `test_document.py`、`test_ops.py`、`test_store.py`、`test_modes.py`、`test_runs.py`、`test_merge.py`。临时稀疏检出缺少包级导入链中的 `deeptutor.core` 等非 Memory 模块，六个文件在 collection 阶段停止；没有调用测试体、Provider 或付费服务，也没有为此安装完整上游。测试结论只来自源码审阅，不能表示“上游测试已通过”。

## 4. L1/L2/L3 与文件映射

### 4.1 路径模型

`deeptutor/services/memory/paths.py` 定义 per-user 文件树：

```text
trace/<surface>/<YYYY-MM-DD>.jsonl     # L1
L2/<surface>.md                        # L2
L3/<recent|profile|scope|preferences>.md  # L3
backup/<timestamp>/...
```

Surface 包括 `chat/notebook/quiz/kb/book/partner/cowriter`；L3 slot 包括 `recent/profile/scope/preferences`。这是清晰、可浏览的物理分层，但“目录层级”本身没有提供拾流所需的 citation authority。

### 4.2 L1 Trace

`trace.py` 的 `TraceEvent` 含 ID、时间、surface、kind、payload、session 和 turn。写入按 surface 使用进程内 `asyncio.Lock`，向每日 JSONL 追加；失败会记录日志并被吞掉，以免影响生产者。

对拾流的判断：

- 可借鉴 append-only 事件的可读投影和按 domain 分区。
- 不能借鉴为 L1 authority：没有跨进程锁、durable receipt、fsync 或幂等键；API 还能删除 Trace。
- V5-B L1 必须继续以 V5-A 的 EvidenceIdentity/EvidenceUse/Validation/Event 为权威，Transcript/ASR 保持事实根。

### 4.3 L2/L3 Markdown Document

`document.py` 把每条 bullet 保存为带 `m_<ULID>` HTML comment 的稳定 Entry，并把来源保存为 footnote refs。`parse` / `serialize` 支持 legacy 格式且对标准序列化结果可 round-trip。

`ops.py` 提供 Add/Edit/Delete：

- Add/Edit 必须有 refs；
- 一批操作先全部验证，ID 冲突、目标缺失或 malformed ref 会拒绝整批；
- Delete reason 限于 contradicted/superseded/stale/low-signal；
- 真正应用后 Delete 会把条目从文档物理移除。

这证明“稳定用户可见 ID + preflight + whole-batch atomicity”值得采用；物理删除、仅靠 footnote 字符串的 lineage 不适合拾流。

## 5. Read / Write / Update / Delete 与幂等性

### 5.1 Store 行为

`store.py` 是基于用户路径上下文的无状态 facade：

- `read_doc` / `read_raw` / `read_l3_concat` 读取各层；
- `overwrite_doc` 允许直接保存完整 Markdown；
- `apply_ops_payload`、`update_l2`、`update_l3` 在进程内锁下写入；
- 文件更新使用临时文件、flush/fsync 和 replace；
- `delete_entry` 物理删除条目；reset/overwrite 可替换整个文档；
- v1 migration 把旧文件移动到 backup，并有 partner surface migration。

### 5.2 Preference correction

`write_preference` 对显式 preference 支持 add/edit：

- 对大小写/空白归一化后的同文 Add 返回已有 Entry，形成一条窄幂等语义；
- Edit 必须指定现有 target ID；
- preference 不进入自动 consolidation；
- partner tool 只允许 add/edit，并要求“不要推测”，把用户 correction 绑定到 trace ref。

它适合作为 Explicit User Memory 的产品参考，但不能证明通用命令幂等：没有 payload-hash receipt，重复 edit、跨进程并发和 crash-after-write 都不具备 V5-A 等级保证。

### 5.3 删除与修正边界

DeepTutor 的 Delete、PUT overwrite、reset 和 trace delete 会丢失现行文件中的旧事实。其 run-scoped Undo 仅在当前进程内 Run 记录仍存在时有效。因此 V5-B 不采用物理删除：

- Candidate reject 写 append-only UserDecision；
- Fact correction 创建新 FactRevision，并 supersede 旧 revision；
- Fact retire/retract 保留 evidence、decision 和 lineage；
- Topic Page edit/revert 创建新 PageRevision；
- 文件系统只保留由 SQLite 权威重新生成的不可变导出。

## 6. Incremental consolidation 与 lineage

### 6.1 增量输入

`consolidator/meta.py` 用 sidecar JSON 保存 `seen_entity_refs`（L2）和 `seen_l2_entry_ids`（L3），采用原子写。`modes/update.py` 通过 ID 集合差集而非 mtime 发现新输入，并在 L2 的每个 chunk 后写文档和 meta checkpoint。

这对拾流的可采用点是“稳定输入 ID + 差集 + 小步 checkpoint + 重启继续”，但 Stage 1 应用 SQLite receipt/unique constraint，而不是 sidecar meta。

### 6.2 引用精度

`references.py` / update mode 对 L2 把 refs 限制在当前 entity chunk pool，模型返回池外 ref 会被丢弃或拒绝。该 fail-closed 测试模式值得保留。

L3 更新只使用 surface-level refs/section blocks，不能精确指向 L2 Entry；这是 lossy lineage。拾流 L3 必须逐项保存 `artifact_fact_link` / `page_fact_link`，再沿 FactRevision 回到 EvidenceIdentity/EvidenceUse/Validation。

## 7. Run 状态与可观察性

`consolidator/runs.py` 的 `RunManager` 提供：

- `queued/running/cancelled/done/error`；
- 每个文档最多一个 active run；
- 带 cursor 的事件回放和 SSE；
- cancellation、run-scoped checkpoint 和 Undo；
- bounded history/event buffers。

源码明确说明 crash/restart 会清空 RunManager，依赖文件原子落盘和 ID-diff 恢复；事件截断后还会重新编号。V5-B 只采用产品形态，不采用其持久性语义：BuildRun、状态转换、错误、command receipt 和稳定 event ID 必须在 SQLite；SSE/polling 只是投影。

## 8. 相关测试源码审阅

| 测试 | 已核验意图 | 对 V5-B 的用途 |
| --- | --- | --- |
| `test_document.py` | parse/serialize round-trip、legacy | 稳定导出格式测试参考 |
| `test_ops.py` | add/edit/delete、batch conflict、refs、失败不改文档 | Review command preflight/rollback |
| `test_store.py` | read/write/delete、preference add 幂等、edit、migration | correction 与 filesystem failure reference |
| `test_modes.py` | no-new-input 幂等、池外 ref、audit/dedup | 增量 intake 与 fail-closed ref |
| `test_runs.py` | busy、cancel、cursor replay、error、undo | durable BuildRun 的行为清单 |
| `test_merge.py` | merge 幂等、legacy refs | bounded consolidation reference |

“测试存在”不等于“已在本 Session 执行”。执行状态见第 3 节。

## 9. SQLite + Filesystem 映射决定建议

### SQLite：唯一权威

Stage 1 的身份、状态、lineage 和正文 canonical representation 都放入 SQLite：Candidate intake、UserDecision、Fact/FactRevision、Evidence link、Artifact/ArtifactRevision、TopicPage/PageRevision、BuildRun、CommandReceipt、Validation observation 和 immutable events。

### Filesystem：派生、可重建的不可变导出

- Markdown/JSON 导出按 revision ID + content hash 寻址；
- 使用拾流已有 ArtifactStore 的 temp + replace 模式；
- 文件不得作为 current-head、review status 或 citation authority；
- 导出失败不回滚已成功的 SQLite 权威提交，而是产生可重试、可观察的 export 状态；
- overwrite 只覆盖“指向当前 revision 的派生指针/缓存”，不覆盖历史版本文件。

此选择避免 SQLite 与 filesystem 双主导致的 crash gap，也保留可读 Artifact。

## 10. Adoption Matrix

| 机制 | 决定建议 | 理由 |
| --- | --- | --- |
| L1/L2/L3 可见分层 | `reimplement_pattern` | 重新定义为 Evidence/Event → Fact → Artifact/Page |
| 稳定 Entry ID、refs-required、批量 preflight | `reimplement_pattern + test_reference` | 与既有 Evidence/Receipt 不变量兼容 |
| preview → apply、用户 add/edit | `product_or_behavior_reference` | 适合 Review Inbox；权威语义需重写 |
| ID-set incremental consolidation | `reimplement_pattern` | 用 SQLite unique/receipt/checkpoint 替代 sidecar |
| Markdown 可读导出 | `reimplement_pattern` | 仅派生导出，不作权威 |
| L1 JSONL Trace authority | `reject` | 可删除、非幂等、非跨进程安全 |
| 物理 delete/overwrite/reset | `reject` | 破坏 audit、correction 与 lineage |
| process-only locks/runs/undo/SSE cursor | `reject` | 重启不持久、游标不稳定 |
| L3 surface-level refs | `reject` | 不满足 claim-level citation |
| DeepTutor 个性化事实语义 | `reject` | 不能成为拾流 Transcript Grounded Fact |
| 源码/依赖复制 | `defer_and_not_authorized` | 当前没有必要，也扩大 License/依赖面 |

## 11. 未证明项与后续触发器

- 未运行 DeepTutor 完整测试或 Memory 测试体；只完成源码审阅和有界 collection 尝试。
- 未运行 LLM consolidation、OAuth、partner channel 或任何 Provider。
- 未证明其 filesystem locking 在多进程/网络文件系统上的正确性；源码本身也未提供该保证。
- 未验证长期大规模 Markdown/sidecar 迁移表现。
- 若未来要复制任一源码/测试、引入依赖或采用其 UI 组件，必须重新做文件级 License 和最新 Commit JIT 核验。

## 12. 请求 V5 Main 决定

请 V5 Main 有限审查并决定是否接受：

1. 将 DeepTutor 固定为 `44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8` / Apache-2.0 的 P0 研究证据；
2. 接受 `reimplement_pattern + test_reference + product_or_behavior_reference`，拒绝依赖/复制；
3. 接受 SQLite 唯一权威、filesystem 仅不可变派生导出的映射；
4. 接受物理删除、process-only run、surface-level L3 refs 和 L1 JSONL authority 为明确拒绝项。

上述请求不构成 Charter、Stage 1 或实现授权。
