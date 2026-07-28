## 1. Audit Result

```text
Completed with Blocking Unknowns
```

核查已完成。阻塞点不是 V3 Retrieval 能力，而是 V3.5 Evidence 所需的 Raw Segment 身份、Source Version 绑定与一个非单调字幕 Artifact。

## 2. Executive Summary

1. **Confirmed Fact** — 可直接复用 `SearchRequest → SearchPlanner → SearchOrchestrator → RawSearchResponse → SearchResultConsolidator → EvidenceEnricher → ProductSearchResponse` 调用链。
2. **Blocking Risk** — `SearchOrchestrator` 和 `ProductSearchService` 构造时建表，搜索时持久化 Trace；当前“读取型”调用不是严格无写副作用。
3. **Confirmed Fact** — Raw Subtitle/ASR 的统一 Segment Schema 是 `{from, to, content}`，时间单位为秒；Evidence 时间可以由 Raw Segment 重建。
4. **Blocking Risk** — Raw Segment 没有显式稳定 ID、Artifact ID 或 Source Version；Retrieval Chunk 也不保存 segment indices、Artifact path/hash。
5. **Inference** — 同一 Artifact 重读和索引重建时，Chunk ID 可稳定；字幕重新抓取、ASR 重跑或顺序变化后的 Segment 引用不具备版本安全性。
6. **Confirmed Fact** — Snapshot `20260720T094346Z_c7663365` 完整存在，DB SHA-256 匹配；372 个已声明 Artifact 全部存在且 hash 匹配。
7. **Confirmed Fact** — Live DB 已从 Snapshot 漂移到 145 videos / 1565 retrieval units；V3.5 Seed 必须使用冻结 Snapshot，不能用当前 Live DB 替代。
8. **Confirmed Fact** — 现有 10 个 Approved Query–Video Intervals 全部能映射到 Snapshot Raw Segments，且 Artifact hash 全部匹配。
9. **Blocking Risk** — 129 个 Raw Subtitle Artifact 中有 1 个非单调案例：video 88 在 index 1389 从 `2767.133s` 跳回 `0.133s`；10 个 Seed 不受影响。
10. **Confirmed Fact** — 当前 full suite：`518 passed / 0 failed / 0 skipped / 7 warnings`；测试前后 worktree 状态一致。

## 3. Repository Identity

| 项目 | 结果 |
|---|---|
| Expected path | `/Users/elliot/new-systems/agent-job-prep/Shiliu` |
| Resolved repository root | `/Users/elliot/new-systems/agent-job-prep/Shiliu` |
| Branch | `codex/v3-domain-completion`，相对 origin ahead 1 |
| HEAD | `8287c8d92378b87290274d02605cdc704cb8c470` |
| Dirty worktree | 是：5 个 tracked modified，62 个 untracked |
| Submodule | `references/upstreams/bilibili-cli`，commit `dbe2855…` |
| Nested repo | 只发现上述 submodule 的 `.git` |
| Staged changes | 无 |

Tracked modifications：

- `V3_CURRENT_STATE.md`：文档变化。
- `src/shiliu/retrieval/__init__.py`：导出 Bilibili jump URL helper。
- `src/shiliu/retrieval/product_search.py`：Product Result 展示字段、一次性 metadata 查询、jump URL；未改变 Raw ranking。
- `src/shiliu/templates/base.html`：Search 导航与 template blocks。
- `src/shiliu/web.py`：新增 `/search` 页面。

Untracked 文件完整分组：

