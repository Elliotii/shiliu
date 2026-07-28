# Shiliu V3.5 Stage 2R-B Recovery B Report

Date: 2026-07-23 (Asia/Shanghai)  
Final status: **Stage 2R-B Recovery B Blocked — Reviewer Preflight Not Reliable**

## Executive result

The Reviewer Draft Schema, deterministic Compiler, practical project-sensitive isolation profile, independent-path orchestration, and directed tests were implemented. The Canonical Annotation Review v2 contract remains unchanged. The directed Recovery B suite passes (`13 passed`), and a repository-external allowlisted Workspace passed real sandbox read-denial probes for the project tree, Raw Source root, Shiliu application state, Codex attachments, and known credential locations.

B0 is nevertheless blocked. Before any model invocation, the first test command accidentally included the legacy `test_v3_5_eval_v2_stage2r_b_clean_restart.py`. That legacy test's Safe Projection integrity case opened the Safe Projection file and its manifest. The data was not copied into the reviewer Workspace, no Reviewer was invoked, and no Held-out/Gold/Review/Adjudication asset was opened. However, Recovery B explicitly forbids reading the Safe Projection Query during this round. Model calls were therefore stopped rather than spending the permitted call budget on a run that could not satisfy the session boundary.

Consequently, neither the Primary nor DeepSeek live Reviewer path was executed, and this report does not claim a passed preflight or readiness for B1.

## Draft Schema and deterministic compilation

The model-facing `ReviewerDraft` contains natural-language aspect text plus zero-based array indices. It contains no `aspect_id`, `span_id`, or `group_id` fields. Required spans refer to Packet segment IDs and aspect indices; evidence groups refer to aspect and required-span indices. Validation rejects out-of-range indices, unknown Segment IDs, duplicate local references, empty group span lists, unsupported aspect mappings, and status/partition inconsistencies.

The deterministic Compiler assigns identities strictly by array order:

- aspects: `A1`, `A2`, ...;
- required spans followed by optional spans: `S1`, `S2`, ...;
- evidence groups: `G1`, `G2`, ....

For every span, local code reconstructs video/source identity, source version, timeline run, language/type, start/end time, and segment membership from the Packet. It rejects cross-run, source/version, language/type, or video inconsistency. The Compiler also binds first/last Segment IDs and the full-transcript marker locally. Fixed Draft + Packet + compilation context produces byte-identical canonical JSON and an identical SHA-256; this is covered by tests.

The existing `v3.5-annotation-review-v2` Pydantic models and JSON Schema were not replaced or modified. The added Draft Schema is an input contract for model output; compilation still yields the original Canonical Annotation Review v2.

## Reviewer and provider result

Primary requested model configuration remains `gpt-5.4`; it is not described as GPT-5.6. No Primary request was sent, so initial legality, Repair legality, Canonical compilation, tokens, and latency are all `not_reached`.

The Secondary request builder was verified locally with:

- model: `deepseek-v4-pro`;
- reasoning strength: `max`;
- thinking: enabled;
- `provider_usage: annotation_secondary_review`;
- no persisted Authorization value.

No DeepSeek request was sent, so actual V4 Pro Max success, response model echo, initial legality, Repair legality, Canonical compilation, tokens, and latency are all `not_reached`. The independent runner is tested to continue the other Reviewer after one path reaches `invalid_after_repair`, and to permit at most one Repair per path, but that is test evidence rather than a live provider result.

Usage totals are therefore zero model calls, zero tokens, zero model latency, zero Repairs, and USD 0 cost.

## Packet and transcript integrity

Only the prior non-formal three-segment fixture was exported to the external Reviewer Workspace:

- case: `V2C_FIXTURE01`;
- Packet input hash: `70ad5947169ed782b133c5627a41d59f6aa62d9fbbdc73f6432300954be237c3`;
- segments: 3;
- first/last: `seg_1` / `seg_3`;
- source artifact/version/run: `artifact_fixture` / `version_fixture` / `run_1`.

