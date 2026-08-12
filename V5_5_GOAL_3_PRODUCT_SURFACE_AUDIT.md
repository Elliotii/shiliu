# Shiliu V5.5 — Goal 3 前置产品表面审计

## 1. Audit baseline

- branch: `codex/v5-5-productization`
- HEAD: `09e50bd0f3b4c4a7d86ad90306d766369b4b2572`
- worktree at audit start: clean
- method: current-source inspection plus GET-only inspection of the current HEAD against existing local projections. No Provider call, product mutation, test run, reviewer, commit, or Goal 3 implementation was performed.
- existing-data checkpoint: task `rtask_c9a09e60bcab6ffb30bc29baa226bae4` visibly contains 3 saved Facts, 1 Artifact, 1 published Topic Page, and 1 completed `direct_reuse` result. Its personal workspace contains 0 records; V5-C assistance remains at baseline.
- worktree after this report: only this requested, uncommitted audit file is new.

## 2. Current core product surfaces

| Surface | Actual route / location | Current primary purpose and actions |
| --- | --- | --- |
| Home / Library | `/` | Recent saved videos; sync, read state, Mark, archive, notes, transcript/summary, retry/refine/ASR. |
| Mark / Notes / Archive | `/?view=marked`, `/?view=noted`, `/?view=archived` | Filtered Library views using the same video-card surface. There is no separate `/library` route. |
| Search | `/search` | Search the collection and return to video/transcript evidence; common filters plus advanced retrieval/corpus/sufficiency options. |
| Ask Fast / Deep | `/ask` | Grounded answers from current subtitles. Fast and Deep are explained as two modes of one task; Fast can explicitly continue to Deep. |
| Research | `/research`, `/research/{task_id}` | Create and revisit durable multi-step Research tasks; inspect result, evidence, state, controls, Knowledge, V5-C personalization, and trace. |
| Knowledge / Topic Page / Reuse | embedded in `/research/{task_id}` | Review/publish saved conclusions, view Topic Page cards, inspect currentness, and assess a later query for reuse/refresh/research. No standalone Knowledge route or global navigation entry exists. |
| Personalization / Focus / Progress | embedded in `/research/{task_id}` | Integrated Journey, route recommendation, answer presentation preference, Knowledge Assistance, and Personal/Corpus Workspace. No standalone Personal Workspace surface exists. |
| Supporting surfaces | `/videos/{video_id}/transcript`, `/taxonomy`, `/setup` | Transcript drilldown, a corpus-snapshot experiment, and configuration. Taxonomy is nevertheless exposed in the primary navigation. |

Route evidence: `src/shiliu/web.py:250-353`; navigation: `src/shiliu/templates/base.html:13-16`.

## 3. Already resolved by G1/G2

- **RESOLVED — Ask purpose and Fast/Deep distinction.** `/ask` says what the surface does, when to use Fast or Deep, what evidence is authoritative, and offers Fast → Deep continuation plus a Search alternative (`src/shiliu/templates/ask.html:6-30`, `74-82`, `126-129`).
- **RESOLVED — Research truthfulness and immediate status.** The accepted task shows one plain-language summary for “正在做什么 / 已找到什么 / 为什么停下 / 你现在可以做什么”; Branch/Replay durable creation requires confirmation. This resolves the G1 completion-truth and accidental-derivation problems, not the whole page hierarchy (`src/shiliu/templates/research.html:61-79`; `src/shiliu/static/research.js:1019-1037`).
- **RESOLVED — Save to Knowledge review/publish path.** G2 presents “保存到知识”, review-before-publish, source/currentness language, transcript drilldown, and clear publish/reject/update actions (`src/shiliu/templates/research.html:199-231`; `src/shiliu/static/research.js:450-530`).
- **RESOLVED — Reuse/refresh decision inside the G2 Knowledge section.** The primary route labels are user-facing (“已有知识足够，可以直接使用 / 需要补充 / 需要重新研究”), with evidence links and diagnostics folded under details (`src/shiliu/static/research.js:676-720`).
- **RESOLVED — G2 internal vocabulary is no longer the main Knowledge action language.** `ArtifactRoute`, revision IDs, gates, and contributions remain in advanced diagnostics; the ordinary G2 decision uses user language.
- **NOT RESOLVED — Mark versus Notes.** The two concepts remain separate top-level entries and the existing sparse data makes both views show the same card. This remains a current Goal 3 candidate rather than a G1/G2 issue.