- 根目录报告：`00_V3_RETRIEVAL_VERSION_BRIEF.md`、`01_V3_SESSION_OPERATING_CONTRACT.md`、`V3_STAGE5_WEB_SEARCH_SURFACE_AND_EVIDENCE_REPORT.md`、`V3_STAGE6A_HUMAN_GOLD_REVIEW_REPORT.md`、`V3_STAGE6A_RECOVERY_CORPUS_AND_GOLD_CANDIDATE_REPORT.md`、`V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md`、`V3_STAGE6B_GOLD_LOCK_BLOCKING_REPORT.md`、`V3_STAGE6B_INCREMENTAL_HUMAN_REVIEW_PACKET_REPORT.md`。
- `research/v3_eval/`：`GOLD_LOCK_SUMMARY.md`、`V3_EVAL_PROTOCOL.md`、`V3_GOLD_REVIEW_PACKET.md`、`V3_STAGE6B_INCREMENTAL_HUMAN_REVIEW_PACKET.md`、`ai_summary_diagnostic.md`、`artifact_manifest.jsonl`、`corpus_manifest.json`、`cross_language_diagnostic.md`、`dense_truncation_impact.md`、`eval_gold.locked.jsonl`、`eval_gold_candidates.jsonl`、`eval_gold_review.decisions.amended.jsonl`、`eval_gold_review.decisions.jsonl`、`eval_per_query_results.jsonl`、`eval_pool_candidates.jsonl`、`eval_queries.candidate.jsonl`、`eval_queries.locked.jsonl`、`eval_results.csv`、`eval_results.json`、`eval_summary.md`、`failure_cases.md`、`gold_lock_audit.json`、`human_ledger_amendment_audit.json`、`incremental_human_review_evidence.jsonl`、`unjudged_sensitivity.md`。
- `research/v3_stage5/screenshots/`：`01_exact_entity_results.png` 至 `06_narrow_layout.png`。
- `src/shiliu/eval/`：`__init__.py`、`gold_lock.py`、`metrics.py`、`pooling.py`、`queries.py`、`reporting.py`、`review.py`、`runner.py`、`snapshot.py`。
- Web：`src/shiliu/static/search.css`、`src/shiliu/static/search.js`、`src/shiliu/templates/search.html`。
- Tests：`test_bilibili_jump_url.py`、`test_eval_candidate_pool.py`、`test_eval_gold_lock.py`、`test_eval_metrics.py`、`test_eval_query_schema.py`、`test_eval_reporting.py`、`test_eval_review_packet.py`、`test_eval_runner.py`、`test_eval_snapshot.py`、`test_search_display_metadata.py`、`test_search_page.py`。

## 4. V3 Frozen Baseline Integrity

| Component | Status | Evidence | Risk |
|---|---|---|---|
| FTS5 / BM25 | Confirmed Unchanged | `INDEX_VERSION=v3-stage1-lexical-v1`；无 local diff | 无 |
| Qwen model/dimension | Confirmed Unchanged | Qwen3-Embedding-0.6B、512d、revision/hash 与 Snapshot 一致 | 无 |
| Dense pooling/normalization | Confirmed Unchanged | `mrl-first-512-normalized`，无 diff | 无 |
| RRF | Confirmed Unchanged | `v3-stage2-rrf-v1`、`rrf_k=60` | 无 |
| Auto routing | Confirmed Unchanged | Planner 无 diff | 无 |
| Query type rules | Confirmed Unchanged | `classify_query()` 无 diff | 无 |
| Chunk policy | Confirmed Unchanged | 800 target / 1200 max / 120s / trailing overlap | 无 |
| Window merge | Confirmed Unchanged | 20 seconds | 无 |
| Same-video grouping | Confirmed Unchanged | `SearchResultConsolidator` 无 diff | 无 |
| Search ranking | Confirmed Unchanged | local Product delta 只增加 display metadata/jump URL | 无 ranking 风险 |
| Structured filters | Confirmed Unchanged | Planner/filter code无 diff | 无 |
| Incremental lifecycle | Confirmed Unchanged | coordinator/service 无 diff | 无 |
| V3 Snapshot | Confirmed Unchanged | DB SHA-256 `61589a…c4e1`；372/372 Artifact hash 匹配 | 无 |
| V3 Gold | Unknown | 文件可解析、tests 通过，但资产未被 Git 跟踪，也无独立外部 frozen hash 可比 | Main Session 应确认权威 hash |
| V3 formal metrics | Unknown | 当前报告可解析，但未被 Git 跟踪且未重跑 Formal Eval | 不得冒充重新验证结果 |

Live DB 与 Snapshot 的 `videos`、memberships、events、retrieval units、dense vectors/meta、sync state 已漂移；这是 Snapshot 后的 Live 增长，不是冻结 Snapshot 被修改。

