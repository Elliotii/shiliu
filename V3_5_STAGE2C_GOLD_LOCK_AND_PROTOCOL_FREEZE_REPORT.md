# Shiliu V3.5 Stage 2C — Gold Lock and Eval Protocol Freeze Report

## 1. Result

**Accepted with Documented Limitations Candidate**

Stage 2C completed within its authorized boundary. CASE_004 focused Human adjudication was exact-hash validated and merged as the only semantic override. The 18-Case Master Gold, 8-Case Development Gold, 10-Case Held-out Gold, reason registry, leakage-safe split, Eval Protocol, Held-out isolation contract, manifest, and audit are locked. Final acceptance remains with the V3.5 Version Session.

## 2. Scope Compliance

Performed only CASE_004 adjudication validation/merge, full 18-Case mechanical revalidation, Gold granularity review, membership/split/reason/protocol freeze, lock generation, audit, tests, Current State update, and this report. No original Human Intake, validated historical ledger, Review Packet, Raw Artifact, Snapshot, Stage 1 Contract, V3 Retrieval, V3 Gold/Eval asset, API/UI, or product behavior was modified. No Provider, network, or LLM call occurred.

## 3. Repository Before / After

- Repository: `/Users/elliot/new-systems/agent-job-prep/Shiliu`.
- Branch: `codex/v3-domain-completion`.
- HEAD before/after: `8287c8d92378b87290274d02605cdc704cb8c470`.
- Staged changes before/after: none.
- Pre-existing dirty worktree was preserved. Stage 2C before-state evidence and exact input copies are in `/tmp/shiliu_v3_5_stage2c_before/`.
- Intended Stage 2C changes are confined to `V3_5_CURRENT_STATE.md`, this report, `research/v3_5/gold/**`, the Stage 2C locked-contract addition in `research/v3_5/preliminary_leakage_report.json`, `src/shiliu/eval_v3_5/stage2c.py`, and `tests/test_v3_5_eval_stage2c.py`.

## 4. Input Identity and Hashes

All four mandatory identities matched exactly before any Gold output was generated.

| Input | Required/current SHA-256 | Result |
|---|---|---|
| 10-Case validated calibration ledger | `06ce0e3980e09618a901f572e96ab9d0970660219f33cab79630860532f01737` | verified |
| 8-Case validated Round 2 ledger | `9c2a8ac2feb9d18fb7bac0f68b196192b8a22fac4948b0a4351b263b74fb16bb` | verified |
| Provisional 18-Case ledger | `ed2f18e8850d4fef891c1d89c191d49a793190bd40c8e4ae84b5e3b192a60ba0` | verified |
| CASE_004 completed adjudication | `9a6f193fe472efb7647d66dc16916466bc99131eff12e8adad3926ada8f79f22` | verified |

## 5. CASE_004 Adjudication Validation

The adjudication contains exactly one completed `human_user` record for CASE_004. It remains `partial`, medium confidence, and now has `needs_second_review=false`. G1 supports A3 only; A1/A2 remain missing. G1_S1 reconstructs exactly from 129.16–138.91 seconds using the two authorized Segment IDs, in one Timeline Run. Source text remains rendered as ASR `ra`; no transcript repair occurred. Conflict notes and reviewer flags retain ASR/entity uncertainty.

## 6. Prior / Adjudicated CASE_004 Comparison

Unchanged: case identity, reviewer, review version, completion state, required Aspects, supported/missing Aspects, label, confidence, G1 structure, exact Segment IDs, stored times, Timeline Run, and the Human evidence interpretation that only A3 is supported.

Authorized changes: `needs_second_review` true→false; primary reasons `limited_aspect_coverage` + `asr_transcription_uncertainty`→canonical `partial_aspect_coverage`; adjudication time, conflict notes, reviewer flags, and support notes were updated to record focused-review provenance and retained ASR uncertainty. Provenance layer: `v3.5-case-adjudication-v1`. The original Round 2 record remains unchanged.

## 7. Adjudicated 18-Case Master Ledger

`research/v3_5/gold/review_decisions.master.18_cases.adjudicated.jsonl` contains 18 unique completed Cases in the authorized canonical order. Only CASE_004 differs from the provisional ledger; the other 17 records are value-identical. SHA-256: `340e90bdd078e9b9a7aeac2bd98245b22d0e0b1f6d04812c675805996ad1fc09`.

Final labels: sufficient 9, partial 1, insufficient 6, unverifiable 2. Sources: AI 10, ASR 2, human subtitle 2, title-only 2, query-corpus 2. `needs_second_review=true`: 0.

## 8. Complete Mechanical Revalidation

