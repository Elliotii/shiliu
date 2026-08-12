# Post-V5 Real-use Observations

Status: `REAL_USE_TESTING_PAUSED — SUFFICIENT EVIDENCE FOR TRIAGE`

This is the single running log for naturally occurring Search, Fast Ask, Deep Ask,
Research, Knowledge, and UI observations after Post-V5 product closeout. Cases are
diagnosed trace-first and remain observation-only unless the user explicitly authorizes
a bounded fix.

## Session closeout — 2026-08-12

- The current natural-use round is complete. Repeating broad Ask/Deep/Research cases is
  unlikely to add enough information to justify more user testing before repairs.
- Prioritize triage around: shared Ask provider-failure/sufficiency semantics; progressive
  evidence and candidate-lead disclosure; default-feed pagination/performance; and the
  end-user boundary of Long-term Research.
- Keep standalone Evidence Search and Citation return-to-source; treat Mark versus Notes
  as acceptable for this round; defer further testing until targeted regression checks
  exist for an authorized repair.
- Later-version note: Bilibili tags are obtainable through the existing CLI dependency
  and may later support retrieval/filtering/classification, but are outside the current
  practice and repair scope.

## RU-20260812-001 — Fast Ask reports insufficient despite retrieved Shanghai-food evidence

- Timestamp: 2026-08-12 17:51:55 Asia/Shanghai
- User action: Fast Ask — `有什么上海美食?`
- Subjective result: failure / unclear
- Trace identity: `ask_run_817767c8749a41fd908dec4299f6880c`
- Initial classification: Answer provider/runtime failure, with misleading UI status;
  not Retrieval Failure and not yet a Coverage Gap.
- Evidence:
  - Query analysis succeeded and produced `上海美食推荐` and `上海特色小吃`.
  - All three child Search traces persisted successfully with empty scope filters,
    `transcript_chunk` scope, hybrid execution, 50 raw hits each, and 20–22 unique
    videos each.
  - The retrieved results included directly relevant videos such as `来上海旅行吃什么`,
    `吃了上千家，才有了这篇上海2023年度美食榜单！附详细清单`,
    `我吃遍了上海最強的街頭小吃，第9家強的離譜！`, and `上海面馆红黑榜`.
  - Ask materialized 65 valid evidence items and selected 12 context spans.
  - The answer provider call reached its 4096-token output safety limit with
    `finish_reason=length`; persisted code is `output_budget_exhausted` and the run
    terminated as `provider_error`.
  - The UI simultaneously maps response status `insufficient` to `证据不足`, even
    though its termination copy maps `provider_error` to `回答服务暂时不可用`.
- Diagnosis: Retrieval succeeded and evidence existed. The answer-generation provider
  exhausted its output budget before returning valid structured output. Finalization
  converted that provider failure into an `insufficient` answer status, making a runtime
  failure look like evidence insufficiency. Default Ask scope was all currently indexed
  active favorite memberships with no folder/time/source filter, excluding ignored
  items. It did not use a frozen Eval/taxonomy snapshot or Research task snapshot.
- Confidence: high
- Product impact: high — blocks the grounded Ask loop and misdirects diagnosis.
- Recurrence: first_seen
- Recommended action: bounded_fix_candidate; separate provider-generation failure from
  evidence sufficiency in the user-visible result, then assess whether output-budget
  handling needs a bounded retry or generation-budget correction.
- Implementation status: not_authorized

## RU-20260812-002 — Scoped Fast Ask succeeds but is slow and under-detailed

- Timestamp: 2026-08-12 18:04:45 Asia/Shanghai
- User action: repeated Fast Ask `有什么上海美食?`, limited to the default favorite
  folder and favorites from 2026-01-01 onward.
- Subjective result: partial / friction
- Trace identity: `ask_run_0eabf36f514f40a382cc15bbdc1ff3f3`
- Initial classification: Answer/Product Expectation mismatch plus Provider latency;
  not Retrieval Failure.
- Evidence:
  - The requested folder and `favorite_time_from=2026-01-01` filters were present on
    all three child Search traces.
  - Query analysis took about 2.0 seconds. The three raw retrieval executions took
    about 1.43, 0.20, and 0.17 seconds. Total Ask latency was 55.6 seconds.
  - The final answer Provider call consumed 49.7 seconds, making it the dominant
    latency source.
  - Retrieval produced 61 valid evidence items and 12 context spans; 38 additional
    spans were dropped by the bounded context policy. The final answer cited six
    evidence spans and completed successfully as `partial / answer_ready`.
  - Provider usage was 10,067 prompt tokens and 2,690 completion tokens, of which
    2,358 were reported as reasoning tokens. The visible answer was one sentence
    listing several foods.
  - The current grounded-answer instruction explicitly prefers the fewest concise
    answer blocks and merges overlapping points, which can under-serve a broad
    recommendation question even when diverse evidence exists.
