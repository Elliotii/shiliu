# Shiliu V3.5 Stage 4A — Mechanical Sufficiency Gate Report

## 1. Result

**Accepted with Mechanical-gate Baseline Risk Candidate**

The deterministic Gate reliably separates mechanically valid EvidenceBundles from operationally unverifiable states. S1 still produces readable-insufficient false-sufficient errors, exactly demonstrating why Stage 4B remains necessary.

## 2. Scope Compliance

Only Stage 4A contracts, policy, pure runtime gate, Development-only runner/diagnostics, S0/S1, traces, tests, artifacts, state, and this report were implemented. Provider calls: 0. No LLM, semantic judge, answer synthesis, retrieval/builder/selector retuning, formal Held-out Eval, API/UI, Agent, Memory, Harness, Translation, Stage 5/6, or V4 work started.

## 3. Repository Before / After

Before: `/Users/elliot/new-systems/agent-job-prep/Shiliu`, branch `codex/v3-domain-completion`, HEAD `8287c8d92378b87290274d02605cdc704cb8c470`, ahead 1, with extensive pre-existing tracked and untracked work. Exact pre-state is preserved at `/tmp/shiliu_v3_5_stage4a_before/`.

Pre-existing tracked changes remain `V3_CURRENT_STATE.md`, retrieval files, `base.html`, and `web.py`, plus the pre-existing untracked history recorded in the snapshot. Stage 4A intended changes are limited to `V3_5_CURRENT_STATE.md`, this report, `research/v3_5/stage4a/**`, `src/shiliu/evidence/stage4.py`, `src/shiliu/eval_v3_5/stage4a.py`, and two `tests/test_v3_5_stage4a_*.py` files. Unexpected changes: none.

## 4. Time-budget Check

Intake cumulative range was 11.5–15.0 hours. Conservative Stage 4A maximum 3 hours plus a 6-hour minimum reserve reaches, but does not exceed, 24 hours. Actual Stage 4A estimate is 1.5–2.0 hours; cumulative is 13.0–17.0 with 7.0–11.0 remaining.

## 5. Input Identity

Development Gold `569383...90d0`; Execution Manifest `ef08e5...34e`; Snapshot `61589a...c4e1`; Artifact Manifest `36e63e...d08f`; Eval Protocol `01f1dd...90f`; Isolation Contract `faeccb...f18e`. All matched required values before/after. Stage 4A manifest hash: `de1b4d46c46e51a054d944a7c361c885dd3959cd6fab12aa65eae2ea913e1017`.

## 6. Held-out Isolation

Held-out/Master Gold, adjudicated ledgers, Gold lock/membership/split/reason registry, Human reviews, review packets, and legacy Eval Gold/query assets were not opened, parsed, hashed, imported, or searched. Guard path tests cover every protected spelling without opening targets. Held-out accessed: false; forbidden attempts: 0.

## 7. Stage 3 Frozen Runtime

Final Builder: `stage3b-acronym-w3.5-v1` / generic policy `v3.5-stage3b-asr-acronym-anchor-v1`. Fine Selector: `v3.5-deterministic-fine-selector-v1`. Structured LLM selector: rejected and unused. Track A preserves frozen V3 candidates; Track B is oracle-video conditional and never end-to-end claim eligible.

## 8. Service Architecture

`apply_mechanical_sufficiency_gate(request, evidence_resolution_state, evidence_bundle, policy)` is pure: no file, database, network, Provider, selector, or Gold access. It validates already-constructed runtime objects only.

## 9. SufficiencyRequest Contract

`v3.5-sufficiency-request-v1` is strict (`extra=forbid`) and includes required query/track/identity/version/source/trace fields. It has no Case ID, Gold field, raw transcript, or Candidate Pool.

## 10. MechanicalGateDecision Contract

`v3.5-mechanical-sufficiency-gate-v1` strictly enforces the `judge_eligible` and `terminal_unverifiable` consistency rules, including semantic-judge-required and terminal-field invariants.

## 11. SufficiencyDecision Contract

