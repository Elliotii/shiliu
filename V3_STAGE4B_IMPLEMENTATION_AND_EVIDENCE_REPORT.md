# Shiliu V3 Stage 4B Implementation and Evidence Report

## 1. Scope and Integrity

**[Confirmed Fact]** 本轮只实现 Stage 4B 的 post-retrieval Product Result
Consolidation：同视频分组、时间证据窗口、确定性字幕锚点、辅助 AI Chapter、Product
API/CLI 和 Presentation Trace。没有修改 Stage 4A Planner、Auto Router、fallback、
BM25、Dense、RRF、Chunk、timestamp 或 Product Hooks。

开始时执行了 `pwd`、`git status --short`、`git diff --stat`、
`git diff --cached --stat` 和 `git status -sb`；既有未提交 V3 工作均被保留。

正式 Smoke 前后五张 Product Source 表哈希完全一致，Retrieval/FTS/Dense 保持
`1547/1547/1547`。

## 2. Read-only Evidence Map

修改前以源码、正式数据库和真实 Artifact 完成以下 Map：

| # | Actual module / artifact | Current schema or behavior | Stage 4B use / guess risk |
| ---: | --- | --- | --- |
| 1 | `retrieval/orchestrator.py`, `RawSearchHit/RawSearchResponse` | 有序 rank、score、unit/video/type、组件分数、title/uploader/source、start/end、300-char excerpt | Consolidator 唯一输入；猜错会破坏排序/证据 |
| 2 | `Application.search_orchestrator`、Raw API、CLI | 共同调用 `SearchOrchestrator.search` | Product service 复用命名边界 `search_raw`; 不复制检索 |
| 3 | `retrieval_search_traces`、`_persist_trace` | UUID trace、Plan/mode/timing/identity、有限 Unit 排名证据 | Presentation 用同一 trace_id；猜错会断开 Stage 6 对照 |
| 4 | `retrieval_units.video_id -> videos.id` | 每个 Unit 有稳定 `video_id` | 同视频 Group key；不能从标题推断 |
| 5 | `videos` | `title,uploader,source_id,video_url,duration_seconds` | canonical Product metadata；Raw Hit 仅作缺失降级 |
| 6 | DB `raw_subtitle_path` 的同目录 `subtitle-raw.json` | 正式样本绝对路径 `/Users/elliot/Documents/Shiliu/videos/<BVID>/subtitle-raw.json`，顶层 array | Anchor authoritative reader；不能把 `.txt` 当 JSON |
| 7 | `domain.SubtitleSegment` | AI/Human/ASR 均归一为同一模型 | 不按来源重写历史 Artifact |
| 8 | Raw Segment JSON | 实际键 `from,to,content`；模型字段 `start,end,content` | jump_time 只取 `start`；猜字段会伪造 fallback |
| 9 | `summary[.<active_revision>].json` / `summary.json` | object；真实正式样本含 `important_chapters` | Chapter reader按现有 revision fallback |
| 10 | `domain.ImportantChapter` | `title,start_seconds,summary` | 派生 interval；不能使用 Prompt 示例字段 |
| 11 | `videos.duration_seconds` | Materialized Product duration，`>0` 才可靠 | 仅派生末 Chapter end |
| 12 | `orchestrator._raw_hit` | `matched_excerpt[:300]` | 无字幕 Anchor 时的 bounded fallback |
| 13 | `web.py` | FastAPI handler + Pydantic `BaseModel` + structured JSON error | `ProductSearchRequest` 遵循同一风格 |
| 14 | `cli.py` Retrieval search branch | 所有 filters 已集中构造 | `--grouped` 只切换 shared service，不复制逻辑 |
| 15 | `GET /api/search/traces/{trace_id}` | Stage 4A 返回 `trace` raw object | 保留 `trace` 兼容键并新增 `raw_trace,presentation` |

**[Confirmed Fact]** 正式 Raw 样本为 106 段且键严格为 `content/from/to`；正式 Summary
样本为 object，Chapter 键严格为 `start_seconds/summary/title`。

## 3. Architecture