- Diagnosis: Narrowing the favorite scope did not materially reduce the final context
  size and is not the main reason the retry succeeded. Compared with the prior run,
  Provider generation completed instead of exhausting its output limit. The remaining
  55-second latency is overwhelmingly answer-generation time. The terse result reflects
  both the current brevity policy and inefficient reasoning-token use, rather than lack
  of retrieved evidence.
- Confidence: high
- Product impact: medium — result is grounded and usable, but latency and answer depth
  weaken the core Fast Ask value proposition.
- Recurrence: pattern_candidate with RU-20260812-001 for grounded-answer Provider
  latency/output efficiency; first observation for under-detailed successful output.
- Recommended action: gather_more_cases, then consider a bounded answer-quality/latency
  fix that defines useful response depth for broad recommendation questions without
  expanding retrieval architecture or weakening citation validation.
- Implementation status: not_authorized

## RU-20260812-003 — Ask hides completed retrieval while waiting for final generation

- Timestamp: 2026-08-12 18:09:04 Asia/Shanghai
- User action: reviewed the limitations shown by scoped Fast Ask
  `ask_run_0eabf36f514f40a382cc15bbdc1ff3f3`.
- User observation: Show retrieved evidence as soon as it is available; allow the final
  model answer area to remain pending instead of blocking the whole result for roughly
  50 seconds.
- Subjective result: friction
- Initial classification: UI/UX and Product Expectation/Product Boundary; backend
  retrieval exists earlier but the current synchronous Ask UI does not expose it.
- Evidence:
  - `本次提供的字幕证据仅覆盖部分上海美食，可能未包含全部种类。` was generated by
    the answer model inside the same structured response as the answer.
  - `上下文预算已截断部分候选证据` was appended deterministically by the local
    finalizer because `context_truncated=true`; it required no Provider call.
  - Neither limitation caused an additional model round trip. The model-generated
    limitation shares the existing 49.7-second answer call.
  - The HTTP Ask route waits for the complete synchronous Ask service result before
    returning JSON. The UI therefore shows only a loading state while query analysis,
    retrieval, materialization, and answer generation run, even though retrieval
    finishes much earlier than the final Provider response.
- Diagnosis: The main problem is perceived and actual response gating, not the cost of
  rendering the two limitation lines. Current persistence can preserve run and Search
  identities, but the current product contract does not stream or progressively expose
  intermediate Ask results. A staged experience could show retrieved evidence first and
  update the answer/limitations when final generation completes or fails.
- Confidence: high
- Product impact: medium — especially important when Provider latency is 50–90 seconds
  or answer generation fails after successful retrieval.
- Recurrence: first_seen; linked to the latency/output-efficiency family in
  RU-20260812-001 and RU-20260812-002.
- Recommended action: architectural_discussion after more natural cases; preserve as a
  candidate for progressive Ask disclosure rather than implementing an unbounded
  streaming/runtime rewrite from one case.
- Implementation status: not_authorized

## RU-20260812-004 — Deep Ask repeats output-budget failure as evidence insufficiency

- Timestamp: 2026-08-12 18:15:39 Asia/Shanghai
- User action: Deep Ask `有什么上海美食?`, limited to the default favorite folder
  and favorites from 2026-01-01 onward.
- Subjective result: failure
- Trace identity: `ask_run_a64a1e857a5a4dadb44141a8acf129be`
- Initial classification: repeated Answer provider/runtime failure plus misleading UI
  status; not Retrieval Failure or Coverage Gap.
- Evidence:
  - Deep completed four decision rounds and three tool calls, visited eight videos and
    314 segment identities, and resolved the question against seven evidence items.
  - Finalization retained seven valid evidence items and five bounded context spans;
    no final context span was dropped and `context_truncated=false`.
  - Deep search/decision work reached finalization after about 16.4 seconds. The final
    answer Provider then consumed another 64.2 seconds; total latency was 80.6 seconds.
  - The final Provider request used 3,524 prompt tokens and all 4,096 completion tokens
    as reported reasoning tokens. It ended with `finish_reason=length`, persisted
    `provider_error_code=output_budget_exhausted`, and returned no answer or citation.
  - Finalization again mapped the Provider failure to answer status `insufficient`,
    which the UI displays as `证据不足`.
- Diagnosis: Deep retrieval and evidence resolution succeeded. The shared grounded-answer
  Provider exhausted its output budget before producing structured visible output. This
  repeats RU-20260812-001 across both Fast and Deep and confirms that the failure is in
  their shared final answer path, not in either retrieval mode.
- Confidence: high
- Product impact: high — repeated failure blocks both Fast and Deep grounded-answer
  loops after substantial successful work and long user wait.
- Recurrence: repeated; establishes a failure family with RU-20260812-001 and reinforces
  the Provider latency/output-efficiency pattern from RU-20260812-002.
