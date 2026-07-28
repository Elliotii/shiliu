# Shiliu V3.5 Stage 2R-B0 Clean Restart Preflight Report

## Executive Result

```text
Stage 2R-B0 Blocked
Not Ready for B1 Pilot
```

No live model request was sent. No formal Pilot Case was selected or opened.

## Boundary Audit

- Session boundary: **failed under the literal B0 rule**. The user supplied the controlling restart prompt as a Codex attachment and explicitly instructed Codex to read it. That bootstrap instruction file was opened before the embedded prohibition on reading Codex attachments could be known. It was not copied into a Reviewer workspace or sent to a model, but this session cannot truthfully claim that no Codex attachment was read.
- Forbidden project-data contents: no Safe Projection Query, Safe Projection Manifest, Eval Gold, Held-out Gold, Development Gold, historical Reviewer Output, historical Agreement Result, historical Adjudication Asset, formal Review Packet, formal Master Case, or formal Query content was opened.
- Git state inspection enumerated worktree paths only; no listed report, Safe Projection, Gold, Review, Adjudication, or formal Case file content was opened.
- Legacy test: not collected.
- Safe Projection test: not collected.
- Formal Case test: not collected.
- Gold / Held-out / Review / Adjudication: no content read.

Because the attachment boundary failed, the mandatory fail-closed action was taken: stop before test execution, synthetic packet export, workspace export, or model invocation.

## Exact Test Collection

Working directory:

```text
/Users/elliot/new-systems/agent-job-prep/Shiliu
```

Command:

```bash
.venv/bin/pytest --collect-only -q \
  tests/test_v3_5_eval_v2_reviewer_draft.py \
  tests/test_v3_5_eval_v2_review_compiler.py \
  tests/test_v3_5_eval_v2_recovery_b.py
```

Collection result: 13 items from the three explicit allowlisted files only.

Full collected node list, obtained with `--collect-only -vv` against the same three explicit files:

```text
tests/test_v3_5_eval_v2_reviewer_draft.py::test_model_facing_draft_is_index_only
tests/test_v3_5_eval_v2_reviewer_draft.py::test_out_of_range_indices_are_rejected
tests/test_v3_5_eval_v2_reviewer_draft.py::test_unknown_packet_segment_is_rejected
tests/test_v3_5_eval_v2_reviewer_draft.py::test_status_and_aspect_partition_must_agree
tests/test_v3_5_eval_v2_reviewer_draft.py::test_group_without_required_span_is_rejected
tests/test_v3_5_eval_v2_review_compiler.py::test_compiler_generates_local_ids_groups_and_packet_identity
tests/test_v3_5_eval_v2_review_compiler.py::test_repeated_compilation_is_byte_and_hash_identical
tests/test_v3_5_eval_v2_review_compiler.py::test_compiler_rejects_cross_run_or_source_version_mismatch[timeline_run_id-run_2-cross_timeline_run]
tests/test_v3_5_eval_v2_review_compiler.py::test_compiler_rejects_cross_run_or_source_version_mismatch[source_version-version_other-source_or_version_mismatch]
tests/test_v3_5_eval_v2_recovery_b.py::test_primary_workspace_allowlist_and_project_sensitive_denial
tests/test_v3_5_eval_v2_recovery_b.py::test_deepseek_v4_pro_max_annotation_request
tests/test_v3_5_eval_v2_recovery_b.py::test_one_repair_and_independent_secondary_completion
tests/test_v3_5_eval_v2_recovery_b.py::test_valid_after_exactly_one_repair
```

The directed tests were **not executed** because the mechanical gates did not all pass.

```text
passed: not run
failed: not run
skipped: not run
warnings: not run
```

HEAD:

```text
8287c8d92378b87290274d02605cdc704cb8c470
```

Dirty worktree: yes; substantial pre-existing modified and untracked files were present. They were not altered by this B0 attempt.

## Engineering Assets