All 18 records passed formal schema, case and Packet identity, source identity/version, Segment existence/order, stored time reconstruction, Timeline Run locality, Aspect references, Group OR semantics, required-span AND semantics, four-state invariants, and reason compatibility. Readable-source and query-corpus negative cases fabricate no unsupported useful-answer Gold; unverifiable cases fabricate no Evidence Group. Errors: 0.

## 9. Gold Granularity Audit

Ten Cases / eleven Evidence Groups were reviewed in `gold_granularity_audit.json`. CASE_001/002/004/008/011 pass. CASE_003/005/007/009/010 pass with documented breadth: their continuous or complementary spans map to distinct required Aspects, and removing a span would lose required support. Duration alone was not treated as failure. No obvious unrelated lead-in/tail, provenance error, semantic edit requirement, or Human granularity-review blocker was found. No Span, Segment, Group, Aspect, or label was changed.

## 10. Final Master Membership

Master membership is exactly CASE_001–CASE_018, count 18. CASE_019, CASE_020, and all Reserves are excluded. Active Reserve count: 0. Membership lock SHA-256: `e95e23e6f9d4043b01d43e04c7a53ed56fe7577d2a1bcfc0b7b8996d12d60a93`.

## 11. Canonical Reason Code Registry

The locked registry preserves the observed concepts and their action families. `limited_aspect_coverage` is a historical alias of `partial_aspect_coverage`; immutable intake is not migrated. `query_target_mismatch` remains distinct from `semantic_neighbor_only`; `no_approved_target` remains distinct from `out_of_domain_negative_control`; ASR uncertainty may remain auxiliary. Registry SHA-256: `6725bd1a55457319557e83b350aae50145ccb3a912d3070b4d95e859aa80f0fc`.

## 12. Final Leakage Groups

- LG_MCP: CASE_001, CASE_003, CASE_012.
- LG_MEMORYOS: CASE_002, CASE_013.
- LG_RAG_OPTIMIZATION: CASE_007, CASE_014.
- LG_PI_AGENT: CASE_011, CASE_016.

Every group is wholly contained in one split. The historical preliminary report retains its original top-level status for compatibility and now also records the Stage 2C locked contract explicitly.

## 13. Development / Held-out Split

Development (8): CASE_001, 002, 003, 005, 012, 013, 015, 017. Labels 4/0/3/1; all five source categories are represented. CASE_012 remains Development-only.

Held-out (10): CASE_004, 006, 007, 008, 009, 010, 011, 014, 016, 018. Labels 5/1/3/1; all five source categories and the only readable English-source Case are represented. CASE_004 is Held-out and unavailable for tuning. The sets are disjoint and their union equals Master. Limitation: Development contains no real Human-approved partial Case.

## 14. Locked Gold Assets and Hashes

| Asset | SHA-256 |
|---|---|
| Master Gold 18 | `340e90bdd078e9b9a7aeac2bd98245b22d0e0b1f6d04812c675805996ad1fc09` |
| Development Gold 8 | `5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0` |
| Held-out Gold 10 | `6b7d06a6a0f3eeb61a9bc542ee8c2a8d12fc6d52fbb6576f64eff72d0d662789` |
| Master membership | `e95e23e6f9d4043b01d43e04c7a53ed56fe7577d2a1bcfc0b7b8996d12d60a93` |
| Development/Held-out split | `fc3ff77b7d22668b5a7e555e8db44abdec1ce856c0b629f80327145831b7731c` |
| Reason registry | `6725bd1a55457319557e83b350aae50145ccb3a912d3070b4d95e859aa80f0fc` |
| Granularity audit | `8ba9c4bbc11aa3bb1243ce189d75bf35bb07e18ad3a5fccd100ae3ba3ed45aef` |

Development and Held-out are deterministic projections of Master and introduce no semantic field changes.

## 15. Frozen Eval Protocol

`research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md` freezes Evidence/source/version/timeline authority, Group OR and span AND semantics, four-state Sufficiency, reason codes, query-video/query-corpus behavior, metric eligibility, split/leakage/isolation rules, abstention, deterministic quote/time reconstruction, Human adjudication, granularity, per-class/absolute-count/uncertainty reporting, and non-mechanical readiness interpretation. SHA-256: `01f1dd8d6f26bd68962ccb42b489f5be3d086cef2ed0fe90616cb9d3e43db90f`.

## 16. Held-out Isolation Contract

Development labels/Evidence are available for later implementation. Held-out Query metadata is runner-only; Held-out labels, Aspects, Evidence Groups, spans, and reasons are forbidden during Candidate Builder, Selector, and Sufficiency development. No threshold/prompt tuning, failure inspection, case exception, or post-result Gold change is allowed. Contract SHA-256: `faeccb772dd624775e58b55e8614af836fb64d102e7762244b3869767641f18e`.

## 17. Gold Lock Manifest

