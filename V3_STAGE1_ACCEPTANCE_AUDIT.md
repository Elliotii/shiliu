## 1. Read-only Integrity

[Confirmed Fact]

开始时执行：

```bash
pwd
git status --short
git diff --stat
git diff --cached --stat
git status -sb
```

结果：

```text
cwd: /Users/elliot/new-systems/agent-job-prep/Shiliu
branch: codex/v3-domain-completion
staged changes: none

Modified:
src/shiliu/app.py
src/shiliu/cli.py

Untracked:
V3_CURRENT_STATE.md
V3_STAGE1_IMPLEMENTATION_AND_EVIDENCE_REPORT.md
src/shiliu/retrieval/
tests/test_retrieval.py
```

已执行控制文本要求的全部 Diff 命令。`git diff --check` exit 0、无输出。

本轮：

- 未修改文件；
- 未修改或重建正式数据库；
- 未调用 Provider；
- 测试使用 `tmp_path` 下的临时数据库和 Artifact root；
- 特殊字符探针只使用 SQLite `:memory:`；
- 未进入 Stage 2。

## 2. Diff Review Summary

[Confirmed Fact]

Diff 中的职责：

- [app.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/app.py:15)：把 `RetrievalService` 加入 Application composition。
- [cli.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/cli.py:31)：增加 `retrieval rebuild/stats/search` 及过滤参数。
- [models.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/models.py:19)：Retrieval unit、filter、result 和 folder provenance。
- [chunking.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/chunking.py:10)：确定性 raw-subtitle chunking。
- [service.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:66)：Schema、rebuild、replace、delete、search。
- [test_retrieval.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/tests/test_retrieval.py:83)：10 个 Retrieval 测试。
- [V3_CURRENT_STATE.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/V3_CURRENT_STATE.md)：Stage 状态。
- [V3_STAGE1_IMPLEMENTATION_AND_EVIDENCE_REPORT.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/V3_STAGE1_IMPLEMENTATION_AND_EVIDENCE_REPORT.md)：用户要求落盘的验收报告。

已跟踪 Diff：

```text
src/shiliu/app.py |  2 ++
src/shiliu/cli.py | 57 +++
2 files changed, 59 insertions(+)
```

[Confirmed Fact]

没有新增：

```text
Dense Retrieval
Hybrid Retrieval
Query Understanding
Search API
Search UI
Retrieval Eval
Taxonomy runtime integration
```

`shiliu.retrieval` 没有导入 Taxonomy 模块。

## 3. Schema and Identity Findings

[Confirmed Fact] Retrieval DDL，位置：[service.py:81](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:81)。

```python
CREATE TABLE IF NOT EXISTS retrieval_units (
    unit_id TEXT PRIMARY KEY,
    unit_type TEXT NOT NULL CHECK(unit_type IN ('video', 'transcript_chunk')),
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    ...
    content_hash TEXT NOT NULL,
    index_version TEXT NOT NULL
);
```

Folder provenance：

```python
CREATE TABLE IF NOT EXISTS retrieval_unit_folders (
    unit_id TEXT NOT NULL
        REFERENCES retrieval_units(unit_id) ON DELETE CASCADE,
    source_db_id INTEGER NOT NULL
        REFERENCES favorite_sources(id) ON DELETE CASCADE,
    ...
    PRIMARY KEY(unit_id, source_db_id)
);
```

FTS tokenizer/table，位置：[service.py:27](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:27)、[service.py:142](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:142)：

```python
INDEX_VERSION = "v3-stage1-lexical-v1"
FTS_TOKENIZER = "trigram"

CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_units_fts USING fts5(
    unit_id UNINDEXED,
    search_text,
    tokenize='trigram'
);
```

Video ID，位置：[service.py:384](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:384)：

```python
unit_id=f"video:{platform}:{source_id}:p{part}"
```

Chunk hash/ID，位置：[chunking.py:120](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/chunking.py:120)：

```python
content_hash = sha256(text.encode("utf-8")).hexdigest()
identity = json.dumps({
    "platform": platform, "source_id": source_id, "part": part,
    "source_type": source_type, "start_time": start_time,
    "end_time": end_time, "content_hash": content_hash,
}, sort_keys=True, separators=(",", ":"))
chunk_id = "chunk_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
```

Chunk unit ID，位置：[service.py:445](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:445)：

```python
unit_id=(
    f"transcript_chunk:{video['platform']}:{video['source_id']}:"
    f"p{video['part']}:{chunk.chunk_id}"
)
```

[Risk]

`UNIQUE(video_id, chunk_id)` 不会阻止多个 `chunk_id IS NULL` 的 Video rows；当前 builder 和确定性 `unit_id` 保证每个 Video 只生成一个 Video unit，但该约束没有独立在数据库层强制“一 Video unit”。

