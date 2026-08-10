# V5-D Candidate Revision R1-E1 Closeout and Source Gate Report

> Amendment: R1-E1 mechanical execution only
> Exact result: `candidate_v1_1_rejected`
> Execution branch: `codex/v5-d`
> Entry head: `ae3367548943098904d88623b9a3d132936563ac`
> E1 freeze commit: `cbc8917aaa625897ae7e718e7d15e784aeeb0705`
> Candidate: `V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001` v1.1.0
> Candidate status: `proposed_non_active`; active/shadow false
> Main acceptance: required; not self-accepted

## 1. Outcome first

R1-E1 corrected only the frozen Treatment per-arm input cap from 175,000 to the accepted Product Runtime
maximum of 140,000, passed a no-Provider regression at the real `run_to_boundary` validation entry, carried the
valid R1 D02 Baseline A1 forward without rerun, and executed the preregistered D02 Treatment A1.

Both D02 arms are valid. The amended Treatment performed one material objective-coverage-bundle recovery, but
added no Evidence and ended `valid_insufficient` with zero current Citations, zero grounded sources and zero
covered required aspects. It did not reach its post-recovery completion gate. The frozen evaluator therefore
records required-aspect/Citation/source deltas of 0 and fails grounded improvement, source diversity, material
mechanism change and recovery/stop gates.

The exact result is `candidate_v1_1_rejected`. Per the hard stop, D04 was not run because no later pair can make
the requirement that every valid source pair pass true. No Candidate amendment, v1.2, reserve/held-out or Stage 3
work followed.

## 2. Authority and entry audit

| Item | Verified value |
| --- | --- |
| Main governance authority | `1dab08972ecb4c70524be8d93b9b5c9a5c127ebd` |
| Authority contract SHA-256 | `97d90bfe42c993701d64ccb6c6c8db218539c3ace58faf1031d13597e0615d85` |
| Actual entry branch / head | `codex/v5-d` / `ae3367548943098904d88623b9a3d132936563ac` |
| Entry worktree | clean |
| Candidate v1.1 | `c40c4df488c15801eb521530f16833158028cef076ba348ce811f3a8794d4efc` |
| Treatment logic | `cdb52593fec31876df2a8fe73ea67cbccbc21d0fd22ef83466aa486927f4254f` |
| Evaluator | `4227dafd04e2d0e8fb6909f144a853919105bf7f50a3a25e2b3932d4c5d51c08` |
| Re-attribution | `9c4b6a5ccaf3e5e887a6bcaf2db151a7aecfc1cbd8ec723971d149f6fcf4d750` |
| Product `src` tree | `41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01` |

Schema 14, database integrity `ok`, FK violations 0, 157 videos / 140 completed videos, lexical/dense index
identities, source-case hashes, DeepSeek endpoint/models and credential-reference hash all matched the Contract.
No material entry mismatch was found.

## 3. Mechanical amendment and freeze

The two 62-character Treatment-hash display typos in the old R1 Closeout and Current State were corrected to the
actual 64-character value. Candidate v1.1, Treatment logic, evaluator, gates/thresholds, Provider configuration,
corpus/index, D02/D04 and Reserve identities were unchanged.

| Identity | Value |
| --- | --- |
| Old R1 freeze | `789cf176adcc8c7a66dccbf0c507e875537bcc1a` |
| Old freeze manifest | `230989ebc8c8437b56edd051ebe2d810cc6f38d80adfd9de089a79c0509d0d9c` |
| Old private freeze receipt | `b24b05d94d741e48e82d62ff2a9b46271451f88aeb8a607c9df53dfcc3b766f4` |
| Old private run manifest | `41bd4d7feacca3440e6f7759fe27d69665b76346f921f57fe186353e80dce680` |
| Old final isolated DB | `d7ce1000f1a0c95de69211db3b69a2f779a58125e36c27a86f1b3ff07678425b` |
| Old invalid D02 Treatment | `8401a9375566b2289319e1d9f84a14fba5192be4acb8c358b5ae3e450b637cbf` |
| E1 freeze commit / tree | `cbc8917aaa625897ae7e718e7d15e784aeeb0705` / `ccead23d0edeb00bc24228474eed6b367a3a1c04` |
| E1 freeze manifest | `b25e2b14337d214b25d59afd031339a08887c999632c298784cdf5da04ecdb68` |
| E1 private freeze receipt | `7ceb6cd7cda7149df8cacda71c6e70b66c0f695bf224490aa419de77489d7544` |
| E1 runner | `f6a45d7ca5220f079d2788e2914c5d023eb098e94e2fa017ea30c1fdc88ab957` |
| Runtime regression | `6cc92307a490fb0cc774eb190f877959e40ed91132a6e0fdad2664b729fa7645` |

The regression called the actual accepted `ReceiptBoundResearchProductOrchestrator.run_to_boundary` boundary.
Baseline 125,000 and amended Treatment 140,000 both reached the post-validation test stop; legacy 175,000 was
rejected. Provider factory and receipt dispatch were never called. The directed freeze suite passed 22 tests
with `PYTHONPATH` explicitly bound to this worktree.

## 4. Carried D02 Baseline provenance

```yaml
task_id_sha256: 659402cb0dd9d7c89160dcefbd8a556e75617d2d72d91bf64b4005d0fc25b12a
deep_trace_sha256: 1cce5577d33faf6e57015682b1ce3f08590417b5b0a54e8f111c974d33d66538
rerun: false
replace: false
resample: false
answer_status: valid_insufficient
termination_reason: repeated_search
current_grounded_citations: 0
grounded_sources: 0
logical_http_calls: [5, 5]
input_output_tokens: [8893, 549]
deep_tool_calls: 3
cost_usd: 0.000646613
```

