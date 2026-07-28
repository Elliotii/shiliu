# Shiliu V3.5 Stage 2A Follow-up — Calibration Report

## 1. Result

**Accepted for Follow-up Candidate**

The Follow-up produced the authorized six-case active calibration batch, six blank calibration decisions, a compact human guide, corrected review/protocol boundaries, and two real independent missing-source Reserve candidates. Only the V3.5 Version Session may accept this candidate and authorize human calibration.

## 2. Scope Compliance

Work was limited to frozen-asset verification, real unverifiable-candidate search, calibration assets, protocol/README/Current State corrections, validation, tests, and this report. No Human Decision, Evidence Gold, Sufficiency label, formal split, protocol freeze, retrieval change, Candidate Builder, Selector, Sufficiency Judge, LLM/provider call, formal Eval, API/UI, or V4 work occurred.

## 3. Repository Before / After

- Repository: `/Users/elliot/new-systems/agent-job-prep/Shiliu`.
- Branch before/after: `codex/v3-domain-completion`.
- HEAD before/after: `8287c8d92378b87290274d02605cdc704cb8c470`.
- Staged files before/after: none.
- Before state: `/tmp/shiliu_v3_5_stage2a_followup_before/manifest.md`.
- Pre-existing changes: six tracked V3 Web/retrieval files and accepted untracked V3 assets.
- Stage 2A changes: accepted protocol, report, Current State, `eval_v3_5`, tests, and original `research/v3_5/**` assets.
- Follow-up intended changes: section 4.
- Unexpected changes: none detected.

No reset, clean, stash, checkout, switch, rebase, commit, deletion, or rewrite of the existing 26 packets was performed.

## 4. Files Created and Modified

Created:

- `V3_5_STAGE2A_FOLLOWUP_CALIBRATION_REPORT.md`
- `research/v3_5/active_review_calibration.jsonl`
- `research/v3_5/review_decisions.calibration.template.jsonl`
- `research/v3_5/HUMAN_REVIEW_CALIBRATION_GUIDE.md`
- `research/v3_5/review_packets/RESERVE_007.md`
- `research/v3_5/review_packets/RESERVE_008.md`
- `src/shiliu/eval_v3_5/calibration.py`
- `tests/test_v3_5_eval_stage2a_followup.py`

Modified within authorization:

- `V3_5_EVAL_PROTOCOL_DRAFT.md`
- `V3_5_CURRENT_STATE.md`
- `research/v3_5/README.md`
- `research/v3_5/master_case_reserves.jsonl` (two appended records only)
- `research/v3_5/review_packet_manifest.json` (two appended packet entries only)
- `src/shiliu/eval_v3_5/models.py`
- `src/shiliu/eval_v3_5/packets.py`
- `tests/test_v3_5_eval_stage2a.py` (expected counts updated for the two authorized additions)

## 5. Stage 2A Asset Verification

Confirmed before mutation: 20 Primary, 6 original Reserve, 26 original packets, and 26 original decision records. All original decisions were `unreviewed` with blank Gold/aspect/reason fields; candidate manifests had no Gold, Label, or split fields. Packet hashes and Source Versions matched `review_packet_manifest.json`; the original Stage 2A key hashes were captured externally.

After Follow-up, all 26 pre-existing packet byte hashes remain exactly those recorded at intake. The original decision template remains SHA-256 `8580ce39cb93989dc4dec21ea0c213ae0a5367820e5c061ff568a6cd5b3f88ee` and still contains exactly 26 blank records. The original Stage 2A report was not changed.

## 6. Unverifiable Candidate Search

Search was restricted to frozen V3 Gold/ledger judgments, artifact manifest, and immutable Snapshot DB. Checked scope:

- 6 `title_only_relevant_ids` (`U_title`/title-only relevant) judgment pairs across 5 unique videos;
- 5 `unjudged_missing_content_ids` pairs across 5 unique videos;
- 12 Snapshot videos with `skipped_no_subtitle / no_supported_subtitle`;
- 14 Raw Subtitle manifest records with `status=not_declared`.

Existing title-only coverage consumed videos 137 (CASE_015), 49 (CASE_016), and 125 (RESERVE_002). Priority U_title search then yielded independent videos 142 and 143, so the time-boxed search stopped after satisfying the requested 1–2 candidates. Missing-content video 44 has a now-readable frozen Raw source and was not treated as unverifiable; other missing-content records were not needed after the priority target was met.

## 7. Additional Candidate Results

| Candidate | Frozen query/judgment | Video/BVID | Frozen source fact | Independence and packet feasibility |
|---|---|---|---|---|
| RESERVE_007 | Q02 `RAG`; video 142 in `title_only_relevant_ids` | 142 / `BV1zjNG6mEPi` | `skipped_no_subtitle`, `no_supported_subtitle`, Raw artifact `not_declared`, verified metadata present | Different from 137/49/125; no-body packet feasible without fabrication |
| RESERVE_008 | Q22 `Agent`; video 143 in `title_only_relevant_ids` | 143 / `BV1wtEt6YEiC` | `skipped_no_subtitle`, `no_supported_subtitle`, Raw artifact `not_declared`, verified metadata present | Different from all existing title-only videos; no-body packet feasible without fabrication |