## 4. Chunking Findings

[Confirmed Fact]

Rollover，位置：[chunking.py:63](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/chunking.py:63)：

```python
next_characters = characters + separator + len(candidate_text)
next_duration = candidate.end - first_start
exceeds_bound = bool(selected) and (
    next_characters > resolved.maximum_characters
    or next_duration > resolved.maximum_duration_seconds
)
if exceeds_bound:
    break
```

时间边界来自首尾完整字幕段：

```python
start_time=selected[0].start,
end_time=selected[-1].end,
text=" ".join(segment.content.strip() for segment in selected),
```

Overlap，位置：[chunking.py:101](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/chunking.py:101)：

```python
if (
    cursor < len(usable)
    and resolved.trailing_segment_overlap
    and len(selected) > 1
):
    cursor -= 1
```

[Confirmed Fact]

- 输出确定；
- 不切断字幕段；
- 正常 rollover 同时考虑字符数和持续时间；
- 一个上游段自身超限时保留为单段 Chunk；
- `source_type/start/end/content_hash` 进入稳定 Chunk identity。

## 5. Eligibility and Visibility Findings

[Confirmed Fact]

Eligibility，位置：[service.py:326](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:326)：

```sql
WHERE v.removed_at IS NULL
  AND EXISTS(
      SELECT 1 FROM video_source_memberships m
      WHERE m.video_id=v.id AND m.removed_at IS NULL
  )
```

正式库只读结果：

```text
videos: 143
eligible Videos: 142
Video units: 142
```

唯一被排除记录：

```text
videos.id: 28
BVID: BV13g4y1F7TG
status: completed
removed_at: 2026-07-15T18:45:32+00:00
is_ignored: 1
archived_at: NULL
Membership total: 1
Active Membership: 0
Removed Membership: 1
Indexed Video unit: 0
```

143→142 的直接原因同时包括：

- Video 本身 `removed_at IS NOT NULL`；
- 没有 active Membership。

可见性结论：

- `ignored` 不属于 indexing eligibility 条件，因此 eligible ignored Video 会被索引；搜索默认通过 `u.is_ignored=0` 排除，可用 `include_ignored=True` 包含。
- `archived` 不属于 indexing eligibility 条件，默认仍被索引和搜索。
- `removed` 在 rebuild eligibility 阶段被排除；搜索 SQL 另有 `u.removed_at IS NULL` 防御条件。
- 当前正式库没有 eligible ignored 或 archived Video；上述 ignored/archive 行为由本轮实际执行的临时库测试确认。

## 6. Test-to-Acceptance Matrix

本轮完整执行了 `tests/test_retrieval.py`，因此下表中的 `Yes` 表示对应测试函数本轮实际运行且通过。

| Acceptance condition | Test name | Actually executed |
|---|---|---|
| deterministic chunk output | `test_chunking_is_deterministic_preserves_segments_and_overlap` | Yes |
| whole segment preservation | 同上；`test_chunking_honors_duration_and_keeps_oversized_whole_segment` | Yes |
| timestamp boundaries | `test_chunking_is_deterministic_preserves_segments_and_overlap` | Yes |
| character/duration behavior | `test_chunking_honors_duration_and_keeps_oversized_whole_segment` | Yes |
| overlap behavior | `test_chunking_is_deterministic_preserves_segments_and_overlap` | Yes |
| source retention | `test_raw_subtitle_source_is_retained_for_ai_human_and_asr` | Yes |
| stable Chunk ID | `test_chunking_is_deterministic_preserves_segments_and_overlap` | Yes |
| schema initialization idempotency | `test_schema_initialization_and_unchanged_rebuild_are_idempotent` | Yes |
| unchanged rebuild no duplicates | 同上 | Yes |
| full rebuild removes stale units | `test_full_rebuild_removes_video_without_active_membership` | Yes |
| per-video replace removes stale units | `test_replace_removes_stale_units_and_delete_removes_fts_rows` | Yes |
| per-video delete cleans metadata and FTS | 同上 | Yes |
| metadata/FTS counts consistent | schema idempotency test；replace/delete test | Yes |
| malformed optional artifact fallback | `test_malformed_optional_assets_degrade_and_video_without_subtitle_is_indexed` | Yes |
| no-subtitle Video-level unit | 同上 | Yes |
| exact entity search | `test_lexical_search_levels_top_k_and_chunk_provenance` | Yes |
| Video-level search | 同上 | Yes |
| Chunk-level search and provenance | 同上 | Yes |
| top-k | 同上 | Yes |
| creator/uploader filter | `test_metadata_visibility_and_folder_filters` | Yes |
| reading-state filter | 同上 | Yes |
| mark filter | 同上 | Yes |
| favorite-folder filter | 同上 | Yes |
| favorite-time range filter | — | **Missing Evidence** |
| removed default exclusion | `test_full_rebuild_removes_video_without_active_membership` | Yes, indirect |
| ignored exclusion and explicit inclusion | `test_metadata_visibility_and_folder_filters` | Yes |
| archived default inclusion | 同上 | Yes |
| mixed active/removed Membership | — | **Missing Evidence** |
| short-query fallback | `test_short_query_uses_documented_fallback` | Yes, partial |

