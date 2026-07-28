# V3.5 Stage 2R-B0 Reviewer Preflight Report

Final status: **Stage 2R-B0 Blocked — Formal Pilot Not Started**

Date: 2026-07-22 (Asia/Shanghai)  
Repository: `/Users/elliot/new-systems/agent-job-prep/Shiliu`  
Branch: `codex/v3-domain-completion`  
Intake HEAD: `8287c8d92378b87290274d02605cdc704cb8c470`

## Executive result

Stage 2R-B0 did not pass. During read-only candidate-source discovery, the executor opened `research/v3_eval/eval_queries.candidate.jsonl`. That asset contains `held_out: true` assignments and therefore exposes protected Held-out Query identity. This violates the B0 no-Held-out-access gate even though no Held-out Gold, transcript, review packet, evidence span, or human ledger was opened and no Eval v1 file was modified.

The stop rule was applied immediately after discovery: no Codex Reviewer invocation was started, no DeepSeek request was sent, no formal Pilot Case was created, and Stage 2R-B1 was not entered. The guard was strengthened so future Stage 2R work rejects both `eval_queries.candidate.jsonl` and `eval_queries.locked.jsonl` before opening them.

## Intake and frozen-asset verification

- Intake HEAD and branch matched the requested state.
- The worktree was already dirty before this stage. Its initial `git status` and a non-Held-out file inventory were recorded before any stage edit; unrelated existing changes were preserved.
- `V3_5_STAGE2R_A_SCHEMA_AND_PROTOCOL_LOCK_REPORT.md` and `research/v3_5/eval_v2/stage2r_a/manifests/stage2r_a_manifest.json` were checked.
- Every one of the 15 files listed by the Stage 2R-A manifest existed and matched its recorded SHA-256.
- Frozen identities remained unchanged: Master Case v2, Annotation Packet v2, Annotation Review v2, Annotation Agreement v2, Annotation Protocol v2, Primary Prompt v2, Secondary Prompt v2, Leakage Policy v2, and Pilot Selection Policy v2.
- No protocol semantics, four-state definitions, Agreement thresholds, Mandatory Human Review rules, Leakage Policy, or Pilot Selection Policy were changed.

## Required B0 answers

1. Isolated Codex Reviewer successfully called: **no; not attempted after the gate violation**.
2. Actual Primary model: **not applicable; no invocation**.
3. Primary Workspace inventory: **not created**.
4. Existing DeepSeek Provider loaded: **configuration/key presence was verified locally before the violation; no request was sent**.
5. DeepSeek V4 Pro confirmed: local public configuration reported `deepseek-v4-pro`; Provider response confirmation was **not obtained**.
6. Thinking Strength Max confirmed: **no**. The ordinary video pipeline publicly reports `high`; an annotation-specific Max request was not sent before the stop.
7. `annotation_secondary_review` used: request builder is frozen to that usage, but **no real invocation occurred**.
8. Identical Reviewer Packet Hash: **not applicable**.
9. Full Transcript complete: **not exercised by a real Reviewer**.
10. First/Last Segment consistent: **not exercised by a real Reviewer**.
11. Repair occurred: **no**.
12. Invalid-after-repair: **no real review**.
13. Usage/latency/cost persisted: **no model usage; zero calls and USD 0 incurred**.
14. Secret safety: **passed for observed output**. Key presence was recorded only as a Boolean; no key or Authorization value was printed or written.
15. Held-out accessed: **true**. One protected query-assignment asset was opened during candidate-source discovery. A later read of the broad Current State document also encountered historical text that indirectly mentions Held-out label facts. No underlying Held-out Gold or transcript was opened.
16. Eval v1 modified: **false**.
17. B0 Gate passed: **no**.
18. Blocker: **Held-out isolation breach during discovery; the candidate query asset was not covered by the filename-based Protected Path Guard**.

## Invocation and cost summary

| Reviewer | Logical invocations | Raw model calls | Tokens | Estimated cost |
|---|---:|---:|---:|---:|
| Codex-side Primary | 0 | 0 | 0 | USD 0 |
| DeepSeek Secondary | 0 | 0 | 0 | USD 0 |
| Total | 0 | 0 | 0 | USD 0 |

## Isolation and secret audit

```text
heldout_accessed: true
forbidden_access_attempts: 2
eval_v1_modified: false
provider_configured: true
secret_redaction_passed: true
primary_workspace_created: false
formal_pilot_cases_created: 0
stage2r_b1_started: false
```

`forbidden_access_attempts` counts two files encountered in this run that exposed protected information: the candidate query assignment asset and the broad Current State document containing historical Held-out label facts. It does not count individual records within either file.

## Engineering correction and verification

The Protected Path Guard now fails closed on:

- `research/v3_eval/eval_queries.candidate.jsonl`
- `research/v3_eval/eval_queries.locked.jsonl`

The directed guard regression was extended to prove both paths are rejected without opening. No attempt was made to sanitize or derive a replacement projection in this blocked run because that would require an independently authorized, Gold-blind source process.

Verification result: **10 passed** (`tests/test_v3_5_eval_v2_stage2r_a.py` plus the existing DeepSeek thinking-control safety test), with one pre-existing Starlette/httpx deprecation warning. No full-repository regression was claimed. A secret-pattern scan of the changed guard and this report passed. The test module contains a pre-existing dummy literal used to verify redaction; it is not a real credential and was not introduced by this run.

## Change inventory for this blocked run

- `src/shiliu/eval_v3_5/eval_v2/isolation.py` — engineering-only guard correction.
- `tests/test_v3_5_eval_v2_stage2r_a.py` — regression for the newly protected paths.
- `V3_5_STAGE2R_B0_REVIEWER_PREFLIGHT_REPORT.md` — this report.

No B1 report or human adjudication packet exists because the formal Pilot did not start.

## Required stop state

```text
Stage 2R-B0 Blocked
Formal Pilot Not Started
```

Do not proceed to Stage 2R-B1 or B2 from this run. A future clean session needs a pre-approved, separately generated non-Held-out candidate projection that contains no Held-out membership or label information, and must restart B0 from the beginning.
