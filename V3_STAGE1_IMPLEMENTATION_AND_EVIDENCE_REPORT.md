# Shiliu V3 — Stage 1 实施与证据报告

结论分类：`Accepted for Stage`（Closure Fix 后，等待 Version Session 复审）

Stage 1 已交付并停止。未进入 Stage 2，也未实现 Dense、Hybrid、Query Understanding、Search API/UI、正式 Retrieval Eval 或 Taxonomy 运行时集成。

## 1. Scope and Diff

[Confirmed Fact]

创建：

- [V3_CURRENT_STATE.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/V3_CURRENT_STATE.md)
- [retrieval/__init__.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/__init__.py)
- [retrieval/models.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/models.py:19)
- [retrieval/chunking.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/chunking.py:10)
- [retrieval/service.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:27)
- [test_retrieval.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/tests/test_retrieval.py)

修改：

- [app.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/app.py:12)：组合 `RetrievalService`
- [cli.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/cli.py:31)：增加 `retrieval rebuild/stats/search`

Diff：

```text
已跟踪文件：
2 files changed, 59 insertions(+)

新文件：
6 files, 1,635 lines

合计：
约 1,694 行新增，无删除
```

当前修改未暂存、未提交。

## 2. Retrieval Model and Schema

[Confirmed Fact]

正式库新增四个 additive 对象：

```text
retrieval_units
retrieval_unit_folders
retrieval_index_meta
retrieval_units_fts
```

定义位置：[RetrievalService.initialize_schema](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:81)。

关键设计：

- `retrieval_units.unit_id` 为主键。
- `video_id` 外键指向 `videos(id)`。
- Chunk 必须具有 `chunk_id/start_time/end_time`。
- Folder context 通过 `retrieval_unit_folders` 保存。
- FTS 表使用 SQLite FTS5。
- Tokenizer：`trigram`。
- Index version：`v3-stage1-lexical-v1`。
- BM25 返回值取负，使更高 `lexical_score` 排名更前。

确定性身份：

```text
Video:
video:{platform}:{source_id}:p{part}

Chunk:
SHA256(
  platform,
  source_id,
  part,
  subtitle source,
  start_time,
  end_time,
  content_hash
) 前 32 位

Chunk unit:
transcript_chunk:{platform}:{source_id}:p{part}:{chunk_id}
```

实现位置：[build_raw_subtitle_chunks](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/chunking.py:36) 和 [_make_chunk](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/chunking.py:109)。

重建及增量原语：

- 全量重建：[rebuild](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:150)
- 单 Video 替换：[replace_video](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:197)
- 单 Video 删除：[delete_video](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:211)

## 3. Chunking Behavior

[Confirmed Fact]

默认参数：

```text
目标字符数：800
正常最大字符数：1,200
正常最大持续时间：120 秒
重叠：前一 Chunk 最后一个完整字幕段
```

Chunk 只使用数据库关联的 raw subtitle，并保留完整上游字幕段及原始秒级时间戳。

[Observation]

如果单个上游字幕段本身超过限制，不会人为拆分并伪造更细时间边界；该段形成一个超限的单段 Chunk。

## 4. Test Evidence

[Confirmed Fact]

```text
Command:
.venv/bin/python -m pytest tests/test_retrieval.py -q

Exit: 0
Passed: 13
Failed: 0
Skipped: 0
```

```text
Command:
.venv/bin/python -m pytest \
  tests/test_database_and_sync.py \
  tests/test_library.py \
  tests/test_pipeline.py \
  tests/test_asr.py \
  tests/test_v1.py \
  tests/test_boundaries_and_web.py -q

Exit: 0
Passed: 44
Failed: 0
Skipped: 0
```

```text
Command:
.venv/bin/python -m pytest -q

Exit: 0
Passed: 301
Failed: 0
Skipped: 0
```

完整套件仅出现既有 TestClient 和 multiprocessing/fork deprecation warnings。

忽略状态及过滤专项证明：

```text
Command:
.venv/bin/python -m pytest \
  tests/test_retrieval.py::test_metadata_visibility_and_folder_filters -q

Exit: 0
Passed: 1
Failed: 0
Skipped: 0
```

该测试确认：

- ignored 默认排除；
- `include_ignored` 可显式包含；
- archived 默认可搜索；
- folder、favorite source、reading state、mark、uploader、archive 过滤有效。

所有测试使用临时数据库和临时 Artifact root，没有调用外部 Provider。

## 5. Formal-data Rebuild

[Confirmed Fact]

正式执行：

```text
.venv/bin/shiliu retrieval rebuild
```

第一次结果：

```text
eligible Videos:             142
Video units:                 142
Transcript Chunk units:    1,405
Total units:               1,547

Chunk source:
ai:                        1,326
asr:                          14
human:                        65

Missing raw JSON:              0
Malformed raw JSON:            0
Malformed summary JSON:        0
Malformed transcript JSON:     0

Index version: v3-stage1-lexical-v1
Tokenizer: trigram
Duration: 0.593998 seconds
```

