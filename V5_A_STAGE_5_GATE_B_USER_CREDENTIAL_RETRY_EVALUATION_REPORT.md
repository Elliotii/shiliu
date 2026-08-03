# V5-A Gate B User Credential Retry Evaluation Report

## 1. Outcome

The user-authorized credential retry successfully acquired the existing Keychain
reference and reached the real Provider. The run then stopped fail closed after the
first case because the runner's post-orchestration projection expected
`input_requests` in the kernel projection returned by `app.research.get_task()`.
That collection is exposed by the Stage 4/product control projection, not the kernel
projection, so `_case_projection()` raised `KeyError: 'input_requests'`.

```yaml
run_id: GB-20260803T180111Z-b5592eb-postfix-credential-user-retry
entry_gate: pass
credential_access: success
run_status: evaluation_infrastructure_failure_postprovider_no_rerun
provider_calls: 5
http_attempts: 5
input_tokens: 5063
output_tokens: 685
total_cost_usd: 0.000976227
executed_cases: [GB-G-01]
not_exercised_cases: [GB-I-01, GB-H-01]
gate_B_self_accepted: false
gate_C_started: false
next_action: V5_main_session_review
```

## 2. Durable product evidence

`GB-G-01` ran exactly once. All five receipt-bound SideEffects succeeded and have real
Provider operation IDs; no SideEffect is `unknown` or `in_flight`. The isolated eval DB
contains one Attempt, five Checkpoints, one `valid_insufficient` Stage 2 provisional
artifact, one Stage 3 deterministic outer audit with outcome `blocked`, one continuation
decision, one Stage 4 current InputRequest, and one Trace. The Task is safely
`waiting_user` at state version 23 with `termination_reason=needs_user_input` and
`failure_class=none`; no terminal Result is expected at this boundary.

The durable run-wide ledger records 5,063 input tokens, 685 output tokens, five logical
calls/five HTTP attempts, and US$0.000976227. `GB-I-01` and `GB-H-01` were created but
remain `ready`; neither was executed and neither consumed Provider budget.

## 3. Evaluation interpretation

This is useful real-Provider diagnostic evidence for receipt binding and the durable
Stage 2 → Stage 3 → Stage 4 waiting boundary, and it proves the Keychain permission path
can succeed. It is not a complete Gate B integration validation:

- `GB-G-01` produced no answer blocks or EvidenceUses, so answer and citation quality
  cannot be scored.
- `GB-I-01` did not exercise the honest insufficient terminal path.
- `GB-H-01` did not exercise fixed-answer exact-once HITL continuation.
- The failure is classified as evaluation infrastructure, not Provider failure or a
  product state-integrity failure.

No rerun was performed. Fixing the projection source and authorizing any further paid
validation are decisions for V5 Main Session.

## 4. Evidence and boundaries

- External immutable root:
  `/Users/elliot/Documents/Shiliu-Evaluations/V5-A/Gate-B/GB-20260803T180111Z-b5592eb-postfix-credential-user-retry`
- External manifest SHA-256:
  `24fa028dfa2af38d94f264ce4f97845063fe99c48233ffdd084520e7ce438075`
- Eval DB SHA-256:
  `bb1965af04fac1e19d58aed088e4cfd15e5b2a5a34df30353e7cd63ee4745fdd`
- Immutable schema-9 snapshot SHA-256:
  `e1e276dfde8194bf3c3282d2014bcbc272b5eea330633049342aeb24329922c3`
- Prompt, Tool, Schema, model, case text, evaluator authority, and approved budget caps
  were unchanged.
- No secret was printed or persisted. No live migration or live runtime-state write was
  performed. Original and earlier failure roots were not modified.
