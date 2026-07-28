# Shiliu V3 — Stage 5 Web Search Surface and Evidence Report

## 1. Scope and Integrity

**[Confirmed Fact]** Stage 5 was limited to the Web presentation of the existing `POST /api/search` Product Search contract. No Planner, classifier, router, lexical/dense/hybrid retriever, grouping, temporal merge, anchor, chapter assignment, projection, provider, index, Product hook, or Stage 6 evaluation code was changed.

**[Confirmed Fact]** Authorized changes are confined to the search route/template/static assets, additive Product display metadata and jump URL helper, focused tests, browser screenshots, this report, and `V3_CURRENT_STATE.md`.

**[Confirmed Fact]** The audited branch is `codex/v3-domain-completion`; the Stage 5 starting HEAD was `8287c8d`. Formal database integrity remained `ok` and `foreign_key_check` remained empty. The first before/after hash pair was contaminated by the existing LaunchAgent's automatic startup sync; after that sync settled, an isolated `GET /search` plus formal `POST /api/search` retained every protected Product/Index count and hash (section 29).

## 2. Read-only Web Map

The required pre-change map was performed before implementation. “Minimal change” below describes the Stage 5 use actually selected.

| # | Actual location | Current behavior | Stage 5 usage / minimal change | Risk if guessed |
|---|---|---|---|---|
| 1 | `src/shiliu/web.py:create_web_app` | Creates FastAPI Web app and routes | Add `GET /search` to this factory | Route registered on wrong app |
| 2 | `src/shiliu/templates/` | Jinja templates | Add `search.html` | Template not found/runtime 500 |
| 3 | `src/shiliu/static/` plus Jinja blocks | Existing CSS/JS are separate assets | Add `search.css` and `search.js`; expose blocks in base | Inconsistent asset loading |
| 4 | `src/shiliu/web.py` `/`; `index.html` | Home/library waterfall | Keep unchanged; add shared-nav entry | Search ranking shown as masonry |
| 5 | `/videos/{video_id}/transcript`; `transcript.html` | Local video/full-text detail | Generate `detail_url` on backend | Broken/guessed detail URL |
| 6 | Same transcript route; `/media/{id}/raw-subtitle` is raw asset | Transcript is user-facing full text | Link to transcript page only | Linking raw data instead of detail |
| 7 | `videos.cover_url`, `videos.cover_path`; `/media/{id}/cover` | Local cover preferred where stored | Batch-enrich `cover_url` | Missing/broken cards |
| 8 | `videos.reading_state`, `is_marked`, `archived_at`, `is_ignored` | Product state and filters | Display reading/mark; send supported filters | Invented enum or default semantics |
| 9 | `favorite_sources` + active `video_source_memberships`; `Database.list_sources` | Folder title and membership | Route supplies options; service batch-enriches names | Raw IDs or stale memberships |
| 10 | `videos.source_id` (BVID), `videos.video_url` | Original identity/URL | Preserve identity in jump helper | Wrong original video |
| 11 | No existing Bilibili timestamp helper | No centralized construction | Add one backend helper | Duplicate/incorrect URL handling |
| 12 | `base.html` shared navigation | Common page entry structure | Add “搜索” link | Search page undiscoverable |
| 13 | Product API structured `{ok:false,error:{code,stage,message,trace_id}}`; Pydantic 422 uses `detail` | Bounded API errors | Map status/code to safe user text | Leaking internals or wrong state |
| 14 | `ProductSearchResponse` in `product_search.py` | Plan/execution/fallback/results/warnings/timing and internal counters | Consume user-facing subset only | UI depending on guessed fields |
| 15 | `ProductVideoResult` in `product_search.py` | Group identity/rank/count/windows; missing display metadata before Stage 5 | Add cover/detail/state/mark/folders/excerpt | Frontend N+1 or ranking mutation |
| 16 | `EvidenceWindow` output from `consolidation.py` + enrichment | start/end/duration, excerpt, sources, jump and chapter | Render unchanged and in returned order | Recomputing evidence client-side |
| 17 | `pytest` + FastAPI `TestClient` under `tests/` | Route/API unit and integration style | Add three focused test files | Unidiomatic/unreliable coverage |
| 18 | In-app browser control and screenshot capability available | Real interactive browser validation possible | Use formal server plus controlled fixture | Static-only “browser” claim |
| 19 | LaunchAgent `app.shiliu.web`; `.venv/bin/shiliu serve`; port `18520` | Formal local Web runtime | Restart via `launchctl kickstart -k` | Testing a different runtime |
| 20 | Existing CSS media queries at 1050/700 px | Responsive native CSS | Add search-card breakpoint without framework | Narrow-screen overflow |

