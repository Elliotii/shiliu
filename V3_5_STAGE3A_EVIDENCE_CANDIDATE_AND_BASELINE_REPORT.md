# Shiliu V3.5 Stage 3A — Evidence Candidate and Deterministic Baseline

## 1. Result

Result classification: **Accepted with Development Failures Candidate**.

Stage 3A implements both authorized service paths and a Development-only dual-track evaluation. It preserves CASE_003 and CASE_005 as Track A upstream retrieval failures. Track B covers complete Gold groups in 3/4 evidence-bearing cases; its deterministic bundle hits 1/4.

## 2. Scope Compliance

No V3 search, ranking, router, RRF, chunk policy, Snapshot, Raw Artifact, Gold, API/UI, embedding, network, LLM, Sufficiency Judge, Agent, Memory, Harness, Translation, Held-out Formal Eval, or V4 work was performed.

## 3. Repository Before / After

- Branch/HEAD remained `codex/v3-domain-completion` / `8287c8d92378b87290274d02605cdc704cb8c470`.
- Pre-existing changes: all opening tracked/untracked changes recorded in `/tmp/shiliu_v3_5_stage3a_final_before/`; none were reverted.
- Stage 3A intended changes: `src/shiliu/evidence/stage3a.py`, `src/shiliu/eval_v3_5/stage3a.py`, guard pattern, focused tests, Stage 3A assets, this report, and current-state update.
- Unexpected changes: none detected.

## 4. Input Identity

Development Gold `569383...d90d0`; Execution Manifest `ef08e5...a534e`; Snapshot `61589a...c4e1`; Artifact Manifest `36e63e...d08f`; protocol `01f1dd...90f`; isolation contract `faeccb...f18e`. Every required hash matched before and after.

## 5. Held-out Isolation

`HeldoutAccessGuard` rejects all required protected path families, including `reason_code_registry`. No forbidden content, Held-out label, aspect, group, span, or reason code was loaded. Formal Held-out execution is false.

## 6. Stage 1 Contract Reuse

The implementation reuses frozen source identity/version, timeline-run, exact mapped segment IDs, chunk replay policy identity, SearchCandidateSet identity, and trace contracts without modifying Stage 1.

## 7. Service Architecture

`resolve_from_search_candidates` is the product boundary. `build_within_video_candidates` is the bounded within-video boundary shared by legal Track A video candidates and Track B oracle videos. `select_deterministic_bundle` consumes only query plus predicted candidates.

## 8. Track A Contract

Only ordered frozen Manifest candidates are accepted. Chunk candidates are validated against exact Raw segment IDs; video-level candidates enter only their recalled video's Raw transcript; an empty legal video set returns `upstream_retrieval_failure`.

## 9. Track B Contract

The boundary accepts exactly case ID, Original Query, and Manifest target video. Extra or Gold semantic fields are rejected. Every output is `oracle_video_conditional`, `oracle_video_used=true`, `end_to_end_claim_eligible=false`.

## 10. EvidenceCandidate Contract

Version `v3.5-evidence-candidate-v1`; schema and invariants are materialized in `research/v3_5/stage3a/evidence_candidate_contract.json`.

## 11. EvidenceBundle Contract

Version `v3.5-evidence-bundle-v1`; all references are validated against the CandidateSet and one video. Candidates may be from different runs, but each normalized span remains run-local.

## 12. Stable Identity

Candidate and bundle identities use canonical sorted-key UTF-8 JSON and SHA-256; timestamps, trace IDs, database IDs, process order, and UUIDs are excluded. Two selected-config runs produced identical IDs and ordering.

## 13. Chunk-bounded Candidate Generation

CASE_001 follows frozen exact-mapped chunk segment regions only. Windows never escape the parent mapped region.

## 14. Video-level Within-video Generation

CASE_002 follows the authorized video-level path for video 40. The full Raw transcript is scored, but output is capped at 32 micro-windows, 6 segments/window, 6,000 characters, and 600 seconds interval union.

## 15. Oracle-video Conditional Generation

CASE_001/002/003/005 use only Manifest query/target identity plus version-verified frozen Raw. Gold is opened later by the Eval Runner only.

## 16. Micro-window Policy

Chunk-mapped, query-anchor, and boundary-preserving methods are implemented. Windows are complete Raw segments, maximum 6 segments/500 characters/60 seconds, and never cross a timeline run.

## 17. Dedup and Overlap

Exact span duplicates merge provenance. Segment Jaccard and interval overlap suppress near duplicates; retained overlaps record related candidate IDs and relations. Stable ordering breaks ties.

## 18. Normalization and Typed Errors

Typed checks cover missing segment/source, source artifact/version mismatch, run mismatch, ordering, contiguity, budget, missing subtitle, invalid bundle reference, manifest/set mismatch, and upstream retrieval failure. Titles, descriptions, summaries, and product text never substitute for Raw evidence.

## 19. Deterministic Candidate Scoring

Scoring uses exact/compacted technical phrase, query coverage, Chinese n-grams, English/entity tokens, parent rank, length, local anchor context, overlap, and diversity. No case ID, video ID, Gold, embedding, LLM, or external service feature is used.

## 20. Bundle Assembly

The selected configuration greedily assembles at most six same-video candidates using lexical score, marginal query coverage, locality, overlap, candidate-count, and union-duration penalties.

## 21. Coverage Semantics

Version `v3.5-candidate-union-coverage-v1`: groups OR; required spans AND; candidate segment sets UNION. Covering subset ties use fewest candidates, shortest interval union, fewest extra segments, then candidate ID.

