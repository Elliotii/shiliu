# Shiliu V3.5 Current State

## H0-R Corrected Handoff State — 2026-07-25

```yaml
session_state:
  v3_5_a_session_closeout_approved: true
  v3_5_a_state: preparing_final_handoff_package
  v3_5_version_complete: false
  next_version_owner: v3_5_b

product_search:
  default_mode: auto
  wiring_version: v3-product-search-default-auto-v1
  router_modified: false
  retrieval_retuned: false

stress_set_v2:
  total: 31
  role: evidence_sufficiency_stress_set_v2
  labels: {sufficient: 11, partial: 9, insufficient: 7, unverifiable: 4}

corrected_stress_track_a:
  target_video_recall: 20/20
  complete_gold_group_candidate_coverage: 11/20
  bundle_hit: 1/20
  conditional_bundle_hit: 1/11
  failure_attribution: {retrieval_failure: 0, candidate_builder_failure: 9, deterministic_selector_failure: 10, end_to_end_bundle_hit: 1}

product_query_set:
  final_set_frozen: false
  historical_search_log_required: false
  scenario_grounded: true
  library_grounded: true
  independent_authoring: true
  user_validation_required: true
  target: 24
  minimum: 20
  maximum: 24

f1a: {status: paused, resume_gate: product_initial_baseline_complete}
f1b: {status: paused, resume_gate: product_initial_baseline_and_f1a_decision_complete}
mechanical_gate_v1: {status: historical_baseline, requires_stage4a_r: true}
stage4b: {status: not_started}

frozen_evaluation_set:
  formally_run: false
  terminology:
    active: frozen_evaluation_set
    historical_aliases: [held_out, blind_held_out, independent_held_out]

stage3r_pqs_b0:
  task_contract_status: accepted
  execution_candidate_exists: true
  acceptance_status: unreviewed_execution_candidate
  review_owner: v3_5_b
  v3_5_a_reviews_after_handoff: false
```

This corrected handoff section supersedes only the stale state descriptions above the historical sections below. The existing Stage 3R-PQS-B0 artifact is an unreviewed execution candidate, not an accepted result; no B0 execution, F1A/F1B, Stage 4B, or Frozen Evaluation is started by this update.

## Stage 3R-S1 Authoritative Update — 2026-07-24

- Stage 3R-S1 is complete as **Segment Identity Scoring Repair Accepted; One Bounded Generic Runtime Fix Recommended**. It repaired only the scoring identity bridge and rescored the already-frozen Stage 3R predictions; no Runtime fix was applied.
- Canonical scoring identity is `Artifact ID + Source Version + Timeline + zero-based Original Raw Segment Ordinal`, with exact time bounds and transcript-text SHA-256 checks. Fuzzy, nearest-neighbor, case/video-only, and cross-version mappings are forbidden.
- Full mapping audit: 457/457 case-scoped Gold segment references resolved exactly; missing 0; ambiguous 0; duplicate identity 0; cross-source/version/timeline mismatch 0. The frozen Runtime universe contains 2,667 physical segments and 4,503 CandidateSet membership occurrences; 274 Gold references are present in the frozen candidate sets.
- Frozen Prediction identity is preserved. Track A prediction SHA-256 is `6696f3a83449bdbb5df21f7b841bace705633b718a367dc549990238e9b3b4d4`; Track B prediction SHA-256 is `2f188746ccd432e4fc634592e36cd2f0e04e4c27a2bfb8ce9210483d9b9f83fe`; all per-case prediction files are unchanged.
- Corrected Track A: target-video recall 0/20; transcript-chunk recall 0/20; complete-group candidate coverage 0/20; Bundle hit 0/20. Corrected Track B: complete-group candidate coverage 11/20 = 0.55; mean span recall @1/@3/@5 = 0.0542/0.0667/0.1125; Bundle hit 2/20 = 0.10 and 2/11 = 0.1818 conditional on complete-group coverage.
- Corrected failure attribution supports exactly one separately authorized bounded generic Stage 3R-F1 repair: deterministic-selector multi-span coverage objective, affecting 9 cases across 5 query families. Stage 3R-F1 must rerun all frozen 31 Development cases and must not introduce case-specific logic.
- Retrieval calls 0; Candidate Builder calls 0; Selector calls 0; prediction-runner calls 0; network/external-model calls 0; Held-out access false. Directed S1 plus related regression: 131 passed.
- Next action is Main-session review and, if separately authorized, Stage 3R-F1. Stage 4A-R is not authorized before that fix is completed and reviewed.

## Stage 2R-A Authoritative Update — 2026-07-22