- Recommended action: bounded_fix_candidate. Repair Gate B (repeated failure family) and
  Gate C (core grounded Ask blocker) are now satisfied. A repair should separately fix
  provider-failure presentation and bounded final-answer generation behavior, with Fast
  and Deep regression tests; progressive evidence disclosure remains the separate
  RU-20260812-003 product idea.
- Implementation status: not_authorized

## RU-20260812-005 — Successful Deep answer is split into terse blocks with a model limitation

- Timestamp: 2026-08-12 18:21:12 Asia/Shanghai
- User action: Deep Ask `有什么上海美食?`, limited to the default favorite folder
  and favorites from 2026-06-01 onward.
- Subjective result: partial / unclear
- Trace identity: `ask_run_917e153e8c9a4e59a2bc24b4dc7e2005`
- Initial classification: Answer presentation/Product Expectation plus repeated Provider
  latency; not Retrieval Failure.
- Evidence:
  - The final answer contained three `answer_blocks`, each with its own supporting
    citation. All three blocks were returned together in one structured Provider call;
    they were not three sequential calls or streamed sentences.
  - The answer contract tells the model to split independently supported facts into
    separate blocks and to prefer a small number of concise, non-duplicate blocks.
  - `本次回答仅基于提供的有限字幕证据，可能未涵盖全部上海美食。` was generated in
    that same structured answer. There was no later reflection call or repair call.
  - `context_truncated=false` and no context spans were dropped, so this run had no
    deterministic truncation limitation appended by the local finalizer.
  - Deep completed successfully as `partial / answer_ready`, but still took 80.4 seconds;
    its single final-answer call took 63.9 seconds and used 2,810 reasoning tokens out of
    3,134 completion tokens.
- Diagnosis: The three-line layout is deliberate block-level citation grouping produced
  in one model response. The limitation is model-authored scope caution in the same
  response, not a second-stage reflection. The result reinforces the under-detailed
  answer and final-Provider latency pattern while showing that a narrower date filter can
  avoid budget exhaustion without making Deep materially fast.
- Confidence: high
- Product impact: medium
- Recurrence: repeated presentation/latency pattern with RU-20260812-002; successful
  counterpart to the output-budget failure in RU-20260812-004.
- Recommended action: gather_more_cases and include answer-block depth/organization plus
  model-vs-deterministic limitation provenance in any bounded answer UX repair.
- Implementation status: not_authorized

## RU-20260812-006 — Fast results are not reused by Deep and Ask history is not exposed

- Timestamp: 2026-08-12 18:26 Asia/Shanghai
- User observation: A successful Fast result should be available as prior experience for
  a subsequent Deep search; the product also appears to lack usable search/Ask history.
- Entry point: fast_ask → deep_ask / ui
- Subjective result: unclear / product expectation mismatch
- Initial classification: Product Expectation/Product Boundary, with UI discoverability
  and potential durable-lineage reuse implications.
- Evidence:
  - `AskRequest` accepts only query, mode, and filters. It has no prior-run or parent-run
    field.
  - Fast and Deep each create a fresh run; all observed `parent_run_id` values are null.
  - The UI action labelled `使用深入搜索继续` only switches the form to Deep while
    preserving the current query and filters. It does not submit the Fast `ask_run_id`,
    evidence, citations, rewrites, or child Search lineage.
  - Schema v16 durably preserves Ask runs and traces, but the current product UI does not
    provide a user-facing Ask/Search history list or select a prior run for reuse.
- Diagnosis: Current persistence is forensic, not conversational memory or execution
  reuse. Deep independently searches from the retained query/filter form state. Explicit
  Fast-to-Deep continuation could potentially reuse validated evidence and lineage, but
  must preserve changed-filter semantics, source versions, stale checks, and citation
  authority rather than silently importing an old answer.
- Confidence: high
- Product impact: medium; potential value is lower repeated work, clearer continuity,
  and easier return to prior evidence, but natural recurrence is not yet established.
- Recurrence: first_seen
- Recommended action: architectural_discussion / gather_more_cases. Evaluate explicit
  run continuation separately from a broader history UI or general memory architecture.
- Implementation status: not_authorized

## RU-20260812-007 — “长期研究” purpose and actual usability are unclear

- Timestamp: 2026-08-12 18:29:05 Asia/Shanghai
- User action: encountered the Long-term Research entry and asked why it exists, whether
  it is actually usable, or whether it was primarily exercised during feature testing.