## 3. Existing Web Architecture

**[Confirmed Fact]** The app remains FastAPI + Jinja + native JavaScript/CSS. `Application` remains the composition root. Stage 5 reuses the shared `base.html`, the existing Product service and formal `POST /api/search`; the home waterfall, transcript page, media routes, and API contracts remain intact.

**[Confirmed Fact]** The only shared-template change is an asset-block hook and the Search navigation entry. No SPA, frontend framework, package, build system, or broad Web refactor was introduced.

## 4. Search Page Architecture

**[Confirmed Fact]** `GET /search` renders `src/shiliu/templates/search.html` with current active favorite sources. The page uses `src/shiliu/static/search.css` and `src/shiliu/static/search.js`.

**[Confirmed Fact]** Results are a single-column ordered list. Each `ProductSearchResponse.results` item produces exactly one `<article>` card, and `map()` preserves response order; no frontend sort exists.

## 5. URL State

**[Confirmed Fact]** URL restoration and serialization cover `q`, `mode`, `scope`, `folder_id`, `reading_state`, `marked`, `uploader`, `favorite_time_from`, `favorite_time_to`, `archived`, and `ignored`. Defaults (`lexical`, `all`, excluded archived/ignored) are omitted from the URL but are explicit in the request.

**[Confirmed Fact]** Submit uses `history.pushState`; `popstate` restores controls and searches; a direct URL and refresh automatically execute when `q` is non-empty. Browser validation confirmed direct URL, refresh, back, and forward restoration.

## 6. Search Input and Mode Controls

**[Confirmed Fact]** The trimmed query submits by button or Enter. Empty input does not call the API and shows the validation state. There is no type-ahead, autocomplete, or query suggestion service; static examples submit only on click.

**[Confirmed Fact]** User-facing modes map to `lexical=关键词`, `auto=自动`, `dense=语义`, `hybrid=混合`. The default remains `lexical`; Auto is optional and Hybrid is non-default.

## 7. Scope and Filters

**[Confirmed Fact]** Scope values are `all`, `video`, and `transcript_chunk`; the client passes them through without altering results.

**[Confirmed Fact]** Common filters are named favorite folder, actual reading enum (`unread`, `in_progress`, `read`), and mark state. More filters contain exact uploader, favorite date bounds, scope, archived, ignored, and mode. Clearing filters preserves the query and restores defaults.

**[Confirmed Fact]** Every request explicitly sends `archived:false` and `ignored:false` unless the user enables them.

## 8. Product Metadata Extension

**[Confirmed Fact]** `ProductVideoResult` was additively extended with `cover_url`, `detail_url`, `reading_state`, `marked`, `folder_names`, and bounded `match_excerpt`. Existing fields were neither deleted nor renamed.

**[Confirmed Fact]** `ProductSearchService._display_metadata()` executes one SQL query for all selected video IDs, joining only active memberships. It prefers `/media/{id}/cover` for a stored cover, falls back to an absolute remote cover, creates the real `/videos/{id}/transcript` detail URL, and defaults missing display state safely.

**[Confirmed Fact]** Metadata enrichment occurs only after backend grouping/ranking and does not reorder groups or windows. Tests assert one metadata query and unchanged ranking/window order.

## 9. Result Card Design

**[Confirmed Fact]** Each card displays cover/fallback, title, uploader, folders, reading state, mark state, duration, a user-facing match summary, primary evidence, additional evidence toggle, local detail link, and timestamp link where available.