## 4. Confirmed remaining problems

### P1 — V5-C is an internal console, not a comprehensible product surface

- page / route: `/research/{task_id}` — Integrated Journey, Next Path, Knowledge Assistance, Personal and Corpus Workspace.
- user actually sees: `V5-C · STAGE 3/4/5`, `baseline`, hashes, `execution authority false`, `ArtifactRoute`, `Provider-backed Ask`, `Durable Research`, `Manual ASR`, exact video/snapshot IDs, `WorkspaceRecord`, record kinds/statuses, semantic key, source refs JSON, confidence, expiry, and immutable-history/revision controls.
- why this is a product problem: the surface explains safety invariants and storage types, but not what personalization will do for the user, why it helps now, or the one next action to take. The main Research view exposes creation and mutation controls for internal record types.
- source: `src/shiliu/templates/research.html:97-141`, `234-310`; rendered status/record language in `src/shiliu/static/research.js:788-950`.
- severity: `must_fix_for_g3`

### P2 — V5-C cold start occupies a large main-view area without usable guidance

- page / route: `/research/{task_id}` on the existing Goal 2 task.
- user actually sees: 0 WorkspaceRecords; route recommendation `baseline / no_confirmed_route_preference`; four assistance lanes showing `no_progress`, `no_stale_lineage`, `snapshot_pair_absent`, and `no_confirmed_focus`; Integrated Journey shows four baseline/hash steps.
- why this is a product problem: empty state is expressed as internal reason codes. It does not tell the user what Current Focus, Progress, Collection Delta, or Radar would help with, or how ordinary product use produces meaningful data. Large empty panels therefore look broken or unfinished.
- source: `src/shiliu/static/research.js:831-918`, `920-950`; empty workspace copy at `src/shiliu/static/research.js:794-828`.
- severity: `must_fix_for_g3`

### P3 — Published Knowledge is real but not globally discoverable

- page / route: Knowledge exists only inside `/research/{task_id}`; there is no `/knowledge` route or navigation entry.
- user actually sees: the current task contains published conclusions, a Knowledge summary, a published Topic Page, and a later-query reuse form. To find any of it later, the user must remember and reopen the originating Research task, then scroll deep into that page.
- why this is a product problem: G2 completed durable Knowledge and reuse behavior, but the user journey stops at storage. “Knowledge / Topic Page / later related query” is not a findable product destination.
- source: route set in `src/shiliu/web.py:250-353`; navigation in `src/shiliu/templates/base.html:15`; embedded Knowledge only in `src/shiliu/templates/research.html:199-232`.
- severity: `must_fix_for_g3`

### P4 — Research still mixes the primary task with policy, maintenance, personalization, and diagnostics

- page / route: `/research/{task_id}`.
- user actually sees, in one long default page: task state, plain summary, server policy, current operations, Integrated Journey, route controls, answer preference, answer, evidence, Candidate Delta, Knowledge, Assistance, Workspace record creation, and durable trace. Main-view language still includes `EvidenceUse`, `citation`, `evaluator`, `Outer Audit`, `Candidate Delta`, `KnowledgeDelta`, `CorpusDelta`, hashes and raw task IDs.
- why this is a product problem: G1 repaired product truth and G2 repaired its Knowledge subsection, but ordinary reading and next action still compete with internal policy and maintenance systems. The user cannot quickly distinguish “use the result” from “operate or diagnose the system.”
- source: `src/shiliu/templates/research.html:21-35`, `51-141`, `191-322`; delta rendering starts at `src/shiliu/static/research.js:180-206`.
- severity: `must_fix_for_g3`

### P5 — Existing task flows have navigation, but weak contextual handoffs

