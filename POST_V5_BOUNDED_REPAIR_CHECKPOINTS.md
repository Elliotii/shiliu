# Post-V5 Bounded Repair Checkpoints

Date: 2026-08-12 (Asia/Shanghai)

Baseline: `codex/post-v5-product-closeout` at
`5f1bf4dd899e97583a234b224e209f8c6aac9294`.

Repair branch: `codex/post-v5-bounded-repair`.

This is the compact rollback/checkpoint record required by
`POST_V5_BOUNDED_REPAIR_CHARTER.md`. It does not reopen deferred scope.

## Goal A — Ask Finalization Reliability

Related observations: RU-001, RU-004, RU-011.

Root failure family: successful Retrieval/Evidence followed by Grounded Answer Provider
failure was projected as evidence insufficiency; output-budget and empty-output failures
had no eligible role-specific recovery.

Bounded implementation:

- Added the response/trace `execution_outcome` projection without a database migration.
  `generation_failed`, `evidence_insufficient`, `evidence_unavailable`, and
  `answer_generated` remain distinct while the v16 `answer_status` persistence contract
  stays intact.
- Provider/runtime failure now renders `回答生成失败`, never `证据不足`, and cannot emit
  an answer block or Citation.
- Preserved the normal `deepseek-v4-pro` thinking-enabled Grounded Answer path. The prior
  H0 evidence rejected Thinking Off as the primary path because of quality regression.
- Added exactly one eligible recovery for `output_budget_exhausted` or
  `empty_model_output`, using the same evidence and the same deadline through a
  role-specific Pro/Thinking-Off recovery provider. Network, authentication,
  configuration and generic Provider failures do not enter that recovery.
- Every answer Provider invocation now records `call_kind`, finish reason, latency,
  token usage and retry count in existing usage/trace JSON.

Deterministic proof:

- Fast/Deep Ask, contract, page, provider-routing and persistence tests: 76 passed.
- V4.1 H0/Continuation nearby non-regressions: 37 passed.
- Original-family regressions cover output-budget exhaustion in Fast and Deep,
  empty-model output, recovery failure, authentication/network/configuration/deadline,
  invalid JSON, model-declared insufficiency, zero/stale evidence and Citation
  revalidation.

Natural smoke measurements:

| Run | Outcome | Total / final Provider | Prompt / completion / reasoning | Calls / repair | Citations |
|---|---|---:|---:|---:|---:|
| Before Fast `ask_run_0eabf36f514f40a382cc15bbdc1ff3f3` | `partial / answer_ready` | 55.6 s / 49.7 s | 10,067 / 2,690 / 2,358 | 1 / 0 | 6 |
| After Fast `ask_run_0a4a00d56a3a42d580a697e97770d12c` | `partial / answer_generated` | 76.20 s / 63.68 s | 9,948 / 3,464 / 2,679 | 1 / 0 | 5 |
| Before Deep `ask_run_917e153e8c9a4e59a2bc24b4dc7e2005` | `partial / answer_ready` | 80.4 s / 63.9 s | unknown / 3,134 / 2,810 | 1 / 0 | 3 answer blocks |
| After bounded Deep `ask_run_2173c642c9234e03a88db4639977c020` | `complete / answer_generated` | 69.71 s / 50.03 s | 3,531 / 3,730 / 3,446 | 1 / 0 | 3 |

Additional honest terminal checks:

- Fast `ask_run_3cefac1ebc394ea0ad8f5aacb8b03b15`: model-declared
  `evidence_insufficient`, 14.22 s total, 3.36 s final Provider, 103 reasoning tokens.
- Deep `ask_run_02d0729c82614490ba6d9ab69da145a6`: deterministic search stop plus
  model-declared `evidence_insufficient`, 22.48 s total, 3.12 s final Provider, 97
  reasoning tokens.

Gate result: **PASS**. Provider failure and evidence insufficiency are durably and
visibly distinct; Fast/Deep share the semantics; recovery is bounded to one eligible
attempt; Pro model identity, Retrieval, Evidence and Citation Authority are unchanged.

Residual limitation: normal successful Pro calls still show variable latency and can
spend most completion tokens on reasoning. The repair does not claim a latency SLA or
adopt primary Thinking Off. The after-Fast sample was slower than the earlier scoped
sample, while bounded Deep was faster; more natural use is required before attributing
latency change. The new recovery path is deterministically covered but was not induced
against the live Provider.

## Goal C — Real-corpus Library Scaling

Related observations: RU-012 and RU-014.

Root failure family: the home route loaded and enriched every membership card before
first paint; Ask's hidden keyboard contract required Cmd/Ctrl+Enter for short queries.

Bounded implementation:

- Added a 40-card server-rendered keyset page using the existing exact ordering tuple:
  effective favorite time descending, source position ascending, discovery time
  descending, video ID descending and source ID ascending.
- The opaque versioned cursor carries the complete unique ordering identity plus a
  membership-row high-water mark. Before and after navigation use `page_size + 1`; the
  home route loads Notes, ASR state and summary artifacts only for the returned page.
  Note counts are also aggregated only for video IDs on that page.
- Continuation excludes memberships inserted after the traversal began and derives each
  pre-existing membership's source position at that boundary. This prevents a forward
  sync in one folder from moving an already-seen non-anchor card behind a cursor anchored
  in another folder, including equal-favorite-time interleaving.
- Previous/Next links preserve `view` and `source`; all four views and existing
  multi-folder membership-card semantics remain unchanged.
- Ask now submits on Enter outside IME composition, keeps Shift+Enter as newline, retains
  button and Cmd/Ctrl+Enter behavior, and exposes the keyboard hint. Existing empty and
  in-flight guards remain in `executeAsk()`.

Deterministic proof:

