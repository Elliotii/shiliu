# Shiliu V5-D Stage 1 Closeout and Evidence Package

> Stage: Stage 1 — Attribution + One Candidate Contract
> Result: `candidate_contract_ready`
> Status: submitted for V5 Main limited acceptance
> Authority: evidence production and proposed/non-active Candidate only; no self-acceptance
> Recorded at: 2026-08-11T01:33:06+08:00

## 1. Decision

Stage 1 retains the accepted Failure Family and freezes one attribution, one falsifiable Hypothesis and one
proposed/non-active Candidate Contract:

```yaml
stage_1_result: candidate_contract_ready
failure_family: non_progress_search_repetition_without_recovery
responsible_policy_surface: follow_up_strategy
attribution_id: V5D-S1-ATTRIBUTION-20260811-A
attribution_confidence: moderate_high
hypothesis_id: V5D-S1-HYPOTHESIS-20260811-A
candidate_id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
candidate_version: 1.0.0
candidate_status: proposed_non_active
stage_2_execution_authorized_or_performed: false
formal_acceptance: pending_V5_Main
```

The earliest common failure is not the final `repeated_search` guard. It is the preceding follow-up decision: the
policy had already observed zero current transcript-Evidence gain, unresolved user-objective work, previous action
keys and remaining budget, but selected no materially new evidence-bearing target and did not honestly stop.

## 2. Entry gate and frozen evidence identity

```yaml
entry:
  authority_commit: e53fa410682691bfa86000c768f60e99cd459547
  branch: codex/v5-d
  entry_head: fbf7a0d56816797d0ad481b2381b6d5aba81657c
  entry_working_tree: clean
  stage_0_main_decision: accept
  accepted_failure_family: non_progress_search_repetition_without_recovery
  candidate_effectiveness_generalization_regression_negative_transfer: unproven
```

The authorized discovery evidence was frozen before attribution:

| Evidence | SHA-256 |
|---|---|
| Stage 0 qualification artifact | `76f3a3effcc685d426ad387c4fb50a2069467916f6e291a19d149d553f408896` |
| No-Skill scaffold | `126d774fd8f5d43db8e3439e86b4603009ac31f464125de545d1d3bf304d7647` |
| Stage 0 run manifest | `bb1d4acd9920a01e430bf5b5b26556ab9e5689324ac06d39e690db4fc7984384` |
| D02 durable trace file | `470e6d13356e2af3ae7a3ce521d5aaa47aa9f6e28e2fda0d8ddb9a3b82548e41` |
| D02 product projection | `11bf180672118524a35a79205e559026a7f8d2f5cf081e000fe7dbf4184a6320` |
| D02 Provider trace | `778bae8588c26f8f67cff892a941958e959ccab0fcca48c713855fb422d81894` |
| D04 durable trace file | `02506732cea28a2216eb51129562636f26c964d37cbda6e0cdc0e070341951ee` |
| D04 product projection | `4ca69b799dd15b2b4eba68ea1aaf2f6770669623198bdcc94bebbd49b0bc8766` |
| D04 Provider trace | `4a75a16b876ec899679b4bfa1870a06b654beb388211d0775f02420d4c41c806` |
| D03 control trace | `9fcb0f50a4b70507ab5cdb0b93dc85eba3dcd077a0cdc01f66205cfdb69f25fb` |
| D01 replacement control trace | `e30c0a83c611b5a23332f424dcf1904dd200908dba062e2ad0e80caa403e65dd` |

Material policy/runtime source identities at the unchanged accepted product tree are:

```yaml
source_identity:
  src_tree: 41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01
  tests_tree: 4579751da1bd1ed3693247a9530fa70ad6b75acb
  deep_policy_py: 8cbcdc047ed5b9a018962c6d7f5b604a56cd6550a62a55d34f577e4ff75225b9
  decision_view_py: 53aab8ecf9ab2fc282b396f4d7a006682cfaaf8969d54333f68f06fad18d8410
  deep_graph_py: f3a72e100a347e5494f1883b055f8d9c754283bac48825c45adcf4e02f4bc211
  deep_reducer_py: 2bc78acac9f4935d26beeab8518657550c5130c28350605becc070e39edf129c
  provider_product_py: 6cb8adf30ce88db9e8cda6313d76b2bebed8a506fa2ef175a393a0366e48a0e5
  inner_service_py: 394cd49b2817cb96da5c3bc04abef6cedbad35b82849b92cde7d43a934b6b8ee
  outer_service_py: 46a25befb0d32e909bb966271e2f3bdaf8377d6ab387ca9ff3b3b0b391a2e396
```

