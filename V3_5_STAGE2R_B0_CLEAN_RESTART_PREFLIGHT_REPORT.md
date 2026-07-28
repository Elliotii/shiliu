# Shiliu V3.5 Stage 2R-B0 Clean Restart Preflight Report

Date: 2026-07-23 (Asia/Shanghai)  
Branch: `codex/v3-domain-completion`  
HEAD before run: `8287c8d92378b87290274d02605cdc704cb8c470`  
Final status: **Stage 2R-B0 Clean Restart Blocked — Formal Pilot Not Started**

## Executive result

B0 did not pass. The fresh Codex-side Primary reviewer produced an invalid initial review and remained invalid after its one permitted repair. The repaired evidence group referenced `condition_alpha` and `condition_beta`, while its declared aspects were `A1` and `A2`; deterministic validation therefore returned `illegal_group_reference:G1`. No further repair or resampling was performed.

The strict isolation audit also found that the profile actually used for the model calls denied the repository parent, Shiliu Raw Source root, Shiliu application-state root, and Codex attachments, but did not prove a universal deny for every non-workspace path. Under the prompt's fail-closed capability requirement, that is an additional B0 blocker. A subsequent deny-by-default profile remained unable to start the Codex binary (`status 134`) and was not used for another model call.

Because the Primary result was terminally invalid, the DeepSeek Secondary model was not invoked, Agreement was not run, candidate mining did not begin, and no formal Pilot Case or Gold asset was created.

## Safe input and frozen assets

- Only `research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.jsonl` and its manifest were used as Query candidate inputs.
- Projection SHA-256: `2c2fd3e0d06452201119f22ab3b68dcdfc738f91d19a916e50dbb9fd2051b564`; it matches both the prompt and manifest.
- Four JSONL records parsed successfully; Candidate IDs were unique; every Query was non-empty; every `pilot_candidate_allowed` value was `true`.
- Every record contained exactly the seven approved fields. Forbidden-key count was zero.
- The Stage 2R-A manifest's 15 frozen files all matched their declared SHA-256 values.
- The raw assignment files were not opened, searched, parsed, or hashed. The ordinary guard's fail-closed behavior was exercised only with a non-existent synthetic matching path in tests.
- `heldout_accessed: false`
- `forbidden_access_attempts: 0` (operational run; synthetic negative-test probes did not open a file)
- `raw_assignment_accessed: false`
- `eval_v1_modified: false`

Audit: `research/v3_5/eval_v2/stage2r_b_clean_restart/preflight/audits/safe_projection.audit.json`.

## Provider preflight

- Existing keychain-backed provider configuration loaded successfully without printing or persisting the key.
- Configured annotation model: `deepseek-v4-pro`.
- Request builder model: `deepseek-v4-pro`.
- Thinking request: `{"type":"enabled"}`.
- Reasoning strength request: `max`.
- `provider_usage: annotation_secondary_review`.
- Authorization is absent from the persisted request body and audit.
- Request model was confirmed locally. No response model or reasoning echo exists because the Secondary call was not made after the terminal Primary failure.
- There was no silent downgrade, Mock Provider call, browser invocation, or reuse of a Stage 3/4 provider role.

Audit: `research/v3_5/eval_v2/stage2r_b_clean_restart/preflight/secondary_request/provider_request.audit.json`.

## Primary invocation and workspace audit

Primary mechanism: fresh ephemeral `codex exec` process, requested model `gpt-5.4`, one logical invocation. The provider response did not independently echo a model field; the configured invocation model is recorded as the actual requested model.

Workspace used:

`/tmp/shiliu-v3-5-review/stage2r-b-clean-20260723T001500Z/B0_PREFLIGHT_FIXTURE_CALL1`

Closed inventory:

- `annotation_protocol_excerpt.md`
- `primary_reviewer.v2.md`
- `annotation_review.v2.schema.json`
- `current_case.packet.json`
- `output/`
- `workspace_manifest.json`

The workspace is outside the repository. It contains no `.git`, `.env`, repository copy, Safe Projection, mining note, Secondary output, Agreement, adjudication, Gold, split assignment, or system prediction. Repository-parent, Shiliu Raw Source, Shiliu application-state, and attachment-root reads were denied during the model calls. Universal non-workspace read denial was not proven, so strict capability isolation is recorded as failed rather than inferred.

Audit: `research/v3_5/eval_v2/stage2r_b_clean_restart/preflight/audits/workspace_inventory.audit.json`.

## Fixture and transcript integrity