## 5. Confirmed Search Contract

真实调用链：

```text
SearchRequest
→ SearchPlanner.plan() → SearchPlan
→ SearchOrchestrator.search()/search_raw()
→ RetrievalService / SQLiteExactDenseIndex / HybridRetrievalService
→ RawSearchResponse[RawSearchHit]
→ SearchResultConsolidator.consolidate()
→ EvidenceEnricher.enrich()
→ ProductSearchService.search()
→ ProductSearchResponse[ProductVideoResult]
→ CLI 或 POST /api/search
```

关键入口：

- Internal Raw：`SearchOrchestrator.search(request: SearchRequest) -> RawSearchResponse`
- Named Raw boundary：`search_raw(request: SearchRequest) -> RawSearchResponse`
- Product：`ProductSearchService.search(request: ProductSearchRequest) -> ProductSearchResponse`
- CLI：`shiliu retrieval search`
- API：`POST /api/search/raw`、`POST /api/search`
- 代码证据：[orchestrator.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/orchestrator.py:124)、[product_search.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/product_search.py:142)、[web.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/web.py:297)。

简化输入：

```python
SearchRequest(
    query="RAG 工作机制",
    mode="hybrid",
    scope="transcript_chunk",
    raw_top_k=20,
    filters=SearchFilterRequest(folder_id=123),
)
```

简化 Raw 输出：

```python
RawSearchResponse(
    trace_id="…",
    executed_mode="hybrid",
    index_identity={
        "lexical_index_version": "v3-stage1-lexical-v1",
        "dense_index_version": "v3-dense-qwen3-0.6b-mrl512-v1",
        "fusion_version": "v3-stage2-rrf-v1",
    },
    raw_hits=(RawSearchHit(
        unit_id="transcript_chunk:bilibili:BV…:p1:chunk_…",
        video_id=77,
        unit_type="transcript_chunk",
        rank=1,
        score=…,
        retrieval_method="hybrid_rrf",
        subtitle_source="ai",
        start_time=…,
        end_time=…,
        excerpt="…",
    ),),
)
```

字段对照：

| 字段 | Request | Raw hit/response | Product |
|---|---|---|---|
| query/mode/scope/filters | 有 | plan 中有 | plan 中有 |
| video_id | — | 有 | 有 |
| retrieval_unit_id | — | `unit_id` | `best_unit_id`、component IDs |
| chunk_id | — | 未单独保留；编码在 `unit_id` | `best_chunk_id` 实际为 unit ID |
| unit_type | — | 有 | `best_unit_type` |
| text | — | `excerpt` | match/window excerpt |
| start/end | — | 有 | window/anchor times |
| score/rank | — | 有 | best score/rank |
| retrieval_method | — | 有 | 聚合 methods |
| source_type | — | `subtitle_source` | window `subtitle_sources` |
| index_version | — | response `index_identity` | Product Result 中丢失 |
| trace_id | — | response level | response level |
| parent/raw references | — | 无 parent | component unit IDs/raw ranks |

**Confirmed Fact** — 调用方无需直接读 DB；Service 自己读取 DB/Artifact。

**Blocking Risk** — 构造 Service 会执行 `CREATE TABLE IF NOT EXISTS`，每次搜索会写 Raw Trace，Product Search 还会写 Presentation Trace。

**Recommendation** — 已接近 `search_library(SearchRequest) -> SearchCandidateSet`；缺的是局部 Adapter/contract projection，以及明确的 `persist_trace=False` 或隔离 Eval DB 机制，不需要大规模 Retrieval 重构。

## 6. Confirmed Subtitle and Segment Facts

