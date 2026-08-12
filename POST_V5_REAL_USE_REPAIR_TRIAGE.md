# Shiliu Post-V5 Real-use Repair Triage

Date: 2026-08-12 (Asia/Shanghai)

Status: `SCOPE_FROZEN — AWAITING BOUNDED_REPAIR_AUTHORIZATION`

Baseline reviewed: `codex/post-v5-product-closeout` at
`5f1bf4dd899e97583a234b224e209f8c6aac9294`.

This document is a Main-Owner decision over the trace-backed evidence in
`POST_V5_REAL_USE_OBSERVATIONS.md`. It authorizes no implementation by itself. No code,
configuration, database, prompt, provider setting, LaunchAgent or live runtime state was
changed during triage.

## 1. Executive decision

Fifteen observations consolidate into four repair families, not fifteen fixes:

1. **P0 — Ask finalization reliability and outcome semantics.** Retrieval and evidence
   construction repeatedly succeed, but the shared grounded-answer Provider can exhaust
   its output budget or return no usable output. `AnswerFinalizer` then emits
   `status=insufficient`, causing a generation failure to look like evidence
   insufficiency. This repeats across Fast and Deep.
2. **P1 — Terminal candidate-evidence disclosure.** When no verified answer is produced,
   durable child Search lineage still contains useful transcript candidates or
   metadata-only leads, but the Ask result is an empty dead end. These candidates must
   remain explicitly separate from final Citation Authority.
3. **P0 — Real-corpus library scaling, with one bounded input affordance.** The primary
   feed performs an unbounded SQL read, note load, per-card ASR lookup and summary-file
   read for roughly 2,055 cards before first paint. Server-side pagination is required.
   Ask Enter/Shift+Enter behavior is a small, independent UI correction that may ride in
   the same bounded core-surface package.
4. **P1 — Research product boundary and user-level completion semantics.** The durable
   Research kernel works. The visible product boundary does not: a deterministic
   no-Provider extractive artifact can be projected as user-level success, internal
   runtime vocabulary dominates the page, and Branch/Replay creates permanent records
   without confirmation.

No evidence supports reopening Retrieval, embeddings, chunking, Deep policy, Research
runtime architecture, V5 accepted results or V6. A new bounded Repair Session is
recommended only for the four packages frozen below.

## 2. Evidence summary and source verification

### Ask

- Fast run `ask_run_817767c8749a41fd908dec4299f6880c` persisted 65 valid evidence
  spans and three successful child Search traces, then ended
  `insufficient / provider_error / output_budget_exhausted` after the 4,096-token output
  allowance was consumed.
- Deep run `ask_run_a64a1e857a5a4dadb44141a8acf129be` persisted two successful child
  Search traces and completed its evidence work before the same output-budget family
  failed in shared finalization.
- Fast run `ask_run_4bc7cddeef64416da75d9f103339ad6d` had 85 valid evidence spans but
  ended `insufficient / provider_error / empty_model_output`.
- Successful broad-answer counterparts
  `ask_run_0eabf36f514f40a382cc15bbdc1ff3f3` and
  `ask_run_917e153e8c9a4e59a2bc24b4dc7e2005` show the Provider call dominates total
  latency and spends most completion tokens on reasoning. They establish an efficiency
  pattern, but not enough evidence for broad answer-style tuning.
- Source confirms Fast and Deep share `AnswerFinalizer`. Its `_insufficient()` projection
  is used both for absent evidence and Provider/runtime failure. `GroundedAnswerService`
  requests a 4,096-token structured output while the grounded-answer Provider currently
  retains reasoning, explaining how a response can spend the full budget before emitting
  valid visible JSON.

### Candidate lineage

- `ask_search_trace_links` durably connects every reviewed Ask run to Search-owned
  traces. The representative Shanghai Fast failure links to
  `2e10bd0b-885b-4763-bed1-fc37f5f9e485`,
  `4ef20b88-43cf-47ff-b05c-976246218051`, and
  `70854961-aaaa-499a-9a85-04aa8dfc5edc`.
- Search presentations retain bounded group identities, ranks, video IDs, transcript
  windows and component chunk IDs. They are sufficient for a bounded reconstructed
  candidate projection without copying Search payloads into Ask or adding a new
  persistence platform.