- Reviewer Draft Schema implementation: present and imported by allowlisted tests.
- Deterministic Review Compiler: present and imported by allowlisted tests.
- Canonical Annotation Review v2 contract: present; no schema modification was made.
- Canonical Schema SHA-256: not computed after the boundary failure.
- Outer Guard: **failed**. The existing project-sensitive macOS profile and denial probes cover the external Reviewer workspace path. No dedicated fail-closed outer B0 Runner or guarded pytest process was found, so Reviewer-workspace isolation cannot be promoted to outer-runner isolation.
- Governance repair: not attempted after the literal attachment boundary failure.
- Modified implementation files: none.

## Frozen Registry Audit

The model gate also cannot pass with the current implementation:

- Secondary request construction freezes `deepseek-v4-pro`, reasoning effort `max`, thinking enabled, and usage `annotation_secondary_review`.
- Primary runtime contains model constant `gpt-5.4`, but no formal `annotation_primary_review` Registry entry was found.
- Primary reasoning configuration and temperature are not frozen in the inspected runtime.
- Repair prompt versions are not represented as formal Registry values.
- The maximum-repair behavior is enforced in the runtime as at most one repair, but it is not exposed as a complete frozen Registry record.

Environment or provider defaults were not used as substitutes.

## Primary Result

```text
requested_model: not sent
response_model_echo: not available
initial_validity: not run
repair_attempted: false
canonical_compilation: not run
canonical_sha256: not available
tokens: not available
provider_latency: not available
end_to_end_latency: not available
cost: not available
```

## Secondary Result

```text
requested_model: not sent
response_model_echo: not available
initial_validity: not run
repair_attempted: false
canonical_compilation: not run
canonical_sha256: not available
tokens: not available
provider_latency: not available
end_to_end_latency: not available
cost: not available
```

Primary failure did not suppress Secondary execution; both were suppressed by the shared mechanical boundary gates before either path began.

## Packet Integrity

The synthetic fixture was not opened or exported after the boundary failure.

```text
primary_packet_sha256: not computed
secondary_packet_sha256: not computed
packet_hash_equality: not established
segment_count: not read
first_segment_id: not read
last_segment_id: not read
source_artifact: not read
source_version: not read
timeline_run: not read
full_transcript_marker: not read
```

## Isolation and Secret Audit

- Reviewer workspace inventory: no B0 Reviewer workspace was created.
- Outer-runner denial probes: not established; existing implementation is Reviewer-workspace scoped.
- Request artifact secret scan: no request artifact was created.
- Authorization persistence: no provider request was made and no Authorization value was persisted by this attempt.
- Repository access by Reviewer: no Reviewer process ran.
- Raw Source access by Reviewer: no Reviewer process ran.
- Application-state access by Reviewer: no Reviewer process ran.
- Codex attachment access: the bootstrap task instruction attachment was read by the controlling session; no Reviewer ran.
- Project-sensitive isolation: **fail / not established for the required outer-runner scope**.
- Universal filesystem isolation: `best_effort_not_proven`.

## Agreement Readiness

No Agreement Checker was opened or run after the gate failure. Cross-reviewer semantic matching independent of local A/S/G array-order IDs was therefore not verified in this clean session. This remains a B1-precondition blocker.

## Final Decision

```text
Stage 2R-B0 Blocked
Not Ready for B1 Pilot
```

Blocking conditions:

1. Literal Codex-attachment boundary cannot be satisfied in this session because the controlling prompt itself was read from an attachment.
2. The outer B0 Runner / pytest process lacks a proven fail-closed forbidden-path guard.
3. The formal frozen Reviewer Registry is incomplete for the Primary path.
4. Packet identity, two live calls, canonical compilation, post-call isolation, secret audit, and Agreement readiness were consequently not established.

No B1, B2, Stage 2R-C, Stage 3R, Stage 4, Stage 5, Stage 6, or V4 work was started.