- Artifact 定位：`videos.raw_subtitle_path` 指向 `subtitle-raw.txt`，解析器以同目录 `subtitle-raw.json` 为权威。
- Parser：[domain.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/domain.py:116)、[service.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/service.py:480)、[enrichment.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/enrichment.py:150)。
- 顶层 Schema：JSON array。
- Segment：`{"from": float seconds, "to": float seconds, "content": str}`。
- Pydantic 当前不约束 `start >= 0`、`end >= start`、排序或 overlap；extra fields 被忽略。
- Official/Platform Subtitle：Bilibili body 的 `from/to/content` 直接保存，时间单位为秒。
- ASR：Paraformer `begin_time/end_time` 毫秒除以 1000，负值归零，`end=max(begin,end)`。
- Source 枚举：`human | ai | asr | unknown`。
- Language 枚举：仅 `zh | en`。官方取 track language；ASR 用字符启发式检测，可信边界有限。
- 官方示例：`{"from":0.266,"to":1.5,"content":"如果你是产品经理"}`，source=`human`。
- ASR 统一示例：`{"from":0.03,"to":6.55,"content":"做A方向…"}`
- 无字幕示例：video 23，`raw_subtitle_path=NULL`、status=`skipped_no_subtitle`、error=`no_supported_subtitle`。
- Snapshot source 分布：5 human、120 AI（其中 119 zh/1 en，1 条没有 Raw path）、5 ASR、14 null。

身份与版本：

- 显式 `segment_id`：不存在。
- 数组 index：Artifact 中不保存，仅运行时 `enumerate()`。
- Segment identity 派生：不存在。
- DB / Retrieval Unit 中 Segment ID：不存在。
- 同一 Artifact 重读：数组 index 可重复，但只是假设 Artifact 不变。
- 跨索引重建：**Unknown**；没有 Segment ID contract/test。
- Artifact Version：Runtime Artifact 没有 `artifact_id/version/hash/generated_at/source_updated_at`。
- Snapshot Manifest 有 Artifact SHA-256，但 Retrieval Unit 不保存它。
- Provider/model：ASR DB 有 provider/model；统一字幕 Artifact 本身没有。
- `source_version_mismatch`：当前无法检测。

**Recommendation** — V3.5 可局部增加 `source_artifact_hash + segment ordinal + time/text digest` 的确定性引用，不必修改 V3 ranking；是否需要回填 Live/Snapshot DB 由 Main Session 决定。

## 7. Chunk-to-Segment Mapping

Chunk 构建事实：

- 完整 Segment 拼接，不切割 Segment。
- 空文本 Segment 在 Chunk 前被过滤。
- 文本使用 `strip()` 后以单个空格拼接。
- Chunk 保存：`chunk_id/start/end/text/content_hash/segment_count`。
- 不保存：segment IDs、segment indices、原数组范围、Artifact path/hash/version。
- Chunk ID 输入：platform、source_id、part、source_type、start、end、chunk text hash。
- overlap：当前 Chunk 至少两段且还有后续时，下一个 Chunk 从前一个 Chunk最后一个完整 Segment开始。
- 当前 dedup 只按 `unit_id` 去重 Chunk；无法把两个不同 parent Chunk 中的同一 Raw Segment 去重。
- 不会因相同文本直接合并两个不同 Segment；但未来若用纯 text key，会有误合并风险。

只读映射示例：

| Retrieval unit | Artifact | Segment indices | Time | Relationship |
|---|---|---:|---|---|
| `…BV1G29EBGE8b…chunk_da39154…` | Snapshot `BV1G29EBGE8b/subtitle-raw.json` | 0–46 | 0.04–118.36s | 重建文本与 `source_text` 完全相等，hash 匹配 |
| `…BV1JLN2z4EZQ…chunk_da080a…` | Snapshot `BV1JLN2z4EZQ/subtitle-raw.json` | 0–54 | 0.04–118.72s | 重建文本完全相等，hash 匹配 |

**Confirmed Fact** — 在同一冻结 Artifact 上，可以通过重跑当前 Chunk 算法确定性恢复映射。

**Blocking Risk** — DB 中没有直接 mapping；若 Artifact 顺序、空白、时间或文本变化，必须先验证 Source hash，不能对新 Artifact 做模糊反向匹配。

时间权威：

- 单段 start/end：Raw `from/to`。
- 多段 Span：第一段 `from` 至最后一段 `to`。
- Chunk/AI Chapter 不能覆盖 Raw Segment 时间。
- Bilibili jump 优先使用 Enricher 匹配到的 Raw Segment start；失败时退回 Chunk start，再 floor 到整数秒。
- Snapshot 65,024 个 Segment：0 空文本、0 零时长、0 负/反向；发现 1 个非单调/跨段 overlap 案例。