- Buran Deep run `ask_run_cb58ead1fabf46d8a14f44336d251db6` links to video-level trace
  `3a9624a5-65e0-44fb-b053-35801bbadf5c`, where video 179 ranks first but has no
  transcript window. This is a discovery lead and source-coverage limitation, not
  factual answer evidence.

### Library

- The home route calls `list_video_cards()` with no bound, then loads notes and calls
  `_video_view()` for every row.
- `_video_view()` performs per-card ASR lookup and may read/parse a summary artifact.
- The observed default-folder response rendered 2,055 cards, exceeded 8 MB and took
  about 8.7 seconds before response completion. This follows deterministically from the
  current data-access and rendering path.

### Research

- Task `rtask_7d85f6b46e2276e92782d55827f8c3fb` has a durable provisional artifact
  with `valid_partial` and limitation `无 Provider deterministic extractive synthesis；
  尚未执行 Outer Goal Audit`, but the later Outer decision upgraded the terminal result
  to `valid_success / answer_ready` solely because no required constraint remained
  unresolved.
- Task `rtask_1dba17022494ca7f6c3326ed8d071b59` repeats the same product outcome.
- Waiting task `rtask_cb9642043850c5da575238003e7b4790` generated two immutable Replay
  derivations, child tasks `rtask_788621ee3a21f405d168e90ef4ed99cf` and
  `rtask_66289cf296cccaf5674cacb51dcb624a`. Source confirms `deriveTask()` has no
  confirmation, whereas Cancel already does.
- `Application` explicitly wires both inner and outer Research with
  `provider_runs_authorized=False`. The page is therefore a restricted deterministic
  runtime, not a generally enabled Provider-backed research product.

## 3. Failure-family consolidation and case matrix

| Case | Failure family | Root layer | Recurrence | Product impact | Repair decision |
|---|---|---|---|---|---|
| RU-001 | A — Ask finalization | Answer / Reasoning + UI projection | Repeated with RU-004 and later runs | High, core grounded loop fails misleadingly | **P0 / Package A** |
| RU-002 | A — Provider efficiency and terse success | Answer / Reasoning + Product Expectation | Latency repeated; answer-depth evidence limited | Medium | **Observe** depth; reliability covered by A |
| RU-003 | B — evidence-first Ask UX | UI / UX + synchronous runtime boundary | Pattern confirmed by RU-011 | Medium | **P1 / Package B** for terminal disclosure; full streaming **P2** |
| RU-004 | A — Ask finalization | Shared Answer / Reasoning finalizer | Repeated across Fast and Deep | High | **P0 / Package A** |
| RU-005 | A — terse block presentation | Answer / Reasoning + UI | Repeats latency/presentation pattern | Medium | **Observe**; no broad prompt tuning now |
| RU-006 | Fast→Deep/history expectation | Product Expectation / Boundary | Singleton | Medium | **P2 — defer** |
| RU-007 | D — Research boundary | Product Expectation / Boundary | Repeated by RU-009/015 | High trust impact | **P1 / Package D** |
| RU-008 | Mark vs Notes naming | UI / UX | Singleton, sparse-state amplified | Low | **Accept** current model; copy only if touched nearby |
| RU-009 | D — false user-level Research success | Product Boundary + Answer/Reasoning projection | Repeated by RU-015 | High | **P1 / Package D** |
| RU-010 | Search positioning | Product Expectation / Boundary | Singleton | Medium | **Observe**; preserve standalone Search |
| RU-011 | B — hidden retrieved candidates | UI / UX + Evidence Construction projection | Repeated Fast/Deep | High | **P1 / Package B** |
| RU-012 | C — unbounded library feed | UI / UX + data-access boundary | Deterministic on every large-folder open | High, primary surface blocker | **P0 / Package C** |
| RU-013 | B — metadata lead discarded | Source-intrinsic Limitation + Coverage Gap + UX | Pattern with RU-011 | Medium/high | **P1 / Package B** for lead disclosure; factual insufficiency **Accept** |
| RU-014 | C2 — Ask keyboard affordance | UI / UX | High-frequency repeated friction | Low/medium | **P1 companion in Package C** |
| RU-015 | D — Research console and accidental derivation | UI / UX + Product Boundary + durable side effect | Repeated | High | **P1 / Package D** |

The matrix intentionally does not classify RU-013 as Retrieval failure: the video-level
retriever found the exact lead, while the authoritative transcript needed for a factual
history answer did not exist.

## 4. Frozen priorities

### P0