- page / route: `/`, `/search`, `/ask`, `/research/{task_id}`.
- user actually sees: Library cards offer transcript/summary and maintenance actions but no contextual Search/Ask action; Search results only offer “查看拾流详情”; Ask offers Search and Fast → Deep, but no bounded escalation to Research; the only cross-consumer journey is a technical V5-C panel inside Research.
- why this is a product problem: Search, Ask, Deep, Research and Knowledge each make sense in isolation, but the user must reconstruct when to move between them. This breaks the intended Library → query → Research → Knowledge → later reuse journey at entry and escalation points.
- source: Library actions `src/shiliu/templates/index.html:76-94`; Search result action `src/shiliu/static/search.js:182-217`; Ask transitions `src/shiliu/templates/ask.html:74-82`, `126-129`; technical Journey `src/shiliu/templates/research.html:97-110`.
- severity: `must_fix_for_g3`

### P6 — Mark and Notes still require the user to infer their semantic difference

- page / route: `/?view=marked`, `/?view=noted`, plus primary navigation.
- user actually sees: “Mark” is described as worth revisiting; “我的笔记” as items with written notes. Both use the same card, and current real data shows the same single video in both views. Mark remains English in navigation, badges, buttons, and archive metadata.
- why this is a product problem: the data distinction is valid, but intent and next action remain too similar at the product level. The historical issue is still directly reproducible.
- source: `src/shiliu/templates/base.html:15`; `src/shiliu/templates/index.html:7-10`, `34-54`, `84-101`.
- severity: `should_fix_if_bounded`

### P7 — Home and Search expose internal status/execution language to ordinary users

- page / route: `/`, `/search`.
- user actually sees: Home cards and source/sync chrome print raw values such as `completed`, `skipped_no_subtitle`, `cooldown`, and `running`. Search advanced options expose `Research Task context`, task IDs, `Corpus-aware`, `soft prior`; the optional sufficiency result expands into pipeline stage, mechanical gate, semantic sufficiency, reason codes, policy version, evidence IDs and trace ID on the normal results surface.
- why this is a product problem: these labels describe implementation state rather than user meaning. Search’s advanced function is legitimate, but its results do not separate a user decision from execution diagnostics.
- source: `src/shiliu/templates/index.html:13-15`, `20-24`, `34-41`; `src/shiliu/templates/search.html:44-77`, `104-116`; `src/shiliu/static/search.js:290-365`.
- severity: `should_fix_if_bounded`

### P8 — An experimental corpus tool remains a peer of primary product destinations

- page / route: `/taxonomy`, linked as “分类实验” in the global navigation.
- user actually sees: a `V3 · CORPUS SNAPSHOTS` tool for selecting folders and freezing snapshot IDs/hashes.
- why this is a product problem: it is a real advanced/internal surface, but primary navigation gives it equal weight with Library, Ask, Search and Research. This adds another apparent product path without explaining when an ordinary user needs it.
- source: `src/shiliu/templates/base.html:15`; `src/shiliu/templates/taxonomy.html:1-80`.
- severity: `minor`

## 5. V5-C current product visibility

| Capability | Current visibility judgment |
| --- | --- |
| Current Focus | **存在但价值隐藏 / cold.** It is a Workspace record kind and can appear in answer-presentation status, but current data has no focus and the ordinary user is offered a typed-record form rather than a product explanation (`research.html:264-306`; `research.js:124-150`). |
| Knowledge Progress | **存在但价值隐藏 / cold.** The lane is visible but only says `no_progress`; no meaningful progress summary or path to producing progress is shown. |
| Staleness | **已被 G2 部分吸收.** Knowledge cards naturally say “来源仍有效 / 需要检查更新”; the V5-C staleness lane itself remains empty and technical. |
| Collection Delta | **仅内部/高级且 cold.** The main panel asks for baseline/current snapshot IDs and reports `snapshot_pair_absent`; no user-level change story is visible. |
| Corpus-aware assistance | **存在但价值隐藏.** Research links to Search with task context, and Search supports a soft prior, but setup/explanation uses task IDs, `Corpus-aware`, lanes and baseline ranks (`search.html:66-74`; `search.js:174-179`, `220-238`). |
| Route Recommendation | **存在但价值隐藏 / cold.** It is advisory and safe, but current output is baseline; available paths and permissions are expressed as internal route names and execution gates rather than a recommendation the user can understand. |
| Project Radar / Knowledge Assistance | **仅内部且 cold.** Radar has no confirmed focus; all four assistance lanes show reason codes instead of value or next action. |
| Integrated Journey | **存在但未自然产品化.** It links Answer/Search/Next path/Assistance, but presents hashes, baseline states and `execution false`; it reads as observability rather than a journey. |