- Stage 4A is accepted and retained. Stage 4B is paused. Eval v1 is a frozen historical baseline. The former 24-hour hard stop is cancelled; future corpus expansion is governed by coverage, saturation, and marginal value.
- Stage 2R-A is complete as **Ready for Pilot Review**. It freezes Master Corpus v2, four-state annotation, blind reviewer prompts/isolation, deterministic agreement, human adjudication, leakage-aware splitting, pilot selection, and V3/V3.5 projections.
- Versions: Master Case `v3.5-master-case-v2`; Packet `v3.5-annotation-packet-v2`; Review `v3.5-annotation-review-v2`; Agreement `v3.5-annotation-agreement-v2`; Protocol `v3.5-annotation-protocol-v2`; Leakage `v3.5-leakage-policy-v2`; Pilot `v3.5-pilot-selection-policy-v2`.
- The five formal Gold layers are identity, corpus truth, retrieval, evidence, and sufficiency. Answer Gold and Agentic Search Gold are forbidden. No v1 asset was overwritten or migrated.
- Stage 2R-A used synthetic fixtures and mock/request-construction paths only: formal annotation cases 0; formal Gold records 0; real Codex reviewer calls 0; real DeepSeek API calls 0.
- Held-out accessed: false; forbidden access attempts: 0. Directed plus isolation-safe core regression: 30 passed, one dependency deprecation warning. An additional wider subset attempt hit a pre-existing collection/import issue in `test_duration_policy_patch.py`; no tests from that failed collection ran.
- Next authorized activity is Stage 2R-B pilot review (8–12 new cases, recommended 10). Stage 2R-A did not choose cases or begin the pilot.

## Stage 4A Authoritative Update — 2026-07-22

- Stage 3A is closed. Stage 3B is closed as a negative Structured-selector result. The preferred V3.5 Fine Selector is deterministic; no Structured LLM selector was used in Stage 4A.
- Stage 4A is complete as **Accepted with Mechanical-gate Baseline Risk Candidate**. Stage 4B, Stage 5, Stage 6, and V4 were not started.
- Contracts: Sufficiency Request `v3.5-sufficiency-request-v1`; Mechanical Gate `v3.5-mechanical-sufficiency-gate-v1`; Sufficiency Decision `v3.5-sufficiency-decision-v1`; policy `v3.5-mechanical-gate-policy-v1`.
- Frozen runtime: final Stage 3B generic Candidate Builder `stage3b-acronym-w3.5-v1` plus Stage 3A deterministic selector `v3.5-deterministic-fine-selector-v1`.
- Track A: 8 Development cases; 4 `judge_eligible`, 4 `terminal_unverifiable`; actions: retrieval 4, all other terminal action families 0; unknown operational states 0; invalid decisions 0.
- Track B (oracle-video conditional, not end-to-end): 4 evidence cases; 3 `judge_eligible`, 1 `terminal_unverifiable`; candidate-generation/evidence-resolution actions 1; unknown operational states 0; invalid decisions 0.
- Judge-input adequacy: Track A 3 adequate / 1 inadequate among 4 eligible; Track B 1 adequate / 2 inadequate among 3 eligible. Combined diagnostic: 4/7 adequate. Gold opened only after all Gate predictions and their freeze hash were fixed.
- S0 always-sufficient: accuracy 4/8 = 0.500; false-sufficient 4/4 = 1.000 on insufficient + unverifiable; 4 correct / 4 incorrect.
- S1 mechanical-gate-only: accuracy 3/8 = 0.375; false-sufficient 2/4 = 0.500 on insufficient + unverifiable; 3 correct / 5 incorrect. CASE_012/013 are readable-insufficient false-sufficient cases, confirming Stage 4B remains necessary.
- Partial Development calibration: unavailable; Development has zero Human-approved partial support. No credible four-class Macro-F1 claim is made.
- Held-out accessed: false. Formal Held-out Eval: not started. Provider/LLM calls: 0. Semantic Judge: not implemented or invoked.
- Stage 4A effective-hours estimate: approximately 1.5–2.0. V3.5 cumulative estimate: approximately 13.0–17.0 effective hours; approximately 7.0–11.0 remain against the 24-hour hard stop.
- Active risks: a mechanical gate cannot distinguish readable semantic insufficiency; two Track A sufficient cases terminate upstream; three eligible evidence paths are Judge-input-inadequate; Track B remains conditional and cannot support end-to-end claims.

## Stage 3A Authoritative Update — 2026-07-21