`v3.5-sufficiency-decision-v1` is frozen. Stage 4A creates only terminal `unverifiable` decisions with `mechanical_gate_applied=true` and `semantic_judge_invoked=false`; it rejects final-decision synthesis for eligible inputs.

## 12. Operational Reason Policy

All required retrieval, candidate, selector, source, normalization, integrity, and unknown reason enums are frozen. Selector aliases normalize to `selector_failed`. Unknown remains a typed fail-closed state; final Development count is zero.

## 13. Action-family Policy

The frozen families are retrieval, evidence resolution, selector recovery, source recovery, data integrity, and none. Operational reasons never enter `semantic_reason_code`.

## 14. Mechanical Mapping Rules

Retrieval misses terminate to retrieval action; Candidate failure to evidence-resolution action; selector aliases to selector-recovery action; source authority failures to source-recovery action; identity/normalization failures to data-integrity action. None maps to semantic `insufficient`.

## 15. Valid-bundle Eligibility Rules

Eligibility requires a present normalized Bundle, correct contract/object shape, empty validation errors, non-empty existing Raw-derived Candidate references, frozen Builder/Selector versions, consistent query/track/SearchCandidateSet/EvidenceCandidateSet/Bundle identities, and valid source integrity. Evidence text meaning is never inspected.

## 16. Stable Decision Identity

Canonical UTF-8 JSON with sorted keys, compact separators, finite values, and SHA-256 binds the required contract/query/track/set/Bundle/outcome/reason/action/policy fields. It excludes time, random UUID, trace ID, process ordinal, and database IDs. Repeat-call byte equality and ID equality pass.

## 17. Track A Results

Eight cases: 4 judge eligible, 4 terminal unverifiable. Actions: retrieval 4; evidence resolution, selector recovery, source recovery, and data integrity 0. Unknown state 0; invalid decision 0. Gold comparison: sufficient 2 eligible/2 terminal; insufficient 2/1; unverifiable 0/1; partial support 0.

## 18. Track B Results

Four evidence cases: 3 judge eligible, 1 terminal. CASE_003 preserves frozen Candidate Builder failure and maps to evidence-resolution action. No other terminal actions, unknown states, or invalid decisions. Track remains `oracle_video_conditional`, `end_to_end_claim_eligible=false`.

## 19. Judge-input Adequacy

Track A: 3 adequate / 4 eligible, 1 inadequate. Track B: 1 adequate / 3 eligible, 2 inadequate. Combined diagnostic: 4/7 adequate. Prediction freeze SHA-256 is `1172e4952d23a6179bbd5ee3766f41e1b48118c51fedf32d65fdeaf93330d982`; Development Gold opened afterward. CASE_002 in both tracks and CASE_005 Track B are attributed to upstream evidence-resolution coverage, not future Judge failure.

## 20. S0 Always-sufficient Baseline

Accuracy 4/8 = 0.500; correct 4, incorrect 4. False-sufficient 4/4 = 1.000 over insufficient + unverifiable: insufficient→sufficient 3; unverifiable→sufficient 1. Sufficient precision/recall 0.500/1.000; insufficient recall 0; unverifiable recall 0.

## 21. S1 Mechanical-gate Baseline

Accuracy 3/8 = 0.375; correct 3, incorrect 5. False-sufficient 2/4 = 0.500: insufficient→sufficient 2; unverifiable→sufficient 0. Sufficient precision/recall 0.500/0.500; insufficient recall 0; unverifiable precision/recall 0.250/1.000. S1 is diagnostic, not product policy.

## 22. Per-case Results

| Case | Gold | Track A gate | S0 | S1 | Track B gate |
|---|---|---|---|---|---|
| CASE_001 | sufficient | eligible | sufficient | sufficient | eligible |
| CASE_002 | sufficient | eligible | sufficient | sufficient | eligible |
| CASE_003 | sufficient | retrieval terminal | sufficient | unverifiable | candidate terminal |
| CASE_005 | sufficient | retrieval terminal | sufficient | unverifiable | eligible |
| CASE_012 | insufficient | eligible | sufficient | sufficient | n/a |
| CASE_013 | insufficient | eligible | sufficient | sufficient | n/a |
| CASE_015 | unverifiable | retrieval terminal | sufficient | unverifiable | n/a |
| CASE_017 | insufficient | retrieval terminal | sufficient | unverifiable | n/a |

