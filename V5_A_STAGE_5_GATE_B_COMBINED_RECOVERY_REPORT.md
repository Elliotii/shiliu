# V5-A Gate B Combined Projection and I/H Recovery Report

## 1. Outcome

The bounded control-projection fix is commit
`633b926a8080ce72ae3877d48f0edaddfe55ce44`. A real no-network regression now drives a
Task to `waiting_user` with a current InputRequest and proves the runner reads
`open_input_requests` from `research_control.get_status()`, not the kernel projection.
The full V5-A Stage 1–5/Gate B targeted set passed `175` tests with only the existing
Starlette/httpx warning; compileall and diff-check passed.

The authorized recovery produced useful but incomplete Gate B evidence. It is preserved
as three distinct roots, not represented as one run.

## 2. GB-G-01: frozen parent plus zero-call projection recovery

The original G root was never modified or rerun. A pure query-only projector opened its
frozen eval DB with SQLite `mode=ro&immutable=1`, reconstructed the complete projection,
verified the parent hashes before and after, and wrote evidence to a new sibling root.
Credential and Provider call counts for this recovery are both zero.

The recovered historical boundary remains exactly:

- `valid_insufficient` Stage 2 provisional artifact;
- Stage 3 audit `blocked` with `authorized_evaluator_required`;
- one current Stage 4 InputRequest;
- Task `waiting_user`;
- five frozen succeeded receipts, five HTTP attempts, 5,063 input / 685 output tokens,
  US$0.000976227.

## 3. GB-I-01: first and only execution

I ran once in a fresh schema-10 evaluation copy. Four actual-identity receipt-bound
calls completed, all SideEffects are `succeeded`, and none is unresolved. The product
formed a `valid_insufficient` artifact without EvidenceUses, refused to invent 2027
three-platform failure rates, then reached a deterministic `blocked` audit and current
InputRequest at `waiting_user`.

This is an honest bounded result within the frozen expected outcome set. It consumed
3,746 input tokens, 478 output tokens, four HTTP/logical calls and US$0.000664970.

## 4. GB-H-01: exact-once HITL, then infrastructure stop

H's deterministic pre-Provider path created one InputRequest. The frozen answer was
applied exactly once and command replay returned the same HumanDecision. The original
Attempt became terminal with a non-terminal goal-revision Result, and a child Attempt
was created with exact parent Attempt and source Checkpoint lineage at control generation
1.

Immediately afterwards, the runner tried to serialize
`current["checkpoint_id"]`. The canonical InputRequest field is
`source_checkpoint_id`, so it raised `KeyError: 'checkpoint_id'`. This happened before
the H Provider orchestrator was constructed: H has zero Provider calls and zero
SideEffects. Its isolated child Attempt remains `running`; no continuation, retry, or
automatic repair occurred.

The failure is evaluation infrastructure, not Provider failure, unknown SideEffect, or
product-state integrity failure. Under the written stop condition, V5-A did not patch
and resume the same run.

## 5. Combined accounting and boundaries

G and I together account for nine logical/HTTP calls, 8,809 input tokens, 1,163 output
tokens and US$0.001641197. The I/H root stayed below its remaining subset limits and the
combined cost stayed below US$0.50. Current official DeepSeek V4-Pro prices were checked
before Entry Gate: cache-hit 0.003625, cache-miss 0.435 and output 0.87 USD per million
tokens, with the announced 2x peak multiplier conservatively reserved.

No secret was printed or persisted. No live DB migration, Gate C, Merge, Push, or Tag was
performed. All evidence roots were made read-only after finalization.

## 6. Submission

```yaml
gate_B_recovery_status: submitted_for_v5_main_review
GB_G_01_rerun: false
GB_I_01_run_count: 1
GB_H_01_provider_run_count: 0
GB_H_01_fixed_answer_exact_once: true
gate_B_self_accepted: false
gate_C_started: false
next_action: V5_main_session_final_gate_B_review
```