- Stage 2 is closed and frozen; the accepted reachability audit and Development Execution Manifest v1 remain authoritative.
- Stage 3A implementation is complete as **Accepted with Development Failures Candidate**. Stage 3B is not authorized.
- Product entrypoint: `resolve_from_search_candidates`; conditional within-video entrypoint: `build_within_video_candidates`.
- Evidence Candidate contract: `v3.5-evidence-candidate-v1`; EvidenceBundle contract: `v3.5-evidence-bundle-v1`; selector: `v3.5-deterministic-fine-selector-v1`.
- Track A, four evidence-bearing cases: target/video reachable 2/4; transcript chunk reachable 1/4; upstream retrieval failure 2/4; complete Gold groups in CandidateSet 2/4; deterministic Bundle hit 1/2 selector-eligible. CASE_003 and CASE_005 remain true upstream retrieval misses.
- Track B, oracle-video conditional only: Candidate Builder complete-group coverage 3 correct / 1 incorrect; complete groups 3/4; required spans 6/7; deterministic Bundle hit 1 correct / 3 incorrect; mean Gold-segment Recall@1/@3/@5 = 0.0500 / 0.3200 / 0.4903; median start-time error 14.06s.
- Track B is marked `oracle_video_conditional`, `oracle_video_used=true`, and `end_to_end_claim_eligible=false`; no Gold evidence field is a runtime builder/selector input.
- Development failures: CASE_003 Candidate Builder miss (ASR renders MCP as NCP); CASE_002 and CASE_005 Selector failures; CASE_001 succeeds. These remain visible and are not attributed to V3 retrieval in Track B.
- No-Gold Development cases are excluded from span/selector metrics and used only for typed empty/bounded behavior.
- Held-out accessed: false. Formal Held-out Eval: not started. Sufficiency Judge: not started. Structured LLM Selector: not started.
- Focused tests: 54 passed. Prescribed isolation-safe regression: 578 passed, with seven dependency deprecation warnings.
- Stage 3A effective-hours estimate: 2.5–3.5. V3.5 cumulative estimate: 9.75–14.25. Remaining against the 24-hour hard stop: approximately 9.75–14.25 effective hours.
- Active risks: deterministic lexical selection is weak on repeated entity mentions and complementary long spans; CASE_003 needs a Gold-blind Candidate Builder improvement before any formal evaluation; Track B must never be quoted as end-to-end performance.

## Version Identity

- Version: Shiliu V3.5 — Evidence Resolution and Sufficiency.
- Mission: turn frozen V3 retrieval candidates into version-safe evidence and a later sufficiency decision.
- V3 status: Accepted with Bounded Limitations.
- V3 Retrieval Baseline: Frozen; further V3 retrieval tuning rejected.
- Seed Snapshot: `20260720T094346Z_c7663365`.

## Authority and Governance

- Authority: V3.5 Version Owner and Technical Supervisor; this file records repository state and does not redefine version scope.
- Evidence Gold must be labeled against `Query + Full Target-video Raw Transcript`; Candidate Builder output must not restrict Gold annotation.
- Locked V3.5 Gold supports `gold_evidence_groups` with Group OR / required-span AND semantics.
- Evaluation should use one V3.5 Master Evaluation Case Set. Development / Held-out may be frozen only in Stage 2, before Candidate, Prompt, or Policy tuning.
- Readiness Targets are reference signals, not mechanical pass lines.
- Sufficiency `status` is for product expression; `reason_codes` are for failure attribution and future V4 action.
- V3.5 target: 16–22 effective hours; ordinary operating expectation: 20–24; hard stop: 24.

## Local Repository State

- Repository: `/Users/elliot/new-systems/agent-job-prep/Shiliu`.
- Branch: `codex/v3-domain-completion`.
- Stage 1A intake HEAD: `8287c8d92378b87290274d02605cdc704cb8c470`.
- Dirty worktree was pre-existing and is preserved. Stage 2C before-state evidence is in `/tmp/shiliu_v3_5_stage2c_before/`.
- Stage 1A and 1B intake HEAD remained `8287c8d92378b87290274d02605cdc704cb8c470`; the pre-existing dirty worktree is preserved. Stage 1B before-state evidence is in `/tmp/shiliu_v3_5_stage1b_before/`.

## Confirmed V3 Frozen Baseline

- No change is authorized to FTS5/BM25, embeddings, dense pooling or normalization, RRF, planner/router, query rules, chunking, grouping, window policy, ranking, filters, retrieval unit schema, index lifecycle, Gold, or formal Eval.
- V3 runtime schema continues to have no persisted source version or raw segment identity. Stage 1 derives these read-only at the evidence boundary and performs no backfill.

## V3 Eval Asset Fingerprints

These are intake fingerprints. Only the amended ledger hash has a historical authority match; the others are newly fingerprinted at V3.5 intake and do not prove absence of change before intake.