The packet was explicitly classified `non_formal_preflight_fixture`, `not_master_case`, and `not_gold`. It was not taken from the Safe Projection or any held-out source.

- Case: `V2C_FIXTURE01`
- Packet hash: `70ad5947169ed782b133c5627a41d59f6aa62d9fbbdc73f6432300954be237c3`
- Segments: 3
- First/last: `seg_1` / `seg_3`
- Source artifact/version/run: `artifact_fixture` / `version_fixture` / `run_1`
- Language/type: `en` / `raw_subtitle`
- Request truncation: false
- Response truncation: false

The repaired Primary declared full-transcript review and the correct first/last segment IDs. Its spans used real segments with correct reconstructed times and source identity. It nevertheless failed the Evidence Group reference invariant. The Secondary packet hash comparison was not reached.

Audit: `research/v3_5/eval_v2/stage2r_b_clean_restart/preflight/audits/full_transcript.audit.json`.

## Validation, repair, usage, and cost

Primary initial validation failed with:

- `full_transcript_not_reviewed`
- `transcript_boundary_mismatch`
- `illegal_aspect_reference`

The one allowed repair received only the original Packet, the Primary's own raw output, the output schema, and those errors. It then failed with `illegal_group_reference:G1`. Final Primary review status is `invalid_after_repair`; no second repair was attempted.

- Logical reviewer invocations: 1
- Raw model calls: 2
- Primary total latency: 94,163 ms
- Input tokens: 22,818
- Output tokens: 964
- Cached input tokens reported: 1,920
- DeepSeek calls/tokens: 0 / 0
- Estimated cost: unavailable; no price was inferred or fabricated

Usage: `research/v3_5/eval_v2/stage2r_b_clean_restart/preflight/usage/preflight_usage.json`.

## Secret and repository integrity

No API key, Authorization header, `.env`, or authenticated exception was copied into the repository or reviewer workspace. A pattern scan of persisted B0 artifacts passed. The existing dirty worktree was preserved; no cleanup, reset, checkout, or destructive Git command was run. Eval v1 was not modified.

Integrity audit: `research/v3_5/eval_v2/stage2r_b_clean_restart/preflight/audits/run_identity_and_integrity.audit.json`.

## Tests

The directed B0 clean-restart tests, Stage 2R-A regression, Safe Projection guard regression, provider configuration/safety tests, workspace allowlist tests, packet/hash/full-transcript tests, one-repair tests, Agreement tests, adjudication tests, and no-Gold/no-third-case assertions passed:

`23 passed`

Command:

```text
.venv/bin/pytest -q tests/test_v3_5_eval_v2_stage2r_b_clean_restart.py tests/test_v3_5_eval_v2_safe_projection.py tests/test_v3_5_eval_v2_stage2r_a.py
```

No claim is made that the full repository regression passed.

## B0 questions answered

1. Only Safe Projection used: yes.
2. Safe Projection hash verified: yes.
3. Raw Assignment accessed: no.
4. Held-out accessed: no.
5. Repository-external Primary workspace created: yes.
6. Workspace files: the six allowlisted entries listed above.
7. Primary model recording: requested invocation model `gpt-5.4`; response echo unavailable.
8. Existing DeepSeek Provider loaded: configuration and keychain credential loaded; model invocation not reached.
9. DeepSeek V4 Pro request confirmed: yes, locally in the request builder.
10. Max request confirmed: yes, locally in the request builder.
11. Provider response echo: unavailable because no Secondary call was made.
12. `annotation_secondary_review` used: yes in the isolated request configuration; no model call.
13. Packet hash identical across reviewers: not reached.
14. Full transcript preserved: yes in the Packet and Primary repair input.
15. First/last segment consistent: yes in the repaired Primary, but overall review invalid.
16. Repair occurred: yes, one Primary repair.
17. Invalid-after-repair: yes, Primary.
18. Usage/latency/cost persisted: yes; cost explicitly unavailable.
19. Secret safety: passed.
20. Eval v1 unchanged: yes.
21. B0 passed: no.
22. Minimal blocking cause: the Primary remained schema/semantic-invalid after its single allowed repair; strict universal workspace-only read isolation was also not proven.

## Stop decision

```text
Stage 2R-B0 Clean Restart Blocked
Formal Pilot Not Started
```

No B1 report is generated because B1 did not start. No third model, third Case, Agreement, human Gold decision, Gold lock, B2, Stage 2R-C, Stage 3R, Stage 4, Stage 5, Stage 6, or V4 work was performed.
