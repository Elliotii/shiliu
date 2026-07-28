# Shiliu V3.5 Stage 2B — Round 2 Intake and Adjudication Preparation Report

## 1. Result

**Accepted with Follow-up Candidate**

All eight Round 2 Human Decisions passed mechanical validation and were preserved in a canonical ledger. An 18-case Provisional Master Ledger was created. Final Gold cannot be locked because CASE_004 is the sole `needs_second_review=true` Case and requires focused Human adjudication.

## 2. Human Intake Identity

Path: `research/v3_5/human_reviews/intake/round2_primary_cases_002_004_005_006_011_014_016_018.completed.jsonl`  
SHA-256: `036fad9aa0d2bc4c437fb31fbfa86ab07e1694554f804e66ba8feeab3dabf73e`  
Records: 8

The file exists at the exact authorized path, matches the expected hash, and remains byte-for-byte unchanged. The validated 10-Case ledger also matches its required hash `06ce0e3980e09618a901f572e96ab9d0970660219f33cab79630860532f01737`.

## 3. Eight-case Accounting

Actual order exactly matches authorization: CASE_002, CASE_004, CASE_005, CASE_006, CASE_011, CASE_014, CASE_016, CASE_018. There are eight records, eight unique IDs, zero unknowns, and zero duplicates. Every record is `completed` by `human_user`. CASE_019/020 and all Reserves remain inactive.

## 4. Schema Validation

All records pass `CompletedReviewDecision`. Aspect IDs are unique; supported/missing and Group-supported Aspect references resolve; Groups have non-empty required Spans and valid OR/AND structure. No Human label, Aspect, Group, Span, reason, note, confidence, or flag was edited.

## 5. Evidence / Source / Timeline Validation

Every cited Segment ID exists in the expected frozen Raw Source and Review Packet. Candidate Source Version, Packet manifest Source Version, Artifact manifest hash, and actual bytes agree. Segment order follows original ordinals; stored start/end exactly reconstruct from first/last selected Segments; every Span remains in one Timeline Run.

Four Cases have Gold Groups: CASE_002, CASE_004, CASE_005, CASE_011. CASE_005 and CASE_011 use complementary multi-Span Groups. No Round 2 alternative OR Group exists. The longest is CASE_005/G1: four Spans and 151.62 seconds union duration. Validation produced zero warnings and errors.

## 6. Round 2 Label Distribution

| Label | Count |
|---|---:|
| sufficient | 3 |
| partial | 1 |
| insufficient | 3 |
| unverifiable | 1 |

Source distribution: AI 3, ASR 2, human subtitle 1, title-only 1, query-corpus 1. Languages: zh 5, en 1, unavailable/not applicable 2. Transcript/ASR uncertainty flags in CASE_002, CASE_004, and CASE_005 were preserved.

## 7. CASE_004 Second-review Requirement

CASE_004 mechanically validates as the exact prior Human Decision: `partial`, medium confidence, `needs_second_review=true`, A3 supported, A1/A2 missing, reasons `limited_aspect_coverage` and `asr_transcription_uncertainty`. Its approved Span is the exact Segment ordinal 20–21 range, 129.16–138.91s, in one Timeline Run.

Frozen ASR renders the key token as `ra`. Codex did not repair it, alter the Span, clear the flag, or relabel the Case. The focused Guide asks whether `ra` is reliably interpretable as RAG, whether A3 is supported, whether the strength reaches partial, whether A1/A2 are absent, and whether the Span should be retained/changed/rejected by the Human adjudicator.

## 8. Round 2 Validated Ledger

Path: `research/v3_5/human_reviews/review_decisions.round2.8_cases.validated.jsonl`  
SHA-256: `9c2a8ac2feb9d18fb7bac0f68b196192b8a22fac4948b0a4351b263b74fb16bb`

It is value-identical to Human Intake; only authorized order, sorted keys, compact serialization, and newline normalization differ. Validation audit SHA-256: `2040ad87298171c8970669803bddb5824a9020891c55fe915b64ad1c71bd3dee`.

## 9. Provisional 18-Case Ledger