- Entry point: research / ui
- Subjective result: unclear
- Initial classification: Product Expectation/Product Boundary and UI/UX semantics.
- Evidence:
  - V5-A deliberately introduced a durable recursive research runtime so a multi-step
    task can preserve goals, attempts, checkpoints, evidence lineage, results, user
    decisions, command receipts, and uncertain side effects across failure/restart.
  - The accepted V5-A closeout proves durable runtime and safety mechanics, but explicitly
    says representative grounded completion remained unproven.
  - The live Research page explicitly states `当前只启用无 Provider 机械路径` and
    `Provider · NOT EXERCISED`.
  - Current application wiring sets Research Provider execution authorization to false;
    normal Provider-backed product orchestration therefore fails closed.
  - Live SQLite contains one minimal restart-smoke Research Task in `ready` state, with
    zero attempts, checkpoints, results, or EvidenceUse rows. The onboarding report
    identifies it as a minimal non-Provider persistence smoke.
- Diagnosis: The durable task/control/lineage infrastructure is real and mechanically
  validated, not merely a mock. However, the current live product does not authorize the
  Provider-backed path that would perform substantive research, and real grounded
  completion/value has not been demonstrated. For ordinary users today, this is best
  described as restricted infrastructure/product scaffolding rather than a proven
  end-to-end long-term research feature. Its prominent product entry can therefore imply
  more immediate capability than the current contract supports.
- Confidence: high
- Product impact: high — directly affects navigation, feature trust, and whether users
  understand the boundary between Deep Ask and Durable Research.
- Recurrence: first_seen
- Recommended action: documentation_or_ui_copy plus product-boundary discussion. Decide
  later whether to expose it as an explicitly experimental/restricted workspace, enable
  and validate a bounded Provider-backed workflow, or de-emphasize it until real use is
  proven. Do not induce synthetic Research cases merely to justify V5-A.
- Implementation status: not_authorized

## RU-20260812-008 — Mark and My Notes navigation semantics overlap

- Timestamp: 2026-08-12 18:29:59 Asia/Shanghai
- User observation: Asked what distinguishes the `Mark` and `我的笔记` interfaces.
- Entry point: ui / library
- Subjective result: unclear
- Initial classification: UI/UX information architecture and terminology friction.
- Evidence:
  - Mark is a single boolean video flag (`is_marked`) intended for content worth
    revisiting or continuing to process. It can be toggled without writing text and is
    available as an explicit Search/Ask filter.
  - My Notes lists videos having one or more user-authored Markdown note records. Notes
    can be added, edited, and deleted independently of Mark.
  - User notes can affect video-level Search/navigation and appear as low-priority Deep
    navigation context, but they are not raw transcript/ASR Citation Authority and cannot
    independently ground final factual Ask claims.
  - The states are independent: a video can be marked only, noted only, both, or neither.
  - Current live data contains one marked video and one note on one video; therefore the
    two views currently project the same item and make their distinction hard to infer.
- Diagnosis: The data model distinction is coherent, but two top-level navigation entries
  show nearly identical card layouts and do not explain the different user intent. Sparse
  current state amplifies the ambiguity.
- Confidence: high
- Product impact: low
- Recurrence: first_seen
- Recommended action: documentation_or_ui_copy; observe whether the distinction becomes
  natural with more real marks/notes before considering navigation consolidation.
- Implementation status: accepted_as_is_for_current_round

## RU-20260812-009 — First natural Research task is mechanically accepted without useful research synthesis

- Timestamp: 2026-08-12 18:30:44 Asia/Shanghai
- User action: Created the Long-term Research task `梳理上海美食`, found the page and
  stop-condition language difficult to understand, and observed that the task stopped
  almost immediately without producing an intelligible research experience.
- Entry point: research
- Subjective result: failure / unclear
- Trace identity: `rtask_7d85f6b46e2276e92782d55827f8c3fb`
- Initial classification: Product Expectation/Product Boundary, Reasoning/Result
  acceptance failure, and UI/UX terminology/state inconsistency. This is not a Research
  persistence failure: the durable workflow and lineage were recorded correctly.

### Plain-language meaning of the constraint/evaluator copy

- The UI term is `evaluator`, not “elevator”. It means a server-owned deterministic rule
  that can decide whether one exact success constraint is satisfied.
- A user may type arbitrary natural-language success constraints, such as “cover at least
  ten restaurants” or “compare local and tourist recommendations”. The runtime refuses
  to let either the caller or a model simply declare such text satisfied.
- Unless the server has an evaluator registered for that exact constraint semantics, the
  task fails closed: it becomes blocked/waits for clarification instead of fabricating a
  successful verification.
- This is a legitimate safety boundary, but the current product asks ordinary users to
  understand internal implementation language (`evaluator`, registry, fail closed) and
  does not explain what constraints are actually supported.

### Actual task lifecycle

1. **Task/Goal creation — 18:30:44.713.** The runtime persisted a new Task and Goal with
   objective `梳理上海美食`. No explicit success constraints were supplied. The selected
   policy was `grounded_current_evidence` and execution was recorded as
   `deterministic_no_provider`.