## 7. Targeted Test Result

[Confirmed Fact]

实际执行：

```bash
.venv/bin/python -m pytest tests/test_retrieval.py -q
```

输出：

```text
.......... [100%]
TARGETED_EXIT_STATUS=0
```

统计：

```text
exit status: 0
passed: 10
failed: 0
skipped: 0
```

测试隔离证据：[tests/conftest.py:10](/Users/elliot/new-systems/agent-job-prep/Shiliu/tests/conftest.py:10)。

```python
@pytest.fixture
def app_paths(tmp_path: Path) -> AppPaths:
    state = tmp_path / "state"
    content = tmp_path / "content"
    ...
```

## 8. FTS Query and Fallback Findings

[Confirmed Fact]

用户 Query 通过参数绑定进入 MATCH，不进行 SQL 字符串拼接，位置：[service.py:302](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:302)：

```python
WHERE retrieval_units_fts MATCH ?
...
query_parameters = [_fts_phrase(normalized), *parameters, top_k]
```

FTS 转换，位置：[service.py:764](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:764)：

```python
def _fts_phrase(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'
```

它把完整输入转换为 phrase，并将内部双引号加倍。

纯内存 SQLite 探针：

```text
GPT-4o          -> "GPT-4o"          no syntax error, matched
C++             -> "C++"             no syntax error, matched
double " quote  -> "double "" quote" no syntax error, matched
(MCP)           -> "(MCP)"           no syntax error, matched
OR              -> 实际 search 走 2-character substring fallback
```

[Risk]

现有自动化测试没有覆盖上述 FTS 特殊字符。对三字符以上 MATCH 路径也没有捕获 `sqlite3.OperationalError` 后的 fallback；虽然指定探针均未触发 syntax error，但其他未预见输入若触发 FTS 错误，会直接向调用方抛出。

短 Query，位置：[service.py:289](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:289)：

```python
WHERE instr(lower(u.search_text), lower(?)) > 0
  AND {where}
ORDER BY u.unit_type, u.video_id, u.start_time
LIMIT ?
```

[Confirmed Fact]

代码确认 1–2 字符 fallback：

- 使用绑定参数；
- 应用同一 Metadata Filter；
- 应用 `top_k`；
- 排序确定；
- 默认排除 removed/ignored；
- archived 默认包含。

[Missing Evidence]

现有 short-query 测试只断言结果存在、method 和 score；没有自动化断言 top-k、filter、排序、removed/ignored 或 archived 行为。

Metadata Filter SQL，位置：[service.py:632](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:632)：

```python
clauses = ["u.removed_at IS NULL"]
if not include_ignored:
    clauses.append("u.is_ignored=0")
...
folder_clauses.append("f.favorite_time>=?")
folder_clauses.append("f.favorite_time<=?")
```

Score 方向，位置：[service.py:303](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:303)：

```python
SELECT u.*, -bm25(retrieval_units_fts) AS lexical_score
...
ORDER BY lexical_score DESC, u.unit_id
```

因此返回分数越高，排名越靠前。

## 9. Rebuild / Replace / Delete Consistency

### Full rebuild

[Confirmed Fact]

位置：[service.py:150](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:150)：

```python
with self.db.connect() as connection:
    connection.execute("DELETE FROM retrieval_units_fts")
    connection.execute("DELETE FROM retrieval_unit_folders")
    connection.execute("DELETE FROM retrieval_units")
    self._insert_units(connection, units)
    connection.execute("INSERT INTO retrieval_index_meta ...")
```

`Database.connect()` 在正常退出时 commit、异常时 rollback，位置：[db.py:400](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/db.py:400)。

[Confirmed Fact]

- FTS、folder、metadata 清理和重新插入处于同一 write transaction。
- 不再 eligible 的旧单元通过全表清理后只重插 eligible units 而消失。
- unit 构建发生在 write transaction 之前；构建失败时旧索引不变。
- write transaction 中任一插入失败时，删除及已完成插入均 rollback。
- `initialize_schema()` 是 rebuild 之前的独立 transaction；首次失败可能留下空 Schema，但不会留下半套 rebuild 数据。