No Stage 1 Provider call, Keychain access or new product run was used.

## 3. Trace-level attribution

### D02 timeline

| Decision round | Redacted action | Information delta | Attribution |
|---:|---|---|---|
| 1 | navigation, action fingerprint `7f672dc7…163d` | 8 routing documents; no grounded authority | legitimate routing progress |
| 2 | different navigation, `cc77be71…e63b` | 8 further routing documents | legitimate routing progress |
| 3 | transcript search scoped to one source, `a625159d…5718` | 0 valid Evidence in the Deep trace | observed no-grounded-progress signal |
| 4 | navigation `7f672dc7…163d` again | exact prior action; no possible new scoped information | **first actionable failure** |
| finalize | deterministic guard | `repeated_search`; 0 context spans/citations/blocks | consequence, not first cause |

The task required more than one explicit source obligation. At round 4, a source obligation remained unsearched
for transcript Evidence, the last evidence-bearing action had added nothing, three of six decision rounds and nine
of twelve tool slots still remained, and the previous action key was known. A follow-up policy could have chosen a
different evidence-bearing target tied to the unresolved user objective or stopped honestly. Re-selecting round
1's navigation action could not improve grounded outcome.

### D04 timeline

| Decision round | Redacted action | Information delta | Attribution |
|---:|---|---|---|
| 1 | navigation, `7e36bf34…e2ab` | 0 navigation results; bounded transcript fallback also added 0 current Evidence | observed no-grounded-progress signal |
| 2 | navigation `7e36bf34…e2ab` again | identical scope after the empty fallback | **first actionable failure** |
| finalize | deterministic guard | `repeated_search`; 0 context spans/citations/blocks | consequence, not first cause |

The objective carried multiple explicit source obligations, targeted offline retrieval had already demonstrated
that the frozen current sources were reachable, and five decision opportunities including the current round plus
ten tool slots remained. The
DecisionView exposed the last observation, previous scoped query keys, open question and remaining budget. The
policy nevertheless selected the same action instead of changing the evidence target or honestly stopping.

### Earliest common mechanism and differences

```yaml
failure_attribution:
  earliest_common_failure_mechanism: >-
    after an evidence-seeking action produced zero current transcript-Evidence delta while user-objective work
    remained unresolved, the next follow-up decision failed to select a materially different evidence-bearing
    target or an honest stop
  responsible_policy_surface: follow_up_strategy
  observed_no_progress_signal:
    - last action yielded zero valid/current evidence
    - unresolved user-objective work remained
    - previous action keys and remaining budget were available
  expected_but_missing_policy_decision:
    - one bounded new target derived from objective/open questions and routing observations
    - otherwise honest partial/insufficient stop
  D02_difference: partial routing coverage and one failed scoped transcript search preceded the repeat
  D04_difference: empty navigation plus automatic transcript fallback preceded the repeat
  grounded_outcome_impact:
    D02: 0 answer blocks, 0 grounded citations, 5 frozen aspects missing
    D04: 0 answer blocks, 0 grounded citations, 6 frozen aspects missing
```

Navigation hit count is not Evidence progress. Conversely, new navigation documents may be legitimate routing
progress when they identify a new source target. The Candidate therefore does not ban navigation or require a
query rewrite after a fixed number of attempts; it conditions on current Evidence delta, unresolved objective
coverage and whether a materially different evidence target exists.

## 4. Outer Audit, stop correctness and alternative causes

The existing Outer Audit arrived only after provisional synthesis and recorded
`authorized_evaluator_required`; it did not supply a pre-action missing-aspect target. Frozen Gold/evaluator output
must not enter Candidate execution. Therefore the missing policy mapping must use the user objective and current
open questions, not post-hoc Gold or reserve metadata.

For D02/D04, continuing with the same action was incorrect. A new bounded evidence-bearing target was preferred
because explicit target obligations and budget remained. If no such target could be justified, `valid_insufficient`
was the honest fallback. In a future applicable case with some current Evidence, the corresponding safe fallback
is an honest partial answer with limitations, not further non-progress search.