- Package A — Ask Finalization Reliability and Outcome Semantics.
- Package C — Real-corpus Library Pagination.

### P1

- Package B — Terminal Candidate Evidence and Metadata-lead Disclosure.
- Package D — Restricted Research Product Boundary.
- Ask Enter/Shift+Enter, only as the small companion item in Package C.

### P2 / defer

- Full progressive streaming or a staged asynchronous Ask runtime.
- Fast→Deep continuation, parent-run reuse and validated evidence reuse.
- Ask/Search history UI.
- Search naming or full information-architecture consolidation.
- Broad answer-depth/prompt tuning from RU-002/RU-005.
- Manual ASR launched from an insufficient Ask result.

### Accept / observe / reject

- Accept transcript-only factual Citation Authority and honest insufficiency when a
  relevant video has no transcript.
- Accept Mark and Notes as separate data concepts; observe terminology with more use.
- Preserve standalone Evidence Search and return-to-source timestamps; observe its label
  and default complexity.
- Reject enabling normal Provider-backed Research in this repair.
- Reject Query-triggered Evidence Enrichment, retrieval/index changes, dynamic routing,
  Research runtime rewrite, new eval framework and all V6/non-goal architecture.

## 5. Approved repair packages

### Package A — Ask Finalization Reliability and Outcome Semantics (P0)

#### Problem statement

After successful retrieval and evidence construction, grounded-answer generation can
exhaust the completion budget or return no valid structured output. The current shared
finalizer turns that operational failure into `insufficient`, so users are told evidence
is missing when the answer service actually failed.

#### Evidence

- RU-001: `ask_run_817767c8749a41fd908dec4299f6880c`; child Search traces
  `2e10bd0b-885b-4763-bed1-fc37f5f9e485`,
  `4ef20b88-43cf-47ff-b05c-976246218051`,
  `70854961-aaaa-499a-9a85-04aa8dfc5edc`.
- RU-004: `ask_run_a64a1e857a5a4dadb44141a8acf129be`; child Search traces
  `5731e4b6-227f-4985-bef2-b8026bc16062` and
  `d35c6843-4e9f-4f5f-9cd7-7070a5186385`.
- RU-011: `ask_run_4bc7cddeef64416da75d9f103339ad6d` proves the same misleading
  terminal surface for `empty_model_output`.

#### Root cause

`AnswerFinalizer` is correctly shared by Fast and Deep, but its output model conflates
two axes:

```text
evidence sufficiency
vs
answer-generation execution outcome
```

Observed Provider usage shows reasoning tokens can dominate the fixed structured-output
allowance, after which no usable answer JSON is available. This establishes the required
outcome—reliable structured-output budget for Grounded Answer—but does not freeze whether
the smallest compatible mechanism is disabling/reducing reasoning, separating budgets,
using a Provider flag, adjusting output tokens, or another role-specific setting.

#### Allowed scope

- Add or derive an explicit generation/execution outcome so Provider failure is not
  presented as evidence insufficiency. Preserve the exact provider error code and
  termination reason durably.
- Keep `insufficient` for successful model-declared insufficiency or deterministic lack
  of authoritative evidence, not as the primary user-facing label for Provider failure.
- Retain `deepseek-v4-pro` for grounded answers. First audit the current DeepSeek
  Provider, compatibility layer and `GroundedAnswerService`, then choose the smallest
  role-specific generation configuration that gives the visible structured answer a
  reliable budget. The specific Provider mechanism remains an implementation decision.
- Permit at most one narrowly classified retry/repair for output-budget or received-but-
  invalid structured output. It must reuse the same evidence, remain inside the existing
  deadline, and be recorded in usage/trace. Authentication/configuration errors and
  generic network failures must not enter a new retry loop.
- Apply the behavior once in the shared final-answer path and prove both Fast and Deep.
- Prefer the existing v16 `status`, `termination`, `provider_error_code`, usage, trace and
  result payload to express the corrected generation outcome. Do not introduce schema
  v17 unless source audit proves the frozen acceptance criteria cannot be met; any such
  change requires a written justification and a Main-owner/User gate before migration.

#### Non-scope

- Retrieval, embedding, chunks, query rewrites, Deep graph/actions/budgets, model identity,
  Citation Authority, general provider retry infrastructure or broad answer-style tuning.
- No promise to make every Provider call fast and no hard-coded handling of the Shanghai
  query.

#### Acceptance criteria

