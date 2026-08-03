# V5-A Gate B Completion Validation Report

Date: 2026-08-04  
Status: submitted for V5 Main review; not self-accepted

## Outcome

The authorized completion validation did not establish the missing
representative grounded product path. It did preserve a valid, receipt-bound
diagnostic run and then stopped at the accepted run-wide wall-time boundary.

`GB-PC-G-01` executed four real DeepSeek V4 Pro operations. Every SideEffect is
`succeeded`, every operation has provider identity and receipt evidence, and no
operation is unknown or in flight. The product returned `valid_insufficient`,
zero current EvidenceUse/citations, and a `targeted_continue` audit. Its durable
child Attempt was recovered without Provider replay and fenced to an honest
`blocked` boundary. This is a product-quality failure for the representative
grounded-path rubric, not an infrastructure success disguised as an answer.

`GB-PC-H-01` was never dispatched to the Provider. By the time the append-only
recovery reached its pre-HITL product step, the original run-wide 1,320-second
budget was exhausted. The service committed a terminal `valid_insufficient /
budget_exhausted / none` Result before an InputRequest or HumanDecision could be
formed. The clock was not reset and the budget was not expanded.

## Exact evidence

```yaml
accepted_product_completion_head: 8d600b64338ca994a7ffc1f912365436969737df
exact_case_hashes:
  GB-PC-G-01: fc493889bae303c4761a663cf22853b0a24a087f5238667fc7e98cdb98d8175d
  GB-PC-H-01: 36fa44adc7db63abc951baeeb4ad2f0f6de23b27e80d1025d3ed9a3b29d8b760
provider_model: deepseek_openai_compatible / deepseek-v4-pro
logical_calls: 4
http_attempts: 4
input_tokens: 3499
output_tokens: 391
cost_usd: 0.000813131
unknown_or_in_flight_side_effects: 0
live_database_runtime_use: false
live_database_migration: false
```

The final durable recovery DB contains two Tasks:

- G: `blocked`, `valid_insufficient`, nonterminal targeted-continuation Result,
  four succeeded Provider receipts, no EvidenceUse.
- H: `terminal`, `valid_insufficient`, `budget_exhausted`, failure class `none`,
  no InputRequest, HumanDecision, or Provider operation.

Durable Provider evidence root:
`/Users/elliot/Documents/Shiliu-Evaluations/V5-A/Gate-B/GB-PC-20260803T195429Z-e2ac1f2-completion-recovery1`
(`manifest` `63ca5612…`, `eval.db` `865c77ed…`). Final recovery root:
`/Users/elliot/Documents/Shiliu-Evaluations/V5-A/Gate-B/GB-PC-20260803T201500Z-ff7c207-durable-recovery4`
(`manifest` `96740d0f…`, `eval.db` `1fba5800…`).

## Entry and recovery evidence

- Stage 1–5 joint targeted suite: `185 passed`; only the existing
  Starlette/httpx warning.
- Default no-Provider regression: `1683 passed, 4 deselected`; same warning.
- Five Prompt/Tool/Schema blobs stayed identical to the accepted tree.
- Official DeepSeek V4 Pro prices were frozen at cache-hit input
  `$0.003625/M`, cache-miss input `$0.435/M`, output `$0.87/M`; conservative
  reservation `$0.20111616` remained below the `$0.25` cap.
- Schema-9 snapshot, corpus, artifact and index identities were copied into
  isolated schema-10 evaluation DBs; artifact paths were rebound to read-only
  copies under each new root.
- Historical roots were never overwritten, reused or deleted. Recovery roots
  record their parent manifest and eval DB hashes.

The recovery incidents were mechanical and occurred before any new Provider
operation: missing durable run-budget binding, running-boundary projection,
expired owner takeover, and stopped child lineage. Each was fixed with a
no-network regression before a new sibling root was created. Completed G
operations were never replayed. The final H stop is different: it is the
authorized hard wall-time policy taking effect, so execution ended rather than
resetting the run.

## Main-session decision requested

Gate B completion remains unproven. The evidence supports receipt/budget/
identity integrity and honest bounded failure, but not the missing grounded
representative path or the H exact-one InputRequest journey. V5-A requests the
V5 Main Session to decide `partial_accept / rework / pause / reject`. Gate C,
live schema migration, merge, push and tag remain outside this Session.

```yaml
gate_B_completion_validation: submitted_for_main_review
gate_B_self_accepted: false
gate_C_authorized: false
next_action: V5_main_session_final_gate_B_completion_review
```