- Library, Ask-page, Web boundary, v1 source semantics and backfill regressions: 59
  passed.
- A temporary SQLite corpus of 2,055 membership cards completed a full 40-card traversal
  with no missing/duplicate pre-existing membership identities after a realistic full
  forward-sync refresh inserted a new top favorite and shifted source positions.
- A separate all-sources, two-folder equal-time regression inserts a new top card in the
  non-anchor folder after page one and proves exact traversal of the eight boundary-time
  memberships without duplicate or omission; the new card appears only in a new traversal.
- Bidirectional page round-trip, bounded HTML, invalid cursor, all views, source filter,
  multi-folder duplicates and reading/Mark/Notes/archive mutations are covered.
- Ask checks execute the shared JavaScript keyboard decision for Enter, Cmd/Ctrl+Enter,
  Shift, IME `isComposing`, keyCode 229 and non-Enter input; template/static checks cover
  the visible hint plus the existing empty-input and in-flight submission guards.

Live warm-machine measurement using the same local response-completion method as
RU-012:

| Page | Cards | HTML bytes | Response completion |
|---|---:|---:|---:|
| RU-012 baseline, unbounded | 2,055 | 8,465,186 | 8.69 s |
| Current first page (2,209 active memberships) | 40 | 199,013 | 0.355 s |
| Current second page (2,209 active memberships) | 40 | 292,741 | 0.336 s |

Gate result: **PASS**. Initial payload is below 1 MB and both measured pages are below
1.5 seconds by a wide margin. No cache, service/storage layer, pagination framework,
frontend rewrite or schema change was added.

Residual limitation: the row high-water mark and derived position form an
insertion-stable traversal boundary, not a general database snapshot. Arbitrary
concurrent edits to pre-existing favorite times or membership removal can still change
page composition. View mutations intentionally change view membership on refresh.

## Goal B — Terminal Candidate Disclosure

Related observations: RU-003, RU-011 and RU-013.

Root failure family: Ask persisted adopted final evidence and durable child Search
lineage separately, but its terminal response/UI only projected Answer Citations. Useful
completed retrieval therefore disappeared whenever answer generation failed or evidence
coverage remained honestly insufficient.

Bounded implementation:

- Added a non-authoritative `candidate_disclosure` response/trace contract. It is
  reconstructed from existing `ask_search_trace_links`, durable Search presentation
  summaries, exact retrieval-unit identities and current video metadata; no new table,
  column, payload archive or persistence platform was added.
- Reconstruction inspects at most 12 ordered child Search identities and eight groups per
  presentation, deduplicates to unique videos across rewrites, returns five by default
  and enforces a hard maximum of eight. The response reports truncation and unavailable
  presentations explicitly.
- Transcript candidates retain producing Search trace/query/rank, exact historical unit
  and window identity, current exact-unit excerpt and timestamp. Metadata-only groups are
  labelled `相关视频线索 · 无可用字幕，不能作为回答证据` and carry no transcript unit or
  excerpt.
- Missing current video identity is shown as unavailable. A missing or changed exact
  transcript unit is shown as stale and is never replaced with a different current unit.
  Candidate projection failure is isolated from Answer/Citation delivery.
- Candidate records have no Citation ID and never enter `citations` or `final_evidence`.
  Windows overlapping an adopted Citation are removed; partial answers can disclose only
  the remaining unadopted comparison candidate.
- The terminal UI uses a collapsed `本次检索到的候选证据` section, explicitly calls the
  content a current reconstruction rather than historical replay, and states that
  retrieval relevance does not prove the requested conclusion. Zero-candidate runs show
  an honest empty state.

Deterministic proof:

- Ask contracts, Fast/Deep services, Ask page, Product Search presentation and execution
  persistence regressions: 88 passed.
- Focused cases cover model-declared insufficiency, Provider-generation failure,
  multi-rewrite deduplication, Web/service restart, stale exact transcript unit,
  metadata-only lead, unavailable historical video, five/eight-card bounds, partial
  comparison coverage and a true zero-candidate run.
- Existing Citation content/identity, timestamp jump and durable `final_evidence`
  assertions remain unchanged; focused tests assert candidate objects contain no
  `citation_id`.

Historical durable-lineage reconstruction on the current real corpus:

| Run | Terminal | Search presentations | Unique reconstructed / visible | First projection |
|---|---|---:|---:|---|
| RU-011 `ask_run_1046902129f64af190b4d08797ef9f69` | Fast insufficient | 3 | 18 / 5 | current transcript candidate, rank 1 |
| RU-011 `ask_run_8c69dd48c8044ee7ad01be05bcc0b281` | Fast insufficient | 1 | 8 / 5 | current transcript candidate, rank 1 |
| RU-011 `ask_run_4bc7cddeef64416da75d9f103339ad6d` | Fast Provider failure | 3 | 14 / 5 | current transcript candidate, rank 1 |
| RU-013 `ask_run_cb58ead1fabf46d8a14f44336d251db6` | Deep insufficient | 3 | 9 / 5 | current metadata-only lead, rank 1 |

Gate result: **PASS**. The fresh-context Citation Authority/restart-boundary review found
one High in its first pass: a historical transcript window missing exact unit identity
could be projected as current. The bounded repair now makes current transcript candidates
require exact unit plus complete window identity, marks missing/mismatched identity stale
without excerpt/jump, and encodes metadata non-authority fields in the contract. The only
bounded re-review found no Blocking/High/Medium and recommended PASS.

Residual limitation: this is bounded current reconstruction, not exact historical UI
replay. Older Search presentation summaries intentionally retain identities/ranks/windows
but not historical title or body text, so current metadata and exact current retrieval
unit text are used only when the retained identity still resolves. Search lineages beyond
the inspection bounds are represented by `truncated=true`, not silently expanded.