The exported Packet preserves all three segments and both transcript boundaries. Cross-reviewer Packet-hash equality was not reached because neither request was sent.

## Isolation and secret audit

The external Primary Workspace contained exactly:

- `annotation_protocol_excerpt.md`;
- `current_case.packet.json`;
- `output/`;
- `primary_reviewer.draft.v1.md`;
- `reviewer_draft.v1.schema.json`;
- `workspace_manifest.json`.

It contained no repository copy or secret file. The generated macOS sandbox profile passed read-denial probes for the project parent, Raw Source root, Shiliu application-state root, Codex attachments, Codex auth files, `.ssh`, and known cloud credential locations. The audit reports the required distinction exactly:

```text
project_sensitive_isolation: required
universal_filesystem_isolation: best_effort_not_proven
```

No container platform or general-purpose sandbox was built. The scoped persisted-artifact secret scan found no API key, bearer token, or Authorization value.

## Boundary and frozen-asset audit

- Held-out accessed: false.
- Gold accessed: false.
- Review/Adjudication assets accessed: false.
- `eval_queries.candidate.jsonl` accessed: false.
- `eval_queries.locked.jsonl` accessed: false.
- Safe Projection exposed to a Reviewer: false.
- Safe Projection read by the session: **true, accidentally through the legacy regression test**, which blocks B0.
- Eval v1 modified by this session: false.
- Frozen V3 modified by this session: false.
- Canonical Annotation Review v2 Schema modified: false; observed SHA-256 `bd7506c823ed06ddf024a4ed0aa143e4fc671df3689af80ca32ffef8418be24b`.
- The pre-existing dirty worktree was preserved; no cleanup, reset, checkout, or destructive Git action was used.

## Required questions

1. **How does the Draft Schema reduce model ID management?** It removes all formal A/S/G fields and permits only array indices plus Packet Segment IDs.
2. **How does the Compiler generate A/S/G IDs?** Deterministically from aspect, span, and group array order; it converts every index to the corresponding canonical reference.
3. **Is the original Canonical Schema unchanged?** Yes.
4. **Was the Primary initial output or Repair valid?** Not reached; no call was sent.
5. **Was the DeepSeek initial output or Repair valid?** Not reached; no call was sent.
6. **Did both sides compile successfully?** No live result. Deterministic compilation passes directed unit tests only.
7. **Did DeepSeek V4 Pro Max actually succeed?** No. The exact request was built and audited locally but deliberately not sent.
8. **Were both Packet hashes identical?** Not reached. The single fixture exported for the intended paths has the recorded Packet hash above.
9. **Was the complete transcript preserved?** Yes in the fixture and external Workspace; no live response exists.
10. **Did project-sensitive isolation pass?** Yes, for the generated Workspace/profile and real read probes.
11. **Is Universal Isolation only Best Effort?** Yes: `best_effort_not_proven`.
12. **Token, latency, Repair, and cost?** 0 tokens, 0 model latency, 0 Repairs, 0 raw calls, USD 0.
13. **Was Held-out accessed?** No.
14. **Were Eval v1 or Frozen V3 modified?** No changes by this session.
15. **Ready to re-enter two formal B1 Pilot Cases?** No. A new clean session must rerun B0 using only the synthetic fixture and obtain successful compilation from both live Reviewer paths.

## Verification

Directed command:

```text
.venv/bin/pytest -q tests/test_v3_5_eval_v2_reviewer_draft.py tests/test_v3_5_eval_v2_review_compiler.py tests/test_v3_5_eval_v2_recovery_b.py
```

Result: `13 passed`.

## Stop decision

```text
Stage 2R-B Recovery B Blocked
Reviewer Preflight Not Reliable
```

No Pilot was selected, no formal Case was reviewed, no Agreement or Gold was produced, and B1/B2/2R-C/Stage 3R/4A-R/4B/V4 was not started.