2. **Ownership and Attempt — 18:30:44.733–44.741.** A local runner claimed a bounded
   owner lease and opened Attempt 1. This is durability/concurrency bookkeeping, not
   research reasoning.
3. **Plan checkpoint — 18:30:44.767.** A deterministic inner action moved the state to
   navigation. No Provider call occurred.
4. **Navigation checkpoint — 18:30:45.607.** The fixed path focused eight existing
   videos. Navigation added no factual evidence itself.
5. **Transcript Search checkpoint — 18:30:46.453.** Search materialized six current
   transcript evidence uses.
6. **Transcript Window checkpoint — 18:30:46.623.** One bounded window read added a
   seventh evidence use.
7. **Provisional synthesis — 18:30:46.837.** With Provider execution disabled, the
   deterministic extractive policy copied three long raw transcript passages into three
   answer blocks (5,298 synthesis-context characters). It did not organize, compare, or
   meaningfully summarize Shanghai food. The artifact correctly labelled itself
   `valid_partial` and carried the limitation `无 Provider deterministic extractive
   synthesis；尚未执行 Outer Goal Audit`.
8. **Outer Goal Audit — 18:30:46.935.** Because the user supplied no explicit success
   constraints, the only effective server rule was essentially “a grounded artifact has
   at least one currently valid EvidenceUse”. Seven evidence uses satisfied that rule.
   The audit did not semantically determine whether the result actually “梳理”上海美食,
   yet returned `accept / all_required_constraints_satisfied`.
9. **Terminal result.** The Task was upgraded from the provisional artifact's
   `valid_partial` to terminal `valid_success / answer_ready / failure_class=none` after
   about 2.22 seconds. The product projection says “已有可用答案并完成本次目标审计”.
10. **Candidate deltas — 18:30:46.994.** The runtime recorded Knowledge/Corpus/UserModel/
    SystemExperience candidate deltas. Knowledge entries remained
    `candidate_only_not_promoted`; the other delta families were empty. No durable
    Knowledge truth was automatically created.
11. **Durable boundary — 18:30:47.000.** The workflow ended with 12 events, six
    checkpoints, five inner actions, one audit, and 12 command receipts. Persistence and
    traceability worked as designed.

### Evidence-backed diagnosis

- Provider status is `not_exercised`; this was not genuine model-backed long-term
  research and no Provider error occurred.
- The task did not stop because of an unsupported free-text constraint, because the user
  supplied none. It stopped because the permissive default evidence-presence evaluator
  accepted the mechanically extracted artifact.
- The durable kernel is functioning, but its success semantics are not aligned with the
  natural-language objective. “Has current citations” is necessary for grounded research
  but is not sufficient to prove “the requested research was completed”.
- The displayed artifact limitation says the Outer Audit has not run, even though the
  later durable trace proves that it ran and accepted the task. The projection exposes a
  stale stage-local limitation after terminalization.
- The UI presents internal state-machine vocabulary, authority boundaries, deltas,
  evaluator registration, and checkpoints without a user-level explanation of what the
  user asked, what was found, what remains unresolved, and why the task stopped.

- Confidence: high
- Product impact: high — the first natural Research use produced a result the user could
  not understand while the system labelled it successful, undermining trust in both the
  feature and its status semantics.
- Recurrence: pattern_candidate with RU-20260812-007; this is the first natural end-to-end
  Research execution and supplies concrete evidence that real product value/grounded
  completion remains unproven.
- Recommended action:
  - immediate bounded candidate: do not present deterministic extractive output as
    user-level `valid_success` merely because current evidence exists; reconcile or
    remove stale pre-audit limitations in terminal projection;
  - documentation/UI candidate: replace evaluator/registry/fail-closed copy with examples
    of supported constraints and plain-language blocked/accepted explanations;
  - product/architecture discussion: decide whether Long-term Research remains visibly
    restricted, gains one explicitly authorized and validated Provider-backed workflow,
    or is de-emphasized until it can perform meaningful synthesis;
  - preserve the durable Task/Attempt/Checkpoint/EvidenceUse machinery, which behaved
    correctly, and avoid treating this Case as authorization for a Research rewrite.
- Implementation status: not_authorized

## RU-20260812-010 — The need for a separate “搜索证据” product entry is unclear

- Timestamp: 2026-08-12 18:47 Asia/Shanghai
- User observation: Asked whether the Search Evidence feature is unnecessary.
- Entry point: search / ui
- Subjective result: unclear
- Initial classification: Product Expectation/Product Boundary and UI information
  architecture; not a Search capability failure.