| Asset | SHA-256 | Historical status |
|---|---|---|
| `eval_queries.locked.jsonl` | `21382e8ba058cc6e51ea41c776ad216824363090888ee3a5569e36dc971c36ba` | Newly fingerprinted at V3.5 intake |
| `eval_gold.locked.jsonl` | `873b5fbf78ba2e8fc90dfb2fca96776e0e703a1c4fedd56dd20a49e43995b300` | Newly fingerprinted at V3.5 intake |
| `eval_gold_review.decisions.amended.jsonl` | `e93fd09bd06151d8665f50a17cc24bc2673105d21886e77b8a4cfa12f7ba0257` | Historical Hash Verified |
| `gold_lock_audit.json` | `46d81526341a9e7c1e311aed3a03a964563e9e91f87c17be0fc796b7f0975db0` | Newly fingerprinted at V3.5 intake |
| `human_ledger_amendment_audit.json` | `d3a488a57fcc7a8e41c6c06ce46cde61498336cb3a201dc505b038011baa4ee1` | Newly fingerprinted at V3.5 intake |
| `eval_results.json` | `9bf49fe37565bbd8694e4bcd61a2c1126950b3387604797b8936407cd1c3bfbc` | Newly fingerprinted at V3.5 intake |
| `eval_results.csv` | `3412f7e5e3be2732b68042d8066612f828b9599b3c324d14b24f3554c34ebaa9` | Newly fingerprinted at V3.5 intake |
| `eval_per_query_results.jsonl` | `2b540e4c2ab7c7580ee4b4df212fe8aeb854845d6d4c55e743ef2e82b637d647` | Newly fingerprinted at V3.5 intake |
| `failure_cases.md` | `3f08db8086089a6545cd244775ced1894ec071c5b14995c1197f2cf6dad82d3e` | Newly fingerprinted at V3.5 intake |
| `V3_EVAL_PROTOCOL.md` | `225d39836fcee67adfe9fc567bdc2b759dd3daf94f9940ecb7b4100063d00bbe` | Newly fingerprinted at V3.5 intake |
| `V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md` | `80e4abfd1d6b87f50a1c3e905a99af6fcc89d0ed2ce55d85c934f25809be9a75` | Newly fingerprinted at V3.5 intake |
| `SHILIU_V3_VERSION_DECISION.md` | missing | File Missing |

## Confirmed Search Contract

The frozen path remains `SearchRequest → SearchPlanner → SearchOrchestrator → RawSearchResponse → SearchResultConsolidator → EvidenceEnricher → ProductSearchResponse`. Stage 1B adds a single-execution read projection: `ProductSearchService.search_with_raw()` returns the one Raw execution and its unchanged Product projection; `EvidenceSearchService.search_library()` projects both views without reranking, rescoring, recall, grouping, or window changes.

`SearchCandidateSet` is frozen after Stage 1B as `v3.5-search-candidate-v1`. It retains raw-unit order, product-video order, scores, trace and index identity, fallback, metadata-only Video units, all Transcript mapping outcomes, and ineligible candidates at original rank. `EvidenceCandidateSet` is not implemented.

## Confirmed Subtitle and Segment Facts

- Authoritative source is `subtitle-raw.json`, schema `{from, to, content}`.
- Raw array order and unmodified text are authoritative. Empty segments retain ordinals and identities but are not evidence candidates.
- Retrieval chunks consist of complete non-empty raw segments; exact frozen-policy replay is available without fuzzy matching.

## Source Artifact Identity

Stage 1A provisional `v3.5-source-identity-v1` is superseded before Gold lock by `v3.5-source-identity-v2`; no migration is required because no V3.5 Gold, bundle, or persistent evidence identity exists.

v2 `source_artifact_id = "source_artifact_" + SHA-256(UTF-8 canonical JSON)` over `artifact_role=raw_subtitle`, integer `part`, `platform`, `source_id`, and normalized `source_lineage ∈ {human, ai, asr, unknown}`. JSON uses sorted keys, compact `,`/`:` separators, `ensure_ascii=false`, and rejects NaN. `source_language` remains descriptive metadata and is excluded; paths, Snapshot ID, CID, DB key, index state, and content bytes are also excluded.

`source_version` is the lower-case SHA-256 hex digest of the authoritative `subtitle-raw.json` bytes, with no parsing or normalization before hashing.

## Segment Identity

`segment_id = "segment_" + SHA-256(UTF-8 canonical JSON)` over `original_ordinal`, `source_artifact_id`, and `source_version`. It is independent of chunk IDs, database keys, and timeline policy.

`segment_digest` hashes canonical JSON over float-parsed `from`, float-parsed `to`, and the exact content string. Text is not stripped or Unicode-normalized. Python finite IEEE-754 values serialize through deterministic JSON; this binds parsed float semantics, while `source_version` remains the byte-level authority.

## Timeline Run Contract

- Version: `v3.5-timeline-policy-v1`; epsilon: `0.000001` seconds, fixed and not an Eval parameter.
- In original array order, `current.start_time < previous.start_time - epsilon` starts a new run.
- Same starts, normal overlaps, and prior-end/later-start overlap do not split runs. No global sort or rotation occurs.
- `timeline_run_id` hashes canonical JSON over `source_version` and zero-based `run_ordinal`.
- Evidence spans, future micro-windows, and future candidates must remain within one run. Multiple runs do not invalidate all run-local evidence.

## Chunk-to-Segment Mapping