```text
ProductSearchRequest
  -> Stage 4A SearchOrchestrator.search_raw
  -> ordered RawSearchHit[]
  -> SearchResultConsolidator
  -> EvidenceEnricher
  -> ProductSearchResponse
  -> best-effort retrieval_search_presentations
```

实现文件：

- `src/shiliu/retrieval/consolidation.py`
- `src/shiliu/retrieval/enrichment.py`
- `src/shiliu/retrieval/product_search.py`

`SearchResultConsolidator` 不读 Retriever/FTS/Embedding；`EvidenceEnricher` 只读 Product
metadata、raw subtitle 和 Summary Artifact；`ProductSearchService` 是 API/CLI 共享薄入口。

## 4. Product Search Request

`ProductSearchRequest` 复用 Stage 4A 的 `query/mode/scope/SearchFilterRequest`：

```text
mode default: lexical
scope default: all
result_limit: 1..20, default 10
max_windows_per_video: 1..5, default 2
extra fields: forbidden
```

未重新实现 normalization、classification 或 routing。

## 5. Raw Over-fetch

内部固定计算：

```text
raw_top_k = min(100, max(50, result_limit * 5))
```

正式 `result_limit=10` 均传入 `raw_top_k=50`。Grouped API 不暴露 raw_top_k，也不做
二次检索或分页补召回。

## 6. Raw Hit Deduplication

先按 `unit_id` 去重；重复时保留 `(rank asc, score desc, unit_id asc)` 最优记录，并记录
`duplicate_raw_hit_count`。正式 18 个 Product 请求均为 0；自动测试注入重复 Unit，证明
稳定保留更高 Raw rank。

## 7. Same-video Grouping

去重后的 Hits 按 `video_id` 合并。Video Hit 与 Chunk Hits 进入同一 Group；最终每个
Video 只返回一个主结果。Group 记录 best Unit、命中 Unit 数、Chunk 数、Video Hit
存在性、retrieval methods、窗口总数与未窗口化 Chunk 数。

正式 OpenAI：50 Raw Hits -> 21 unique Videos，duplicate occupancy 29（0.58）；只返回
10 个 Video Groups。首组 Video 85 含 4 Units，但只占一个 Product Result。

## 8. Group Ranking

排序严格为：

```text
best_raw_rank ascending
best_score descending
video_id ascending
```

没有 Chunk score 求和、命中数加分、跨方法归一化或重新运行 RRF。自动测试证明一个
拥有更多高分 Chunks 的长视频不会越过 best Raw rank 更高的视频。

## 9. Temporal Evidence Consolidation

版本 `v3-temporal-consolidation-v1`，固定 merge gap 20 秒。有效 Chunk 按
`start,end,raw rank,unit_id` 排序，若 `next.start <= current.end + 20` 则链式合并；
窗口边界取组件 min start / max end。

缺失、非有限、负数或 `start>end` 的 Chunk 不进入窗口，计入
`unwindowed_chunk_count`，但仍保留在 `matched_unit_count`。

## 10. Window Ranking

窗口按最佳组件相关性而非时间排序：

```text
window_best_rank ascending
window_best_score descending
window_start ascending
```

内部先生成全部窗口，再按 `max_windows_per_video` 裁剪；其余通过
`additional_window_count` 表达。组件 Unit IDs、Raw ranks、methods 与 subtitle sources
全部保留。

## 11. Query-aware Jump Anchor

版本 `v3-query-aware-anchor-v1`。Query/Segment 匹配视图使用 NFKC、casefold 和空白折叠，
不改写、不翻译 Query。匹配优先级：

1. 完整 normalized query phrase -> `exact_query_phrase/high`；
2. ASCII technical entity -> `exact_entity_term/high`；
3. keyword coverage -> `keyword_overlap/medium`；
4. best Chunk start -> `chunk_start_fallback/fallback`。

支持 C++、C#、GPT-5、Qwen3-Embedding-0.6B 等符号/版本词项，过滤明确低信息 stopwords。

## 12. Subtitle Segment Authority