- Evidence:
  - Search is the retrieval foundation used by Fast Ask, Deep Ask, and Research. Removing
    the underlying capability is not viable without removing their evidence acquisition.
  - Standalone Search does not call a remote LLM by default and exposes direct result
    groups, transcript windows, filters, scope, mode, and return-to-source timestamps.
  - The user's recent standalone `上海美食` trace
    `b17c541e-8105-4677-ad0e-0f50981ccf4a` completed hybrid retrieval in about 456 ms and
    presentation in about 80 ms, returning 10 video groups and 15 evidence windows.
  - In contrast, observed Fast/Deep final-answer Provider calls take roughly 50–76
    seconds and can fail after successful retrieval. Standalone Search preserves useful
    evidence access when answer generation is slow or unavailable.
  - The current top-level label `搜索证据` does not plainly explain its relationship to
    `问答`. The page also exposes advanced concepts—scope, lexical/dense/hybrid mode,
    Research Task context, Corpus-aware behavior, and optional sufficiency judgment—that
    can make a core direct-search path feel like a duplicate or developer tool.
- Diagnosis: The standalone evidence-first workflow has demonstrated real utility and is
  especially important under the current Ask latency/failure family. The product problem
  is positioning and complexity, not redundancy of the underlying function. Progressive
  Ask disclosure (RU-20260812-003) could share this evidence presentation while a simpler
  direct-search entry remains available for browsing and verification.
- Confidence: high
- Product impact: medium
- Recurrence: first_seen; related to the broader Fast/Deep/Search boundary ambiguity.
- Recommended action: observe natural use, then consider clearer naming and a simplified
  default Search surface with advanced options progressively disclosed. Do not remove or
  merge the standalone path before verifying that direct evidence browsing,
  return-to-source, and Provider-failure fallback remain accessible.
- Implementation status: not_authorized

## RU-20260812-011 — Insufficient Ask results hide successfully retrieved candidate evidence

- Timestamp: 2026-08-12 18:58:22 Asia/Shanghai
- User observation: When Ask reports insufficient evidence, provide an expandable control
  so the user can inspect what was retrieved.
- Entry point: fast_ask / deep_ask / ui
- Subjective result: friction
- Initial classification: UI/UX and Evidence Presentation; related to, but distinct from,
  the progressive-disclosure idea in RU-20260812-003.

### Recent-run evidence

- Fast `大冰` (`ask_run_1046902129f64af190b4d08797ef9f69`) materialized 109 valid
  transcript spans and 12 final context spans, but the answer model returned
  `insufficient / answer_ready` with no citations.
- Fast `我收藏过哪些有关大冰的连麦视频`
  (`ask_run_8c69dd48c8044ee7ad01be05bcc0b281`) materialized 50 valid spans and
  12 context spans, then returned the same empty insufficient result. This also exposes a
  likely product-boundary mismatch: a list/known-item request may be better served by
  Search presentation identities than by transcript-only factual answer finalization.
- Fast Switch comparison (`ask_run_4bc7cddeef64416da75d9f103339ad6d`) materialized 85
  valid spans, but Provider returned an empty model output; the UI again showed an empty
  insufficient result.
- A narrower Fast Switch 2 vs Lite query
  (`ask_run_e86bec8229e44d8e948fea0f0cdefba5`) materialized 96 spans but was judged
  insufficient. The subsequent Deep run found usable 2020 Switch Lite evidence while
  explicitly reporting no Switch 2 transcript evidence, yielding a partial one-citation
  answer. This demonstrates why candidate inspection must distinguish topical matches
  from evidence that covers every requested comparison dimension.
- Recent MacBook runs repeated the shared final-answer pattern: Fast partial in 69.9 s;
  Deep Provider output-budget failure in 119.4 s; Deep partial retry in 78.3 s.

### Current contract boundary

- `AskResponse` requires an insufficient response to have no answer blocks. Current
  finalization also emits no citations for insufficient answers.
- Persistence stores `final_evidence` only for evidence actually cited by the final
  answer, so insufficient runs have empty final evidence even when many valid spans were
  materialized.
- The ordered child Search trace IDs and durable Search presentation records remain
  available. They preserve queries, ranks, unit/window identities, and presentation
  summaries, though not a byte-for-byte historical UI response.
- Therefore this is not a pure show/hide UI change. A safe implementation must either
  reconstruct a bounded current projection from child Search lineage or durably retain a
  separate bounded `retrieved_candidate_evidence` projection at Ask completion.

### Diagnosis and desired semantics

- Empty insufficient pages conflate honest missing coverage, model-declared
  insufficiency, repeated-search stop, Provider failure, and output-budget failure.
- An expandable section should be labelled `本次检索到的候选证据` rather than `回答引用`.
  It should show which query/rewrite produced each result, video/title, transcript window,
  timestamp, and a warning that retrieval does not mean the candidate supports the whole
  requested conclusion.
- Provider failures should expose successfully retrieved candidates while separately
  stating that no verified answer was generated. Honest insufficiency should explain the
  missing aspect when known (for example, Switch 2 evidence absent while Switch Lite
  evidence exists).

