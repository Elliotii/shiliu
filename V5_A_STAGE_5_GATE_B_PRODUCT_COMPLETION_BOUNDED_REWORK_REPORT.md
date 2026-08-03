# V5-A Gate B Product-completion Bounded Rework Report

Date: 2026-08-04
Authority: V5 Main Session bounded rework delegation
Status: submitted_for_main_review; not self-accepted

## Outcome

The default `Application` / `ResearchProductService` composition now has one
server-owned product success profile, `grounded_current_evidence` v1. The profile
allows an arbitrarily worded objective to pass the deterministic Outer Gate only
when the committed provisional artifact has an admissible answer status and at
least one current `EvidenceUse` / citation. The binding is persisted inside the
kernel-created `task_created` Event through a private service parameter; public
`evidence_policy`, Provider output, candidate status and confidence cannot create
the binding. A raw API caller that copies the profile name still reaches
`unknown / needs_user`.

The profile applies only when the active Goal has no additional free-text success
constraints. Adding such constraints keeps the task in strict semantic mode:
each required constraint still needs an exact server-registered evaluator and is
never silently made optional. The product create form and task projection expose
this distinction.

For the repeated-question defect, a resolved clarification for the
`authorized_evaluator_required` capability gap is consumed once. If a later Goal
hits the same capability blocker, the product runner commits a fenced
`duplicate_input_request_suppressed` Event and CommandReceipt, moves the current
Attempt/Task to `blocked`, and creates no second InputRequest. A genuinely
different blocker remains eligible for its own input lifecycle.

## Evidence

- Default composition, arbitrary objective, supported profile: terminal grounded
  result with current citations and `server_product_profile` ConstraintSpec.
- Forged raw `evidence_policy`: objective remains `natural_language`, audit is
  `unknown`, and no `satisfied` authority is granted.
- Strict free-text constraint: visible as requiring a supported rewrite or exact
  registered evaluator.
- HumanDecision exact-once: clearing the semantic constraint activates the
  already server-bound profile on the child Goal and reaches a grounded terminal
  boundary with exactly one InputRequest and one HumanDecision.
- Unresolved repeat of the same evaluator capability gap: one historical input,
  no new open input, durable blocked boundary, restart and command replay stable.
- Existing receipt/cost/unknown dispatch, owner/control fence and Provider product
  orchestration tests remain in the joint suite.

Validation at the implementation boundary:

```yaml
stage_5_product_completion_targeted: 13_passed
stage_1_to_5_joint_targeted: 180_passed
default_no_provider_regression: 1678_passed_4_deselected
warning: existing_Starlette_httpx_deprecation_only
compileall: pass
javascript_syntax: pass
diff_check: pass
provider_calls_performed: false
credential_or_keychain_accessed: false
live_database_migration_performed: false
```

Stable-window live DB read-only evidence:

```yaml
schema: 9
integrity_check: ok
videos: 157
completed: 140
sha256: f0f23d87395b652b5486f32f5dd108d2b32b4991fd2faf954c5db67c91402a32
size_bytes: 94588928
mtime: 2026-08-04T02:55:56+0800
changed_during_validation_window: false
```

## Boundaries and unproven items

No Prompt, Provider model, Tool/response schema, retrieval algorithm or evaluator
authority was relaxed. No Provider or credential access occurred. No live schema
migration, Gate C work, merge, push or tag occurred. The profile deliberately
does not prove arbitrary semantic claims; unsupported constraints remain
fail-closed. Real Provider completion under the repaired product policy is still
`not_exercised` and is covered only by the prospective amendment submitted with
this report.

```yaml
bounded_rework_status: submitted_for_main_review
gate_B_self_accepted: false
gate_C_authorized: false
next_action: V5_main_session_bounded_product_completion_review
```