第二次未改变输入重建：

```text
Video units:                 142
Transcript Chunk units:    1,405
Total units:               1,547
Duration: 0.979535 seconds
Duplicate count:               0
```

两次逻辑数量和来源分布完全相同。

数据库大小：

```text
Before:  1,609,728 bytes
After:  36,483,072 bytes
Delta:  34,873,344 bytes
        ≈33.26 MiB
```

最终只读一致性核验：

```text
metadata rows:       1,547
distinct unit IDs:   1,547
FTS rows:            1,547
duplicate count:         0
consistent:           true
PRAGMA integrity_check: ok
PRAGMA foreign_key_check violations: 0
```

271 条历史 Event 仍全部为：

```text
status = pending
processed_at IS NULL
```

本轮没有消费 Event。

## 6. Functional Demonstrations

[Confirmed Fact]

Video-level 实体查询和真实 Folder filter：

```text
shiliu retrieval search LangGraph \
  --level video --top-k 1 --folder-id 3876418799
```

结果：

```text
unit: video:bilibili:BV1wMQjBCEpZ:p1
video_id: 26
title: [开源] RAG 项目框架及源码详解
excerpt: 视频详细讲解了基于 LangGraph 的 RAG 项目 SuperMew 的核心架构……
score: 8.888116439315892
method: lexical
index: v3-stage1-lexical-v1
folder: 2026找工作学习
```

Chunk-level 查询及完整 provenance：

```text
shiliu retrieval search MCP \
  --level transcript_chunk --top-k 1
```

结果：

```text
Video identity: bilibili / BV1G29EBGE8b / part 1
video_id: 78
Chunk identity: chunk_6c982f17915950d79bd4ab0f296e00ee
Subtitle source: ai
Start: 579.04 seconds
End: 698.38 seconds
Excerpt: MCP全称是模型上下文协议……MCP就是AI大模型的标准化工具箱……
Score: 6.1373411944486564
Method: lexical
Index: v3-stage1-lexical-v1
```

短查询降级：

```text
shiliu retrieval search AI --level video --top-k 1
```

```text
method: lexical_substring_fallback
score: 0.0
```

## 7. Limitations

[Confirmed Fact]

- `trigram` 适合中文及中英混合的三字符以上匹配，但一至两个字符无法进入 trigram FTS 查询。
- 短查询使用无 BM25 排名的大小写不敏感 substring fallback。
- 没有字幕的 Video 仍有 Video-level 单元，但没有 Transcript Chunk。
- 可选 Summary/Transcript Artifact 缺失或 malformed 时会降级并计数，不阻止其他单元建立。
- 上游 Subtitle/Segment 没有独立 ID 或内容修订历史。
- 单 Video replace/delete 已交付，但尚未接入实时 Pipeline mutation callback。
- 未实现 Dense 或语义检索。
- 未测试 Bilibili 时间戳链接的端到端行为。
- 尚无正式 Query Set、指标或 failure analysis。

[Unknown]

- 中文检索质量尚未经过正式 Retrieval Eval。
- 内容频繁变更下的在线增量索引性能尚未验证。
- 时间戳结果到最终产品链接的交互正确性尚未验证。

## 8. State and Boundary

[Confirmed Fact]

[V3_CURRENT_STATE.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/V3_CURRENT_STATE.md) 已更新为：

```text
Stage 1 Delivered
Ready for Version Session Re-review
Stage 2 has not been entered
```

估算：

```text
Stage 1 effective use: approximately 2–2.5 hours
Remaining target budget: approximately 14–21 hours
```

[Inference]

现有测试、正式库重建、幂等性、真实查询、过滤、完整性和范围证据满足 Stage 1 acceptance evidence。

[Recommendation]

Version Session 可接受本 Stage；后续工作应等待单独授权，本轮在此停止。

## 9. Stage 1 Closure Fix Evidence

### 9.1 Modified Files

[Confirmed Fact]

Closure Fix 仅修改：

```text
src/shiliu/retrieval/service.py
tests/test_retrieval.py
V3_CURRENT_STATE.md
V3_STAGE1_IMPLEMENTATION_AND_EVIDENCE_REPORT.md
```

未修改 Application、CLI、Chunking、Tokenizer、Taxonomy 或其他产品模块。

### 9.2 Current Index Meta Semantics

[Confirmed Fact]

`retrieval_index_meta` 现在明确代表 current index state：

```text
eligible_video_count = 当前具有 Video unit 的 distinct Video 数
video_unit_count = 当前 Video unit 数
chunk_unit_count = 当前 Transcript Chunk unit 数
updated_at = 最近一次 current-state count refresh
```

历史 full rebuild 信息独立保留：

```text
rebuilt_at = 最近一次成功 full rebuild 时间
```