- Version/method: `v3.5-exact-chunk-mapping-v1` / `exact_chunk_replay`.
- Frozen policy binding: `v3-frozen-transcript-chunk-policy-v1`; exact constants are target 800 characters, maximum 1200, maximum 120 seconds, and one trailing complete-segment overlap. Replay implementation: `v3.5-frozen-chunker-replay-v1`.
- Load authoritative bytes, enforce expected source version, replay the frozen V3 chunker, then exactly compare chunk ID, unit-ID suffix, start, end, source text, content hash, and replayed segment count.
- A failed exact comparison returns `chunk_segment_mapping_failed`, no segment IDs, and candidate ineligibility. There is no fuzzy recovery. Unsupported policy/replay versions fail closed as `chunk_policy_version_mismatch`.
- A reproduced chunk containing more than one run returns `invalid_cross_timeline_chunk` and candidate ineligibility; it is not split or rewritten. Stage 1A's mapping spellings `mapped` and `invalid_cross_timeline_run` are superseded by `exact_mapped` and `invalid_cross_timeline_chunk`.

## Source-version Authority

- Policy version: `v3.5-source-version-authority-v1`.
- Frozen Snapshot: expected version comes from the manifest record after logical BVID/video/path validation; actual raw bytes must match it.
- Pinned replay: caller-provided expected version must match current authoritative bytes; mismatch never refreshes the reference.
- Live product: current raw bytes plus compatible `retrieval_sync_state` and exact chunk replay bind `live_current_exact_replay`. This proves current compatibility only, not the index's historical source version.
- Candidate fields record artifact ID, identity version, expected/actual version, authority enum, and verification state. Missing, unreadable, stale, mismatched, or non-replayable candidates fail closed and remain accounted.

## Corpus-wide Mapping Audit

- Frozen Snapshot transcript chunks: 1,412; accounted: 1,412.
- Terminal statuses: 1,411 `exact_mapped`; 1 `invalid_cross_timeline_chunk`; zero missing, unreadable, version mismatch, policy mismatch, mapping failure, or other status.
- Source type: AI 1,333 exact; ASR 14 exact; human 64 exact plus 1 cross-run invalid.
- Language: English 20 exact; Chinese 1,391 exact plus 1 cross-run invalid.
- Timeline: single-run 1,385 exact; multiple-run 26 exact plus 1 cross-run invalid.
- The only issue is video 88 unit `chunk_cc3222c5f91a7fa074ec5802f8a21799`; it was derived generically, not hardcoded.

## Trace Policy

- Version: `v3.5-search-trace-policy-v1`.
- Default product behavior remains enabled for raw and presentation telemetry.
- Disabled mode skips trace schema initialization and both writes while retaining in-memory trace identity and equivalent substantive results.
- Formal Eval must copy the original Snapshot DB and write traces only to the work copy. Original Snapshot integrity remains protected.

## Error / Status Contract

- Source status: `valid_single_run`, `valid_multiple_runs`, `invalid_segment_time`, `source_unreadable`; multiple runs remain readable.
- Mapping status: `exact_mapped`, `invalid_cross_timeline_chunk`, `chunk_segment_mapping_failed`, `source_version_mismatch`, `source_unavailable`, `chunk_policy_version_mismatch`, `not_applicable`.
- Reasons include `source_contains_multiple_timeline_runs`, mismatch/failure codes, `raw_subtitle_missing`, `source_unreadable`, `no_search_candidate`, `candidate_not_found`, `index_not_ready`, and `retrieval_failed`. Sufficiency mapping remains Stage 4 work.

## video 88 Data Condition

- `BV1TxwQz5E4B`, human/zh, 1,748 segments; artifact SHA-256 `cc6afce905dc90ee1c89d1906c2617ba80c4992196c256e5fa8a66db9c0e2f0c`.
- Run 0: ordinals 0–1388, 567.400–2767.800s. Run 1: ordinals 1389–1747, 0.133–567.333s.
- Of 27 frozen chunks, exactly one is cross-run: `chunk_cc3222c5f91a7fa074ec5802f8a21799` (`2712.466–35.733s`). It is ineligible; the other 26 exact run-local mappings remain eligible.
- The artifact, frozen chunk, Snapshot, Gold, and retrieval behavior remain unchanged.

## Reusable Trace and Eval Assets

- Locked Eval: 24 queries, 452 judgments.
- Legacy V3 Evidence Gold Seed: 10 Approved Intervals mapping to 24 raw segments. They remain regression/provenance evidence only; complete V3.5 Gold and its Development/Held-out split are now separately locked under `research/v3_5/gold/`.
- `SearchCandidateSet`, `SearchCandidateVideo`, and `SearchRawUnitCandidate` are frozen read contracts. No Evidence Candidate Builder, API/UI integration, or ranking integration exists.

## Current Stage

Stage 2 is complete as an **Accepted for Stage 2 Closeout Candidate**. CASE_004 focused Human adjudication was hash-verified, mechanically validated, and merged as the only semantic override. The 18-Case Master Gold, 8-Case Development Gold, 10-Case Held-out Gold, reason registry, leakage-safe split, Eval Protocol, isolation contract, manifest, and audit are locked. Candidate Builder has not started.