1. A run with valid evidence plus `output_budget_exhausted`, `empty_model_output` or
   another Provider execution failure is visibly and durably classified as generation
   failure, never `证据不足`.
2. No answer block or citation is fabricated when generation fails.
3. A successfully generated `insufficient` draft remains `证据不足`; a zero-evidence run
   remains `evidence_unavailable`. These nearby semantics do not regress.
4. Fast and Deep expose the same failure semantics through the shared finalizer.
5. The output-budget path makes no more than one bounded recovery attempt and trace data
   identifies every Provider call, finish reason, token usage and final disposition.
6. Grounded Answer remains Pro and raw subtitle/ASR remains the only factual authority.
7. Representative successful Fast and bounded Deep smoke records before/after
   final-answer Provider latency, total Ask latency, reasoning tokens, visible
   completion/output tokens, and Provider calls/retries. No unsupported hard latency SLA
   is imposed, but the repair must not create an obvious regression and must determine
   whether abnormal reasoning-token consumption decreased.
8. If Provider latency remains consistently long after the semantic/reliability repair,
   it is recorded as a residual limitation rather than expanding this package into model
   replacement, routing, streaming runtime or broad prompt tuning.

#### Regression strategy

- Reproduce RU-001 and RU-004 with deterministic fake Provider outputs that consume the
  budget after evidence succeeds.
- Add Fast and Deep `empty_model_output`, `output_budget_exhausted`, authentication,
  network, deadline and invalid-JSON cases.
- Retain existing model-declared insufficient, stale evidence, citation validation and
  one-repair tests.
- Run one broad Fast and one bounded Deep natural smoke; inspect run IDs and capture the
  required latency/token/call measurements rather than requiring a subjective answer
  style.

### Package B — Terminal Candidate Evidence and Metadata-lead Disclosure (P1)

#### Problem statement

When a verified answer is absent, the product hides completed retrieval. The user sees an
empty result even when Search found strong transcript candidates or a precise
metadata-only video lead.

#### Evidence

- RU-003 and RU-011, including Fast runs
  `ask_run_1046902129f64af190b4d08797ef9f69`,
  `ask_run_8c69dd48c8044ee7ad01be05bcc0b281`,
  `ask_run_4bc7cddeef64416da75d9f103339ad6d`, and
  `ask_run_e86bec8229e44d8e948fea0f0cdefba5`.
- RU-013: Fast `ask_run_9a63bb377f0c47aeb20899a85b22ad2d`; Deep
  `ask_run_cb58ead1fabf46d8a14f44336d251db6`; video-level trace
  `3a9624a5-65e0-44fb-b053-35801bbadf5c` ranks the exact no-transcript lead first.

#### Root cause

Ask persists only adopted final evidence/citations, while Search owns durable candidate
presentations. The Ask result UI renders only citations, so an empty final answer discards
the user-facing value of its child Search lineage.

#### Allowed scope

- Build a bounded candidate projection from existing durable Ask→Search links, Search
  presentation summaries, retrieval-unit identities and current video metadata.
- Define this as bounded reconstruction from durable lineage, not exact historical UI
  replay. Preserve the producing Search presentation identity in the projection.
- Show at most a small unique-video set (recommended default: five; hard maximum: eight)
  in a collapsed `本次检索到的候选证据` section after terminal completion.
- Distinguish:
  - transcript candidates not adopted into a verified answer; and
  - `相关视频线索（无可用字幕，不能作为回答证据）` for metadata-only hits.
- Include producing query/rewrite, rank, video title/status, available transcript window
  and timestamp. State explicitly that retrieval relevance does not prove the requested
  conclusion.
- Make the projection recoverable after Web restart using existing durable lineage.
- If a historical Search identity remains but its referenced video or current metadata
  is unavailable or stale, show that state explicitly; do not silently substitute a
  different current item or imply exact replay.

#### Non-scope

- No promotion of metadata, title, summary, description or navigation text to factual
  Citation Authority.
- No full response streaming, async job protocol, new Search algorithm, Fast metadata
  retrieval lane, schema platform, unbounded payload copy or automatic/manual ASR action.

#### Acceptance criteria

1. Provider-error, honest-insufficient and deterministic-stop results can expose a
   bounded candidate section when durable candidates exist.
2. Candidate cards are never labelled `回答引用` and never enter `citations` or
   `final_evidence` merely because they were retrieved.
