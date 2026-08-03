# V5-A Gate B Grounded Completion Smoke Report

Status: `submitted_failed_acceptance_criteria_not_self_accepted`

## Outcome

The bounded Deep correction and the single authorized `GB-PC-G-01` Provider
smoke both completed. The product fix did what it claimed: after the first empty
`search_navigation`, the graph executed one global `transcript_search`, then
rejected the Provider's repeated navigation instead of consuming the remaining
action budget. No case ID, exact query, video ID, keyword or Gold branch was
added; the five frozen Prompt/Tool/Schema blobs were unchanged.

The product acceptance criteria were not met. The generated retrieval query was
`Agent 开发流程 checkpoint test 完成后 停下来 人工验收`. Both its video-scope
navigation and its forced global transcript search returned zero raw hits even
though the frozen corpus contains reachable checkpoint material under less
conjunctive wording. The run therefore produced no current EvidenceUse or
citation. A second identical navigation was rejected with `repeated_search`;
the durable product then closed honestly as terminal
`valid_insufficient / no_new_evidence / none`, with Outer outcome
`stop_insufficient`.

This narrows the remaining gap: repeated empty navigation is closed, while
long compound retrieval intent still needs a general, bounded query-correction
policy before representative grounded completion is proven. Per authorization,
this was the only G smoke; V5-A did not modify the code after seeing the result
and did not rerun G.

## Code and no-network evidence

- Product fix: `ca0e6f537275465c92b9359603233770cdbdf6da`.
- G-only Entry harness: `ad20febcd7fc692971062a787004ce5a31b4b202`.
- Frozen joint targeted suite: 205 passed; only the existing Starlette/httpx
  deprecation warning.
- The real no-network product test proves empty navigation → transcript search
  → current EvidenceUse/citation → server-owned Outer accept on an arbitrary
  supported query. Existing receipt, replay, unknown SideEffect, owner/control
  fence and budget tests remained in the joint suite.
- No default 1,600+ regression was rerun, exactly as allowed by the bounded
  authorization.

## Entry Gate

The Entry Gate froze the exact case hash
`fc493889bae303c4761a663cf22853b0a24a087f5238667fc7e98cdb98d8175d`,
implementation tree, five blob identities, official DeepSeek V4-Pro prices,
schema-9 snapshot, isolated schema-10 DB, corpus/artifact/index identity and
zero unresolved SideEffects. The conservative next-call reservation was
US$0.08385408 under the US$0.10 hard cap.

An initial builder invocation failed before root creation because the supplied
full Git SHA was mistyped. Credential access and Provider calls were both zero;
the same Entry was then run with Git's actual SHA. This was an invocation error,
not an evaluation run or recovery root.

## Provider and durable evidence

```yaml
run_id: GB-PC-G-20260803T205358Z-ad20feb-empty-nav-smoke
root: /Users/elliot/Documents/Shiliu-Evaluations/V5-A/Gate-B/GB-PC-G-20260803T205358Z-ad20feb-empty-nav-smoke
formal_manifest_sha256: 0de158ea4e2ed46ba6ef19a005249cdb40d8ae295a4295a27c390320124994ee
eval_db_sha256: 2461927a4e8a1019ce4beec362581b0661d7fd49a192d9d4388d69cf88729424
provider: deepseek_openai_compatible
endpoint: https://api.deepseek.com/v1
model: deepseek-v4-pro
logical_calls: 3
http_attempts: 3
input_tokens: 2395
output_tokens: 314
cost_usd: 0.000486765
succeeded_side_effects: 3
unknown_or_in_flight_side_effects: 0
task_status: terminal
attempts: 2
checkpoints: 11
outer_audits: 2
results: 2
current_EvidenceUse: 0
citations: 0
answer_status: valid_insufficient
termination_reason: no_new_evidence
failure_class: none
outer_outcome: stop_insufficient
```

All three Provider operations have actual endpoint/model/role/thinking identity,
Provider operation IDs, request/response hashes, usage/cost and succeeded
receipts. No operation was replayed. The isolated DB reports schema 10,
integrity `ok`, zero FK violations, 157 videos / 140 completed, and no
unknown/in-flight SideEffect.

## Immutability and boundaries

The original formal root remained unchanged: manifest
`705484087b…`, report `18105cd549…`, and schema-9 snapshot `e1e276dfde…`.
All historical roots were retained. The live DB was neither runtime state nor a
migration target. H was not run. V5-A does not self-accept Gate B and did not
start Gate C, live migration, Merge, Push or Tag.

The completed root's exact manifest/DB/case-evidence hashes are recorded and all
filesystem write bits were removed after the run. All older roots remain
unchanged.

```yaml
gate_B_grounded_completion: unproven
gate_B_smoke_disposition: valid_failed_product_quality_evidence
gate_B_self_accepted: false
gate_C_authorized: false
automatic_rerun_performed: false
next_action: V5_main_session_final_gate_B_decision
```