Pre-Stage 3A input projection is complete. The eight-Case Development execution manifest, lock, audit, and execution-input contract now provide Original Query, query/target identity, and deterministic frozen V3 SearchCandidateSets without requiring a future Stage 3A implementation session to read the full query registry, Master Gold, Held-out Gold, or Human Review assets. Manifest SHA-256 is `ef08e5c262d9fc885ab38d81c90f10ce4be6820c31d931c03f0ecdcfe71a534e`; audit errors are empty. Candidate Builder remains unimplemented. The projection session recorded an isolation warning: an initial broad discovery search accidentally exposed one CASE_015 line from two forbidden full semantic files, neither used for projection; therefore this session is not eligible for Stage 3A implementation and a fresh isolated session is mandatory. No Held-out Gold content was read. Stage 3B is not authorized; Sufficiency Judge and Formal Held-out Eval are not started.

Pre-Stage 3A reachability audit is complete. Stage 3A was blocked before this audit and is now
ready to resume as a Candidate Builder implementation candidate under the frozen boundaries;
no Candidate Builder work was performed here. Manifest v1 remains active and no v2 was needed.
Per-case projection classification is CASE_001 `none`, CASE_002 `video_level_candidate`, and
CASE_003/CASE_005 `true_v3_retrieval_miss`. The CASE_002 Video-level path is authorized and
validated against its hash-verified, valid single-run frozen Raw Transcript. Track A and Track B
are defined by the non-destructive Stage 3A addendum. CASE_003 and CASE_005 remain frozen
`upstream_retrieval_failure` cases in Track A. `HeldoutAccessGuard` now rejects legacy V3 Eval
Gold/review path spellings as well as the V3.5 protected paths, with path-only tests. V3 Retrieval
remains frozen. Stage 3B remains unauthorized.

## Delivered

- Stage 1A source, segment, timeline, validation, exact mapping, safety, and interval contracts.
- Stage 1B identity v2, source authority, policy/replay binding, 1,412-chunk audit, frozen SearchCandidateSet projection, trace isolation, and normalized status/reason contracts.
- Real Snapshot regression for AI, human, ASR, video 88, all 10 Approved Intervals, raw/product order, mapping failures, empty search, and enabled/disabled traces.
- Stage 2A draft protocol, 20 primary candidates, the original 6 reserves/26 packets/template, packet validator, and leakage precheck.
- Follow-up six-case active calibration manifest, six blank calibration decisions, compact human guide, and two additional inactive real `U_title` + `no_supported_subtitle` reserve candidates (videos 142/143).
- Stage 2B exact-hash intake manifest, canonical ten-case validated human calibration ledger, machine-readable validation audit, and eight-case Round 2 manifest/template/guide.
- Round 2 exact-hash eight-case validated ledger/audit, 18-case Provisional Master Ledger/manifest, Reason Code registry audit, and blank CASE_004 focused second-review materials.
- Stage 2C adjudicated 18-Case ledger, locked Master/Development/Held-out Gold, membership and split locks, canonical reason registry, Gold granularity audit, frozen Eval Protocol, Held-out isolation contract, Gold Lock manifest/audit, tests, and closeout report.
- Pre-Stage 3A Development-only execution manifest (8 Cases), stable SearchCandidateSet identities, manifest lock, projection audit, execution-input contract, two-run determinism verification, and isolated handoff report.

## Active Issues

- Runtime retrieval rows do not persist historical `source_version`, segment IDs, or segment count. Live authority therefore proves current Artifact/replay compatibility, not historical index binding.
- video 88 retains one frozen cross-run V3 chunk by design; downstream Candidate Builder must honor mapping ineligibility.
- `SHILIU_V3_VERSION_DECISION.md` is absent locally; no actual hash conflict was found.
- English-source coverage is one readable semantic-neighbor candidate (Q23–video 37). English-source positive evidence is not established, and cross-language evidence resolution is not evaluated.
- Candidate Builder, micro-windows, Selector, runtime Sufficiency, and Formal Eval remain intentionally unimplemented.
- Hard Leakage Groups are frozen as LG_MCP (CASE_001/003/012), LG_MEMORYOS (CASE_002/013), LG_RAG_OPTIMIZATION (CASE_007/014), and LG_PI_AGENT (CASE_011/016). CASE_012 is Development-only.
- CASE_004 remains the sole Human-approved `partial`, is Held-out, and has `needs_second_review=false`. Its ASR `ra`, exact two-Segment span, label, Aspects, and medium confidence were not repaired or changed by Codex.
- Development has no real Human-approved partial Case. English positive evidence is not established; cross-language evidence resolution is not evaluated; the Master Set is not statistically representative.

## Eval Status

