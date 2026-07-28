# Shiliu V3.5 Stage 2B — Calibration Intake and Round 2 Report

## 1. Result

**Accepted for Stage 2B Intake Candidate**

Both exact-hash Human Intake batches passed mechanical validation. A canonical ten-case validated human calibration ledger, validation audit, and exact eight-case Round 2 workload were created. Final acceptance belongs to the V3.5 Version Session.

## 2. Scope Compliance

Codex acted only as a mechanical validator and packet preparer. Human labels, Aspects, Evidence Groups, Span boundaries, notes, reasons, confidence, and flags were not edited. No Reserve was activated; no Gold lock, Development/Held-out split, retrieval/product change, Candidate Builder, Selector, Sufficiency Judge, LLM/provider call, formal Eval, API/UI, or V4 work occurred.

## 3. Repository Before / After

- Repository: `/Users/elliot/new-systems/agent-job-prep/Shiliu`.
- Branch before/after: `codex/v3-domain-completion`.
- HEAD before/after: `8287c8d92378b87290274d02605cdc704cb8c470`.
- Staged paths before/after: none.
- Before-state record: `/tmp/shiliu_v3_5_stage2b_intake_before/manifest.md`.
- Pre-existing V3, Stage 1, Stage 2A, and Follow-up changes were preserved.
- Stage 2B changes are limited to this report, Current State, `human_reviews/**`, Round 2 assets, leakage notes, minimal `eval_v3_5` validation/models, and Stage 2B tests.
- Existing Review Packets, empty templates, Human Intake bytes, frozen contracts, Snapshot, V3 Eval, retrieval, API, and UI were not modified.
- Unexpected changes: none detected.

The initial Batch 02 pathname typo was corrected by the user before validation resumed. Codex did not rename or modify it.

## 4. Human Intake Files and Hashes

| Intake | Records | Exact SHA-256 | Status |
|---|---:|---|---|
| `calibration_batch_01_cases_015_017_013_001_003_012.completed.jsonl` | 6 | `b6b004c45514182676f67ceda664bd8c45d34d8efeb49ef63f56a4fe44fc2566` | received exact / validated |
| `calibration_batch_02_cases_007_008_009_010.completed.jsonl` | 4 | `970a502d5041444489addb226a8a4e687408a998747dec6ea30897998dfbce09` | received exact / validated |

Both originals remain byte-for-byte unchanged. `calibration_intake_manifest.json` records filename, hash, record count, Case IDs, receipt/validation status, timestamp, and validator version `v3.5-human-intake-validator-v1`.

## 5. Record and Case Accounting

Received 6 + 4 = 10 records, 10 unique IDs, 0 duplicates, and 0 unknown IDs. Authorized/canonical order:

```text
CASE_015, CASE_017, CASE_013, CASE_001, CASE_003,
CASE_012, CASE_007, CASE_008, CASE_009, CASE_010
```

All records have `decision_status=completed` and `reviewer=human_user`. Shared export timestamps within each batch were accepted as batch completion timestamps.

## 6. Schema Validation

All 10 records passed `CompletedReviewDecision` with extra fields forbidden. Required fields, four-state values, Aspect objects, Group/Span objects, confidence, second-review boolean, flags, and notes were present and structurally valid. Aspect IDs are unique per Case; top-level and Group Aspect references resolve to declared Aspects.

## 7. Evidence Span Validation

Six Cases contain Gold Evidence Groups: CASE_001, CASE_003, CASE_007, CASE_008, CASE_009, and CASE_010. Every cited Segment ID exists in the matching frozen Raw Source and corresponding Review Packet. Segment order matches original ordinal order. Stored start is the first selected Segment start; stored end is the last selected Segment end. No non-contiguous-subset warning was required.

Group OR / required-span AND structure passed. CASE_008 contains two independently complete OR Groups. CASE_007, CASE_009, and CASE_010 use multiple complementary AND Spans within one Group.

## 8. Source-version and Timeline Validation

For every readable `query_video` Case, candidate Source Version, Packet manifest Source Version, frozen Artifact manifest hash, and actual Raw bytes agree. Every Span remains in exactly one declared Timeline Run. No cross-run Group or Span exists.

CASE_012 has two readable Timeline Runs, no Gold Group, and was validated run-locally; its multi-run nature was not treated as unverifiable. CASE_015 has no Raw authority and no Group. CASE_017 is `query_corpus`, has no target/Span, and is excluded from Fine Evidence Span metrics.

## 9. Four-state Invariant Validation

