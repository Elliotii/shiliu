# V5-D Candidate Revision Cycle R1 Closeout and Source Gate Report

> Cycle: Candidate Revision R1
> Exact result: `invalid_run`
> Execution branch: `codex/v5-d`
> Entry head: `254d72a03a1251ee0d08cac49d100b91b5de7593`
> Freeze commit: `789cf176adcc8c7a66dccbf0c507e875537bcc1a`
> Candidate: `V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001` v1.1.0
> Candidate status: `proposed_non_active`; effectiveness unproven
> Main acceptance: required; not self-accepted

## 1. Outcome first

R1 completed the authorized offline re-attribution, falsifiable Hypothesis, Candidate v1.1 definition,
experiment-only Treatment, directed tests and clean freeze. It did **not** form a valid D02 pair and did not
reach the D04 pair.

D02 Baseline A1 was valid. D02 Treatment A1 was then rejected before any Treatment Provider dispatch because
the frozen runner passed a 175,000 per-arm input-token cap to an accepted Runtime boundary whose Gate B maximum
is lower. The invalid Treatment consumed 0 Provider calls/tokens/USD. This is a frozen scaffold implementation
failure, not Candidate quality, Provider failure, data failure or an adverse Research Outcome.

A frozen-identical replacement would deterministically repeat the same validation failure. Changing the cap
would modify the frozen Scaffold after a valid Baseline outcome, which the R1 Contract prohibits. Therefore no
replacement, D04 run, source judgment, reserve access or v1.2 was performed. The exact R1 exit is
`invalid_run`; it is not `candidate_v1_1_rejected` and not `source_gate_passed`.

## 2. Entry and authority audit

| Item | Verified value |
| --- | --- |
| Main authority | `5aab85ef5412c36df02b18c60cec591b66cd9199` |
| Actual entry branch / head | `codex/v5-d` / `254d72a03a1251ee0d08cac49d100b91b5de7593` |
| Entry worktree | clean |
| v1.0 Candidate | `6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe` |
| accepted Stage 2 freeze | `0c72277e7b30bac68800ef27acc9e8d52222efd6` |
| accepted v1.0 D02 pair | `0518795a65ee02134f742b3f2ca972a28702c610fd6424527c1210275b26d74a` |
| reserve ciphertext | `d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c` |
| reserve key/access/runs at entry | mode `000`; access log 4; post-freeze access 0; runs 0 |

No material entry mismatch was found.

## 3. Post-treatment re-attribution

The full bounded analysis is in `V5_D_POST_TREATMENT_REATTRIBUTION_R1.md` (SHA-256
`9c4b6a5ccaf3e5e887a6bcaf2db151a7aecfc1cbd8ec723971d149f6fcf4d750`).

```yaml
re_attribution_id: V5D-R1-REATTRIBUTION-20260811-A
confidence: moderate_high
first_actionable_post_recovery_step: D02_treatment_decision_round_5_before_guard
remaining_mechanism: evidence_only_recovery_success_handoff_loses_objective_coverage_obligation
```

In the accepted v1.0 Treatment, the round-4 Candidate recovery added 60 transcript segments and 6 current
Evidence spans. Positive Evidence caused v1.0 to release control. The next Baseline decision selected the exact
same transcript action key as round 3; only then did the downstream guard stop the run. Final citations were
current but resolved to one source, so all frozen two-source comparison aspects remained uncovered.

Alternative corpus, retrieval/index, Provider, evaluator and Outer Audit causes were reviewed. They are not the
primary cause of the round-5 re-entry. Preliminary planning and Provider choice may amplify selection, but the
policy-visible handoff remained first actionable. “Allow another recovery” and “stop earlier” were rejected:
the first recovery succeeded, while an early stop without required coverage would still fail Research Outcome.

## 4. Hypothesis and v1.0 to v1.1 delta

Hypothesis `V5D-R1-HYPOTHESIS-COVERAGE-BUNDLE-HANDOFF-001` states that one objective-derived coverage-bundle
Evidence action plus a retained post-recovery completion gate can prevent non-progress Baseline re-entry and
improve grounded coverage without a second recovery. Either valid D02 or D04 source failure falsifies it.

Candidate v1.1 SHA-256 is
`c40c4df488c15801eb521530f16833158028cef076ba348ce811f3a8794d4efc`.

| v1.0 | v1.1 |
| --- | --- |
| one arbitrary untried source or Provider proposal | one bounded named-source bundle or objective-scoped corpus Evidence action |
| any positive Evidence delta returns to Baseline | post-recovery source-coverage completion/deficit gate retains control |
| no persistent explicit coverage snapshot | explicit objective-derived named/minimum-source coverage snapshot |

Unchanged: same Candidate ID, Failure Family, follow-up surface, one Candidate recovery maximum, No-Skill
fallback, Evidence/Citation/currentness/Provider/tool/authority boundaries. Not added: second recovery, larger
recovery count, single-source-continue heuristic, termination-reason trigger or v1.2.

## 5. Freeze identity