- Confidence: high
- Product impact: high — preserves useful work, improves failure diagnosis, and reduces
  the dead-end feeling after 20–120 seconds of successful retrieval/failed finalization.
- Recurrence: repeated across Fast and Deep; tied to RU-20260812-001, 003, and 004.
- Recommended action: bounded_fix_candidate after the already-established shared Ask
  failure repair is scoped. Keep candidate evidence separate from Citation Authority and
  do not silently promote Search/navigation material into grounded answer citations.
- Implementation status: not_authorized

## RU-20260812-012 — Default-folder content feed renders the entire corpus before first paint

- Timestamp: 2026-08-12 19:42 Asia/Shanghai
- User observation: Opening the content feed is consistently slow; suspected cause is
  being positioned in the default folder and rendering all of it.
- Entry point: library / content feed
- Subjective result: latency / friction
- Initial classification: UI/UX performance and data-access pagination boundary.
- Evidence:
  - The live default folder has 2,055 active memberships; all active folders together
    have 2,211 membership rows.
  - A read-only request to `/?source=3` returned 2,055 cards, an 8,465,186-byte HTML
    response, and took 8.69 seconds before completion (8.68 seconds to response headers).
  - The in-app browser navigation exceeded its 10-second navigation window; attempting
    a full DOM snapshot of the resulting page then failed internally because of the page
    size. In contrast, empty `marked` and `noted` projections for the same folder each
    returned in about 0.03 seconds and about 2 KB.
  - The home route calls `list_video_cards` without a limit or pagination cursor, then
    loads notes and runs `_video_view` for every row. `_video_view` also checks ASR state
    and may read a summary JSON artifact for each card.
- Diagnosis: The user's hypothesis is correct. This is not primarily a transient network
  problem: the server constructs and the browser parses the entire 2,055-item folder on
  every open. Folder selection narrows the corpus but does not bound the result set.
- Confidence: high
- Product impact: high — the primary landing surface blocks for roughly nine seconds and
  transfers more than eight MB before becoming usable.
- Recurrence: repeated on every default-folder feed open.
- Recommended action: bounded_fix_candidate. Add server-side cursor/page-size bounds and
  incremental loading; make the initial payload a small first page and defer card detail
  or summary loading until visible. Preserve filter/order semantics and measure server
  time, first render, and scroll continuity before/after.
- Implementation status: not_authorized

## RU-20260812-013 — Buran query finds an exact description match but has no citable transcript

- Timestamp: 2026-08-12 19:42 Asia/Shanghai
- User action: Asked `暴风雪航天飞机的历史`; the known relevant video has an indirect
  poetic title and no subtitle.
- Entry point: fast_ask / deep_ask / search
- Subjective result: insufficient
- Trace identities: Fast `ask_run_9a63bb377f0c47aeb20899a85b22ad2d`; Deep
  `ask_run_cb58ead1fabf46d8a14f44336d251db6`.
- Evidence:
  - Video 179 (`BV1zSj26VEUW`) is the exact user-identified title. Its durable state is
    `skipped_no_subtitle / no_supported_subtitle`, with no raw subtitle, transcript, or
    summary artifact.
  - Its stored description explicitly contains `“暴风雪”号航天飞机` and
    `Space shuttle buran`. The video-level `video_composite` retrieval unit includes the
    full stored description, and both terms are present in `source_text` and
    `search_text`.
  - Deep video-level searches ranked video 179 first for both `暴风雪航天飞机 历史` and
    `暴风雪号 航天飞机 历史`. This is a direct metadata match, not merely a semantic
    inference from the poetic title.
  - Fast searched transcript chunks for three rewrites. The two Chinese searches each
    returned 50 raw hits and 10 groups/17 windows, but these were unrelated transcript
    matches; the English Buran rewrite returned zero. Fast ended
    `insufficient / answer_ready` with zero final evidence/citations.
  - Deep found eight video-level groups but zero transcript windows, then ended
    `insufficient / repeated_search` with zero final evidence/citations.
- Diagnosis: This case separates discovery metadata from answer authority. The system has
  exact title/description metadata proving that the video is about Buran, and Deep
  navigation successfully finds it, but there is no transcript source text that Ask is
  allowed to cite for a historical account. Fast Ask's transcript-only search lane does
  not surface the exact description match at all. The insufficiency remains honest for a
  factual history answer, but the UX currently discards a strong known-item lead and
  makes an explicit metadata hit look like total search failure.
- Confidence: high
- Product impact: medium/high — correct discovery is discarded at finalization, making a
  source-coverage gap look like a total search failure.
- Recurrence: pattern_candidate with RU-20260812-011.
- Recommended action: show a separate `相关视频线索（无可用字幕，不能作为回答证据）`
  section on insufficient results, with the video title/status and an optional explicit
  manual-ASR route. Do not promote title similarity or video identity into Citation
  Authority.