- Six `sufficient` decisions each have at least one complete Group, all required Aspects covered, and no missing Aspect.
- Zero `partial` decisions were received.
- Three `insufficient` decisions contain no useful-answer Gold Group: CASE_013 and CASE_012 have readable Raw authority; CASE_017 is the authorized curated query-corpus control.
- One `unverifiable` decision, CASE_015, has unavailable Raw authority and no fabricated Evidence.

All invariants passed without semantic relabeling.

## 10. Canonical Ten-case Ledger

Path: `research/v3_5/human_reviews/review_decisions.calibration.10_cases.validated.jsonl`  
SHA-256: `06ce0e3980e09618a901f572e96ab9d0970660219f33cab79630860532f01737`  
Records: 10

The ledger preserves exact Human semantic values. Deterministic transformations are limited to authorized record order, sorted JSON keys, compact serialization, and newline normalization. It is a **validated human calibration ledger**, not final V3.5 Gold, Development Gold, or Held-out Gold.

## 11. Calibration Distribution Analysis

Label distribution: sufficient 6, partial 0, insufficient 3, unverifiable 1. `needs_second_review`: 0.

Source distribution: AI 7, human subtitle 1, title-only 1, query-corpus 1; ASR 0. Source language: zh 8, unavailable/not applicable 2; English source 0. Six Cases have Gold Groups; three have multi-span Groups; one has alternative OR Groups.

## 12. Cases with Long or Composite Evidence

| Case / Group | Span count | Union duration (seconds) | Structure |
|---|---:|---:|---|
| CASE_001 / G1 | 1 | 11.720 | single Group |
| CASE_003 / G1 | 1 | 52.530 | single Group |
| CASE_007 / G1 | 2 | 103.301 | complementary AND Spans |
| CASE_008 / G1 | 1 | 18.621 | OR alternative 1 |
| CASE_008 / G2 | 1 | 11.800 | OR alternative 2 |
| CASE_009 / G1 | 6 | 243.550 | longest; complementary AND Spans |
| CASE_010 / G1 | 3 | 89.050 | complementary AND Spans |

Durations are same-run unions of approved Span intervals.

## 13. Transcript-error Flags

Human reviewer flags identify transcript/entity recognition issues in CASE_003, CASE_007, CASE_009, and CASE_010. These are retained exactly and do not invalidate source identity or Segment mapping. CASE_013's `readable_raw_transcript_reviewed` is a review-status flag, not an error. CASE_015's absence of Raw authority is a source-state fact, not a transcript error.

## 14. Needs-second-review Assessment

Actual `needs_second_review=true` Cases: none. Count: 0. Codex did not infer or add a second-review requirement.

## 15. Partial-class Status

**No human-approved partial Case exists yet.** This is a factual property of the ten accepted decisions, not a defect and not permission to rebalance labels. Round 2 prioritizes CASE_005 for the boundary, but it must not be forced to partial. If no genuine partial appears, Version Session must make the next bounded selection decision.

## 16. Round 2 Active Set

Exactly eight remaining Primary Cases were activated for review, in order:

1. CASE_002 — positive counterpart to CASE_013
2. CASE_004 — ASR positive coverage
3. CASE_005 — highest-priority possible-partial boundary
4. CASE_006 — only readable English-source semantic neighbor
5. CASE_011 — human-subtitle positive coverage
6. CASE_014 — semantic-neighbor counterpart to CASE_007
7. CASE_016 — second title-only boundary
8. CASE_018 — second curated query-corpus control

CASE_019, CASE_020, and all Reserves remain inactive. The prospective minimum total is 10 validated + 8 Round 2 = 18 Cases.

## 17. Leakage Constraints

`preliminary_leakage_report.json` now explicitly records that CASE_002/013, CASE_007/014, and CASE_011/016 must remain together in any future Development/Held-out split. CASE_012 remains `development_only`. `split_assigned=false`; no final leakage group or split was created.

## 18. Round 2 Template and Guide

`active_review_round2.jsonl` and `review_decisions.round2.template.jsonl` contain exactly the eight authorized Cases in order. All decision fields are blank/`unreviewed`; no Aspect, Evidence, Label, reason, or split is prefilled. SHA-256 values:

- Active manifest: `7daeda45184970a1a6d5ee33f66a6b39261f1ed9b1aef330711cadf20a0416e9`.
- Blank template: `61d6bf3a53ca6d9d3062ce33454869f50bb894844c8c2f95715c223caa55e58b`.
- Guide: `1d4be744da2038b2ea3f646d55e510469210d009d68391fdb68ee632c411be17`.