| Alternative cause | Decision | Evidence |
|---|---|---|
| Corpus/data absence | rejected as primary | Answerability and source boundaries were frozen before runs; D02 had 2/2 current sources and 13 chunks, D04 3/3 and 16 chunks. |
| Retrieval/index implementation | rejected as primary; initial miss retained as uncertainty | All 1,633 units were current and targeted checks reached the frozen sources. The attributed failure is the observable lack of recovery after a miss, not the initial broad-query miss. |
| Runtime/state-machine implementation | rejected as primary; one amplifier retained | Trace, action, receipt and guard state were durable and healthy. Preliminary durable Evidence/QueryPlan was not seeded into the Deep executor, but D03 succeeded through the same boundary, so this does not explain the case-local divergence alone. |
| Provider transport/infrastructure | rejected for D02/D04 | All 8 combined case-local Provider receipts succeeded, retry/error/stale counts were zero and structured actions were valid. D01's separate dispatch failure was isolated. |
| Provider decision quality | contributing mechanism, not a reclassification | The Provider selected the duplicate actions, but the Search Policy owns DecisionView instructions, allowed action selection and recovery bounds. D03 proves the same Provider can select a productive sequence; Stage 2 must still falsify this distinction. |
| Evaluator/contract | rejected | Required aspects were frozen, no model judge changed them, and the evaluator was not used to steer the follow-up. |
| Infrastructure | rejected | Isolated DB integrity/FK, source currentness, index identities and run receipts were healthy. |

D03 is the bounded positive control: navigation → two-source transcript search → window → finish produced 7 valid
evidence candidates, 3 answer blocks and 2 current citations in the same environment. D01 is the bounded exclusion
control: current Evidence was available, but the invalid and replacement failures occurred in Provider dispatch
and grounded-citation validation, not follow-up selection.

```yaml
attribution_confidence: moderate_high
unresolved_uncertainties:
  - complete DecisionView message text was not persisted; durable action outputs, trace hashes/summaries and source identity remain
  - unused preliminary durable Evidence and QueryPlan may amplify search inefficiency
  - only two discovery cases support the family
  - Provider choice and policy constraint contributions require a paired treatment to separate causally
failure_reclassified: false
```

## 5. Frozen falsifiable improvement Hypothesis

```yaml
improvement_hypothesis:
  hypothesis_id: V5D-S1-HYPOTHESIS-20260811-A
  status: frozen
  target_component: follow_up_strategy_before_the_next_search_action
  failure_pattern: zero_current_evidence_delta_plus_unresolved_user_objective_followed_by_no_new_target
  causal_hypothesis: >-
    when an evidence-seeking follow-up adds zero current transcript Evidence, an objective-coverage and
    evidence-delta policy that selects at most one materially new evidence-bearing target, or honestly stops when
    none exists, will reduce non-progress repetition and increase grounded required-aspect/citation outcomes
    without degrading unrelated tasks
  applicable_scope:
    - Deep Research follow-up after at least one observation
    - current source/index/runtime health
    - unresolved target derivable from the user objective or open questions
  non_applicable_scope:
    - initial query planning
    - already sufficient answer
    - invalid Provider/infrastructure/evaluator run
    - stale or unavailable source/index
    - Fast/Search/answer-presentation/Evidence-authority behavior
  expected_behavior_change:
    - replace a non-incremental follow-up with one bounded new evidence target
    - otherwise stop partial or insufficient honestly
  expected_grounded_outcome_change:
    - at least one additional frozen required aspect and one additional current grounded citation on each valid source/related treatment case
    - no required-aspect, grounded-citation or result-class regression on unrelated cases
  risks:
    - unnecessary cost or tool use
    - false applicability and negative transfer
    - query rephrasing without scope change
    - masking retrieval or Provider defects
  falsification_conditions:
    - valid source or held-out related treatment does not improve grounded aspect/citation outcome
    - recovery executes but current healthy retrieval repeatedly yields no Evidence
    - either unrelated case regresses
    - overhead exceeds the frozen per-case delta
    - treatment requires Gold/reserve/evaluator/authority access or product boundary mutation
  evidence_that_would_reclassify_the_failure:
    - DecisionView cannot expose a correct no-progress or unresolved-target signal
    - targeted recovery fails across current answerable related cases because retrieval cannot reach Evidence
    - Provider or infrastructure invalidity dominates the paired experiment
```

This Hypothesis is measurable and can be false. It does not claim that the Candidate is effective.

## 6. One proposed/non-active Candidate Contract

The sole Candidate package is
`V5_D_CANDIDATE_EVIDENCE_DELTA_FOLLOWUP_V1.json`, SHA-256
`6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe`.