Path: `research/v3_5/human_reviews/review_decisions.master.18_cases.provisional.jsonl`  
SHA-256: `ed2f18e8850d4fef891c1d89c191d49a793190bd40c8e4ae84b5e3b192a60ba0`

It contains 18 unique Cases: the validated ten followed by Round 2 eight. The companion manifest explicitly marks `Provisional Master Ledger` and `Not Final Gold`. Blocking conditions are CASE_004 second review, no Development/Held-out assignment, and an unfrozen Eval Protocol.

## 10. Combined Distribution and Source Coverage

| Label | Count |
|---|---:|
| sufficient | 9 |
| partial | 1 — CASE_004, provisional |
| insufficient | 6 |
| unverifiable | 2 |

Combined sources: AI 10, ASR 2, human 2, title-only 2, query-corpus 2. Actual values match expectations without rebalancing.

If CASE_004 remains partial, retain the 18 Cases and record partial underrepresentation; do not activate a Reserve. If it changes class, Version Session decides whether RESERVE_004 should be activated. Codex does not.

## 11. Reason Code Registry Audit

Observed codes are `asr_transcription_uncertainty`, `limited_aspect_coverage`, `no_approved_target`, `out_of_domain_negative_control`, `query_target_mismatch`, `semantic_neighbor_only`, and `title_only`. The last two already exist; the first five remain candidate codes. No Human code was renamed.

`limited_aspect_coverage` is a likely alias of `partial_aspect_coverage`, but Stage 2C must decide. `query_target_mismatch` may co-occur with but is distinct from `semantic_neighbor_only`. `no_approved_target` was not collapsed into search-absence codes. The machine audit recommends keeping ASR uncertainty, target absence, out-of-domain control, and target mismatch distinct pending Stage 2C.

## 12. Leakage Audit Update

Preserved: CASE_002/013, CASE_007/014, and CASE_011/016 must stay together in any future split; CASE_012 remains `development_only`. Added exact-query leakage candidate CASE_001/012 (`MCP`). CASE_003 is recorded as a broader MCP/Function Calling risk without forcing final grouping. No split was assigned.

## 13. Tests and Integrity

Targeted Stage 2B intake/Round 2 tests: 14/14 passed. They cover exact identity/order, schema, Packet/Segment/Source/time/run/four-state validation, sole CASE_004 second-review status, canonical 8-Case and 18-Case determinism, distribution/source coverage, blank adjudication template, reason preservation, no split, and no Reserve activation.

Full regression: 571 collected, 571 passed, 0 failed/skipped, 7 existing warnings, 11.12 seconds. The prior 564-test baseline has no regression.

Frozen integrity: Snapshot DB `61589…c4e1`; Artifact manifest `36e63…08f`; trace rows 82 raw / 52 presentation; Stage 1A/1B reports `51d495…931d` / `606a86…220f`. No drift was detected.

## 14. Current State Update

Current State records 8/8 Round 2 decisions validated, the Round 2 and 18-Case ledger hashes, 9/1/6/2 provisional distribution, expected source coverage, CASE_004 second review, final Gold not locked, no split, draft Protocol, and zero active Reserves. It also records exact-query leakage and the unresolved Reason Code alias.

## 15. Next Human Handoff

The only next action is one focused Human second review of CASE_004 using:

- `research/v3_5/human_reviews/adjudication/CASE_004_SECOND_REVIEW_GUIDE.md`
- `research/v3_5/human_reviews/adjudication/review_decision.CASE_004.second_review.template.jsonl`

The template is blank/unreviewed. The Guide labels the displayed decision **Prior Human Decision — Not Final Adjudicated Gold**. No other Case or Reserve should be activated or reviewed.

## 16. Stop Statement

Shiliu V3.5 Round 2 Human Intake validation is complete.

The original Round 2 Human Intake was preserved unchanged.

No Human-approved semantic decision was modified.

A provisional 18-case Master Ledger was created, but final Gold was not
locked because CASE_004 requires focused second review.

No Development / Held-out split, Candidate Builder, Selector,
Sufficiency Judge, Formal Eval, API/UI, or V4 work was started.