| Identity | Value |
| --- | --- |
| Experiment | `V5D-R1-SOURCE-GATE-001` |
| Freeze commit | `789cf176adcc8c7a66dccbf0c507e875537bcc1a` |
| Freeze tree | `3e276d0d1f7113dede8af63e027d89d14c18950b` |
| Freeze manifest | `230989ebc8c8437b56edd051ebe2d810cc6f38d80adfd9de089a79c0509d0d9c` |
| Private freeze receipt | `b24b05d94d741e48e82d62ff2a9b46271451f88aeb8a607c9df53dfcc3b766f4` |
| Treatment | `cdb52593fec31876df2a8fe73ea67cbcc21d0fd22ef83466aa486927f4254f` |
| Runner | `caf739bd95ae279f5021589e5865276f754e7f7be9147f64188deea81bbd144d` |
| Evaluator | `4227dafd04e2d0e8fb6909f144a853919105bf7f50a3a25e2b3932d4c5d51c08` |
| Product `src` tree | `41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01` unchanged |
| Directed mechanical tests | 18 passed before freeze; 18 passed at closeout |

The isolated snapshot retained schema 14, integrity `ok`, FK violations 0, 157 videos, 140 completed videos,
the accepted lexical/dense index identities and a 1,391-file artifact snapshot. The artifact content hash
multiset matched accepted Stage 2. No live DB or index was written/rebuilt.

Frozen source order was D02 `[baseline, treatment]`, then D04 `[treatment, baseline]`. All eight A1/A2 Task
identities were preregistered before the first Provider budget snapshot. D02/D04 remained consumed Source cases,
not generalization evidence.

## 6. Execution and invalid-run evidence

### D02 Baseline A1

```yaml
valid: true
answer_status: valid_insufficient
termination_reason: repeated_search
grounded_current_citations: 0
grounded_sources: 0
required_aspects: not_manually_scored_without_pair
logical_calls: 5
http_attempts: 5
input_tokens: 8893
output_tokens: 549
deep_tool_calls: 3
cost_usd: 0.000646613
unknown_receipts: 0
deep_trace_sha256: 1cce5577d33faf6e57015682b1ce3f08590417b5b0a54e8f111c974d33d66538
```

### D02 Treatment A1

```yaml
classification: implementation_failure_frozen_scaffold_runtime_envelope
valid_arm: false
provider_dispatch_performed: false
provider_receipts: 0
calls_tokens_tools_cost: 0
failure: frozen_per_arm_input_cap_175000_exceeds_accepted_Gate_B_envelope
replacement_eligible: false
exception_evidence_sha256: 8401a9375566b2289319e1d9f84a14fba5192be4acb8c358b5ae3e450b637cbf
```

The Runtime rejected the per-arm call before Candidate execution. This neither supports nor falsifies v1.1.
The invalid class is not a Provider/infrastructure/evaluation execution event allowed a frozen-identical
replacement. A lower cap would be a Scaffold change; the valid D02 Baseline had already been observed.

### D02 pair and D04

```yaml
D02_valid_pair: false
D02_pair_evaluator_run: false
D02_required_aspect_or_citation_delta: unavailable
D04_treatment_run: false
D04_baseline_run: false
D04_provider_calls: 0
valid_source_pairs: 0
source_gate_judgment: unavailable_due_invalid_run
```

No unfavorable valid outcome was deleted or replaced. No best-of or opportunity resampling occurred.

## 7. Whole-R1 accounting

```yaml
valid_arms: 1
outer_attempt_records: 2
invalid_attempts: 1
logical_provider_calls: 5
http_attempts: 5
input_tokens: 8893
output_tokens: 549
deep_tool_calls: 3
paid_cost_usd: 0.000646613
unknown_reservations: 0
active_reserved_cost_usd: 0
credential_reference_accessed: true
credential_value_recorded: false
hard_cap_or_reserve_stop_reached: false
private_run_manifest_sha256: 41bd4d7feacca3440e6f7759fe27d69665b76346f921f57fe186353e80dce680
final_isolated_db_sha256: d7ce1000f1a0c95de69211db3b69a2f779a58125e36c27a86f1b3ff07678425b
```

Only current-product DeepSeek configuration was used. The existing Keychain reference was read at runtime,
the value was neither displayed nor persisted, and no system permission workaround was attempted.

## 8. Reserve, contamination and mutation audit

```yaml
reserve_ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
reserve_key_mode: "000"
access_log_entries: 4
post_freeze_access_entries: 0
reserve_runs: 0
decrypt_or_key_read: false
semantic_split: false
heldout_runs: 0
candidate_designer_reserve_exposure: false
```

The reserve ciphertext and access log hashes remained unchanged. No reserve body, Gold, Evidence ref, result,
key or split semantic was accessed. No Candidate/evaluator/scaffold modification was made after freeze; instead,
the frozen experiment was closed. Product `src`, default No-Skill behavior, Prompt/Provider route, Evidence,
Citation, Verifier, permissions, active/shadow state and live DB remained unchanged.

## 9. Exact result, claim boundary and recommendation

```yaml
exact_R1_result: invalid_run
candidate_v1_1_effectiveness: unproven
candidate_v1_1_source_gate: not_reached
candidate_v1_1_status: proposed_non_active
candidate_v1_0_accepted_verdict: rejected_unchanged
heldout_generalization: unproven
negative_transfer: unproven
stage_3_entry_gate: not_met
```

R1 proves a bounded post-treatment re-attribution and a mechanically testable v1.1 package. It proves no
Research Outcome improvement. Main should accept the exact `invalid_run` record and keep v1.1 non-active.

If the user wants another execution attempt, it requires an explicit amendment/new authorization that fixes
only the per-arm input envelope in a fresh freeze and states how the already observed D02 Baseline is handled.
The current Contract does not authorize that amendment, a new Candidate revision, reserve/held-out, v1.2,
active/shadow use or Stage 3. The V5-D Session stops here for Main limited acceptance.