Both use `source_state=subtitle_missing` and sampling stratum `no_subtitle_source_state`. This makes unverifiable plausible for future human review but does not assign `sufficiency_label=unverifiable`. Both are inactive, unassigned, and have no decision record in the active batch.

## 8. Active Calibration Manifest

`active_review_calibration.jsonl` contains exactly six existing Primary cases in authorized order:

1. CASE_015 — source-authority/title-only boundary — `quick_authority_check`
2. CASE_017 — query-corpus negative boundary — `quick_authority_check`
3. CASE_013 — semantic-neighbor boundary — `focused_semantic_review`
4. CASE_001 — Evidence Group/positive coverage — `focused_semantic_review`
5. CASE_003 — multi-aspect/partial boundary — `deep_multi_aspect_review`
6. CASE_012 — run-local multi-timeline behavior — `robustness_review`

All records use batch `stage2a-followup-calibration-01`, version `v3.5-label-calibration-batch-v1`, valid existing packet paths, explicit review-focus-only constraints, and `decision_status=unreviewed`. No Reserve is present.

## 9. Calibration Decision Template

`review_decisions.calibration.template.jsonl` contains those six cases in the same order. Each record was copied from the original blank schema and retains empty reviewer/time, aspects, Gold groups, supported/missing aspects, reasons, notes, and flags; Label, confidence, second review, and status remain `unreviewed`. The calibration focus was not copied into any decision field.

## 10. Human Calibration Guide

The guide establishes that Full Raw Transcript must remain accessible but does not require linear end-to-end reading. It assigns system responsibility for mechanical source/version/Segment/time/run/navigation work and human responsibility only for semantic aspects, supporting Raw Segments, OR/AND Evidence Groups, four-state decision, reason, and second review. It contains the required six per-case instructions and mandatory `needs_second_review` conditions.

## 11. Reserve Activation Policy

Reserve candidates are inactive by default; active Reserve count is 0. Activation is allowed only for unusable/ambiguous Primary cases, material class/source imbalance, leakage invalidation, or required extra unverifiable coverage. An activation must record `activation_reason`, `replaced_or_supplemented_case`, `activated_at`, and `authorized_by`. No ordinary or new Reserve was activated in this Follow-up.

## 12. Query-corpus Negative Correction

The protocol now defines query-corpus controls as curated out-of-domain controls, not exhaustive proofs that no corpus video contains a related sentence. Human approval is bounded to the frozen library topic and V3 results: no obvious video should be approved as a target evidence source. These cases do not participate in Fine Evidence Span Metrics; they participate in Sufficiency, false-answer rate, no-search/no-answer behavior, and Reason Code evaluation.

## 13. English / Cross-language Correction

The protocol, README, and Current State now state:

- English-source coverage: one readable semantic-neighbor candidate;
- English-source positive evidence: not established;
- cross-language evidence resolution: not evaluated.

The reason is structural: the frozen real pool contains only one distinct English-source pooled query-video pair, and it is not a cross-language positive case.

## 14. Human Review Workflow Correction

The active workflow is frozen as:

1. Round 1: six-case Label Calibration.
2. Round 2: remaining necessary Primary cases.
3. Round 3: targeted Reserve activation only when required.

Stage 2B does not require 26/26 decisions by default. A future Stage 2C lock must require completion of all activated final Master Cases—not every Primary plus every Reserve. Workload is classified into quick authority, seed-assisted, focused semantic, deep multi-aspect, and robustness review rather than equal full-transcript linear reading.

## 15. Validation and Tests

Targeted tests:

```text
14 collected, 14 passed, 0 failed, 0 skipped
```

This includes the original 8 Stage 2A tests (updated only for authorized counts) and 6 Follow-up tests for exact active order, blank decisions, inactive Reserves, real frozen provenance, protocol corrections, original-template hash, and all packet hashes.

Full regression:

```text
557 collected, 557 passed, 0 failed, 0 skipped
7 warnings
10.45 seconds
```

The pre-Follow-up 551 tests have no behavioral regression; all 6 new tests pass. Warnings are the existing Starlette/httpx warning and six multiprocessing `fork()` deprecations.

## 16. Snapshot / Stage 1 / Eval Integrity

- Snapshot DB SHA-256 unchanged: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.
- Artifact manifest SHA-256 unchanged: `36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f`.
- Snapshot traces remain 82 raw / 52 presentation.
- Stage 1A/1B reports remain `51d495…931d` / `606a86…220f`; all six evidence contract/module hashes match intake.
- Canonical V3 Eval hashes match the supplementary Phase 0 intake fingerprints; locked queries/Gold/amended ledger remain `21382e…c36ba`, `873b5f…5b300`, and `e93fd0…0257`.
- Original 26 packets and the 26-record blank template are unchanged.