```yaml
candidate:
  candidate_id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  candidate_type: domain_specific_search_research_policy
  version: 1.0.0
  lifecycle_status: proposed_non_active
  runtime_registration: none
  active: false
  shadow: false
  applicability: Deep Research pre-follow-up with zero current-Evidence delta and unresolved objective work
  trigger_dependency:
    termination_reason: false
    repeat_count: false
  baseline_fallback: existing No-Skill behavior unchanged
  maximum_incremental_delta_per_applicable_treatment:
    Provider_logical_calls: 2
    HTTP_attempts: 4
    input_tokens: 25000
    output_tokens: 5000
    executed_tool_calls: 1
    Provider_route_or_role: 0
    tool_permission: 0
```

Procedure summary:

1. Snapshot current Evidence/citation coverage, visited sources, previous action keys, last observation, unresolved
   user-objective requirements and remaining budget.
2. Distinguish grounded-Evidence progress, routing-only progress and no-grounded-progress; navigation is never
   factual Evidence.
3. Derive eligible targets only from the user objective/open questions and current routing observations.
4. Select at most one evidence-bearing action with a materially different scope/source target.
5. Re-evaluate; continue only after current Evidence gain, otherwise honestly stop partial/insufficient.

Forbidden behavior includes exact action repetition, rephrasing-only recovery, hit/length/search-count success,
Gold/evaluator/reserve access, Evidence/Citation/Verifier/currentness mutation, Provider/permission/corpus expansion,
and hiding invalid runs. Package absence, invalid identity, non-applicability, rejection or rollback deterministically
returns the existing No-Skill baseline.

### Why this is not a simple repeated-search heuristic

The Candidate does not wait for `repeated_search`, count repetitions or prescribe “after N attempts rewrite.” It
acts before termination, using a trace-observed zero current-Evidence delta and unresolved user objective. A
different query is eligible only when its evidence target or scope materially changes. It also permits honest stop
instead of requiring more search. Thus the causal unit is evidence/goal progress, not string novelty or attempt
count.

The Candidate is a declarative contract only. It is not a Skill repository, product Prompt, active/shadow route,
runtime registration or treatment implementation.

## 7. Frozen Stage 2 paired-evaluation design — plan only

```yaml
experiment:
  experiment_id: V5D-S2-PAIRED-EVAL-001
  status: planned_not_authorized_not_run
  baseline: frozen_No-Skill_scaffold_e877a03aa5aee94f440eef294a109470c51c1f3210da3f835619420d752f0dcc
  treatment: candidate_file_6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe
  source_diagnosis_cases: [D02, D04]
  source_cases_are_generalization_evidence: false
  heldout_minimum:
    related: 1
    unrelated: 2
    spare: 1
  environment_shift_required: false
```

### Freeze and custody order

```text
Main accepts Stage 1
→ freeze treatment implementation, Candidate hash, No-Skill baseline, code/scaffold and budgets
→ freeze evaluator, metrics, thresholds, invalid and contamination rules
→ isolated Custodian may then open only the authorized reserve package
→ Custodian assigns 1 related + 2 unrelated + 1 spare from preregistered task semantics, never outcomes
→ freeze split IDs/hashes/access manifest and separately seal bodies/Gold/Evidence/evaluator inputs
→ run counterbalanced baseline/treatment pairs
→ evaluator opens results only after both arms are durable
→ Candidate designer receives redacted paired decision, not held-out bodies/Gold
```

The Custodian classifies a task as related only when its already-frozen objective structurally requires switching
among multiple independent evidence targets after observable non-progress. Unrelated tasks must not require that
mechanism as their primary completion path. Assignment may not use any run result. SHA-256 of
`experiment_id + case_id` freezes arm order parity. If one related, two unrelated and one spare cannot be assigned,
Stage 2 stops before any run as `insufficient_uncontaminated_split`.

The spare can replace a case only for pre-run contamination/eligibility failure, never because of outcome. Any
Candidate/trigger/procedure/stop/threshold modification after split access invalidates all opened held-out cases;
no result may be retained as held-out evidence.

### Runs and exact budget proposal

Five paired tasks are planned: two source diagnosis, one held-out related and two held-out unrelated. This is ten
valid arms. Each arm permits at most one identical-scaffold replacement only for Provider/infrastructure/evaluation
invalidity.