The observed 8,893 input tokens are below both its original 125,000 Baseline cap and the 140,000 Product Runtime
maximum. The E1 Treatment-cap amendment was non-binding for this carried arm.

## 5. Provider permission event

The first launcher attempt reached Keychain access before any arm record or Provider dispatch and received macOS
`Keychain Access Denied`. Execution paused for explicit user authorization as required. It consumed zero calls,
tokens, tools or USD and is not an outer attempt or arm outcome. After the user authorized continuation, the same
frozen preregistered D02 Treatment A1 ran once. No credential value was displayed, copied or recorded.

## 6. D02 valid pair

| Metric | Carried Baseline | E1 Treatment | Delta |
| --- | ---: | ---: | ---: |
| valid | true | true | — |
| answer status | `valid_insufficient` | `valid_insufficient` | no improvement |
| termination | `repeated_search` | `no_new_evidence` | changed |
| covered required aspects | 0 | 0 | 0 |
| current grounded Citations | 0 | 0 | 0 |
| grounded sources | 0 | 0 | 0 |
| logical calls | 5 | 3 | -2 |
| HTTP attempts | 5 | 3 | -2 |
| input tokens | 8,893 | 2,774 | -6,119 |
| output tokens | 549 | 393 | -156 |
| deep tool calls | 3 | 3 | 0 |
| paid cost USD | 0.000646613 | 0.000665144 | +0.000018531 |

Treatment recorded one applicable Candidate action, one material recovery and one coverage bundle, with no
second recovery. It recorded zero post-recovery completion gates and `coverage_satisfied=false`.

```yaml
common_validity_pass: true
grounded_improvement_pass: false
required_source_diversity_pass: false
material_post_recovery_mechanism_change_pass: false
recovery_stop_pass: false
no_material_regression: true
protected_boundaries_pass: true
overhead_pass: true
pair_pass: false
pair_evaluation_sha256: 9eaeb5c4382b9ef7a67bb0ee7bbfcf80081e4379110d01149a0d291a3e7f1afc
```

The Treatment stopped honestly when its sole recovery yielded no Evidence, so repeated search did not recur.
That is not success: required aspects and grounded Citation outcome did not improve, and the Candidate's intended
post-recovery mechanism did not complete.

## 7. Exact result and D04 stop

```yaml
exact_result: candidate_v1_1_rejected
D02_valid_pair: true
D02_pair_pass: false
D04_treatment_run: false
D04_baseline_run: false
D04_provider_usage: 0
replacement_runs: 0
```

The unchanged Source Gate requires every valid pair to pass. D02's valid failure is sufficient and irreversible;
continuing D04 could not change the exact result and would violate the immediate-stop requirement. No unfavorable
outcome was replaced or resampled.

## 8. Budget accounting

| Usage | E1 incremental | R1 + E1 cumulative | Original R1 hard cap |
| --- | ---: | ---: | ---: |
| valid arms | 1 | 2 | 4 |
| outer attempt records | 1 | 3 | 8 |
| logical calls | 3 | 8 | 104 |
| HTTP attempts | 3 | 8 | 208 |
| input tokens | 2,774 | 11,667 | 1,060,000 |
| output tokens | 393 | 942 | 140,000 |
| deep tool calls | 3 | 6 | 100 |
| wall seconds | 465.066 | 505.999 | 5,760 |
| paid cost USD | 0.000665144 | 0.001311757 | 0.20 |
| unknown reservations | 0 | 0 | worst-case accounted |

Active reservations were zero. Remaining cumulative reserve-stop allowance is USD `0.158688243`; remaining hard
allowance is USD `0.198688243`. No cap or reserve stop was reached.

## 9. Evidence, data and custody

```yaml
E1_run_manifest_sha256: 55f186ae76f64cf715847aed336656b6f3497e139c13bf69615d0206daf43bf6
E1_D02_treatment_trace_sha256: 839509e0036c59d9a67bab3ebe05969d55363883aba6e401fc1a82df96b96cec
E1_final_isolated_db_sha256: 122b84a93e449a71c687165d297b57befc24839f5086d2783c1fe2735d58dc78
E1_private_closeout_receipt_sha256: 572e0249924e67739c8c39e17718f8225ec8de253782bf7ef43b62f1a1ebf1cc
database_integrity: ok
foreign_key_violations: 0
provider_side_effects: {succeeded: 3, unknown: 0}
reserve_ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
reserve_key_mode: "000"
reserve_access_log_entries: 4
post_freeze_access_entries: 0
reserve_runs: 0
```

The Reserve ciphertext and access-log hashes remained unchanged. No body, Gold, Evidence ref, key, semantic
split or result was accessed. No live DB write/migration, index rebuild, product `src` change, default Prompt or
Provider-route change, active/shadow registration, v1.2, generic platform, Push, Merge or Tag occurred.

## 10. Claim boundary and recommendation

Candidate v1.1 is rejected by its first valid Source Gate pair. This does not establish D04 behavior,
generalization, unrelated regression, negative transfer, held-out effectiveness or product benefit. Candidate
v1.0's accepted rejection remains unchanged. Candidate v1.1 remains non-active and must not proceed to Reserve,
held-out or Stage 3.

Main should limited-accept the exact `candidate_v1_1_rejected` result, preserve the sealed Reserve, and close the
authorized R1-E1 amendment. No further Candidate revision is authorized.