精确锚点只扫描当前窗口 `start-1s .. end+1s` 覆盖的 authoritative Raw Subtitle
Segments；`jump_time` 只取命中 Segment 的 `from/start`。Semantic Question 始终使用最佳
Chunk start，不冒充句子级定位。字幕缺失或损坏同样降级 Chunk start。

## 13. Evidence Excerpt

优先使用 Anchor Segment 前后各一个真实字幕 Segment，最大 300 字符；其次使用 Stage
4A best Chunk excerpt；最后为空。Product Presentation Trace 不保存 excerpt、完整
Chunk、字幕或 Transcript。

## 14. AI Chapter Enrichment

版本 `v3-ai-chapter-enrichment-v1`。Chapter 按有效 `start_seconds` 排序并稳定去重：

- 中间 end 来自下一 Chapter start；
- 最后 end 来自可靠 Video duration；
- 无 duration 时 open-ended。

使用 jump_time（不可用才用窗口 midpoint）选择最近且不晚于 target 的 Chapter。
返回 title、最多 240 字符 summary、start、derived end、source 和 boundary type。

**[Confirmed Fact]** Chapter 不参与召回、Group/Window ranking、merge 或 jump_time；测试
明确证明 Chapter start 不覆盖 raw Segment jump_time。

## 15. Product Result Schema

`ProductVideoResult` 返回 canonical Video ID/BVID/title/uploader/URL/duration、best Raw
identity/rank/score、Unit/Chunk 计数、Video Hit flag、methods、窗口、总/额外窗口与
unwindowed count。

每个窗口返回边界/duration、best Chunk、组件 IDs/ranks、methods/sources、jump
evidence、bounded excerpt 和 optional Chapter。

`ProductSearchResponse` 同时返回 Raw trace/plan/mode/fallback、over-fetch、occupancy、
group counts、warnings 和分阶段 timing。

## 16. Product Presentation Trace

新增 additive `retrieval_search_presentations`，与 Raw Trace 共用 `trace_id`。记录四个
版本、limits、merge gap、Raw/Video/occupancy/group/window/anchor/chapter counts、各阶段
timing、status/error 和有限 group summary。

`group_summary_json` 仅保存 video_id、best rank、Unit 数、窗口边界/jump、best/component
Chunk IDs、额外窗口数和 Chapter title。正式检查确认无 `excerpt` 或正文 `summary`。

写 Trace 失败时 Product Search 仍 HTTP 200，并返回
`presentation_trace_persisted=false` 与 bounded error。

## 17. Product Search API

新增 `POST /api/search`，保留 `POST /api/search/raw` 原语义。Raw Search 的
400/409/503/500 结构化错误原样传播；Artifact 局部失败进入 bounded warnings 并保持
HTTP 200。

Trace lookup 兼容返回：

```json
{"trace": raw_trace, "raw_trace": raw_trace, "presentation": object_or_null}
```

真实 Raw-only Trace `18900e3b-552e-4f30-95f9-c0e3abd02510` 的
`presentation=null`，旧 `trace.status=success` 仍成立。

## 18. CLI Integration

新增：

```bash
.venv/bin/shiliu retrieval search QUERY --grouped \
  --result-limit 10 --max-windows 2 --trace
```

无 `--grouped` 时保持 Stage 4A Raw 输出；Grouped 调用同一个 `ProductSearchService`。
正式 CLI Trace `488ad41f-a2dd-4ced-98e1-614f4edf7eec`：OpenAI Auto/Lexical、50 Raw
Hits、21 unique Videos、返回 3 Groups，Presentation Trace 成功。

## 19. Automated Tests

每条命令均 exit 0、failed 0、skipped 0：