## 8. Trace and Eval Assets

### Trace

- Raw Trace table：`retrieval_search_traces`。
- Presentation Trace table：`retrieval_search_presentations`。
- Snapshot 含 82 Raw + 52 Presentation traces。
- Raw Trace 有：query、规划字段、mode、filters、candidate counts、简化 raw hits、fallback、index/model identity、latency、status/error。
- Raw Trace 的 persisted hits 只含 unit ID/rank/scores；不含完整 text/time/source/video。
- Presentation Trace 有聚合统计和简化 window/group summary；不保存完整 Product response。
- 两者默认写入传入的 DB；Live Service 即写 Live DB。
- 无独立 Evidence/Sufficiency Trace schema。
- **Recommendation** — 扩展当前 trace family 即可，不需要完全独立系统；Eval 必须指向隔离 DB。

### Snapshot / Gold / Eval

权威候选输入：

- Manifest：[corpus_manifest.json](/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_eval/corpus_manifest.json)
- Snapshot DB：`/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db`
- Artifact root：同目录 `artifacts/`
- Locked queries：[eval_queries.locked.jsonl](/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_eval/eval_queries.locked.jsonl)
- Locked Gold：[eval_gold.locked.jsonl](/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_eval/eval_gold.locked.jsonl)
- Human ledgers：original + amended decisions JSONL。
- Protocol：[V3_EVAL_PROTOCOL.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_eval/V3_EVAL_PROTOCOL.md)
- Failure cases：[failure_cases.md](/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_eval/failure_cases.md)
- Results：`eval_results.json/csv`、per-query results、summary、diagnostics。
- Snapshot ID：`20260720T094346Z_c7663365`
- Snapshot DB SHA-256：`61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`
- 429 manifest records：372 present/hash-match，57 `not_declared`，0 missing/mismatch。

**Recommendation** — V3.5 Seed 使用上述 Snapshot DB + Snapshot Artifact root + locked queries/Gold；禁止使用已增长的 Live DB。

## 9. Existing Interval Mapping

`mapped_segment_count` 使用 Gold 中明确批准的 inclusive index 范围；Gold 边界与相邻 Segment 端点相接时，纯闭区间 overlap 查询会多包含边界邻段，因此运行时应采用明确半开/ordinal contract。

| case_id | query_id | video_id | gold_start | gold_end | artifact_status | mapped_segment_count | mapping_status | risk |
|---|---|---:|---:|---:|---|---:|---|---|
| Q01-V78 | Q01 | 78 | 62.96 | 72.70 | ok/hash match | 3 | exact continuous | Low |
| Q02-V77 | Q02 | 77 | 170.90 | 180.56 | ok/hash match | 2 | exact continuous | Low |
| Q03-V40 | Q03 | 40 | 6.88 | 10.44 | ok/hash match | 1 | exact continuous | Low |
| Q04-V117 | Q04 | 117 | 119.23 | 125.65 | ok/hash match | 2 | exact continuous | Low |
| Q06-V83 | Q06 | 83 | 5.74 | 9.379 | ok/hash match | 1 | exact continuous | Low |
| Q07-V38 | Q07 | 38 | 3.42 | 15.35 | ok/hash match | 7 | exact continuous | Low |
| Q08-V30 | Q08 | 30 | 28.23 | 32.96 | ok/hash match | 1 | exact continuous | Low |
| Q10-V135 | Q10 | 135 | 1.12 | 6.30 | ok/hash match | 2 | exact continuous | Low |
| Q15-V78 | Q15 | 78 | 62.96 | 72.70 | ok/hash match | 3 | exact continuous | Duplicate interval by design |
| Q17-V117 | Q17 | 117 | 175.45 | 183.32 | ok/hash match | 2 | exact continuous | Low |

全部 10 个可安全作为 V3.5 Evidence Seed；它们都是 Snapshot source=`ai`、language=`zh`，且不涉及发现的 video 88 非单调案例。