### Replace

[Confirmed Fact]

位置：[service.py:197](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:197)：

```python
video = self._eligible_video(video_id)
units = self._build_video_units(video, stats) if video is not None else []
with self.db.connect() as connection:
    self._delete_video_units(connection, video_id)
    self._insert_units(connection, units)
```

旧 FTS rows 先按当前 metadata unit IDs 删除，再删除 metadata 并插入新单元，因此旧 Chunk 不残留。

### Delete

[Confirmed Fact]

位置：[service.py:621](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:621)：

```python
DELETE FROM retrieval_units_fts
WHERE unit_id IN (
    SELECT unit_id FROM retrieval_units WHERE video_id=?
)
DELETE FROM retrieval_units WHERE video_id=?
```

Folder rows 依靠 `ON DELETE CASCADE` 删除；`Database.connect()` 开启 `PRAGMA foreign_keys=ON`。

### Row correspondence

[Confirmed Fact]

metadata 和 FTS 以相同 `unit_id` 对应。正式库只读核验：

```text
metadata rows: 1,547
FTS rows: 1,547
metadata duplicate unit IDs: 0
FTS duplicate unit IDs: 0
metadata without FTS: 0
FTS without metadata: 0
folder orphans: 0
integrity_check: ok
foreign-key violations: 0
```

[Confirmed Fact]

metadata 使用普通 `INSERT`，没有 update/replace conflict policy。重复 `unit_id` 会触发主键错误并回滚 transaction，而不是静默更新。

## 10. Missing Evidence

1. 没有 favorite-time range filter 自动化测试。
2. 没有同一 Video 同时具有 active/removed Membership 的自动化测试。
3. 没有 `GPT-4o`、`C++`、双引号、括号和 FTS operator 输入的自动化测试。
4. 没有三字符以上 FTS syntax/operational failure 行为测试。
5. Short-query 测试没有覆盖 top-k、Metadata Filter、确定性排序及 visibility。
6. Delete 测试没有直接断言 folder rows 为 0；该行为目前由外键 Schema、`foreign_keys=ON` 和正式库无孤儿共同证明。
7. 没有故障注入测试直接证明 full rebuild 中途异常 rollback。
8. 没有测试或文档明确规定 `retrieval_index_meta` 的 counts 是“最后一次 rebuild snapshot”还是“当前索引 counts”。

## 11. Bugs or Risks Found

[Risk — follow-up]

`replace_video()` 和 `delete_video()` 不更新 `retrieval_index_meta`。因此执行增量原语后：

- `statistics()` 的实时 `metadata_count/fts_count` 会变化；
- `index.eligible_video_count/video_unit_count/chunk_unit_count` 仍保留最后一次 full rebuild 数值。

如果这些字段被理解为当前索引统计，会产生陈旧数据；如果它们被定义为 rebuild snapshot，则需要明确命名或文档。

[Risk — follow-up]

FTS 表的 `unit_id` 是 `UNINDEXED` 普通列，没有唯一约束或外键。当前 Service transaction 和正式库核验维持了一一对应，但数据库 Schema 本身不强制这一关系。

[Risk — follow-up]

FTS MATCH 没有运行时错误 fallback。指定特殊字符探针正常，但缺少自动化回归。

[Inference]

以上均未证明当前正式索引错误，也没有发现会阻止现有 Stage 1 baseline 工作的确定性故障。

“尚未接入 Pipeline mutation”属于 Stage 3 范围，不作为 Stage 1 Bug。

## 12. Recommended Stage Classification

`Accepted with Follow-up`

理由：

- 核心 Schema、身份、Chunking、FTS/BM25、过滤、rebuild/replace/delete 均有源码证据；
- 本轮 targeted tests 10/10 通过；
- 正式库 metadata/FTS 一致，无重复、孤儿或完整性错误；
- 没有发现 out-of-scope runtime 集成；
- 但存在明确测试证据缺口，以及增量操作后 `retrieval_index_meta` 计数语义/陈旧风险。

该建议不代表 V3 Version Session 的最终决定。

## 13. Final Read-only Verification

结束时再次执行：

```bash
pwd
git status --short
git diff --stat
git diff --cached --stat
git status -sb
```

结果与开始一致：

```text
cwd: /Users/elliot/new-systems/agent-job-prep/Shiliu
branch: codex/v3-domain-completion
staged changes: none
tracked diff: 2 files, 59 insertions
```

相同的 Stage 1 文件仍为 modified/untracked；本轮没有新增或修改项目文件，没有修改正式数据库或索引。