`statistics()` / CLI stats 输出分为：

```text
index               current persisted Index Meta
current             current counts calculated from Retrieval tables
last_full_rebuild   historical completed_at
```

`INDEX_VERSION` 仍为 `v3-stage1-lexical-v1`。

### 9.3 Transactional Update Locations

[Confirmed Fact]

```text
RetrievalService.replace_video(): src/shiliu/retrieval/service.py:214
RetrievalService.delete_video(): src/shiliu/retrieval/service.py:229
RetrievalService._refresh_index_meta_counts(): src/shiliu/retrieval/service.py:672
```

replace/delete 在同一个 `Database.connect()` transaction 中依次修改 FTS、folder/metadata rows，并从当前 `retrieval_units` 刷新 Index Meta。没有重扫 Artifact，也没有改变 Index Version。

Schema 初始化在新库直接创建 `updated_at`；对旧合法库执行 additive：

```sql
ALTER TABLE retrieval_index_meta ADD COLUMN updated_at TEXT;
UPDATE retrieval_index_meta
SET updated_at=rebuilt_at
WHERE updated_at IS NULL;
```

正式数据库临时副本验证：

```text
columns before: 7 existing columns
columns after: existing columns + updated_at
metadata / FTS before: 1547 / 1547
metadata / FTS after two initializations: 1547 / 1547
updated_at backfilled from rebuilt_at: yes
integrity_check: ok
foreign-key violations: 0
```

### 9.4 Added and Expanded Tests

[Confirmed Fact]

```text
test_replace_removes_stale_units_and_delete_removes_fts_rows
  rebuild → replace 1 Chunk with 3 Chunks → delete
  validates metadata, FTS, folder, distinct IDs and Index Meta counts

test_favorite_time_range_is_inclusive_and_combines_with_folder_filter
  validates from, to, from+to, inclusive boundary and folder combination

test_mixed_active_removed_memberships_only_index_active_folder_provenance
  validates active eligibility, removed-folder exclusion, active provenance,
  and replace cleanup after the final active Membership is removed

test_short_query_uses_documented_fallback
  validates top-k, filters, deterministic order, removed/ignored/archive rules,
  include_ignored, method and zero-score semantics

test_fts_special_characters_do_not_raise_and_preserve_filter_and_top_k
  validates GPT-4o, C++, quoted " term and (MCP)
```

### 9.5 Test Results

[Confirmed Fact]

```text
Command: .venv/bin/python -m pytest tests/test_retrieval.py -q
Exit status: 0
Passed: 13
Failed: 0
Skipped: 0
```

```text
Command: .venv/bin/python -m pytest -q
Exit status: 0
Passed: 301
Failed: 0
Skipped: 0
```

Only existing Starlette TestClient and multiprocessing/fork deprecation warnings were emitted.

### 9.6 FTS Special-character Result

[Confirmed Fact]

The accepted Phrase-mode query construction successfully handled：

```text
GPT-4o
C++
quoted " term
(MCP)
```

No `sqlite3.OperationalError` was reproduced. Per the Closure Fix contract, no general Query Parser or runtime fallback was added.

### 9.7 Formal Database Read-only Verification

[Confirmed Fact]

```text
metadata count: 1547
FTS count: 1547
metadata duplicate unit IDs: 0
FTS duplicate unit IDs: 0
metadata without FTS: 0
FTS without metadata: 0
folder orphans: 0
integrity_check: ok
foreign-key violations: 0
```

Formal DB size and mtime remained unchanged. The formal database still has the pre-Closure-Fix seven-column Meta Schema; additive compatibility was verified on a temporary copy instead of mutating formal data.

### 9.8 Remaining Limitations

[Confirmed Fact]

* Queries of three or more characters retain the accepted full-Phrase behavior.
* One- and two-character queries remain deterministic substring fallback with score `0.0`.
* Pipeline mutation integration remains Stage 3 work.
* No formal Retrieval Eval, Dense, Hybrid, API or UI work was started.

### 9.9 Recommended Classification

`Accepted for Stage`

This is a recommendation for Version Session re-review, not an automatic authorization for Stage 2.

### 9.10 Git Diff Summary

[Confirmed Fact]

Stage 1 Retrieval files remain untracked relative to `HEAD`, so ordinary `git diff --stat` only displays the previously accepted Application/CLI integration：

```text
src/shiliu/app.py | 2 ++
src/shiliu/cli.py | 57 +++
2 files changed, 59 insertions(+)
```

Closure Fix line-count delta relative to the restored Acceptance Audit baseline：

```text
src/shiliu/retrieval/service.py: 777 → 846
tests/test_retrieval.py:         385 → 648
V3_CURRENT_STATE.md:             197 → 209
this evidence report:            355 → 528 before this subsection
```

`git diff --check` completed with exit status 0 and no output. No files are staged or committed.