Overall: no V5-C capability is yet naturally productized end to end. G2 has naturally absorbed the user-facing part of Knowledge currentness/staleness, and G1 has absorbed Research’s truthful status/next-step summary.

## 6. Cross-product journey gaps

1. **Library → Search / Ask:** global navigation exists, but a selected video/card does not provide a contextual handoff or carry useful scope.
2. **Search → Ask / Research:** results return to the video detail only; query, filters, and evidence context cannot be continued through a visible user action.
3. **Ask Fast → Deep:** **RESOLVED.** The explicit continuation preserves the current question and scope.
4. **Ask / Deep → Research:** no visible bounded escalation exists when the user needs durable multi-step work.
5. **Research → Save to Knowledge → Knowledge:** **RESOLVED inside the originating Research task**, including review, publish, source drilldown, and currentness.
6. **Knowledge → later related query → reuse/refresh:** behavior exists and is understandable once found, but its only entry is the form inside the originating task. Published Knowledge is absent from global navigation, Search, and Ask.
7. **Personalization across the journey:** Integrated Journey technically links consumers, but baseline hashes/reason codes do not provide an understandable cross-product continuation.

## 7. Explicitly out of Goal 3

- Provider latency, availability, quota, or failure repair.
- Multi-source Research quality, prompt/policy expansion, or semantic completion judging.
- Background worker, scheduler, notification, proactive execution, or automatic Radar actions.
- Automatic required-aspect inference for Knowledge reuse.
- New Memory, Router, Agent, Eval, semantic-judge, or authority architecture.
- Fast → Deep runtime reuse, crash-resumable Research, or execution-persistence redesign.
- Database/model migration, Knowledge lifecycle redesign, or revalidation-engine changes.
- A new classification/taxonomy system, ingestion/sync redesign, or ASR capability expansion.
- Broad visual redesign unrelated to the confirmed comprehension and continuity gaps above.

## 8. Recommended smallest coherent Goal 3 scope

### MUST

- Productize the existing V5-C value: show Focus, Progress, Staleness, Collection Delta, Radar/Assistance, route advice and Journey only in plain user terms, with a clear benefit and next action; keep hashes, authority, record schemas, IDs, permissions and lifecycle controls out of the ordinary main view.
- Make existing published Knowledge/Topic Pages and later reuse/refresh discoverable without remembering an originating Research task.
- Give Research a primary user path—question/status/result/evidence/next action—and move policy, maintenance, Workspace authoring and durable diagnostics behind explicit advanced disclosure.
- Add bounded contextual handoffs for the existing journey: Library → Search/Ask, Search/Ask → Research when needed, and Knowledge → later query/reuse. Do not add a new execution system.

### SHOULD

- Clarify Mark versus Notes with product copy and consistent naming, without changing their valid independent data semantics.
- Translate raw Home status values and de-emphasize the Taxonomy experiment in ordinary navigation.
- Reframe Search’s corpus-aware and sufficiency options/results in user language while keeping pipeline/trace details advanced.
- Provide useful cold-start guidance and avoid rendering large empty V5-C lanes until they have user value.

### DO NOT INCLUDE

- Provider, Research-quality, background/proactive, automatic-aspect, Memory/Router/Eval, data-model, or architecture work listed in Section 7.
- Reimplementation or renewed acceptance of G1/G2 behavior.
- A broad redesign beyond the confirmed language, hierarchy, discoverability, cold-start, and cross-flow gaps.