## 10. Provider and Structured-output Assets

| 项目 | 结论 |
|---|---|
| Adapter | `OpenAICompatibleProvider`，`/chat/completions` 与 `/models` |
| Confirmed Configured Candidate | `deepseek-v4-flash`（fast transcript role） |
| Confirmed Configured Candidate | `deepseek-v4-pro`（formal roles） |
| Unknown Availability | 未调用 Provider，不能确认当前账户/endpoint 可用 |
| ASR configured | DashScope `paraformer-v2`，不是 Selector 候选结论 |
| Temperature | 仅 `thinking_enabled=False` 时固定为 0；不是通用调用参数 |
| Native JSON Schema | 不支持；未发送 `response_format/json_schema` |
| Plain JSON mode | Prompt 约束“JSON only”，不是 Provider 原生 JSON mode |
| Validation | Pydantic `model_validate` |
| JSON extraction | 支持 fenced JSON 和从首 `{` 到末 `}` 的提取 |
| JSON repair | Taxonomy `AuditedJsonCaller`/single-flight workflow 已存在 |
| Retry | Provider 本身无自动 retry；业务 workflow 对 retryable error/repair 做有限重试 |
| Timeout | 支持，默认 120 秒 |
| Raw output | `complete_raw()` 返回 content/usage/id/reasoning；taxonomy workflow 可持久化 raw ledger |
| Token/cost/latency | usage 与 elapsed 可记录；DB 有 cost fields，但 adapter 不自行计算价格 |
| Reuse | Provider 实例可复用 |
| Fake/Stub | 多个测试 Fake Provider、Fake Client、blocking provider |
| Secret handling | LLM/ASR API Key 通过 macOS Keychain reference，不是环境变量；未输出 secret |

证据：[llm.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/llm.py:28)、[provider_single_flight.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/taxonomy/provider_single_flight.py)。

**Recommendation** — V3.5 可以复用 Pydantic validation、raw retention、single-flight repair 和 timeout，但应做局部无 Agent Framework 的调用封装；不需要新通用 Provider 基础设施。

## 11. API and UI Insertion Points

**Recommendation**

- Internal：在 `ProductSearchService.search()` 返回后、任何 Answer 阶段前，增加独立 Evidence Resolution service。
- API：先新增隔离的 read-only Evidence endpoint，输入 `trace_id/video_id/component unit IDs` 或完整候选集；不要改变 V3 ranking。
- Search main flow：无需重写；现有 Product Result 已暴露 windows、source、time、methods、component IDs。
- UI：最小插入点是 `search.js::renderWindow()` 下方的 Evidence Preview；可复用现有 jump URL。
- Transcript detail：现页面显示整理后的 Markdown；Raw Subtitle 已有 `/media/{video_id}/raw-subtitle`，Evidence Preview 应直接从 Raw JSON-backed service 取片段，不把整理稿当权威。
- Error mapping：FastAPI 当前用结构化 `error.code/stage/message/trace_id`。
- 当前 Web 可显示 source、time、status/fallback；method 只作为响应字段，没有直接显示全部 method。
- 未发现迫使 V3.5 重写 Search Surface 的问题。

## 12. Test Baseline

```text
Current Run
```

Exact command：

```bash
PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -B -m pytest -q -p no:cacheprovider
```

结果：

- Exit code: `0`
- Collected/passed: `518`
- Failed: `0`
- Skipped: `0`
- Warnings: `7`
- Wall time: approximately `7.0s`
- Warning composition：1 Starlette/httpx deprecation + 6 multiprocessing fork deprecations。
- Before/after worktree：完全一致；未产生 pytest cache、bytecode 或 tracked/untracked delta。

```text
Historical Baseline
518 passed / 0 failed / 7 warnings
```

该历史结果本轮已被当前运行重新验证，不再只作为历史声明。

## 13. Error-taxonomy Readiness