| Envelope | Baseline attempt | Treatment attempt | Whole experiment maximum including replacements |
|---|---:|---:|---:|
| Valid runs | — | — | 10 |
| Outer attempts | — | — | 20 |
| Logical Provider calls | 12 | 14 | 260 |
| HTTP attempts | 24 | 28 | 520 |
| Input tokens | 125,000 | 150,000 | 2,750,000 |
| Output tokens | 15,000 | 20,000 | 350,000 |
| Deep tool calls | 12 | 13 | 250 |
| Wall time | 720 s | 720 s | 14,400 s |
| Paid cost | case-accounted | case-accounted | hard stop USD 0.50; reserve stop USD 0.40 |

DeepSeek current product configuration is the only proposed Provider; no switch or new credential is allowed.
Any cap stops the experiment and yields an honest `inconclusive` unless a valid Candidate boundary violation
already supports rejection. These figures are a Stage 2 authorization proposal, not current authority.

### Frozen evaluator and decision thresholds

Evaluator identity proposal: `v5-d-stage2-paired-grounded-outcome-evaluator-v1`, deterministic contract checks
plus isolated manual frozen-aspect review; no model judge. Candidate/treatment cannot access task assignment,
Gold, aspect refs, Evidence refs or thresholds beyond this public contract.

Primary measurements per arm:

- frozen required-aspect coverage;
- current grounded Evidence/Citation validity;
- no-progress recovery conformance and exact action-key novelty with material target change;
- source-target/diversity coverage when required by the objective;
- counterexample/limitation preservation;
- partial/insufficient stop correctness;
- Provider/tool/token/USD overhead and invalid-run status.

Candidate `validated` requires all of:

1. D02 and D04 each eliminate the non-incremental follow-up, add at least one current grounded citation and cover at
   least one additional frozen aspect versus its valid baseline.
2. The one held-out related pair meets the same citation and `+1` aspect threshold.
3. Both unrelated pairs have no answer-status, required-aspect, grounded-citation, counterexample-preservation or
   stop-correctness regression; negative-transfer rate is exactly `0/2`.
4. Every treatment remains within `+2` logical calls, `+4` HTTP attempts, `+25,000` input, `+5,000` output and
   `+1` executed tool call relative to the paired baseline, with zero Provider-route/permission delta.
5. All currentness, lineage, invalid-run, experiment-identity and total USD gates pass.

Longer answers, more hits or more searches never count as improvement. A valid failure of source/related
grounded thresholds, any unrelated negative transfer, a protected-boundary violation or Candidate-caused budget
overrun rejects the Candidate. If the split is insufficient or a required arm remains Provider/infrastructure/
evaluation invalid after its one replacement, the experiment is `inconclusive`; no opportunity resampling occurs.

## 8. Stage 1 custody, mutation and mechanical validation

```yaml
stage_1_activity:
  Provider_calls: 0
  Keychain_access: 0
  paid_cost_usd: 0
  reserve_runs: 0
  reserve_decrypt_or_key_read_or_chmod: false
  live_DB_write_or_migration: false
  product_code_test_prompt_provider_route_change: false
  candidate_active_shadow_promotion: false
  stage_2_runs: 0
  upstream_download_or_adoption: false
  push_merge_tag: false
```

Reserve custody at Stage 1 exit:

```yaml
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  ciphertext_mode: "600"
  key_mode: "000"
  plaintext_present: false
  access_log_entries: 4
  post_freeze_access_entries: 0
  runs: 0
  body_gold_evidence_result_or_key_read_by_Stage_1: false
```

The Candidate JSON parsed successfully and passed directed mechanical assertions for version identity,
`proposed_non_active`, null runtime registration, inactive/shadow flags, termination/repeat-count independence,
No-Skill fallback, zero Provider-route/tool-permission delta, two source traces, two bounded controls and explicit
Gold/evaluator/reserve prohibitions. No product test was added because this is a non-executable declarative package.

## 9. Known limits and recommendation

Stage 1 does not prove Candidate effectiveness, held-out generalization, unrelated safety, negative transfer,
Provider reproducibility, user benefit, product integration or promotion readiness. Full DecisionView messages
were not durably retained, preliminary Evidence/QueryPlan handoff remains a possible amplifier, and the sealed
pool is small. One held-out related case is the maximum feasible minimum while preserving two unrelated cases and
one spare; the Stage 2 conclusion must disclose that statistical limitation.

Recommendation: Main should inspect the D02/D04 first-actionable decisions, the retained Runtime/Provider
uncertainties, Candidate inactivity/fallback boundaries, exact Stage 2 thresholds/budget and unchanged reserve
seal. If Main accepts, the user may separately authorize a Stage 2 Contract. Until then V5-D stops; no treatment,
reserve assignment or paired run is authorized.