The Guide freezes the first ten as references, preserves four-state and OR/AND semantics, prioritizes—but does not force—CASE_005, bounds CASE_006 to English semantic-neighbor coverage, and defines CASE_018 as non-exhaustive.

## 19. Tests and Regression

Targeted Stage 2A/Follow-up/2B suite: 21 collected, 21 passed, 0 failed/skipped. Stage 2B adds 7 tests covering exact hashes and counts, unique/ordered IDs, formal schema, Packet/Segment/source/time/run/Aspect/four-state validation, canonical determinism, Round 2 order and blankness, Reserve inactivity, and no split.

Full regression: 564 collected, 564 passed, 0 failed/skipped, 7 existing warnings, 10.14 seconds. The previous 557-test baseline has no regression. Warnings are one Starlette/httpx deprecation and six multiprocessing `fork()` deprecations.

## 20. Snapshot / Stage 1 / V3 Eval Integrity

- Snapshot DB unchanged: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.
- Snapshot traces remain 82 raw / 52 presentation.
- Artifact manifest unchanged: `36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f`.
- Stage 1A/1B reports unchanged: `51d495…931d` / `606a86…220f`; evidence module hashes match intake.
- Locked queries, locked Gold, and amended V3 ledger unchanged: `21382e…c36ba`, `873b5f…5b300`, `e93fd0…0257`.
- All existing Review Packet hashes pass; original Human Intake hashes remain exact.

No frozen drift or Eval contamination was detected.

## 21. V3_5_CURRENT_STATE Update

Current State records two received/validated batches; 10/10 decisions; 6/0/3/1 distribution; 0 second-review Cases; canonical path/hash; eight Round 2 Primary cases; 0 active Reserves; no Gold lock/split; draft protocol; and no Candidate Builder, Selector, or Sufficiency Judge. Estimated Stage 2B use is 0.75–1.25 effective hours; cumulative V3.5 estimate is 5.5–8.25 hours.

## 22. Remaining Risks

Round 2 may still yield no genuine partial. English positive and cross-language coverage remain unestablished. The ten-case ledger is validated but not final Gold. Leakage groups and final activated Master Case membership remain preliminary. None authorizes automatic Reserve activation or semantic edits.

## 23. Next Human Handoff

After Version Session accepts Stage 2B, the Human Reviewer should read `research/v3_5/HUMAN_REVIEW_ROUND2_GUIDE.md`, follow `active_review_round2.jsonl`, and fill a copy of `review_decisions.round2.template.jsonl`. Do not modify the first ten validated records, do not review CASE_019/020 or Reserves, and do not force CASE_005 into any class.

## 24. Exact Commands

Principal commands executed:

```bash
cd /Users/elliot/new-systems/agent-job-prep/Shiliu
pwd -P
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git rev-parse HEAD
git diff --name-status
git diff --cached --name-status
git ls-files --others --exclude-standard

ls -l research/v3_5/human_reviews/intake/calibration_batch_01_cases_015_017_013_001_003_012.completed.jsonl research/v3_5/human_reviews/intake/calibration_batch_02_cases_007_008_009_010.completed.jsonl
shasum -a 256 research/v3_5/human_reviews/intake/calibration_batch_01_cases_015_017_013_001_003_012.completed.jsonl research/v3_5/human_reviews/intake/calibration_batch_02_cases_007_008_009_010.completed.jsonl

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -c 'from shiliu.eval_v3_5.intake import validate_human_intake; ...'
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m shiliu.eval_v3_5.intake
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_v3_5_eval_stage2a.py tests/test_v3_5_eval_stage2a_followup.py tests/test_v3_5_eval_stage2b_intake.py
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest --collect-only -q -p no:cacheprovider

sqlite3 -readonly /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db 'select count(*) from retrieval_search_traces; select count(*) from retrieval_search_presentations;'
shasum -a 256 /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db research/v3_eval/artifact_manifest.jsonl V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md research/v3_eval/eval_queries.locked.jsonl research/v3_eval/eval_gold.locked.jsonl research/v3_eval/eval_gold_review.decisions.amended.jsonl
git status --short --branch
git diff --cached --name-status
git rev-parse HEAD
```

## 25. Stop Statement

Shiliu V3.5 Stage 2B Human Decision intake validation is complete.

The two original Human Intake files were preserved unchanged.

No Human-approved semantic decision was modified.

No Development / Held-out split, final Gold lock, Candidate Builder,
Selector, Sufficiency Judge, Formal Eval, API/UI, Agent, Memory,
Harness, Translation Pipeline, or V4 work was started.

Round 2 was prepared but not reviewed.