3. A metadata-only lead clearly shows its no-transcript status and cannot ground a
   factual answer.
4. Candidate projection remains available after Web restart and is deduplicated across
   rewrites by video/window identity.
5. An actual zero-candidate run renders a clear empty state without inventing leads.
6. The UI and trace language call the result a reconstruction; unavailable/stale
   historical identities remain visible as such and are never silently rewritten.

#### Regression strategy

- Reconstruct RU-011 from multiple child Search traces with overlapping candidates.
- Reconstruct RU-013 with a first-ranked video-level hit and zero transcript windows.
- Add nearby cases: partial comparison coverage, stale/missing video, failed Search trace,
  and a run with no candidates.
- Verify existing citations and timestamp return-to-source behavior are unchanged.

### Package C — Real-corpus Library Pagination and Ask Input Affordance (P0 + P1)

#### Problem statement

The primary library page serializes the complete large folder before first paint. Ask's
hidden Cmd/Ctrl+Enter convention also conflicts with the product's short-query use.

#### Evidence

- RU-012: 2,055 cards, 8,465,186-byte HTML and roughly 8.69-second response for the
  default folder.
- RU-014: Search already submits on Enter; Ask submits only on Cmd/Ctrl+Enter and exposes
  no visible shortcut hint.

#### Root cause

- `list_video_cards()` has no limit or cursor/page boundary. Home then performs note and
  `_video_view()` enrichment for the entire result set.
- Ask's textarea key contract is optimized like a long-form editor despite natural usage
  being short queries.

#### Allowed scope

- Add server-side page bounds to the existing library query and route. Prefer stable
  keyset/cursor pagination whose cursor exactly follows the current stable ordering
  tuple. Use a small server-rendered first page (recommended 40 cards) and explicit
  Previous/Next or Load More navigation; preserve `view` and `source` URL parameters.
- A new forward favorite inserted at the top must not make an in-progress traversal
  unexpectedly duplicate or skip existing rows. If source audit proves keyset cost is
  materially disproportionate, bounded offset pagination is allowed only with a written
  trade-off, a concurrent-forward-sync behavior test, and no claim of snapshot-stable
  traversal.
- Query notes, ASR state and summary artifacts only for the current page. A count query or
  `page_size + 1` probe is acceptable; loading all card rows is not.
- Preserve the exact current ordering tuple, multi-folder membership-card behavior,
  filtering, Mark, Notes, reading state, archive and source semantics.
- In Ask, submit on Enter only when not composing IME text and when Shift is not held.
  Shift+Enter inserts a newline; button and Cmd/Ctrl+Enter remain valid. Add a visible
  hint and retain in-flight/empty-query guards.

#### Non-scope

- No SPA, frontend rewrite, infinite-scroll framework, caching project, new service
  layer, summary API redesign, high-concurrency architecture or data-model change.
- No consolidation of duplicate multi-folder membership cards.

#### Acceptance criteria

1. The default-folder initial response contains at most the configured page size, not
   roughly 2,055 cards.
2. On the live corpus, initial HTML is below 1 MB and local response completion is below
   1.5 seconds under the same warm-machine measurement method used for RU-012.
3. Keyset/cursor navigation preserves the current stable ordering tuple and produces no
   missing/duplicate existing rows when continuous sync inserts a new top favorite. Any
   approved offset fallback documents its weaker semantics and passes the explicit
   concurrent-forward-sync regression.
4. Mark/Notes/reading/archive behavior remains correct on every page and shared videos
   retain their current membership-card semantics.
5. Ask Enter submits once outside IME composition; Shift+Enter inserts a newline; Chinese
   IME composition, empty input, in-flight submission and mobile/button fallback are safe.

#### Regression strategy

- Add 2,055 deterministic membership cards in a temporary DB and assert bounded SQL/page
  output, first/last boundaries and complete stable traversal.
- Insert a new top-ordered favorite between page requests and verify keyset traversal
  does not unexpectedly duplicate or skip prior rows. Test and document the weaker
  behavior explicitly if the approved implementation uses offset pagination.
- Cover all four views, source filtering, multi-folder duplicates and page mutation
  behavior in `test_library`-adjacent integration tests.
- Measure one live default-folder first page and one subsequent page.
- Add DOM/JS interaction checks for Enter, Shift+Enter, `isComposing`, disabled submit and
  empty input.

### Package D — Restricted Research Product Boundary (P1)