## 22. Track A Metrics

| Metric | Result |
|---|---:|
| Evidence-bearing cases | 4 |
| Target video reachable | 2/4 |
| Video candidate reachable | 2/4 |
| Transcript chunk reachable | 1/4 |
| Upstream retrieval failure | 2/4 |
| Complete Gold groups in CandidateSet | 2/4 |
| Selector-eligible cases | 2 |
| Deterministic Bundle hit@1 | 1/2 eligible |
| Builder coverage given target reachable | 2/2 |

## 23. Track B Candidate Builder Metrics

Candidate Builder case/complete-group coverage is 3 correct, 1 incorrect (3/4). Required-span coverage is 6/7. CASE_003 is the single miss.

## 24. Track B Selector Metrics

Deterministic Bundle hit@1 is 1 correct, 3 incorrect (1/4 absolute). Conditional on a complete group in CandidateSet it is 1/3; CASE_002 and CASE_005 are Selector failures, not retrieval failures.

## 25. Recall / Time / Duration Metrics

Mean Gold-segment Recall@1/@3/@5 is `0.0500 / 0.3200 / 0.4903`; median covering-subset start-time error is `14.06s`. Per-case predicted/Gold interval-union duration ratios are in the Track B JSON/CSV. Duration is merged interval union, never min-to-max envelope.

## 26. Candidate Budget Metrics

Track B per-case candidate counts are CASE_001 32, CASE_002 32, CASE_003 32, CASE_005 14. Character/token/bundle count/union duration budgets are reported per case; every configured hard budget passed.

## 27. Per-case Results

| Case | Track A | Track B Builder | Track B Bundle |
|---|---|---|---|
| CASE_001 | hit | complete | hit |
| CASE_002 | selector failure | complete | selector failure |
| CASE_003 | upstream retrieval failure | candidate-generation miss | miss |
| CASE_005 | upstream retrieval failure | complete | selector failure |

No-Gold CASE_012/013/015/017 are excluded from fine-span metrics and exercise bounded/typed behavior only.

## 28. Failure Attribution

Track A CASE_003/005 are `upstream_retrieval_failure`. Track B CASE_003 is `candidate_generation_failure`; CASE_002/005 are `selector_failure`. No normalization failure affects an evidence-bearing metric case.

## 29. Tuning History

The default 24 and authorized 32 builder caps were compared; 32 was selected by complete-group coverage. Selector sizes 4/6/8 and bounded locality weights were compared; six was retained because larger bundles did not improve hits and inflated duration. No case/video exception was introduced.

## 30. Functional Examples

The required CASE_001 chunk, CASE_002 video, CASE_003/005 empty Track A, CASE_003 conditional Track B, stable identity, overlap, version mismatch, and missing-source examples are in `functional_examples.md` and trace samples.

## 31. Trace

Per-case Track A/B traces record manifest/set identity, path/oracle flag, source identity/version/runs, candidates, methods, window bounds, scores, bundle decisions, and typed failures.

## 32. Tests and Regression

- Focused Stage 3A plus Stage 1 contract tests: `54 passed`.
- Prescribed isolation-safe regression: `578 passed`.
- Warnings: one Starlette/httpx and six multiprocessing fork deprecations; no test failure.

## 33. Snapshot / V3 / Gold / Manifest Integrity

All four core hashes were rechecked after generation and remained exact. Git status shows no authorized change to Gold, Manifest inputs, Snapshot, Raw, or V3 retrieval.

## 34. Current State Update

`V3_5_CURRENT_STATE.md` now records Stage 2 frozen, accepted reachability/Manifest v1, actual Track A/B metrics, contract/selector versions, false Held-out access, time budget, risks, and Stage 3B not authorized.

## 35. Known Limitations

CASE_003 loses one required segment under the 32-candidate lexical budget because ASR repeatedly renders MCP as NCP. Repeated entity mentions make CASE_002 lexical bundle selection ambiguous. CASE_005 needs complementary long-span assembly. Development has only four evidence-bearing cases and is not formal Held-out evidence.

## 36. Stage 3B Recommendation

Do not start Stage 3B automatically. A structured LLM selector has clear potential on CASE_002/005, where complete evidence is present but lexical assembly fails. First resolve or explicitly accept the Gold-blind CASE_003 Candidate Builder miss; an LLM selector cannot select a segment absent from the CandidateSet.

## 37. Exact Commands

Used mandated repository/hash commands; focused pytest over Stage 3A/Stage 1 files; the exact prescribed isolation-safe pytest command with six ignores; and a Development runner invocation using Manifest, Development Gold, Artifact Manifest, and read-only Snapshot DB. No network/provider command ran.

## 38. Stop Statement

Shiliu V3.5 Stage 3A is complete.

Track A evaluated the frozen V3-to-V3.5 end-to-end path and preserved CASE_003 and CASE_005 as upstream retrieval failures.

Track B evaluated conditional fine-evidence resolution using only the Original Query, Development oracle target video and frozen Raw Transcript. No Gold Evidence fields were used as runtime inputs.

The Evidence Candidate Builder, deterministic Fine Selector and EvidenceBundle were implemented without modifying V3 Retrieval, Gold, Snapshot or Raw Artifacts.

Held-out labels, Aspects, Evidence Groups, spans and reason codes were not loaded or used.

No Structured LLM Selector, Sufficiency Judge, Formal Held-out Eval, API/UI, Agent, Memory, Harness, Translation Pipeline or V4 work was started.
