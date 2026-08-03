# V5-A Stage 5 Gate B Final Evaluation Report

## 1. Submission outcome

Gate B now has real Provider evidence for all three frozen cases through durable Research
product boundaries. The product safety and persistence mechanisms worked: all 13 post-fix
Provider SideEffects have complete receipts, actual Provider identity, bounded usage and
zero `unknown`/`in_flight` effects. G, I and H each have exactly one product Provider run;
no completed Provider operation was replayed.

The product-quality result is mixed. I honestly refused unsupported future statistics.
H exercised exact-once current-lineage HITL and real Provider continuation, but created a
second InputRequest after the fixed answer. G's durable product path remained
`valid_insufficient / waiting_user`, so the representative grounded-answer product path
was not demonstrated by the post-fix product run. V5-A therefore submits the evidence
without self-accepting Gate B and recommends that V5 Main choose `partial_accept` or
bounded product-quality rework rather than full `accept` on the present evidence.

## 2. Evidence roots and run counts

| Evidence root | Scope | Provider calls | Durable outcome |
| --- | --- | ---: | --- |
| `GB-20260803T081500Z-be96740` | Original direct Deep Ask diagnostic; not product orchestration | 15 | Accepted diagnostic answer/identity/cost evidence only |
| `GB-20260803T180111Z-b5592eb-postfix-credential-user-retry` | G product run, exactly once | 5 | `valid_insufficient → blocked → waiting_user` |
| `GB-20260803T181806Z-633b926-g-projection-recovery` | Read-only G projection recovery | 0 | Same frozen G boundary, parent hashes unchanged |
| `GB-20260803T181908Z-633b926-ih-recovery` | I product run once; H pre-Provider HITL incident | 4 | I waiting; H decision persisted, then harness stop |
| `GB-20260803T183818Z-4ffc99d-h-only-recovery` | H recovery product run, exactly once | 4 | `valid_insufficient → blocked → waiting_user` |

The roots remain separate and read-only. Recovery evidence does not overwrite or disguise
earlier incidents.

## 3. Case rubric

### GB-G-01

- Product run count: 1; five complete receipts; US$0.000976227.
- Stage 2 produced `valid_insufficient` with no EvidenceUses; Stage 3 blocked on
  `authorized_evaluator_required`; Stage 4 created one current InputRequest.
- The boundary is safe and honest, but it is outside G's frozen expected
  `valid_success/valid_partial` set. The required representative grounded-answer product
  path remains unproven.
- The separately accepted original direct-Ask run contains answer-quality evidence but
  cannot substitute for durable product-orchestration proof.

### GB-I-01

- Product run count: 1; four complete receipts; US$0.000664970.
- It did not invent 2027 OpenAI/Anthropic/Google failure rates or unsupported citations.
- Durable outcome: `valid_insufficient → blocked → waiting_user`, within the frozen
  expected set. This is a positive honesty/bounded-stop result.

### GB-H-01

- Product Provider run count: 1; four complete receipts; US$0.000904510.
- The fixed answer was consumed by exactly one HumanDecision. Attempt 2 binds the exact
  parent Attempt and source Checkpoint at control generation 1.
- Real Provider continuation durably produced a second artifact/audit and reached
  `valid_insufficient → blocked → waiting_user`; no unsupported answer was emitted.
- Two InputRequests exist across the journey: the first resolved request and a new current
  post-Provider request. That violates the frozen “only one InputRequest” constraint,
  although the final `waiting_user` outcome itself belongs to the expected set.

## 4. Accounting and reliability evidence

The three post-fix product runs total 13 logical/HTTP calls, 12,519 input tokens, 1,617
output tokens and US$0.002545707. All actual identities bind
`https://api.deepseek.com/v1`, `deepseek-v4-pro`, authorized roles and thinking settings.
Official prices were rechecked before each paid Entry Gate; the final H root reserved a
US$0.10055808 worst case against US$0.498358803 remaining authorization.

Mechanical evidence is `176 passed`, plus compileall, JSON, diff and SQLite
integrity/FK checks. Only the existing Starlette/httpx deprecation warning remains.

## 5. Infrastructure incidents and recovery lineage

The audit trail retains every incident:

1. the original formal runner bypassed product orchestration;
2. one eval copy inherited read-only mode and stopped before credentials;
3. Keychain `-128` stops occurred before Provider calls;
4. G completed five calls before `input_requests` was read from the wrong projection;
5. I completed four calls and H persisted its decision before the harness read
   `checkpoint_id` instead of canonical `source_checkpoint_id`;
6. commits `633b926` and `4ffc99d` added direct no-network regressions and append-only
   recovery; the final H-only run completed without harness failure.

No incident root was overwritten, no complete receipt was replayed, and no observed
answer was used to alter Prompt, model, Tool/Schema, case text or evaluator authority.

## 6. Boundaries and requested decision

No secret was printed or persisted. Live DB was not runtime state and was not migrated.
Gate C, Merge, Push and Tag were not performed.

```yaml
gate_B_status: submitted_for_v5_main_final_acceptance
gate_B_self_accepted: false
representative_grounded_product_path: unproven
honest_insufficient_product_path: proven
HITL_exact_once_and_provider_continuation: proven
H_only_one_InputRequest_constraint: failed
requested_main_decision: partial_accept_or_rework
gate_C_started: false
next_action: V5_main_session_final_gate_B_acceptance
```