`gold_lock_manifest.json` records all contract versions, four input hashes, adjudication provenance, all output hashes, 18/8/10 counts, label/source/language distributions, Leakage Groups, exclusions, zero active Reserves, and known limitations. SHA-256: `268d9b68e29cc7f242375ba108d9d99ef536e2f413c3747d9f95f7ab97588075`.

## 18. Gold Lock Audit

`gold_lock_audit.json` records verified inputs, CASE_004 validation, sole override/17-value-identity proof, 18 completed/schema-valid records, zero second-review flags, valid source/Segment/run/four-state contracts, granularity/reason/membership/leakage/split results, disjoint union, Held-out class/source coverage, exclusions, hashes, errors, and warnings. Errors: 0; one documented warning: Development has no real Human-approved partial. SHA-256: `da65889ae2bbcea2f0a34e40a42c8ee598d185ab3183f07970d0f16e6426e77d`.

## 19. Tests and Regression

- Stage 2C targeted: 6 passed.
- Stage 2A/Follow-up/2B/2C targeted: 34 passed.
- Full repository: 577 passed, 0 failed, 0 skipped; 7 pre-existing warnings (one Starlette/httpx deprecation and six multiprocessing/fork deprecations).
- Re-running the lock generator reproduced the same locked hashes.

## 20. Snapshot / Stage 1 / V3 Eval Integrity

Post-lock verification matched the frozen baselines: Snapshot DB `61589a5b…c4e1`; Artifact manifest `36e63e3…08f`; 82 raw traces, 52 presentation traces, 1,412 transcript chunks; Stage 1A/1B reports `51d495…931d` / `606a86…220f`. All 11 present V3 Eval assets matched their V3.5 intake fingerprints, including historically verified amended ledger `e93fd09b…0257`. `SHILIU_V3_VERSION_DECISION.md` remains absent as previously documented, not as new drift. No stop condition was reached.

## 21. Current State Update

`V3_5_CURRENT_STATE.md` now records Stage 2A/2B acceptance, completed CASE_004 adjudication, locked 18/8/10 assets, zero second-review flags, final 9/1/6/2 distribution, zero active Reserves, frozen protocol, Stage 2 completion, unchanged Stage 1/V3 baselines, actual cumulative hours, and remaining budget.

## 22. Stage 2 Closeout

Stage 2A: accepted. Stage 2B: accepted. Stage 2C: completed as a closeout candidate. Candidate Builder, Selector, Sufficiency Judge, and Formal Eval are not started. Final Version Session acceptance is still required.

## 23. Known Limitations

- English positive evidence is not established.
- Cross-language evidence resolution is not evaluated.
- The only Human-approved partial Case is Held-out; Development has zero real partial Cases.
- Two unverifiable Cases are title-only.
- Runtime failure states require later deterministic contract fixtures without reproducing CASE_004.
- The 18-Case set is not statistically representative.
- `SHILIU_V3_VERSION_DECISION.md` remains locally absent.

## 24. Next Stage

Stop here. After Version Session acceptance, Stage 3 may implement the Candidate Builder using Development only and honoring exact source/version/timeline mapping plus Held-out isolation. No Stage 3 work was begun in this session.

## 25. Exact Commands

```bash
cd /Users/elliot/new-systems/agent-job-prep/Shiliu
pwd -P
git rev-parse --show-toplevel
git status --short --branch
git rev-parse HEAD
sha256sum <four-authoritative-inputs>
sha256sum <Snapshot-DB> research/v3_eval/artifact_manifest.jsonl <Stage-1-reports>
sha256sum <eleven-present-V3-Eval-assets>
sqlite3 -readonly <Snapshot-DB> "select count(*) from retrieval_search_traces; select count(*) from retrieval_search_presentations; select count(*) from retrieval_units where unit_type='transcript_chunk';"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m shiliu.eval_v3_5.stage2c
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_v3_5_eval_stage2c.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_v3_5_eval_stage2a.py tests/test_v3_5_eval_stage2a_followup.py tests/test_v3_5_eval_stage2b_intake.py tests/test_v3_5_eval_stage2b_round2.py tests/test_v3_5_eval_stage2c.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
git diff --cached --name-status
git status --short --branch
```

## 26. Stop Statement

Shiliu V3.5 Stage 2C Gold Lock and Eval Protocol Freeze is complete.

CASE_004 focused Human adjudication was validated and merged as the
only authorized semantic override.

The final 18-Case Master Gold, 8-Case Development Gold and
10-Case Held-out Gold were locked under leakage-safe split rules.

No Human-approved label, Aspect or Evidence Span was modified by Codex.

No Candidate Builder, Selector, Sufficiency Judge, Formal Eval,
API/UI, Agent, Memory, Harness, Translation Pipeline or V4 work
was started.