#### Problem statement

Research is a mechanically correct durable runtime exposed as if it were a mature
user-facing research feature. The default no-Provider extractive path can be shown as
goal success, stale stage-local limitations survive terminal audit, and users can create
immutable Replay/Branch records without understanding the side effect.

#### Evidence

- RU-007 establishes the explicit `provider_runs_authorized=False` boundary.
- RU-009: `rtask_7d85f6b46e2276e92782d55827f8c3fb` upgrades an extractive
  `valid_partial` artifact to user-level `valid_success` after an evidence-presence gate.
- RU-015: `rtask_1dba17022494ca7f6c3326ed8d071b59` repeats the false-completion
  presentation; `rtask_cb9642043850c5da575238003e7b4790` then produced Replay children
  `rtask_788621ee3a21f405d168e90ef4ed99cf` and
  `rtask_66289cf296cccaf5674cacb51dcb624a`.

#### Root cause

The kernel's audit invariant—current evidence exists and registered constraints are
satisfied—is necessary for grounding but insufficient to establish semantic completion
of an arbitrary natural-language objective. Product projection treats the kernel result
as user-level completion and renders diagnostics/controls without a simple primary
workflow or durable-action affordance.

#### Allowed scope

**D-Core — required**

- Preserve historical kernel records and accepted V5 mechanics, but introduce a
  user-level completion projection that distinguishes:
  - verified objective completion;
  - limited deterministic extractive output; and
  - blocked/waiting/failed execution.
- The no-Provider evidence-presence path must project as limited/partial, not as “目标已
  完成”. Do not claim semantic completion without an authorized objective evaluator.
- Reconcile terminal limitations in the projection so `尚未执行 Outer Goal Audit` is not
  shown after a durable Outer Audit actually ran.
- Reposition the navigation/page as `受限 / Experimental` so the restricted
  no-Provider boundary is visible.
- Explain that Branch/Replay creates a permanent derived task and require confirmation
  before the request. Preserve immutable lineage and idempotency.

**D-UX — optional only while bounded inside the existing template/page structure**

- Provide one plain-language summary: `正在做什么 / 已找到什么 / 为什么停下 / 你现在可以做什么`.
- Collapse developer/runtime diagnostics and advanced V5-B/V5-C controls by default;
  hide or de-emphasize unsupported free-text success constraints and show supported
  semantics in plain language.
- If this requires a major Research workspace redesign, frontend rewrite or new
  information-architecture project, drop D-UX. It is sufficient this round to
  de-emphasize the entry, apply the Experimental label and collapse Advanced diagnostics
  where the existing page supports it.

#### Non-scope

- No Provider enablement, Research prompt/policy expansion, semantic judge platform,
  runtime/checkpoint/evidence rewrite, deletion/undo/archive system, Knowledge promotion,
  migration or reclassification of accepted V5/Frozen results.

#### Acceptance criteria

1. A deterministic no-Provider extractive artifact with current EvidenceUse is not shown
   as user-level `valid_success` or “目标已完成”.
2. A real authorized/evaluated success path, blocked constraint path and provider failure
   remain distinguishable and retain their durable records.
3. Terminal projection does not show a stale `Outer Audit 未执行` limitation after that
   audit exists.
4. The default page clearly identifies Research as Restricted / Experimental. If D-UX
   remains bounded, it also foregrounds a plain-language objective/status/finding/gap/
   next-action summary and collapses internal diagnostics; those UX refinements are not
   required when their documented implementation would exceed the bounded page scope.
5. Branch/Replay cannot create a derived task without an explicit confirmation that the
   action is durable. Cancel and existing idempotency/safety behavior do not regress.
6. D-Core passes independently. D-UX is implemented only if the existing template and
   page structure keep it bounded; dropping D-UX for documented scope reasons does not
   block D-Core acceptance.

#### Regression strategy

- Recreate RU-009's no-constraint deterministic task and assert limited user-level
  completion despite intact kernel audit records.
- Cover registered evaluator success, unsupported free-text constraint, waiting-user,
  provider failure and stale-limitation reconciliation.
- Add UI checks for default collapsed diagnostics and Branch/Replay confirmation.
- Run one minimal natural task only after repair; do not enable Provider or conduct a new
  Research benchmark.

## 6. Explicitly deferred or rejected work