**[Confirmed Fact]** Internal unit IDs, raw ranks, BM25/dense/RRF scores, model/revision/index data, trace JSON, latency breakdown, and candidate counters are not rendered.

## 10. Evidence Window Presentation

**[Confirmed Fact]** The first returned window is visible by default. It shows exact returned start/end, duration, bounded excerpt, subtitle-source tags, optional auxiliary chapter, and backend-provided jump link.

**[Confirmed Fact]** Further returned windows remain in backend order behind an accessible toggle. The client requests up to five windows and separately states `additional_window_count` when more exist. Long windows are not split or shortened in the frontend.

## 11. Anchor Wording

**[Confirmed Fact]** `exact_query_phrase`, `exact_entity_term`, and `keyword_overlap` render “从 HH:MM 播放”. `chunk_start_fallback` renders “从相关片段 HH:MM 开始”. The client never relabels a semantic chunk fallback as a precise mention.

**[Confirmed Fact]** Formal semantic-query browser evidence showed `chunk_start_fallback` at 17:30 with the honest fallback wording.

## 12. AI Chapter Presentation

**[Confirmed Fact]** Chapter content is visibly prefixed `AI 章节：`; optional summary is secondary text. Chapter time is not used to construct or replace `jump_time`.

## 13. Local Detail Navigation

**[Confirmed Fact]** Cards use the backend-generated `/videos/{video_id}/transcript` URL. Browser navigation from the MCP result to `/videos/78/transcript`, then Back, restored query, filters, and results; Forward returned to detail.

## 14. Bilibili Jump URL

**[Confirmed Fact]** `build_bilibili_jump_url(video_url, bvid, jump_time)` normalizes protocol-relative URLs, falls back to canonical BVID URL, floors finite seconds and clamps at zero, preserves the video path and unrelated query parameters, replaces `t`, and URL-encodes the query. Invalid/missing identity returns no link.

**[Confirmed Fact]** Seven focused tests cover BVID, existing URL, zero, decimal, large time, existing query/encoding, and missing URL/identity behavior.

**[Confirmed Fact]** Real browser click from the MCP result opened `https://www.bilibili.com/video/BV1G29EBGE8b/?t=600`; the BVID and 600-second anchor matched the card.

## 15. Loading / Empty / Fallback / Error States

**[Confirmed Fact]** The page implements Idle, Loading, Success, Empty, Auto Fallback, validation error, dense-rebuild-required (409), dense-unavailable (503), internal error, and partial-enrichment warning states.

**[Confirmed Fact]** A controlled temporary FastAPI fixture (port 18521, no formal index mutation) verified fallback-with-results, partial warning-with-results, safe validation/internal messaging, and explicit Dense unavailable with “改用关键词搜索”. Formal healthy-index browsing verified Idle, Success, Empty, and validation states.

**[Inference]** Loading is set synchronously before `fetch`; the in-app click primitive awaited the request and did not yield a stable screenshot of the transient state. Source coverage plus the controlled slow-request race proves the transition exists, but no separate loading screenshot is claimed.

## 16. Request Race Handling

**[Confirmed Fact]** Each search aborts the prior `AbortController` and increments a monotonic sequence. Only the current sequence may render data, errors, or restore the button.

**[Confirmed Fact]** A controlled slow Query A followed immediately by fast Query B completed with Query B (`fast-b`) in the URL, input, and result title even after A finished. Enter is handled directly on the query input so a new search can supersede an in-flight request while the submit button is disabled.

## 17. Safe Rendering

**[Confirmed Fact]** Dynamic text is created with `document.createElement` and assigned through `textContent`; `search.js` contains no `innerHTML`. External links use `target="_blank"` plus `rel="noopener noreferrer"`.

**[Confirmed Fact]** Controlled title/excerpt/chapter values containing `<script>` and `<img onerror>` remained literal text and produced zero executable matching DOM nodes. Source-level and rendered-template tests cover this contract.

## 18. Accessibility

**[Confirmed Fact]** Inputs have labels; Enter submits; status/summary/error containers use live/status semantics; the additional-window control has `aria-expanded` and `aria-controls`; covers have title-based alt text; focus-visible styling is present; all actions are native links/buttons.