- V3 formal Eval was not rerun or modified.
- Human Intake batches: 2. Human decisions received/validated: 10/10. Distribution: sufficient 6, partial 0, insufficient 3, unverifiable 1; `needs_second_review`: 0.
- Canonical calibration ledger: `research/v3_5/human_reviews/review_decisions.calibration.10_cases.validated.jsonl`, SHA-256 `06ce0e3980e09618a901f572e96ab9d0970660219f33cab79630860532f01737`.
- Round 2 decisions received/mechanically validated: 8/8. Distribution: sufficient 3, partial 1, insufficient 3, unverifiable 1. CASE_004 focused adjudication completed and validated.
- Round 2 validated ledger: `research/v3_5/human_reviews/review_decisions.round2.8_cases.validated.jsonl`, SHA-256 `9c2a8ac2feb9d18fb7bac0f68b196192b8a22fac4948b0a4351b263b74fb16bb`.
- Locked Master Gold: 18 Cases; sufficient 9, partial 1, insufficient 6, unverifiable 2; SHA-256 `340e90bdd078e9b9a7aeac2bd98245b22d0e0b1f6d04812c675805996ad1fc09`.
- Locked Development Gold: 8 Cases; sufficient 4, partial 0, insufficient 3, unverifiable 1; SHA-256 `5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0`.
- Locked Held-out Gold: 10 Cases; sufficient 5, partial 1, insufficient 3, unverifiable 1; SHA-256 `6b7d06a6a0f3eeb61a9bc542ee8c2a8d12fc6d52fbb6576f64eff72d0d662789`.
- V3.5 Eval Protocol: frozen. Reserves: 8, all inactive. CASE_019/020 remain excluded. `needs_second_review`: 0.
- Gold Lock manifest SHA-256: `268d9b68e29cc7f242375ba108d9d99ef536e2f413c3747d9f95f7ab97588075`; Gold Lock audit SHA-256: `da65889ae2bbcea2f0a34e40a42c8ee598d185ab3183f07970d0f16e6426e77d`.
- Stage 1 regression: corpus 1,412/1,412 accounted; video 88 expectations pass; 10/10 Approved Intervals remain exact and run-local.
- Development cases used: none. Held-out use for tuning: none.

## Prompt / Policy Versions

- `prompt_name`: none
- `prompt_version`: none
- `model`: none
- `temperature`: none
- `development_cases_used`: none
- `source_identity_version`: `v3.5-source-identity-v2` (`v1` provisional, superseded)
- `source_version_authority_version`: `v3.5-source-version-authority-v1`
- `timeline_policy_version`: `v3.5-timeline-policy-v1`
- `chunk_mapping_version`: `v3.5-exact-chunk-mapping-v1`
- `source_chunk_policy_version`: `v3-frozen-transcript-chunk-policy-v1`
- `replay_implementation_version`: `v3.5-frozen-chunker-replay-v1`
- `search_candidate_contract_version`: `v3.5-search-candidate-v1`
- `trace_policy_version`: `v3.5-search-trace-policy-v1`
- `master_case_schema_version`: `v3.5-master-case-draft-v1`
- `review_decision_schema_version`: `v3.5-review-decision-draft-v1`
- `review_packet_version`: `v3.5-review-packet-v1`
- `eval_protocol_draft_version`: `v3.5-eval-protocol-draft-v1`
- `reason_code_draft_version`: `v3.5-reason-code-draft-v1`
- `calibration_batch_version`: `v3.5-label-calibration-batch-v1`
- `human_intake_validator_version`: `v3.5-human-intake-validator-v1`
- `round2_batch_version`: `v3.5-round2-active-review-v1`
- `round2_intake_validator_version`: `v3.5-round2-intake-validator-v1`
- `adjudication_layer_version`: `v3.5-case-adjudication-v1`
- `gold_lock_version`: `v3.5-gold-lock-v1`
- `eval_protocol_version`: `v3.5-eval-protocol-v1`
- `reason_code_registry_version`: `v3.5-reason-code-registry-v1`
- `development_heldout_split_version`: `v3.5-development-heldout-split-v1`
- `heldout_isolation_version`: `v3.5-heldout-isolation-v1`

## Internal Decisions

- Exclude language from v2 identity; bind lineage as stable source provenance and source version to exact raw bytes.
- Preserve raw order; derive, never repair, timeline structure.
- Reuse the frozen chunker and require exact equality. Failed or cross-run mappings fail closed.
- Freeze SearchCandidateSet as a lossless read projection; preserve ineligible items and original rank.
- Disable trace writes only through explicit constructor policy; retain enabled default.
- Keep Reserve candidates inactive by default and require an explicit activation reason, affected case, timestamp, and authorizer.
- Treat query-corpus negatives as curated bounded controls, not exhaustive absence proofs.
- Preserve Human semantic content byte-value-equivalently in the canonical ledger; only record order, key order, compact serialization, and newline normalization are deterministic.
- Freeze exact same-split Leakage Groups LG_MCP, LG_MEMORYOS, LG_RAG_OPTIMIZATION, and LG_PI_AGENT; keep CASE_012 Development-only.
- Interpret historical `limited_aspect_coverage` as an alias of canonical `partial_aspect_coverage` without modifying immutable Human Intake.