No integrity drift was detected.

## 17. V3_5_CURRENT_STATE Update

Current State records Follow-up completion; six active calibration cases; 0 completed reviews; 8 inactive Reserves including two real missing-source additions; 28 packets; draft/not-frozen protocol; no Gold; no split; three-round workflow; corrected English/cross-language limits; and updated budget estimates. Follow-up use is approximately 0.5–0.75 effective hours; cumulative V3.5 estimate is 4.75–7.0 hours.

## 18. Human Review Handoff

After Version Session authorization, the user should read `HUMAN_REVIEW_CALIBRATION_GUIDE.md`, use `active_review_calibration.jsonl` as the exact order, and fill a copy of `review_decisions.calibration.template.jsonl`. Start at navigation aids, inspect context and alternatives, and consult full transcript authority whenever necessary. Do not fill the original 26-record template or any Reserve. Use run-local groups for CASE_012 and set `needs_second_review=true` whenever the Guide requires it.

## 19. Findings Ledger

| Type | Finding | Evidence / impact |
|---|---|---|
| Confirmed Fact | Original decisions remain blank and original packets unchanged. | SHA-256 checks and validators. |
| Confirmed Fact | The active workload is exactly six authorized Primary cases. | Ordered manifest/template tests. |
| Confirmed Fact | Videos 142/143 have real U_title provenance and frozen missing Raw authority. | Locked Gold, Snapshot DB, artifact manifest. |
| Confirmed Fact | All 8 Reserves are inactive; completed human reviews remain 0. | Active manifest exclusion and blank records. |
| Inference | RESERVE_007/008 plausibly improve future unverifiable calibration. | Source-state facts support sampling; no final label is inferred. |
| Unknown | Final usability, aspects, groups, Labels, and activated case set. | Human calibration has not begun. |
| Blocking Risk | None for Version Session handoff. | Required assets and tests pass. |
| Recommendation | Run only the six-case calibration before deciding remaining Primary workload. | Governing correction and bounded workload. |

## 20. Remaining Risks

The two added Reserves may remain unnecessary or may receive a different human Label; they are sampling candidates only. The English/cross-language limitation remains structural. Calibration may reveal unstable aspect boundaries or require second review. No leakage group or final activated Master Case set exists yet.

## 21. Next Step

Version Session should accept or reject this Follow-up candidate. If accepted, authorize human Round 1 calibration only. After six decisions, assess label consistency, ambiguity, and source/class balance before authorizing any Round 2 Primary or Round 3 Reserve work.

## 22. Exact Commands

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

shasum -a 256 V3_5_EVAL_PROTOCOL_DRAFT.md V3_5_STAGE2A_EVAL_PROTOCOL_AND_REVIEW_PACKET_REPORT.md V3_5_CURRENT_STATE.md research/v3_5/master_case_candidates.jsonl research/v3_5/master_case_reserves.jsonl research/v3_5/review_decisions.template.jsonl research/v3_5/review_packet_manifest.json research/v3_5/preliminary_leakage_report.json research/v3_5/review_packets/*.md
shasum -a 256 V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md src/shiliu/evidence/contracts.py src/shiliu/evidence/source.py src/shiliu/evidence/mapping.py src/shiliu/evidence/authority.py src/shiliu/evidence/audit.py src/shiliu/evidence/search.py
shasum -a 256 research/v3_eval/*.jsonl research/v3_eval/gold_lock_audit.json research/v3_eval/human_ledger_amendment_audit.json research/v3_eval/eval_results.json research/v3_eval/eval_results.csv research/v3_eval/failure_cases.md research/v3_eval/V3_EVAL_PROTOCOL.md V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md
shasum -a 256 /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db

jq -s '...' research/v3_eval/eval_gold.locked.jsonl
jq -s '...' research/v3_eval/eval_gold_review.decisions.amended.jsonl
jq -s '...' research/v3_eval/artifact_manifest.jsonl
sqlite3 -readonly /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db '...'

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_v3_5_eval_stage2a.py tests/test_v3_5_eval_stage2a_followup.py
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest --collect-only -q -p no:cacheprovider

git status --short --branch
git diff --cached --name-status
git rev-parse HEAD
```

All Snapshot/Gold/artifact/database inspection used frozen local files and read-only DB access.

## 23. Stop Statement

Shiliu V3.5 Stage 2A follow-up is complete.

No Human Gold, Evidence Group, Sufficiency Label, Development / Held-out split, Candidate Builder, Selector, Sufficiency Judge, Formal Eval, API / UI, Agent, Memory, Harness, Translation Pipeline, or V4 work was started.

Reserve cases remain inactive by default.

The active human review workload is limited to a six-case calibration batch.

Full Raw Transcripts remain available as annotation authority, but reviewers are not required to linearly read every transcript from beginning to end.

Additional recommendations were recorded only and were not implemented.