| Required error | Readiness | Existing mapping |
|---|---|---|
| index_not_ready | Partially Representable | `dense_not_ready`、`dense_rebuild_required`、`local_model_not_ready` |
| retrieval_failed | Already Representable | `retrieval_internal_error` / structured stage |
| candidate_not_found | Missing | 空结果不是结构化错误 |
| raw_subtitle_missing | Partially Representable | `subtitle_unavailable` warning、`no_supported_subtitle` |
| source_version_mismatch | Missing | 无 source version contract |
| evidence_not_found | Missing | 无 Evidence stage |
| selector_invalid_output | Partially Representable | 通用 `invalid_model_output` 可复用，但尚无 Selector mapping |
| selector_unavailable | Missing | 无 Selector stage |
| sufficiency_unavailable | Missing | 无 Sufficiency stage |
| insufficient_evidence | Missing | 无 Sufficiency result/error |
| unverifiable_source | Partially Representable | Artifact missing/parse warning可检测，但无统一 code |
| timeout | Partially Representable | Provider/upstream timeout存在；Search/Evidence 没有统一 timeout code |

## 14. Findings Ledger

### F-01

- Category: **Confirmed Fact**
- Finding: V3 Search 已有稳定内部 Python boundary 和 API/CLI 入口。
- Evidence: `SearchOrchestrator.search_raw()`、`ProductSearchService.search()`。
- Impact on V3.5: 只需局部 candidate projection，不需重构 V3 Retrieval。

### F-02

- Category: **Blocking Risk**
- Finding: Search Service 构造与调用具有 DB schema/trace 写副作用。
- Evidence: `initialize_schema()`、`_persist_trace()`、`_persist_presentation()`。
- Impact on V3.5: 冻结 Eval 必须使用隔离 DB 或显式 no-persist contract。

### F-03

- Category: **Confirmed Fact**
- Finding: Raw Segment 无稳定 ID，Chunk 无 segment references。
- Evidence: `SubtitleSegment` 只有 `from/to/content`；`RawSubtitleChunk` 只有 count。
- Impact on V3.5: Evidence 引用不能仅绑定数组 index 或 Chunk ID。

### F-04

- Category: **Blocking Risk**
- Finding: Runtime 没有 Artifact version/hash，不能检测 source version mismatch。
- Evidence: videos/retrieval_units schema 与 Artifact JSON 均无版本字段。
- Impact on V3.5: Citation 可能在字幕重抓/ASR 重跑后失去来源一致性。

### F-05

- Category: **Confirmed Fact**
- Finding: Snapshot 完整且 hash 自洽；Live DB 已漂移。
- Evidence: Snapshot DB SHA 匹配，372 Artifact hash 匹配；Live 为 145 videos/1565 units。
- Impact on V3.5: Seed 输入必须固定到 Snapshot。

### F-06

- Category: **Confirmed Fact**
- Finding: 10/10 Approved Intervals 可映射到连续 Raw Segments。
- Evidence: 只读 Snapshot DB + Artifact 查询。
- Impact on V3.5: 可建立初始 Evidence Seed，无需重新标注。

### F-07

- Category: **Blocking Risk**
- Finding: video 88 Raw Artifact 有一次时间重置。
- Evidence: index 1388 `2767.133s`，index 1389 `0.133s`。
- Impact on V3.5: Candidate Builder 必须验证单调性/分段，不能默认全库单调。

### F-08

- Category: **Inference**
- Finding: 同一冻结 Artifact 上重跑 Chunker可稳定恢复映射。
- Evidence: 两个示例 text/hash exact；Chunk ID 输入确定性。
- Impact on V3.5: 可作为迁移前的局部恢复机制，但不能代替显式 source-version contract。

### F-09

- Category: **Unknown**
- Finding: Locked Gold 与正式 metrics 的外部冻结 hash 未在本地权威 manifest 中确认。
- Evidence: 文件可解析但 untracked。
- Impact on V3.5: Main Session 应确认其 canonical hash 后再冻结 V3.5 Eval。

### F-10

- Category: **Recommendation**
- Finding: 复用现有 Trace、Pydantic/repair、Search/UI surface，局部增加 Evidence contract。
- Evidence: 现有组件边界清晰。
- Impact on V3.5: 避免 V3 ranking、Agent Harness 或 Segment Dense Index 变更。

## 15. Escalation Assessment

