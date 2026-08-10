# Shiliu V5-D Stage 2 Closeout and Evaluation Report

> Stage: Stage 2 — Frozen Paired Evaluation
> Experiment: `V5D-S2-PAIRED-EVAL-001`
> Candidate: `V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001` v1.0.0
> Exact Candidate verdict: `rejected`
> Operational exit: `source_gate_failed_on_valid_D02_pair`
> Submitted by: persistent V5-D Version Session
> Main acceptance: pending

## 1. Exact result

The Candidate is **rejected**. D02 produced a valid Baseline/Treatment source pair, but the frozen treatment did
not meet the source gate: frozen required-aspect coverage stayed at zero, the two new current citations came from
only one of two required sources, and a later `repeated_search` guard still ended the treatment. The Candidate did
change the attributed first actionable step and stayed inside every overhead/protected-boundary cap, but those
facts do not substitute for grounded Research Outcome improvement.

The frozen rule is decisive: any valid source pair that fails grounded improvement or stop/recovery correctness
rejects the Candidate. D04 and reserve/held-out runs were therefore not executed. Source cases are diagnostic and
are not generalization evidence.

```yaml
candidate_verdict: rejected
bounded_claim:
  supported: >-
    on D02 the frozen treatment can replace the first non-incremental follow-up with one materially new recovery
    and can produce a bounded one-source partial answer within its declared overhead
  rejected: >-
    Candidate v1.0 improves the frozen multi-source grounded outcome and eliminates the complete failure
    mechanism on the source gate
  not_tested:
    - heldout_related_generalization
    - unrelated_regression
    - negative_transfer
    - broad_or_statistical_generalization
```

## 2. Authority and entry

| Identity | Verified value |
| --- | --- |
| Main authority | `7ef5dc7ec12689222d3bd277935cbeb586389d38` |
| Stage 2 entry branch | `codex/v5-d` |
| Stage 2 entry HEAD | `900953df64676a5d1438743918ac806961dfff14` |
| Entry tree | clean |
| Candidate artifact | `6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe` |
| Reserve ciphertext | `d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c` |
| Reserve key/access/runs at entry | mode `000`; 4 log rows; 0 runs |

All directed authority files were read from `7ef5dc7` without cherry-pick or modification. The Stage 0
qualification/scaffold/run/custody identities remained available. The live database was read only; its video and
retrieval populations remained 157/140 and 1,633 units/vectors. Stage 2 ran on a new copy of the accepted Stage 0
isolated corpus snapshot, not on live state.

## 3. Valid experiment freeze

The clean effective freeze is:

| Frozen component | Identity |
| --- | --- |
| Freeze commit | `0c72277e7b30bac68800ef27acc9e8d52222efd6` |
| Freeze tree | `9f56ef123dce7b572c4109c2b3ce88b2aac2a71e` |
| Experiment manifest | `0679c93e1cbaedefdeb419b992c12b47d55c9822261b66604aa32eec616dfa56` |
| Candidate | `6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe` |
| Treatment | `09d8ef4fc50001e499bfd2afa01337220e4cc16fa4f98790d09184fcf90eb3f0` |
| Paired runner | `10f343123f05c5ffd4c767d425dee6ad1c1a4adf5f06c30a4f044b7691e57e47` |
| Evaluator source | `6efc8a0f6118dad39b56b87c675fe5ffa3d8781c316fe0d26889013782177966` |
| Evaluator version | `v5-d-stage2-paired-grounded-outcome-evaluator-v1` |
| Product `src` tree | `41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01` |
| Initial isolated DB | `a6497202263bdc318783a0efc35394dbbb53f282af034a76cbf648fc79172b8f` |
| Artifact snapshot manifest | `5da478bc2a91945f0f6c17e4516865db75508641b361286163866f4805cd1b21` |
| Retrieval units | 1,633; explicit manifest `d9f16b50…eba94` |
| Mechanical tests at freeze | 12 passed |
| Private freeze receipt | `c3787c5cc243069115b9cd57f04cd7d807612950f09335a3dacd55fd3bf3a816` |
| Final private run manifest | `a2f2173da7e6f51564523adc7ff76d39296368948a22edc2168f5d45acbf8e9a` |
| Final isolated DB | `33c52df4782a01d190ad9f3369fe01074b93234b2d75faf6a6cad67b261800db` |