| Exact command | Passed | Warnings |
| --- | ---: | --- |
| `.venv/bin/python -m pytest tests/test_search_consolidation.py -q` | 10 | 0 |
| `.venv/bin/python -m pytest tests/test_search_enrichment.py -q` | 16 | 0 |
| `.venv/bin/python -m pytest tests/test_product_search_api.py -q` | 11 | 1 existing Starlette/httpx deprecation |
| `.venv/bin/python -m pytest tests/test_search_planner.py -q` | 19 | 0 |
| `.venv/bin/python -m pytest tests/test_search_orchestration.py -q` | 17 | 0 |
| `.venv/bin/python -m pytest tests/test_search_api.py -q` | 7 | 1 existing Starlette/httpx deprecation |
| `.venv/bin/python -m pytest tests/test_retrieval.py -q` | 13 | 0 |
| `.venv/bin/python -m pytest tests/test_dense_retrieval.py -q` | 9 | 0 |
| `.venv/bin/python -m pytest tests/test_retrieval_lifecycle.py -q` | 13 | 1 existing Starlette/httpx deprecation |
| `.venv/bin/python -m pytest -q` | 426 | 1 Starlette/httpx + 6 multiprocessing fork deprecations |

## 20. Formal Exact-entity Evidence

| Query | Raw | Unique Videos | Occupancy | Returned Groups | Top result |
| --- | ---: | ---: | ---: | ---: | --- |
| OpenAI | 50 | 21 | 29 / 0.58 | 10 | Video 85, 4 matched Units |
| MCP | 50 | 21 | 29 / 0.58 | 10 | Video 78, 5 matched Units |
| FAISS | 1 | 1 | 0 | 1 | Video 39 |
| LangGraph | 3 | 3 | 0 | 3 | Video 26 |

全部 `auto -> exact_entity -> lexical`。OpenAI/MCP 的同视频多 Raw Hits 均只形成一个
Video Group；精确窗口使用 raw Segment phrase anchors，部分有 auxiliary Chapter。

## 21. Formal Sustained-window Evidence

MCP Trace `c3f95eae-98b8-4f9a-862a-22e1f9658b13`，Video 78：

```text
Raw Chunks:
chunk_6c982f17915950d79bd4ab0f296e00ee
chunk_b054f1bd553c27a5e404f8c761765571
chunk_09db47653d9082ab4dbb23c9887824e4

Consolidated Window: 579.04–831.84 seconds
jump_time: 600.26
jump_source: exact_query_phrase
chapter: CLI vs MCP 深度对比
```

同 Group 共 5 matched Units（4 Chunks + 1 Video），但只返回一个 Product Result。

## 22. Formal Separated-window Evidence

同一 MCP Video 78 的另一个窗口为 `0.04–118.36s`，与
`579.04–831.84s` 之间远超 20 秒，保持两个窗口，没有错误合成长区间。第二窗口最佳
Raw rank 19，因此排在 rank 1 的 579s 窗口之后。

OpenAI Video 123 也形成 4 个窗口；返回的前两窗 `471.78–707.75s` 与
`2095.639–2214.71s` 明确分离。

## 23. Mixed-query Anchor Evidence

| Query / Trace | Result |
| --- | --- |
| MCP 协议 / `138d04f5-d66d-4642-9937-fedee8d969fa` | Hybrid；窗口同时出现 exact_entity_term/high 与 keyword_overlap/medium |
| OpenAI API 调用 / `9dfd696a-6aa5-4315-bb14-529f9589b076` | Hybrid；top window 126.98s，exact_entity_term/high |
| LangGraph 工作流 / `3d64a4f7-e095-4316-ba2d-edc3a541b5b1` | Hybrid；确定性 ASCII entity/keyword policy |

Anchor 只在所属窗口字幕内查找；没有使用 Chapter start 或 LLM 判断。

## 24. Semantic Fallback Evidence

两条正式 Semantic Query 均 `auto -> hybrid`：

- `491126d3-2d4a-4fb2-b87d-0d357b04471b`：34 windows，anchored count 0；
- `7e07d9ba-f1e0-48c1-b2d0-8583e52b26a8`：40 windows，anchored count 0。

所有展示窗口均 `jump_source=chunk_start_fallback`，jump_time 等于 best Chunk start。
报告不声称句子级语义定位。

## 25. Scope and Filter Evidence

OpenAI scope：

