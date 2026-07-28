# Shiliu V3.5 Stage 3A Retrieval Reachability Audit Report

## 1. Result

**Accepted with True V3 Retrieval Misses Candidate.** Manifest v1 is structurally faithful and
remains active. CASE_003 and CASE_005 are `true_v3_retrieval_miss`. CASE_002 is a valid
Video-level candidate with `within_video_path_authorized: true`. No v2 or Retrieval change was
required.

## 2. Scope Compliance

The audit used only CASE_001, CASE_002, CASE_003, and CASE_005. It did not open the prohibited
Held-out/Master Gold, adjudicated decision, Human Review, review packet, or legacy Eval Gold
assets. No network, Provider, LLM, or Embedding execution occurred.

## 3. Repository Before / After

Before-state is preserved at
`/tmp/shiliu_v3_5_stage3a_reachability_audit_before/repository_state.txt`. Branch and HEAD matched
the required `codex/v3-domain-completion` / `8287c8d92378b87290274d02605cdc704cb8c470`.
The repository already contained extensive tracked and untracked work; it was preserved. This
audit changed only the guard, Stage 3A boundary helper/tests, the requested audit assets,
addendum, this report, and `V3_5_CURRENT_STATE.md`.

## 4. Authorized Inputs

Development Gold hash matched
`5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0`; Manifest v1 matched
`ef08e5c262d9fc885ab38d81c90f10ce4be6820c31d931c03f0ecdcfe71a534e`.
The Snapshot hash matched `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.

## 5. Manifest Generation Provenance

`write_projection_assets()` calls `generate_manifest()` twice. Each generation copies the frozen
Snapshot to a temporary DB, builds `EvidenceSearchService` with both raw and presentation trace
persistence disabled, constructs `ProductSearchRequest(query=original_query)`, and calls
`EvidenceSearchService.search_library()`. The function serializes both ordered
`raw_unit_candidates` and ordered `video_candidates`; it does not serialize Product cards alone.

Configuration is lexical / scope all / no filters / Product top-k 10 / raw top-k 50 / maximum
two displayed windows per video. Router identity is
`unversioned:SearchPlanner@sha256:0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e`;
grouping is `v3-temporal-consolidation-v1`; presentation is `v3-product-presentation-v1`;
lexical index is `v3-stage1-lexical-v1`; Snapshot is `20260720T094346Z_c7663365`.

Projection-session-only sources were Development membership, master candidate query/target
metadata, and the exact-query registry join. The frozen Stage 3A runtime input is the resulting
Manifest, not those projection sources.

## 6. Frozen Request Reconstruction

All four `search_request` objects round-trip through `ProductSearchRequest` without changing a
field. Original Query, mode, scope, filters, result limit, and window limit match. Explicit
lexical mode makes fallback unavailable; Router execution remained lexical.

## 7. One-time Deterministic Replay

Exactly one request per case was executed, in order CASE_001, CASE_002, CASE_003, CASE_005, on
one temporary Snapshot copy. Both trace-persistence flags were false. The original Snapshot hash
was unchanged before/after. Execution counts and full ordered identities are in
`frozen_request_replay_manifest.json`.

For non-empty results, direct Python aggregate equality reports false because dataclass tuple
fields are compared to their JSON-array serialization. Counts, ordered unit identities, ordered
video identities, target facts, request, Snapshot, and Index identities match; the locked
projection audit independently proves two canonical generations are byte-identical. This is a
comparison-container artifact, not lost candidate data.

## 8. Per-case Comparison

The machine-readable exact format is in `retrieval_reachability_audit.json`; the compact table is
in `retrieval_reachability_per_case.csv`.

| Case | Actual raw (Video/Chunk) | Product videos | Target Video | Target Chunk | Manifest | Classification |
|---|---:|---:|---|---|---|---|
| CASE_001 | 50 (7/43) | 10 | yes | yes | same counts/order | none |
| CASE_002 | 2 (2/0) | 2 | yes | no | same counts/order | video_level_candidate |
| CASE_003 | 0 (0/0) | 0 | no | no | exact empty | true_v3_retrieval_miss |
| CASE_005 | 0 (0/0) | 0 | no | no | exact empty | true_v3_retrieval_miss |

## 9. CASE_002 Video-level Analysis

The target `video:bilibili:BV1oa6uBXE8J:p1` is raw rank 1, and grouped Product video 40 is rank
1. It comes from a Raw Video unit, not a Product-only projection. The frozen request returned no
Transcript Chunk units, so the Manifest did not omit one.

The frozen Raw Transcript exists and hashes to
`5b3f6473760e29bce827e3f8d1df65c89f94f0d5faa70c9497c9d3740a3e41ac`. It contains 1,035
segments in one valid timeline run
`timeline_run_1bc8e33b91d8842cff3eae7c5d8b96625265a3f1c7a5689df875afc2b1a248de`; the Snapshot has
23 Transcript Chunk units for video 40 and current lexical/dense sync state.

`within_video_path_authorized: true`. Its boundary is Original Query `MemoryOS` + recalled
`video_id=40` + that frozen Raw Transcript.

## 10. CASE_003 Classification

`true_v3_retrieval_miss`. Request, Snapshot, Index, and Manifest agree; replay and Manifest are
both empty; neither target Video nor target Transcript Chunk is present; there is no Projection
or Serialization loss. Track A attribution: `upstream_retrieval_failure`.

## 11. CASE_005 Classification

`true_v3_retrieval_miss`, under the same strict conditions. Track A attribution:
`upstream_retrieval_failure`.

## 12. Projection / Serialization Findings

Raw Video units, Transcript Chunk units, ineligible units, order, and empty results are preserved.
No null-to-non-null mutation, dropped chunk, Product-only projection, or request reconstruction
defect was found.

## 13. Manifest Version Decision

Keep v1. No authorized Projection-class defect exists, so Manifest v2 was not created.

## 14. HeldoutAccessGuard Fix

The guard now also rejects `eval_gold.locked` and `eval_gold_review`, in addition to all required
V3.5 patterns. Tests call `validate_path()` only and never open protected targets. Development
Gold, Manifest, frozen protocols, source code, Snapshot, and Raw paths remain allowed.

## 15. Track A Contract

Track A consumes only the frozen V3 SearchCandidateSet and records target Video, Video candidate,
Transcript Chunk, and future Candidate Builder coverage. It never consumes an Oracle video.

## 16. Track B Contract

Track B accepts only case ID, Original Query, Development Oracle target Video ID, frozen Raw
Transcript path, and its SHA-256. It is conditional fine-evidence Eval, not end-to-end Eval.

## 17. Failure Attribution

Absence before Candidate Builder is `upstream_retrieval_failure`; target reachable but no future
covering candidate is `candidate_generation_failure`; covering candidate present but not selected
is `selector_failure`.

## 18. Protocol Addendum

`research/v3_5/stage3a/V3_5_STAGE3A_REACHABILITY_AND_CONDITIONAL_EVAL_ADDENDUM.md` freezes both
tracks and the Oracle boundary without modifying the locked Eval Protocol.

## 19. Tests and Regression

The new directed suite covers request reconstruction, JSON projection, Video/Chunk/empty
preservation, single-replay enforcement, guard rejection/allowance, Track A attribution, and
Track B Gold-field rejection: **23 passed**.

The isolation-safe regression set passed: **568 passed**, with one Starlette/httpx deprecation
warning class and six multiprocessing fork deprecation warnings. The literal unfiltered full
regression command was deliberately not executed: five legacy Stage 2/Snapshot modules directly
open protected Held-out/Master/Human-review semantic assets, and the old Stage 3A projection test
executes two additional full frozen-search generations. Running either would violate this
session's held-out access and single-replay contracts. Exact exclusions were:

```text
tests/test_evidence_snapshot_regression.py
tests/test_v3_5_eval_stage2a.py
tests/test_v3_5_eval_stage2b_intake.py
tests/test_v3_5_eval_stage2b_round2.py
tests/test_v3_5_eval_stage2c.py
tests/test_v3_5_stage3a_input_projection.py
```

## 20. Snapshot / V3 / Gold Integrity

Snapshot, Artifact Manifest, Development Gold, Manifest v1, frozen V3 Retrieval, and Raw Artifact
bytes remain unchanged. No Ranking, Router, RRF, Chunk policy, Gold, or split was modified.

## 21. Current State Update

`V3_5_CURRENT_STATE.md` records the completed audit, v1 decision, two true misses, authorized
CASE_002 path, both tracks, guard status, frozen Retrieval, and unauthorized Stage 3B.

## 22. Recommendation for Stage 3A

Resume Stage 3A Candidate Builder work only in a subsequent authorized session, using Track A
for end-to-end claims and Track B for explicitly conditional within-video capability. Preserve
CASE_003/005 as upstream misses.

## 23. Exact Commands

Repository identity and hash commands were the required `pwd -P`, Git status/branch/HEAD/diff
inventory, and `shasum -a 256` checks. Replay used `.venv/bin/python -B` to reconstruct the four
locked `ProductSearchRequest` objects and call the frozen service once per case on a temporary DB
copy. Tests use:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_v3_5_stage3a_reachability.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider \
  --ignore=tests/test_evidence_snapshot_regression.py \
  --ignore=tests/test_v3_5_eval_stage2a.py \
  --ignore=tests/test_v3_5_eval_stage2b_intake.py \
  --ignore=tests/test_v3_5_eval_stage2b_round2.py \
  --ignore=tests/test_v3_5_eval_stage2c.py \
  --ignore=tests/test_v3_5_stage3a_input_projection.py
```

## 24. Stop Statement

Shiliu V3.5 Stage 3A Retrieval Reachability Audit is complete.

The frozen Development requests, actual frozen search results and serialized Execution Manifest
results were compared deterministically. No Projection defect requires correction. True V3
retrieval misses remain frozen and are separated from V3.5 conditional fine-evidence capability
through Track A and Track B. The Held-out access guard was corrected before any Stage 3A
implementation began. No Candidate Builder, Fine Selector, Sufficiency Judge, Formal Held-out
Eval, API/UI or V4 work was started.