The Treatment is imported only by the explicit Stage 2 runner. No file under `src/` imports or discovers it;
runtime registration remains null and active/shadow remain false. Candidate missing/identity/non-applicability
falls closed to the unchanged No-Skill path. Provider route, Evidence/Citation/Verifier/currentness, permissions
and authority were not changed.

### Pre-provider invalid freeze instance

The first local freeze hash, `b384531db3d0d84ccc2c7a40d4d17ffc56de7669`, was closed before Provider
dispatch. Its runner bound one whole-experiment durable budget to 24 possible Task IDs but had created only the
current Task; the accepted Runtime correctly raised `Provider run budget membership is incomplete in the durable
database`.

```yaml
classification: implementation_failure_before_provider_dispatch
provider_calls: 0
tokens: 0
deep_tool_calls: 0
paid_cost_usd: 0
candidate_executed: false
heldout_access: 0
same_freeze_replacement: false
```

The old private root and invalid record were preserved. Before any Provider outcome or held-out access, only the
durable membership allocation was corrected: source and held-out use separately pre-registered policies whose
calls/HTTP/output/tool/time/USD caps add to the original whole-experiment caps (input allocation is lower). The
Candidate, Treatment, evaluator, assignment, success thresholds and Provider configuration did not change. The
corrected state was re-frozen at `0c72277`; no evidence from the failed setup informed Candidate behavior.

## 4. Source diagnosis pair — D02

D02 is source/development evidence only. Frozen arm order was Baseline then Treatment. Both primary arms were
valid; no replacement was used.

| Metric | Baseline | Treatment | Delta / gate |
| --- | ---: | ---: | --- |
| Result status | `valid_insufficient` | `valid_partial` | improved status, not sufficient alone |
| Frozen required aspects covered | 0 | 0 | `+0` — fail |
| Current grounded citations | 0 | 2 | `+2` |
| Grounded video sources | 0 | 1 | `+1`; two-source requirement not met |
| Answer blocks | 0 | 3 | not used as a success proxy |
| Material Candidate recovery | 0 | 1 | first actionable step changed |
| Final `repeated_search` guard | yes | yes | not eliminated — fail |
| Stop correctness | fail | fail | fail |
| Logical calls | 5 | 7 | `+2`, pass |
| HTTP attempts | 5 | 7 | `+2`, pass |
| Input tokens | 8,892 | 16,907 | `+8,015`, pass |
| Output tokens | 476 | 3,724 | `+3,248`, pass |
| Executed deep tools | 3 | 4 | `+1`, pass |
| Paid cost | USD 0.001190044 | USD 0.007502329 | `+0.006312285` |
| Unknown reservations | 0 | 0 | pass |

Redacted Task identity hashes:

- Baseline: `ed8a2b00…ed81b7`; deep Trace `e38d8eaf…90717`.
- Treatment: `e33e8e49…44aa1b`; deep Trace `22a7caa3…ce57`.

The treatment's two final citations were current and lineage-valid, but both resolved to one video. The generated
comparison text described two sources, yet the frozen manual aspect review could not credit source-specific
conclusions, common ground, material differences, source-specific support or grounded synthesis without current
Evidence from both sources. Required-aspect delta was therefore zero. A later repeated action also caused the
same terminal guard, so the frozen mechanism and recovery/stop gates failed even though the first divergence was
changed.

Frozen pair evaluation artifact:
`0518795a65ee02134f742b3f2ca972a28702c610fd6424527c1210275b26d74a`.

## 5. D04 and source gate stop

D04 was pre-registered in the source budget but neither arm was run. Once D02 was a valid failed source pair, the
Contract's exact verdict could only be `rejected`; D04 could not restore the all-source requirement. Stopping saved
paid budget and did not constitute opportunity resampling, a replacement, or deletion of a valid arm.

```yaml
D04:
  baseline_provider_run: false
  treatment_provider_run: false
  valid_result_deleted: false
  reason: decisive_valid_D02_source_failure
source_gate_pass: false
reserve_open_allowed_after_result: false
```