## 19. Responsive Layout

**[Confirmed Fact]** Desktop cards use cover-left/content-right. At 390×844 the cover moves above content; measured document width equaled viewport width (390 px), card width was 346 px, and no horizontal overflow was observed. Long text, filter controls, actions, and expanded windows wrap.

## 20. Automated Tests

Exact commands and outcomes:

| Command | Exit | Passed | Failed | Skipped | Warnings |
|---|---:|---:|---:|---:|---:|
| `.venv/bin/python -m pytest tests/test_search_page.py -q` | 0 | 4 | 0 | 0 | 1 |
| `.venv/bin/python -m pytest tests/test_search_display_metadata.py -q` | 0 | 3 | 0 | 0 | 1 |
| `.venv/bin/python -m pytest tests/test_bilibili_jump_url.py -q` | 0 | 7 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_product_search_api.py -q` | 0 | 11 | 0 | 0 | 1 |
| `.venv/bin/python -m pytest tests/test_search_api.py -q` | 0 | 7 | 0 | 0 | 1 |
| `.venv/bin/python -m pytest tests/test_search_enrichment.py -q` | 0 | 75 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_search_consolidation.py -q` | 0 | 10 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest -q` | 1 | 498 | 1 | 0 | 1 |
| `env -u NO_PROXY -u no_proxy -u ALL_PROXY -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u http_proxy -u https_proxy .venv/bin/python -m pytest -q` | 0 | 499 | 0 | 0 | 7 |

**[Confirmed Fact]** The raw required full-suite command was run first without `PYTHONPATH`. Its sole failure was the known environment-provided raw IPv6 `NO_PROXY=::1` causing `httpx.InvalidURL` in unrelated `test_output_budget_exhaustion_is_not_retryable`. Removing only proxy environment variables produced the controlled 499-test pass. Warnings were Starlette and multiprocessing/fork deprecations.

**[Confirmed Fact]** `node --check src/shiliu/static/search.js`, Python compilation, and `git diff --check` also passed.

## 21. Browser Validation

**[Confirmed Fact]** The formal LaunchAgent `app.shiliu.web` was restarted and the real page at port 18520 returned HTTP 200. Browser validation used the real database and formal Product API for queries, filters, scopes, navigation, refresh/history, Bilibili, expansion, and responsive layout. Controlled error/race cases used an isolated temporary fixture and did not damage the formal index.

**[Confirmed Fact]** Final formal-page inspection used `search.js?v=2`, showed 10 MCP cards, had no horizontal overflow at 1144×964, and browser logs contained no warnings or errors.

## 22. Screenshot Evidence

All files were captured from the implemented Stage 5 browser page and contain no credentials, filesystem paths, or trace debug payload:

1. `research/v3_stage5/screenshots/01_exact_entity_results.png`
2. `research/v3_stage5/screenshots/02_semantic_results.png`
3. `research/v3_stage5/screenshots/03_expanded_windows.png`
4. `research/v3_stage5/screenshots/04_filtered_results.png`
5. `research/v3_stage5/screenshots/05_empty_or_fallback_state.png`
6. `research/v3_stage5/screenshots/06_narrow_layout.png`

## 23. Exact Entity Evidence

**[Confirmed Fact]** MCP, RAG, and OpenAI were run in lexical/all mode. Each returned 10 ordered video cards with a visible primary evidence window, local detail link, and Bilibili jump link. MCP’s first result was “CLI vs MCP”, with a 09:39–13:51 window and a precise 10:00 jump. Additional MCP windows expanded from `aria-expanded=false` to `true` without reordering.

**[Confirmed Fact]** RAG’s first jump was at 19:54 and OpenAI’s first jump at 00:08; both used precise-anchor wording.

## 24. Mixed-query Evidence

**[Confirmed Fact]** `MCP 协议` and `OpenAI API 调用` were run with Auto. Each returned 10 cards, showed auxiliary AI chapter labeling, and retained core-entity precise anchor wording where supplied by Stage 4B. The frontend displayed the executed search mode without exposing routing internals.

## 25. Semantic-query Evidence

**[Confirmed Fact]** `Agent 多轮运行后怎样控制上下文增长` in Auto executed Hybrid and returned 10 cards. The first window used `chunk_start_fallback` and displayed “从相关片段 17:30 开始”, not a precise-mention claim.

## 26. Filter and Scope Evidence

**[Confirmed Fact]** Real filter combinations passed:

- folder `2026找工作学习` (`folder_id=3876418799`) + `unread` returned 10 cards and restored through URL state;
- uploader `chocpink_AI版` + marked only, query `vibe coding`, returned exactly the real marked/read video.

**[Confirmed Fact]** `video`, `transcript_chunk`, and `all` were each exercised. For the controlled matching video, `video` rendered one understandable card with no window and “视频概览与查询相关”; `transcript_chunk` and `all` rendered the evidence window supplied by the API.

## 27. Navigation Evidence

**[Confirmed Fact]** Verified paths: Search → local detail → Back; Back/Forward; direct URL with query/filter; refresh; and Search → external Bilibili timestamp. Search state rehydrated from URL on every return. The external link opened a separate tab and preserved the local search tab.

## 28. Runtime Characteristics

Formal API observations (milliseconds; `total` is server Product Search timing, `client` is local HTTP elapsed):

| Query | Mode/scope/filters | HTTP | Results | Raw | Group | Anchor | Chapter | Trace | Total | Client |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MCP | lexical/all/default | 200 | 10 | 29.010 | 0.151 | 37.129 | 3.348 | 1.302 | 73.036 | 83.308 |
| MCP 协议 | auto/all/default | 200 | 10 | 148.787 | 0.071 | 92.311 | 1.196 | 1.356 | 245.291 | 247.865 |
| Agent 多轮运行后怎样控制上下文增长 | auto/all/default | 200 | 10 | 89.712 | 0.083 | 32.953 | 2.182 | 2.526 | 129.566 | 131.562 |
| MCP | lexical/all/folder+unread | 200 | 10 | 4.939 | 0.070 | 20.550 | 0.848 | 1.018 | 28.935 | 31.056 |

**[Confirmed Fact]** Corresponding trace IDs were `929f42e1-0efe-4c37-9cc1-cc7d6f3fcae1`, `0d5f77d9-2795-479d-b4fb-e633b0b0d07d`, `5ed4aa32-6f3d-4927-a074-5e5e422d8210`, and `ae7e917d-6ce5-41ae-9f7d-426afb4f0195`.

**[Inference]** Warm visible searches appeared promptly; browser automation wall time includes interaction/tool overhead and is not a reliable loading-duration instrument. The page records `performance.now()` elapsed in `window.__shiliuLastSearch`, while exact server/client timings above are the reproducible runtime evidence. No model/router change was made for latency.

## 29. Product and Index Integrity

Stable-table hashes used: rows selected as JSON with sorted keys and compact separators, ordered by `rowid`, joined by newline, SHA-256.

**[Conflict]** Restarting the required formal LaunchAgent also triggered its pre-existing automatic favorite-source sync. The initial pre-launch snapshot and the fresh post-launch snapshot therefore differ in three Product tables, even though no browser state action was clicked:

| Table | Rows | Initial pre-launch SHA-256 | Post-startup-sync SHA-256 |
|---|---:|---|---|
| `videos` | 144 | `fcb82d00f2d3635ec3926f627729909d2ba37ed2728b89fb1e204e5fd4c70ce0` | `c3afcf82d23d82c9cff68e0d1b825ff418c2a016134bbb3581edd70cf7f2fbd6` |
| `video_notes` | 1 | `a1a8ba9cd144486dd1fdc766df8ef302d8b6a79dc0a58c08b972c7411f69f960` | same |
| `favorite_sources` | 2 | `6cea9d9bb6f92182290745d6caa163fd0572e5834de283cc9d9998bb8d7fef68` | `afaff8c37ba30109b42f45540a3c53bd1c8adf3eaae3e492d144595fa7164e20` |
| `video_source_memberships` | 146 | `6fbb4ee253cd63004361b11fb58e28b2addaadc2576bdc164ba2487a91a84e2d` | `e5140d52d663edbd5678d82fcbed14a2b9abc7711ad08bc5ee1db32deec4ffc9` |
| `events` | 273 | `41c655f7e69028fcf9c8c52b9672d3659f249a9758a02f5fb0e86da93b395367` | same |

**[Confirmed Fact]** Attribution is explicit in the live rows: source 2 has `last_sync_at=2026-07-19T21:40:38+00:00`, source 1 has `last_sync_at=2026-07-19T21:40:48+00:00`, and 142/3 membership rows have matching `last_observed_at` values. These are the local 05:40 LaunchAgent restart window. This is existing Product Sync behavior, not a write issued by `/search` or `POST /api/search`; no rollback was attempted.

**[Confirmed Fact]** A fresh settled baseline was then taken, followed by `GET /search` (HTTP 200) and `POST /api/search` for lexical/all MCP (HTTP 200, 10 results, trace `39a9e641-e88a-4eca-9c6b-4e48662cfc96`). The settled before/after hashes were identical:

| Table | Rows | Settled before SHA-256 | Settled after SHA-256 |
|---|---:|---|---|
| `videos` | 144 | `c3afcf82d23d82c9cff68e0d1b825ff418c2a016134bbb3581edd70cf7f2fbd6` | same |
| `video_notes` | 1 | `a1a8ba9cd144486dd1fdc766df8ef302d8b6a79dc0a58c08b972c7411f69f960` | same |
| `favorite_sources` | 2 | `afaff8c37ba30109b42f45540a3c53bd1c8adf3eaae3e492d144595fa7164e20` | same |
| `video_source_memberships` | 146 | `e5140d52d663edbd5678d82fcbed14a2b9abc7711ad08bc5ee1db32deec4ffc9` | same |
| `events` | 273 | `41c655f7e69028fcf9c8c52b9672d3659f249a9758a02f5fb0e86da93b395367` | same |

**[Confirmed Fact]** Initial, post-sync, and settled search checks all retained `retrieval_units=1555`, `retrieval_units_fts=1555`, `retrieval_dense_vectors=1555`, `retrieval_dense_index_meta=1`, and `retrieval_sync_state=144`. `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned zero rows.