| Scope | Raw | Unique | Windows | Semantics |
| --- | ---: | ---: | ---: | --- |
| video | 20 | 20 | 0 | 每个 Video Hit 一个 Group |
| transcript_chunk | 44 | 21 | 34 | Chunk 按 Video 分组，均有窗口 |
| all | 50 | 21 | 34 | Video/Chunk 合并为同一 Group |

Filter 1：`folder_id=3876418799 + reading_state=unread`，Trace
`8f204f83-d4b6-40dc-9b0f-9a64894662bc`。Filter 2：
`uploader=chocpink_AI版 + marked=true`，Trace
`23c92f8b-5169-45ce-8124-b256f2b926b1`，6 Raw Hits 全部归为唯一 Video 34。
Filters 记录在 Raw Trace，说明发生在 Raw Retrieval；Grouping 未重新加入任何 Video。

## 26. Runtime Characteristics

18 个正式 Product Presentation Traces 均成功记录分阶段 timing。代表值：

- Exact OpenAI：Raw 50.82 ms，grouping 0.134 ms，anchor 68.856 ms，Chapter
  2.632 ms，trace 约 1.054 ms，total 125.386 ms；
- Exact MCP：total 45.91 ms；
- Mixed MCP 协议首次 Hybrid 包含 cold Qwen load：total 4419.846 ms；
- 后续 Mixed OpenAI API 调用：total 113.631 ms；
- Presentation DB write 的正式持久化值约 0.26–0.43 ms。

Artifact 在每个请求内按唯一 Video Group 读取一次；没有 per-Chunk 重复全文件读取，也没有
建设全局 Cache。Cold Qwen 仅为 Runtime observation，不是 Risk Gate。

## 27. Product and Index Integrity

前后相同：

| Table | Rows | SHA-256 |
| --- | ---: | --- |
| videos | 143 | `81fc4068762457fd554b6d5a0b185e2613e7c6c2b028e597816bc62cd6b83be9` |
| video_notes | 1 | `4acacc0cd3723d2698e9af4a1646953b09a2697baa565f894e6b85c1ad43077f` |
| favorite_sources | 2 | `36544248f5fdb32b349d2a648561e77da2f1b6022c53435e1620b31781f6686c` |
| video_source_memberships | 145 | `3fa7a410c693fc8a85b32c1c715bb22b07f003696ec06d269a63947a6b6d4efc` |
| events | 271 | `275036e4304cce1090fa4fc51d43e207a26c756a13e383e89625387cbb8ca1b2` |

正式 Raw Traces 由 29 增至 48；新增 18 个 Presentation Traces，全部 success。
Retrieval/FTS/Dense 仍为 `1547/1547/1547`；`integrity_check=ok`；
`foreign_key_check=[]`。Stage 4B 未写 Retrieval Units 或 Dense Vectors。

## 28. Remaining Limitations

**[Unknown]** 正式 Retrieval Eval、相关性指标、duplicate occupancy 对质量的净影响和
timestamp anchor error 尚未进入（Stage 6）。

**[Unknown]** Bilibili jump URL 的浏览器端到端行为与 Search Web UI 尚未实现（Stage 5）。

**[Confirmed Fact]** 某些连续命中 Chunks 可链式形成较长窗口；当前结果严格符合固定
20 秒规则，是否需要产品层最大窗口时长属于后续 Version-session 决策，未擅自增加规则。

## 29. Recommended Classification

**Accepted with Follow-up**。

证据满足 Stage 4B Acceptance Gate：同 Video 单结果、best Raw rank、20 秒合并边界、
分离窗口、组件证据、确定性字幕锚点、Semantic fallback、Chapter 辅助边界、共享
API/CLI service、Raw/Presentation Trace 关联、partial enrichment isolation，以及正式
Product/Index 不变。

Follow-up 仅为 Stage 5 UI、Stage 6 Eval 和 Version Session 对长窗口产品展示的复审；
不构成本轮 Needs Fix，也不授权继续。

## 30. Stop Boundary

Stage 4B 到此停止。未开始 Stage 5 Search Page/Result Cards，未开始 Stage 6 Formal
Eval，未加入 reranker、rewrite、LLM anchor、Segment vectors、Parent-child/Chapter
retrieval 或 V3.5。