## 6. Reserve assignment, custody and held-out

The source gate failed before custody assignment. The reserve stayed continuously sealed:

```yaml
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  plaintext_present: false
  access_log_entries: 4
  post_stage0_freeze_access_entries: 0
  decrypt: false
  semantic_assignment: false
  related_unrelated_spare_split: not_created
  reserve_task_rows: 0
  reserve_provider_runs: 0
  evaluation_access: false
  reseal_event: not_required_because_never_unsealed
```

No isolated Custodian context was started because its entry gate never became true. Consequently there is no
held-out related result, no unrelated regression result and no negative-transfer count. These remain unproven;
they are not reported as passes or failures.

## 7. Provider, cost and invalid-run accounting

```yaml
final_frozen_experiment:
  valid_arms: 2
  provider_outer_attempts: 2
  replacements: 0
  logical_calls: 12
  HTTP_attempts: 12
  input_tokens: 25799
  output_tokens: 4200
  deep_tool_calls: 7
  paid_cost_usd: 0.008692373
  unknown_logical_reservations: 0
  unknown_HTTP_reservations: 0
  unknown_token_reservations: 0
  active_reserved_cost_usd: 0
  provider: current_product_DeepSeek_only
  provider_switches: 0
pre_provider_invalid_setup:
  events: 1
  provider_calls_tokens_tools_cost: 0
whole_stage_caps_reached: false
```

All 12 Stage 2 Provider side effects in the effective isolated DB are `succeeded`. The inherited Stage 0 DB's one
historical unknown side effect remains outside Stage 2 accounting. Keychain access was Runtime-only through the
existing reference; the credential value was never displayed, copied or persisted.

## 8. Contamination and mutation audit

- Candidate artifact hash remained unchanged before freeze, throughout both arms and at closeout.
- The worktree stayed at the effective freeze HEAD and clean during Provider execution.
- The evaluator, manual aspect names, success thresholds and budgets were not changed after results.
- D02 is an already-consumed source case; reviewing its private answer for frozen aspects does not create held-out
  contamination.
- No reserve body, Gold, Evidence ref, split semantic, result, raw response or key became visible to Candidate
  design context.
- No held-out run or outcome-based replacement occurred.
- Raw Provider responses, private queries/evidence, full traces, credentials, temp DB and private evaluator inputs
  remain outside Git.
- The isolated DB has `integrity_check=ok`; live DB was never written or migrated.

## 9. One-recovery/stop risk

D02 exercised the recovery-with-Evidence-gain branch: the Candidate made one recovery, gained current Evidence
and returned to baseline continuation. It did not exercise the actual zero-gain `one recovery then honest stop`
branch in a Provider arm; that branch has only mechanical test evidence. More importantly, the subsequent baseline
continuation still repeated a search, showing that bounding only the first recovery did not control the complete
follow-up/stop sequence. This is rejection evidence for v1.0, not authorization to repair Candidate logic against
the same experiment.

## 10. Known limits and recommendation

- Only one source pair ran; this is sufficient for the Contract's rejection rule but not an estimate of effect
  size.
- D04, related generalization, unrelated regression and negative transfer were deliberately not run.
- Provider stochastic reproducibility beyond these two valid arms is unproven.
- The treatment's one-source partial improvement is a bounded diagnostic observation, not Candidate validation.
- Product behavior, user benefit, active/shadow lifecycle and rollback remain untested and unchanged.

```yaml
stage_3_recommendation: do_not_authorize
main_acceptance_recommendation: accept_the_exact_rejected_verdict_and_closed_stage_2_evidence
possible_future_direction: >-
  only under a new explicit contract, return to attribution/Candidate design for a new version that addresses
  multi-source grounded coverage and the post-recovery stop sequence; do not reuse this experiment as held-out
  validation evidence
```

## 11. Explicit non-actions

No active/shadow registration, promotion, Stage 3 execution, live DB write/migration, generic Skill/Eval/Harness/
Learning platform, second Candidate, Provider switch, upstream download/adoption, Push, Merge or Tag occurred.
The V5-D Session stops after the local closeout commit and cannot accept its own Stage 2.