## 23. False-sufficient Analysis

S1 removes the unverifiable false-sufficient error but cannot identify readable semantic insufficiency: CASE_012/013 remain false-sufficient. No keyword, title, Case-specific, query-specific, or semantic rule was added.

## 24. Partial Development Limitation

Partial Development calibration is unavailable. Partial has zero support; no credible four-class Macro-F1 is claimed or reported.

## 25. Failure Attribution

Upstream retrieval and candidate generation remain operational. Bundle coverage inadequacy is attributed upstream after prediction freeze. Selector/source/data-integrity mappings are unit-tested even though their final-run counts are zero. No operational failure is labeled semantic insufficiency.

## 26. Functional Examples

All eight required examples, including S0/S1 readable-insufficient behavior, are in `research/v3_5/stage4a/functional_examples.md`.

## 27. Trace

Twelve traces record query and set/Bundle identities, versions, resolution/failure state, policy/outcome/reason/action, semantic-judge flag, terminal ID, post-freeze Gold-open flag, and Eval-only adequacy. They contain no Held-out content, key, provider reasoning, or pre-prediction Gold fields.

## 28. Tests and Regression

Directed Stage 4A: 33 passed. Prescribed isolation-safe regression: 621 passed. Warnings: one Starlette and six multiprocessing deprecations; no failures.

## 29. Snapshot / V3 / Gold / Manifest Integrity

All authoritative hashes matched after implementation. Snapshot, Raw artifacts, Gold, Execution Manifest, Stage 3 assets, V3 retrieval, Builder behavior, and deterministic Selector behavior were unchanged.

## 30. Current State Update

`V3_5_CURRENT_STATE.md` now records closure, versions, Track A/B counts, S0/S1, adequacy, partial limitation, isolation, zero provider calls, Stage 4B not started, budget, and risks.

## 31. Known Limitations

The Development set is small and has no partial. Mechanical validity does not imply semantic sufficiency or Gold-group coverage. Track A loses two sufficient cases upstream. Track B is conditional. Three of seven eligible paths lack adequate Judge input.

## 32. Stage 4B Recommendation

1. Yes: the Gate deterministically separates operational unverifiability from semantic-judgment eligibility.
2. Yes: S1 false-sufficient occurs on two readable-insufficient cases.
3. Yes: Stage 4B is clearly necessary and must not be replaced by S1.
4. Judge-input adequate: Track A 3; Track B 1; combined diagnostic 4/7 eligible.
5. Yes, cautiously: 7–11 hours remain, leaving room for a bounded Stage 4B while preserving minimum closure/eval reserve.

## 33. Exact Commands

Preflight used the seven mandated Git commands. Hash checks used `shasum -a 256` on authorized assets. Development execution invoked `run_stage4a_development(...)` with the locked manifest, Development Gold, Artifact Manifest, and read-only Snapshot. Directed tests:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_v3_5_stage4a_gate.py tests/test_v3_5_stage4a_eval.py
```

Regression used the exact prescribed command with six `--ignore` paths. No network/provider command ran.

## 34. Stop Statement

Shiliu V3.5 Stage 4A is complete.

The Mechanical Sufficiency Gate deterministically separated reliable EvidenceBundle inputs from operationally unverifiable states. Retrieval, candidate-generation, selector, source-authority and data-integrity failures were preserved as unverifiable operational outcomes and were not misrepresented as semantic insufficiency. Valid deterministic EvidenceBundles were marked judge-eligible without assigning sufficient, partial or insufficient semantic status.

S0 and S1 Development baselines were evaluated only after predictions were frozen. No Gold field entered the runtime gate. No Provider, LLM, Semantic Sufficiency Judge, Formal Held-out Eval, API/UI, Agent, Memory, Harness, Translation Pipeline or V4 work was started.
