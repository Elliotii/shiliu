# V5-A Gate B Completion Validation — Prospective Amendment

Status: proposal_pending_main_authorization
Purpose: validate only the two Gate B product-completion findings left open by
the accepted historical evidence; this document does not authorize Provider or
credential access.

## Immutable history

All prior Gate B roots, manifests, responses, rubric results and failure/recovery
lineage remain immutable. In particular, the old G/H outcomes are not rewritten
as passing. Any authorized completion validation uses a new run ID, a new
isolated root and a new eval DB copied from a newly frozen read-only snapshot.

## Proposed exact cases

### GB-PC-G-01 — supported grounded product completion

```yaml
objective: 请基于收藏中的当前证据，说明长期研究中的 checkpoint 和 SideEffect receipt 分别解决什么问题。
constraint_profile: grounded_current_evidence
success_constraints: []
expected_product_boundary:
  - current EvidenceUse and citation are present
  - deterministic Outer Gate records accept only if the grounded profile passes
  - terminal valid_success or honest valid_partial is allowed
forbidden:
  - case ID or exact-text branching
  - Provider/candidate/confidence granting evaluator authority
```

### GB-PC-H-01 — one current clarification, then supported continuation

```yaml
objective: 可靠性和迭代速度哪个优先？若目标不清楚请先询问用户。
constraint_profile: grounded_current_evidence
success_constraints:
  - 继续前需要用户明确选择优先级
fixed_human_response:
  objective: 请按可靠性优先，说明 checkpoint 与 SideEffect receipt 如何避免重复外部动作。
  success_constraints: []
expected_product_boundary:
  - exactly one current InputRequest and one exact-once HumanDecision
  - child Goal/Attempt retains source checkpoint and parent Attempt lineage
  - no substantively identical second InputRequest
  - continuation ends in terminal grounded success/partial or an honest non-running bounded result
```

The strings above and their canonical hashes must be frozen in the manifest
before any credential access. Prompt, Tool/response schema, model, retrieval
algorithm and deterministic evaluator code remain identical to the reviewed
implementation tree. Neither case may be tuned after observing output.

## Proposed Provider and run-wide envelope

```yaml
provider: deepseek_openai_compatible
base_url: https://api.deepseek.com/v1
model: deepseek-v4-pro
roles:
  query_analysis: {thinking_enabled: false, reasoning_effort: null, max_output_tokens: 1200}
  agent_action: {thinking_enabled: false, reasoning_effort: null, max_output_tokens: 1200}
  grounded_answer: {thinking_enabled: true, reasoning_effort: high, max_output_tokens: 4096}
authorized_cases_if_approved: [GB-PC-G-01, GB-PC-H-01]
max_logical_calls_total: 10
max_http_attempts_total: 20
max_input_tokens_total: 80000
max_output_tokens_total: 17792
max_wall_time_seconds_total: 1320
nominal_cost_usd: 0.05
reserve_stop_usd: 0.20
absolute_max_cost_usd_total: 0.25
credential_access: one_existing_keychain_reference_after_entry_gate_only
live_database_runtime_state: forbidden
live_database_migration: forbidden
opportunistic_rerun: forbidden
```

The official price table must be refreshed and frozen immediately before the
Entry Gate. If conservative worst-case reservation can exceed US$0.25, the run
stops with zero Provider calls pending a new decision.

## Mechanical Entry Gate and stop rules

Before credential access: clean accepted commit; 180+ joint tests; default no-
Provider regression; frozen five Prompt/Tool/Schema blob hashes; exact case
hashes; read-only source and isolated writable eval copy; schema/integrity/corpus/
artifact/index identities; run-wide receipt/cost meter; and zero unknown/in-flight
SideEffects. Failure leaves Provider calls and credential access at zero.

After dispatch, any unknown/unreconciled SideEffect, incomplete Provider identity
or receipt, hard-budget reservation failure, snapshot/material baseline change,
or need to alter Prompt/model/case/evaluator stops the run without automatic
replay. Each case is executed at most once unless a later written recovery
decision establishes that no Provider operation was submitted.

```yaml
provider_run_authorized_by_this_amendment: false
credential_access_authorized_by_this_amendment: false
gate_C_authorized: false
next_action: V5_main_session_review_and_optional_exact_run_authorization
```