## Deviations

- Stage 1A provisional identity v1 and mapping spellings were explicitly superseded before Gold lock; no persistent-ID migration was needed.
- Minimal allowed retrieval changes add opt-in trace disabling and a raw+product return path. Defaults and existing `search()` behavior remain unchanged.

## Escalations

The Stage 3A input-contract conflict is resolved by the locked Development-only execution manifest. A fresh isolated Stage 3A session is still required and must use the execution-input whitelist. The current projection session is disqualified from Stage 3A implementation because its initial broad discovery command exposed one CASE_015 line from two forbidden full semantic assets; neither source contributed to the manifest, and no Held-out Gold content was read. No Stage 2C blocking escalation remains. English positive/cross-language coverage, Development's lack of a real partial Case, and historical-hash limits remain documented limitations. Final Stage 2 acceptance remains with the V3.5 Version Session.

## Estimated Hours Used

- Phase 0 and supplementary audit: approximately 1.0–1.5 effective hours (range; exact minutes were not recorded).
- Stage 1A: approximately 1.5–2.0 effective hours.
- Stage 1B: approximately 1.0–1.5 effective hours.
- Stage 2A: approximately 0.75–1.25 effective hours.
- Stage 2A Follow-up: approximately 0.5–0.75 effective hours.
- Stage 2B: approximately 0.75–1.25 effective hours.
- Stage 2B Round 2 intake/adjudication preparation: approximately 0.5–0.75 effective hours.
- Stage 2C: approximately 1.0–1.5 effective hours.
- V3.5 cumulative: approximately 7.0–10.5 effective hours.

## Remaining Time Budget

- Against 16–22 target: approximately 5.5–15 effective hours remain.
- Against ordinary 20–24 expectation: approximately 9.5–17 effective hours remain.
- Against 24-hour hard stop: approximately 13.5–17 effective hours remain.

## Current Stage Budget

- Stage 2C target: 1.0–1.5 effective hours.
- Stage 2C maximum: 2.0 effective hours.
- Status: within target estimate; Stage 2 stops after Gold Lock, protocol freeze, regression, and reporting. Stage 3 has not started.
- Stage 3A Restart preflight/guard: approximately 0.25 effective hours; stopped within budget on the frozen input-contract conflict. V3.5 cumulative estimate remains approximately 7.25–10.75 effective hours, leaving approximately 13.25–16.75 hours against the 24-hour hard stop.

## Stage 3B Final Update — 2026-07-21

- Stage 3A: closed (`Accepted with Documented Development Failures`).
- Stage 3B: complete as a `Provider / Schema Reliability Blocker` review result; no further selector calls are authorized in this stage.
- Candidate robustness policy: `v3.5-stage3b-asr-acronym-anchor-v1`.
- Track B Candidate Builder: 3/4 complete-group cases and 6/7 required spans. The bounded generic acronym attempt did not recover CASE_003; CASE_001/002/005 did not regress and budgets remained capped at 32 Candidates / 6,000 Candidate characters.
- Structured selector contract: `v3.5-structured-fine-selector-v1`.
- Prompt: `v3.5-structured-fine-selector-prompt-v1`.
- Model/provider: `deepseek-v4-pro`, existing OpenAI-compatible abstraction, high thinking.
- Final-config reliability: 3/5 valid outputs after repair, 2/5 repair exhausted, 5/5 initial outputs invalid, 3/5 repairs successful, 0 abstentions. Invalid-after-repair rate: 40%, exceeding the 25% stop threshold.
- Track A eligible comparison: deterministic 1/2; structured LLM 0/2; delta -1. CASE_001 regressed.
- Track B eligible comparison: deterministic 1/3; structured LLM 0/3; delta -1. CASE_002 and CASE_005 gained no hit; CASE_003 remained selector-ineligible.
- Provider budget: exactly 10 logical calls and 16 raw attempts across two allowed configurations. Final-config median logical latency was 153.26 seconds. Reported usage for three valid final responses totaled 30,639 tokens, including 12,296 reasoning tokens; failed-call usage was unavailable. Cost is unavailable because no reliable repository price table exists.
- Preferred selector: `deterministic` (V3.5 Development preference only).
- Held-out accessed: false. Forbidden open attempts: 0.
- Sufficiency Judge: not started. Formal Held-out Eval: not started. Stage 4 is recommendation-only.
- Stage 3B effective time: approximately 1.2 hours. V3.5 cumulative estimate: approximately 11.5–15.0 hours; approximately 9.0–12.5 hours remain against the 24-hour hard stop.
- Active risks: generic acronym ranking alone did not guarantee complete neighboring-window coverage; structured output required repair on every successful call; 40% remained invalid; valid bundles inflated duration and missed Gold; high-thinking latency and usage are operationally poor.