- Implementation status: not_authorized

## RU-20260812-014 — Ask keyboard behavior conflicts with expected Enter-to-submit convention

- Timestamp: 2026-08-12 19:42 Asia/Shanghai
- User observation: Enter should submit/search and Shift+Enter should insert a newline.
- Entry point: ask / search input
- Subjective result: friction
- Initial classification: UI/UX keyboard interaction.
- Evidence:
  - Standalone Search already uses a single-line search input and intercepts Enter to run
    Search.
  - Ask uses a three-row textarea. Its current handler submits only on Cmd+Enter or
    Ctrl+Enter; plain Enter inserts a newline. No visible copy explains this shortcut.
- Diagnosis: The request applies to Ask, not standalone Search. The current hidden
  Cmd/Ctrl+Enter convention is valid for a long-form editor but mismatched with the
  product's short-query behavior and the user's expectation.
- Confidence: high
- Product impact: low/medium, but high-frequency.
- Recurrence: repeated interaction friction.
- Recommended action: bounded_fix_candidate. In Ask, submit on Enter when IME composition
  is not active; preserve newline on Shift+Enter; keep the button and Cmd/Ctrl+Enter as
  accessible alternatives. Add a small visible hint and regression-test Chinese IME,
  empty input, in-flight submission, and mobile behavior.
- Implementation status: not_authorized

## RU-20260812-015 — Research random clicks create durable task/replay records behind an incomprehensible mixed-language console

- Timestamp: 2026-08-12 19:42 Asia/Shanghai
- User observation: Clicked around in Long-term Research, could not understand what was
  happening, and saw extensive English/internal terminology.
- Entry point: research
- Subjective result: unclear / accidental durable mutation
- Initial classification: UI/UX information architecture, product-boundary disclosure,
  and action safety/affordance.
- Evidence-backed reconstruction:
  1. At 19:34:12, task `rtask_1dba...` for `ai 对于未来的改变` was created without an
     extra success constraint. The deterministic no-Provider path produced raw
     extractive blocks and was mechanically accepted as terminal `valid_success` in
     about 2.2 seconds.
  2. At 19:34:32, task `rtask_cb96...` was created with the extra constraint
     `current EvidenceUse、citation 与有效 provisional artifact`. It still performed
     navigation/search/extraction, but the Outer Audit could not match that free text to
     a registered deterministic evaluator. It is now `waiting_user`, while the visible
     phase says `blocked`, answer says `valid_partial`, stop reason says
     `needs_user_input`, failure class says `none`, and the reason line says only
     `needs_user`.
  3. At 19:34:41, clicking `创建 Replay` derived blocked task `rtask_7886...` from the
     waiting task's checkpoint. At 19:35:15, another Replay derived blocked task
     `rtask_6628...` from the first replay. Both are durable records; neither is merely a
     temporary UI selection.
  4. No control requests, WorkspaceRecords, accepted Knowledge candidates, or other
     promoted knowledge writes were recorded in this sequence. The accidental durable
     effects were task creation, execution traces, candidate-only deltas, and two replay
     derivations.
- Visible-language evidence: the actual page mixes user concepts with `DURABLE RESEARCH`,
  `Provider · NOT EXERCISED`, `evaluator`, `EvidenceUse / citation`, `blocked`,
  `valid_partial`, `needs_user_input`, `SERVER POLICY`, `CURRENT OPERATIONS`, `Branch`,
  `Replay`, `Personalized research journey`, `Next path recommendation`,
  `ArtifactRoute`, `Manual ASR`, `Candidate Delta`, `WorkspaceRecord`, and raw hashes/task
  IDs. The screen exposes more than one product stage and several independent subsystems
  in one long workspace.
- Diagnosis: This is currently an internal observability/control console presented as a
  normal end-user feature. The interface does not establish a simple primary workflow,
  uses inconsistent status vocabularies, and does not explain that Branch/Replay create
  permanent derived tasks. The user's inability to understand it is a predictable result
  of the interface, not a lack of testing effort.
- Confidence: high
- Product impact: high — users can unintentionally multiply durable records and cannot
  tell whether a task succeeded, failed, paused, or needs input.
- Recurrence: repeated; extends RU-20260812-007 and RU-20260812-009.
- Recommended action:
  - stop asking the user to test additional permutations until the primary workflow and
    status model are redesigned;
  - provide one plain-language task summary: `正在做什么 / 已找到什么 / 为什么停下 /
    你现在可以做什么`;
  - translate or hide internal labels, hashes, stages, authority traces, and developer
    controls behind an advanced diagnostics disclosure;
  - label Branch/Replay as durable creation actions, explain their difference, and add a
    lightweight confirmation or undo/archive path;
  - keep candidate-only knowledge unpromoted and preserve the durable audit trail.
- Implementation status: not_authorized
