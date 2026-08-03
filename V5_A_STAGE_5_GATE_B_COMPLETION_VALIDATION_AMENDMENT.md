# V5-A Gate B Completion Validation — Prospective Amendment

Status: accepted_and_execution_authorized_with_exact_case_correction
Purpose: validate only the two Gate B product-completion findings left open by
the accepted historical evidence within the exact Provider, credential and
budget envelope authorized by V5 Main Session on 2026-08-04.

## Immutable history

All prior Gate B roots, manifests, responses, rubric results and failure/recovery
lineage remain immutable. In particular, the old G/H outcomes are not rewritten
as passing. Any authorized completion validation uses a new run ID, a new
isolated root and a new eval DB copied from a newly frozen read-only snapshot.

## Proposed exact cases

### GB-PC-G-01 — supported grounded product completion

```yaml
objective: 基于当前收藏中的字幕证据，说明 Agent 开发流程中的 checkpoint 为什么需要在 test 完成后停下来接受人工验收；请引用来源，并区分视频作者的陈述与基于证据的系统推论。
constraint_profile: grounded_current_evidence
success_constraints: []
expected_product_boundary:
  - at least one current EvidenceUse and citation
  - server_product_profile deterministic Outer Gate only
  - terminal valid_success or honest valid_partial
forbidden:
  - case ID or exact-text branching
  - Provider/candidate/confidence granting evaluator authority
```

### GB-PC-H-01 — one current clarification, then supported continuation

```yaml
objective: 基于当前收藏说明 Agent 开发流程应该优先追求快速迭代还是可靠验收；如果无法确定“优先”的含义，请先询问用户。
constraint_profile: grounded_current_evidence
success_constraints:
  - 继续前需要用户明确选择优先级
fixed_human_response:
  objective: 可靠性优先。请基于当前收藏中的字幕证据，说明 Agent 开发流程中的 checkpoint 与人工验收如何帮助发现 test 后仍不满足条件的问题；请引用来源并说明局限。
  success_constraints: []
expected_product_boundary:
  - exactly one current InputRequest
  - exactly one exact-once HumanDecision
  - current parent/source checkpoint/child Goal and Attempt lineage
  - no substantively identical second InputRequest
  - terminal grounded valid_success/valid_partial, or honest non-running bounded failure clearly reported
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
authorized_cases: [GB-PC-G-01, GB-PC-H-01]
max_logical_calls_total: 10
max_http_attempts_total: 20
max_input_tokens_total: 80000
max_output_tokens_total: 17792
max_wall_time_seconds_total: 1320
nominal_cost_usd: 0.05
reserve_stop_usd: 0.20
absolute_max_cost_usd_total: 0.25
credential_access: one_existing_keychain_reference_after_entry_gate
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
provider_run_authorized_by_this_amendment: true_after_entry_gate
credential_access_authorized_by_this_amendment: one_existing_reference_after_entry_gate
gate_C_authorized: false
next_action: V5_A_execute_exact_completion_validation_then_main_review
```