### Data / Eval Escalation

```text
Original Assumption
Raw Segment 可以被稳定引用，并能绑定到具体 Source Version。

Local Fact
没有 segment_id、artifact_id/version；只有 Snapshot manifest hash。
10 个 Seed 可映射，但全库有一个非单调 Artifact。

Impact
V3.5 Runtime citation 和 source_version_mismatch 目前不能可靠实现；
冻结 Seed 本身可继续使用。

Options
1. 以 Snapshot Artifact SHA-256 + ordinal + segment digest 建立局部引用。
2. 为全库新增持久化 Segment identity/version contract。
3. 暂时只支持冻结 Snapshot Seed。

Codex Recommendation
先采用选项 1，并对非单调 Artifact 做显式 validation/failure；
不要启动大规模重处理或 Segment Dense Index。

Decision Needed
Main Session 是否批准局部 Source-Version/Segment-ID contract，以及是否要求 Live 数据回填。
```

### Architecture Escalation

```text
Original Assumption
Search 可以作为 read-only candidate provider 使用。

Local Fact
Service 初始化会建表；成功、错误和 Product presentation 都会写 Trace。

Impact
直接对冻结 Snapshot DB 调用会修改它，违反 Eval 隔离。

Options
1. 使用 pool_work.db/独立 Eval work DB。
2. 增加 no-persist/read-only adapter。
3. 接受在 Live DB 写 Trace。

Codex Recommendation
冻结 Eval 采用隔离 work DB；产品运行保留 Trace。
如 V3.5 要求严格 read-only Python boundary，再做最小 no-persist adapter。

Decision Needed
Main Session 选择隔离 DB 还是显式 no-persist contract。
```

未发现必须修改 V3 Frozen Ranking、引入 Segment Vector Infrastructure、绑定 Agent Harness 或进入 V4 的理由。

## 16. Proposed Minimal Supplementary Audit

```text
Question
1. video 88 的时间重置是多 P/拼接语义还是损坏 Artifact？
2. Locked Gold 与 formal results 的 canonical frozen hash 是什么？

Why blocking
前者决定 Candidate Builder 的单调性失败策略；
后者决定哪些 untracked Eval 文件可被正式视为 V3.5 Seed 权威输入。

Exact read-only checks
- 读取 video 88 metadata/cid/part 与重置点前后少量 Segment；
- 读取 Stage 6B 生成记录中的 Gold/results hash；
- 对 locked queries、locked Gold、formal results 计算 SHA-256 并与权威记录比较。

Maximum additional time
15 minutes
```

## 17. Exact Commands Executed

主要 shell 命令入口如下；所有 Python heredoc 均为只读 JSON/SQLite 查询：

```bash
pwd
pwd -P
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git rev-parse HEAD
git diff --stat
git diff --name-status
git diff --cached --stat
git diff --cached --name-status
git submodule status
find . -mindepth 2 -type d -name .git -print
rg --files ...
rg -n ... src/shiliu ...
sed -n ... <audited files>
nl -ba ... <audited files>
git diff --unified=2 -- src/shiliu/retrieval/product_search.py src/shiliu/retrieval/__init__.py src/shiliu/web.py src/shiliu/templates/base.html
git log -1 --stat --oneline
git log --oneline --decorate -5
jq . research/v3_eval/corpus_manifest.json
jq . research/v3_eval/eval_results.json
jq . research/v3_eval/gold_lock_audit.json
jq . research/v3_eval/human_ledger_amendment_audit.json
wc -l research/v3_eval/*.jsonl
shasum -a 256 /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest --collect-only -vv -p no:cacheprovider
git ls-files --others --exclude-standard
git status --short
```

未执行 Search、Provider、Sync、Reconcile、Index rebuild、Formal Eval 或 Snapshot generation。

## 18. Stop Statement

```text
Phase 0 read-only audit is complete.

No code, database, index, Gold, Snapshot, Prompt, Policy, or product behavior was intentionally modified.

No V3.5 implementation was started.
No V3 Retrieval tuning was performed.
No V4 work was started.

Additional recommendations were recorded only and were not implemented.
```