| Candidate | Decision | Reason |
|---|---|---|
| Fast→Deep prior-run reuse | P2 / needs more natural evidence | Requires staleness, filter-change and authority semantics; recurrence is one case |
| Ask/Search history UI | P2 | Persistence exists, but no repeated navigation need has been demonstrated |
| Full progressive streaming | P2 | Useful, but requires staged/asynchronous contract changes; terminal candidate disclosure captures most failure value safely |
| Search naming/IA redesign | Observe | Standalone Search is fast, useful and a Provider-failure fallback |
| Mark vs Notes consolidation | Accept | Data semantics are coherent; ambiguity is amplified by sparse usage |
| Query-triggered Evidence Enrichment | Reject | Explicit non-goal and a new execution path |
| Manual ASR from Ask result | P2 | Keep lead/status disclosure now; do not add a new side-effect flow |
| Broad answer-depth tuning | Observe | RU-002/RU-005 show a pattern but do not define a stable quality contract |
| Automatic Fast/Deep routing | Reject | Explicit non-goal |
| Provider-backed Research enablement | Reject | Not bounded and would reopen unvalidated product semantics |
| New eval framework | Reject | Package regressions plus small natural smoke are sufficient |
| Bilibili tags | Reject for this round | Later retrieval/classification input, unrelated to current root causes |

## 7. Cross-package regression strategy

Each package must use the same four-layer proof:

1. **Original failure regression:** encode the observed state transition or payload shape,
   not the private query wording.
2. **Deterministic unit/integration regression:** exercise the shared implementation
   boundary with fake Provider/temp DB fixtures.
3. **Nearby behavior:** cover honest insufficiency, stale evidence, multi-folder cards,
   registered Research success and other adjacent invariants.
4. **Small natural smoke:** one or two user-like cases after tests pass, with durable IDs
   recorded in a repair closeout. Do not restart a 20–30 query eval.

The full deterministic suite remains the final non-regression gate. Frozen Eval assets,
accepted V5 identities and live private corpus files must remain untouched.

## 8. Portfolio-worthy failure cases

| Case | Worth preserving? | Why / allowed interview claim |
|---|---|---|
| Retrieval succeeds → output-budget failure → misleading insufficiency | **Yes** | Demonstrates durable trace diagnosis across Retrieval, evidence construction and shared Fast/Deep finalization; supports a claim about separating model failure from evidence sufficiency |
| 2,055-item corpus → 8 MB / ~9-second feed | **Yes** | Demonstrates why real-corpus onboarding changes product engineering priorities and motivates a measured bounded pagination repair |
| Durable Research kernel correct → semantic objective completion wrong | **Yes** | Demonstrates the distinction between verification invariants, runtime correctness and user-goal success without claiming the Research product is mature |
| Candidate evidence disclosed separately from citations | **Yes, after repair** | Useful evidence-governance story only after tests prove metadata/search leads are never promoted to factual authority |

Do not update README or resume claims during triage. Preserve the evidence for later
interview preparation after the corresponding repairs are actually implemented and
measured.

## 9. Recommended execution order

```text
1. Package A — Ask finalization reliability and outcome semantics (P0)
2. Package C — Library pagination, then bounded Ask keyboard affordance (P0/P1)
3. Package B — terminal candidate disclosure built on Package A's corrected outcomes (P1)
4. Package D — restricted Research boundary and projection (P1)
```

Package A comes first because it repairs the core Find → Evidence → Grounded Answer loop.
Package C is the independent deterministic blocker on the main landing surface. Package B
must consume Package A's corrected terminal classification rather than encode the old
ambiguity. Package D is valuable for trust but remains a restricted, non-core surface.

Each package should be a separately tested and rollback-able checkpoint. A package may be
dropped if its acceptance criteria require scope expansion.

## 10. Repair-session handoff requirements

A new bounded Repair Session should be opened only after user approval of this freeze.
The handoff must:

- start from the current pushed product-closeout baseline and preserve the untracked
  real-use evidence/triage documents;
- implement packages in the frozen order without combining them into a redesign;
- record original Case IDs and new regression IDs in each checkpoint;
- use temporary databases/fake Providers for tests before any live smoke;
- avoid modifying private corpus records merely to improve metrics;
- stop after the approved packages and a small closeout smoke;
- not plan V6 or begin deferred work automatically.

**Gate decision: `OPEN_NEW_BOUNDED_REPAIR_SESSION = YES`, pending explicit user
authorization.**