**[Confirmed Fact]** Allowed observability data advanced from 54 to 81 Raw Search Traces and from 24 to 51 Product Presentation Traces (+27 each, including the isolated settled check). No Product state action was invoked from the search page.

## 30. Remaining Limitations

**[Deferred]** Formal relevance metrics, labeled query set, failure analysis, and Timestamp Anchor Error belong to Stage 6 and remain not started.

**[Deferred]** Whether long evidence windows should be algorithmically changed is a Stage 6/version-session decision. Stage 5 truthfully displays their start, end, duration, and jump time.

**[Follow-up]** Minor visual polish remains permissible, including more detailed mobile typography/screenshot presentation. It does not block search, navigation, evidence comprehension, safety, or responsive use.

## 31. Recommended Classification

**Accepted with Follow-up**

All Stage 5 functional, compatibility, settled-search integrity, automated-test, real-browser, navigation, safety, and screenshot evidence gates are met. The initial hash conflict is fully attributed to existing LaunchAgent startup sync, while a settled before/after request check proves the search surface itself changes only allowed Trace tables. Remaining items are limited to minor visual polish and questions explicitly reserved for Stage 6 (relevance quality, long-window policy, Timestamp Anchor Error). This recommendation does not replace Version Session acceptance.

## 32. Stop Boundary

**[Confirmed Fact]** Stage 5 implementation and evidence collection stop here. Default mode remains Lexical; Auto remains optional; Hybrid remains non-default; Raw and Presentation Traces remain internal.

**[Confirmed Fact]** Stage 6 is **Not Started**. No Eval Dataset, relevance labeling, router optimization, reranker, query rewrite, Segment Dense Index, V3.5, or other out-of-scope work was begun.
