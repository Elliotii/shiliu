# Shiliu V5-D Stage 0 Entry Calibration Report

> Status: submitted for V5 Main limited acceptance
> Exit decision: `qualified_failure_family_found`
> Execution session authority: evidence production only; no self-acceptance
> Reported at: 2026-08-11T00:49:20+08:00

## 1. Executive decision

Stage 0 found one qualifying Search / Research Policy Failure Family:

```yaml
failure_family:
  name: non_progress_search_repetition_without_recovery
  initial_policy_surface: follow_up_strategy
  supporting_discovery_cases:
    - V5D-S0-D-02
    - V5D-S0-D-04
  exit_decision: qualified_failure_family_found
  formal_acceptance: pending_V5_Main
```

Both supporting cases were selected and frozen before any run or failure classification. In both, current
authoritative transcript Evidence existed, source/index identity remained healthy, all case-local Provider calls
were successfully receipted, and the durable trace ended at `repeated_search` after a non-progressing follow-up
decision. The impact was not answer length or hit count: each produced zero answer blocks and zero grounded
citations and missed all frozen required aspects. A third case in the same environment produced a grounded
`valid_partial` result, while two D01 Provider/grounding events were segregated into a different failure domain.

This decision does **not** validate or freeze a Candidate Hypothesis. It does not authorize Stage 1.

## 2. Startup audit and execution identity

```yaml
git:
  required_branch: codex/v5-d
  actual_start_branch: codex/v5-d
  startup_authorization_head: 98ee944a5fdca19c962953b5d71250c7b6dea508
  actual_start_head: 98ee944a5fdca19c962953b5d71250c7b6dea508
  start_working_tree: clean
  accepted_product_code_head: 8904e27df07becebae13110f9be17cd829373b20
  product_source_tree_at_start: 55dc6da8b47c7c46c357dbbeb53e896c9607c138
  accepted_product_source_tree: 55dc6da8b47c7c46c357dbbeb53e896c9607c138
  startup_docs_commit: ca944e14b5a72565bd8dbd15ddcfe4dfe1d90976
  report_submission_commit: this_document_commit_final_HEAD_reported_to_Main
```

The worktree was initially detached at the authorized head. Before creating any file or commit, it was safely
switched to the already-existing `codex/v5-d` branch, which pointed to that same head. The product source tree at
startup exactly matched the accepted product-code tree; later commits in the execution branch changed documents
only.

The eight controlling documents were read completely in the user-specified order before execution. Startup
identity was:

```yaml
database_and_corpus:
  schema: 14
  live_db_access: read_only_identity_and_copy_only
  live_db_sha256_at_copy: 85d706a40f4f8bcad20d3ea373e17b4fd7021ddc738b90eac09a1dd702c25453
  isolated_db_sha256_after_copy_and_path_isolation: 9cd12c6ef27ca128476a28fb973f4b9b78bae2b5841a2b6a5eb6a2ed1877dc67
  isolated_db_sha256_after_runs_and_offline_diagnostics: a6497202263bdc318783a0efc35394dbbb53f282af034a76cbf648fc79172b8f
  integrity_check: ok
  foreign_key_violations: 0
  videos: 157
  completed_videos: 140
  evidence_backed_indexed_videos: 138
  corpus_source_boundary_hash: bf6a345d47aeb5152353d99c9f754c4a1a486c692c31af5d69df0a37520a1f0a
  source_version_set_hash: d7092edf4cece5fa54b574469740b5cdaef86275c993226d8d3f63eabacf4b9b
  retrieval_unit_manifest_hash: afbdeeb2274b407b939cedbfc1216c4174757fa1adc5948d81a6c854fe52ac5b
  live_database_written_by_V5_D: false
```

There were 154 indexed videos, of which 16 had no current raw subtitle and were excluded from the answerability
and selection pool. The 138 Evidence-backed indexed videos were used as the eligible source boundary.

```yaml
retrieval:
  lexical_index: v3-stage1-lexical-v1
  lexical_units: 1633
  dense_index: v3-dense-qwen3-0.6b-mrl512-v1
  dense_model: Qwen/Qwen3-Embedding-0.6B
  dense_model_revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
  dense_units: 1633
  missing_or_orphan_dense_units: 0
  content_hash_mismatches: 0
```

The planning document recorded 447 sync runs; startup had 451 and the post-run audit had 452. The last scheduled
sync changed no corpus or index content: all 1,633 retrieval units and folder mappings remained byte-logically
equal to the isolated copy; lexical/dense metadata changed only `updated_at`; three video rows changed only
`updated_at` and, for two of them, `subtitle_next_check_at`; three memberships changed only `last_observed_at`.
Post-run live identity remained schema 14, 157/140 videos, 1,633 lexical/dense units, integrity `ok`, FK 0 and no
active sync. This is non-material scheduled-sync clock drift, not a baseline rewrite.

```yaml
provider_and_skill:
  provider: deepseek_openai_compatible
  endpoint: https://api.deepseek.com/v1
  model_for_query_analysis_agent_action_grounded_answer: deepseek-v4-pro
  provider_switch: false
  keychain_reference_present: true
  credential_value_displayed_copied_or_recorded: false
  active_skill_repository: none
  active_skill_version: none
  candidate_version: none
  skill_injection: false
  no_skill_baseline: true
```

The initial `.venv/bin/pytest` path did not exist and ran no tests. Using the existing main-repository virtual
environment without modifying it, the affected Research/Provider/Evidence preflight completed `83 passed, 1
warning` with no network calls.

## 3. Candidate-independent case freeze and custody

The ordering invariant was maintained:

```text
rubric freeze
→ all 8 bodies selected and answerability checked
→ discovery/reserve assignments and hashes frozen
→ reserve encrypted, plaintext removed and key chmod 000
→ No-Skill scaffold frozen
→ discovery runs
→ run classification
→ Failure Family qualification
```

A first mechanical preview was rejected before freeze because its theme pairing did not satisfy a predeclared
centrality check. The final rule required the thematic entity to occur in title, one-line summary or key points.
No product run, proposed Candidate surface, historical failure result or reserve outcome informed that correction.

```yaml
freeze:
  rubric_version: v5-d-stage0-coverage-rubric-v1
  rubric_frozen_at: 2026-08-10T16:23:31.046991+00:00
  rubric_sha256: 8b4e29665c2b05d9897c2c577bd43bf6e764d96084b7b2eb6ba8874ce07eadfa
  case_manifest_id: V5D-S0-CASE-MANIFEST-20260811-A
  selected_at: 2026-08-10T16:23:31.134727+00:00
  assignment_frozen_at: 2026-08-10T16:23:31.134886+00:00
  hashes_frozen_at: 2026-08-10T16:23:31.135019+00:00
  case_manifest_sha256: 4850f8f194741623eb0687140b01926012ac6ed169725e76c5f91b606654804f
  access_policy_sha256: 151b7bcbf705a9e09bd243c60db57c6809f048b0a241d8c80e52bd69312441b9
  discovery_count: 4
  reserve_count: 4
```

The redacted case identities are:

| Case | Assignment / archetype | Body SHA-256 | Source boundary SHA-256 | Access |
|---|---|---|---|---|
| D01 | discovery / single-video synthesis | `3198d0b1…27cc` | `b7b8aee2…d90c` | private discovery |
| D02 | discovery / multi-video comparison | `064c613b…55b6` | `b6d4641d…64ed` | private discovery |
| D03 | discovery / claim + counterevidence/limits | `4d6f303c…c713` | `92aee56a…7767` | private discovery |
| D04 | discovery / collection-wide/source-diverse | `9c686166…2896` | `c1e325e7…d404` | private discovery |
| R01 | reserve / single-video synthesis | `a990e7e8…d7a7` | `7f6c5cbd…d622` | sealed unopened |
| R02 | reserve / multi-video comparison | `51286088…3913` | `cf8e59ce…daa2` | sealed unopened |
| R03 | reserve / claim + counterevidence/limits | `a0c9b196…a492` | `e091b8c6…9570` | sealed unopened |
| R04 | reserve / collection-wide/source-diverse | `c6df7f17…dce6` | `f9d37f90…f00f` | sealed unopened |

Reserve custody was implemented by a bounded local custodian process outside Git. The private reserve manifest
was AES-256 encrypted, its plaintext removed, and its independently generated key set to mode `000` before any
discovery run.

```yaml
reserve:
  seal_id: V5D-S0-RESERVE-SEAL-20260811-A
  sealed_at: 2026-08-10T16:23:31.159199+00:00
  ciphertext_sha256_at_seal_and_exit: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  ciphertext_mode: "600"
  key_mode: "000"
  plaintext_present_at_exit: false
  reserve_body_or_gold_seen_by_V5_D: false
  reserve_result_seen: false
  reserve_runs: 0
  reserve_task_rows_in_isolated_DB: 0
  access_log_events: 4
  post_freeze_reserve_access_events: 0
```

Using only preregistered IDs, hashes and high-level archetypes, a future split remains structurally feasible
without unsealing: R02 can occupy one potential related slot; R01 and R03 two potential unrelated slots; R04
remains spare. This is not a final semantic split and does not prove treatment relevance; that requires a future
authorized Contract. No reserve body, Gold, Evidence ref or result was opened to make this mapping.

## 4. Frozen No-Skill scaffold

The final pre-run scaffold was revision 3. Two corrections occurred before any Task, credential access or Provider
call: replacement Task IDs were preregistered and the user USD 2 envelope was conformed to the stricter existing
Runtime run-wide USD 0.50 hard cap; the private runner hash was then bound into the final fingerprint. No post-run
scaffold change occurred.

```yaml
scaffold:
  id: V5D-S0-NO-SKILL-SCAFFOLD-20260811-A
  frozen_at: 2026-08-10T16:25:21.441152+00:00
  final_refrozen_at: 2026-08-10T16:29:16.116345+00:00
  revision: 3
  fingerprint: e877a03aa5aee94f440eef294a109470c51c1f3210da3f835619420d752f0dcc
  private_runner_sha256: 926f4d91c3ac177ed69ed847e8ff7850fe559c77a20c64e5535d1b37042df059
  runner_product_behavior_change: false
  runner_reserve_access: false
  run_id: V5D-S0-DISCOVERY-20260811-A
  code_head: ca944e14b5a72565bd8dbd15ddcfe4dfe1d90976
  product_source_tree: 55dc6da8b47c7c46c357dbbeb53e896c9607c138
```

Material Runtime identities included `v4-deep-policy-v1`, `v5-a-stage1-trace-v1`,
`v5-a-stage2-action-v1`, `v5-a-stage3-outer-audit-v1`, `v5-a-product-profile-v1`,
`v5-a-stage5-product-projection-v1`, `v5-a-gate-b-provider-call-v1`,
`v5-a-gate-b-product-orchestration-v1`, and citation identity `v4-citation-identity-v1`. The retrieval and
provider identities were those recorded in sections 2 and 4. The full source-file hash binding remains in the
private scaffold.

The evaluator was frozen as `v5-d-stage0-required-aspects-trace-classifier-v1`: deterministic contract checks plus
manual Evidence review, with no model judge and no reserve access.

## 5. Discovery runs, receipts and invalid events

One launcher invocation failed before runner import because repository root was missing from `PYTHONPATH`. It
occurred before Keychain access, Task/Attempt creation or Provider calls, consumed no outer attempt or budget, and
is classified `infrastructure_invalid_run` / `infrastructure_pre_run_launcher_invalid`. The identical runner and
scaffold were then launched with the correct import path.

There were five product outer attempts: four valid discovery outcomes plus one invalid Provider attempt on D01.
Only D01 used its single permitted replacement.

| Case / outer | Redacted Task / Attempt / Trace | Runtime result | Governance class / domain | Receipts; input/output; cost USD |
|---|---|---|---|---|
| D01/A1 | `rtask_733a…dc3280` / `attempt_3964…644a89` / `trace_2518…b56718` | blocked after Provider side effect became `unknown` | `provider_failure`, invalid / `provider_quality_or_failure` | 7 committed + 1 unknown; 26,846/1,599 committed; 0.010584420 committed |
| D01/A2 | `rtask_d6ec…d7ab83` / `attempt_cb17…339166` / `trace_7070…faf4dc` | grounded synthesis rejected | `product_quality_failure`, valid / `provider_quality_or_failure` | 8; 31,424/5,082; 0.009311436 |
| D02/A1 | `rtask_4a57…389121` / `attempt_31d7…e15241` / `trace_a824…1823eb` | `valid_insufficient`, `repeated_search`, 0 blocks/citations | `product_quality_failure` / `search_or_research_policy` | 5; 8,893/574; 0.003153083 |
| D03/A1 | `rtask_fce4…025f33` / `attempt_2c05…7d6788` / `trace_f45d…667d68` | `valid_partial`, 3 blocks, 2 current citations, 1 limitation | `valid_partial` / `no_failure` | 6; 17,751/5,282; 0.010770977 |
| D04/A1 | `rtask_2231…17138c` / `attempt_96aa…2c7168` / `trace_0222…737cfa` | `valid_insufficient`, `repeated_search`, 0 blocks/citations | `product_quality_failure` / `search_or_research_policy` | 3; 2,408/256; 0.000607608 |

D01/A1 completed seven Provider calls; the grounded-answer dispatch reached an unresolved `unknown` side effect
with no response/usage receipt. Its active reservation was not silently discarded. D01/A1 accounted usage is 8
logical calls, 9 HTTP attempts, 49,882 input, 5,695 output and USD 0.064921140. D01/A2 then returned a complete
structured answer, but all seven cited identities were outside the current allowlist; all seven Evidence
identities themselves replayed `current`, and deterministic grounded validation recorded seven
`unknown_citation` issues. This is a valid Provider-quality product failure, not a Search Policy instance, and no
second replacement was attempted.

D02/D03/D04 reached the existing outer `authorized_evaluator_required` boundary. That boundary is the expected
manual evaluator requirement, not an invalid run; no product state was manually edited to bypass it.

```yaml
total_accounting:
  product_outer_attempts: 5
  valid_discovery_outcomes: 4
  invalid_product_attempts: 1
  pre_run_launcher_invalid_events: 1
  committed_logical_calls: 29
  accounted_logical_calls_including_unknown_reservation: 30
  committed_http_attempts: 29
  accounted_http_attempts_including_unknown_reservation: 31
  committed_input_tokens: 87322
  accounted_input_tokens: 110358
  committed_output_tokens: 12793
  accounted_output_tokens: 16889
  deep_tool_calls: 18
  committed_cost_usd: 0.034427524
  accounted_cost_usd: 0.088764244
  user_hard_cap_usd: 2.00
  runtime_hard_cap_usd: 0.50
  provider_switches: 0
```

All caps were respected. Raw Provider responses, complete traces, private Task bodies/Gold/Evidence, credentials
and the isolated DB remain outside Git.

## 6. Failure classification and qualification

### D02 first actionable evidence

After bounded progress covered only part of the frozen two-source boundary, a subsequent agent decision selected
an already-used navigation action instead of changing scope or addressing the remaining known source. The
deterministic guard then terminated `repeated_search`. The result contained zero answer blocks/citations and all
five required aspects were absent.

### D04 first actionable evidence

After empty navigation and its bounded transcript fallback, the next agent decision selected the same navigation
query. The deterministic guard terminated `repeated_search` without a scope-changing or source-targeted recovery.
The result contained zero answer blocks/citations and all six required aspects were absent.

The shared first actionable surface is the follow-up decision after non-progress, not initial retrieval hit count.
The preliminary causal question is:

> When a bounded search action makes no or incomplete Evidence progress, does the current follow-up policy make
> premature repeated-search termination more likely than a scope-changing or remaining-source-targeted recovery?

This is a causal question and falsification shape, not a Candidate definition.

Alternative causes were checked as follows:

| Alternative | Evidence and disposition |
|---|---|
| Corpus/data absence | Rejected. Answerability and source boundaries were frozen before runs. D02 had 2/2 completed current raw-subtitle sources with 15 units/13 transcript chunks; D04 had 3/3 with 19 units/16 chunks. |
| Retrieval/index failure | Rejected for the family. All 1,633 retrieval units were unchanged/current. Targeted offline lexical checks reached each D04 source and both D02 source identities; the failed traces made no recovery after their broad/scoped miss. |
| Provider transport/infrastructure | Rejected for D02/D04. All 8 case-local receipts succeeded with well-formed structured decisions; no retry or stale evidence event occurred. D03 succeeded in the same Provider/runtime envelope. D01's distinct events were segregated. |
| Runtime implementation failure | Rejected. Durable Task/Attempt/Trace/EvidenceUse/receipt/outer audit records were complete, and `repeated_search` was the deterministic guard's designed outcome for the selected duplicate action. |
| Evaluator/contract failure | Rejected. Frozen required aspects and a deterministic/manual evaluator were used; no model judge, threshold change, case replacement or reserve access occurred. |

The qualification rule is satisfied by two different valid tasks, not query rewrites of one task; current
authoritative Evidence; healthy case-local Runtime/index/Provider/evaluator; a trace-local first actionable step on
the same `follow_up_strategy` surface; measurable missing grounded outcomes; a pre-Candidate causal question and
future falsification shape; metadata-only reserve split feasibility; and candidate-independent selection.

The future falsification shape is to compare unchanged No-Skill behavior against one later-frozen direction on
authorized unopened related reserve while requiring no regression on at least two unrelated reserve cases and
preserving a spare. Stage 0 defines no treatment, trigger, procedure, stop rule, threshold or Candidate package.

## 7. V5-A compound-query classification

The V5-A compound-query case was not selected for the candidate-independent discovery pool and was not run. No
V5-A policy/retrieval/data classification is claimed by Stage 0.

## 8. Evidence artifacts

Private artifacts are under the local, non-Git root:

```text
/Users/elliot/.codex/private/Shiliu/V5-D/stage0-20260811-MAoyel
```

Material artifact identities are:

```yaml
private_artifacts:
  access_policy_sha256: 151b7bcbf705a9e09bd243c60db57c6809f048b0a241d8c80e52bd69312441b9
  reserve_ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  scaffold_file_sha256: 126d774fd8f5d43db8e3439e86b4603009ac31f464125de545d1d3bf304d7647
  run_manifest_sha256: bb1d4acd9920a01e430bf5b5b26556ab9e5689324ac06d39e690db4fc7984384
  qualification_artifact_id: V5D-S0-QUALIFICATION-20260811-A
  qualification_artifact_sha256: 76f3a3effcc685d426ad387c4fb50a2069467916f6e291a19d149d553f408896
```

The qualification artifact binds the five attempt classifications to private trace/projection hashes. The
reserve key and bodies are deliberately not part of that evidence artifact.

## 9. Explicit non-actions and remaining unproven claims

```yaml
non_actions:
  product_code_modification: false
  product_test_modification: false
  candidate_hypothesis_frozen: false
  candidate_or_skill_created: false
  skill_repository_created: false
  candidate_policy_implemented: false
  active_skill_promoted: false
  live_database_write_or_migration: false
  live_fixture_or_index_rebuild: false
  generic_eval_or_harness_platform: false
  upstream_download_or_adoption: false
  provider_switch: false
  reserve_unseal_or_run: false
  push_merge_tag: false
  stage_1_2_3_execution: false
```

Unproven: no Candidate efficacy, trigger precision, procedure, stop behavior, generalization, negative transfer,
promotion readiness or product benefit has been demonstrated. The Failure Family qualification does not prove
that a Skill is the correct remedy and does not establish that the metadata-only future split is semantically
suitable until a new Contract authorizes the relevant custodian work.

## 10. Submission and next recommendation

Only `V5_D_CURRENT_STATE.md`, `V5_D_DECISION_LEDGER.md` and this report differ from the authorized startup head;
there is no product/test/schema/index change. The submission commit is local on `codex/v5-d`; final HEAD and clean
working-tree status are reported to Main after the commit. Nothing was pushed.

Recommendation: V5 Main should perform the Contract's limited Stage 0 acceptance review, including the freeze
ordering, the D02/D04 redacted trace hashes and alternative-cause evidence, total accounted cost, and reserve seal.
If and only if Main accepts and the user separately authorizes a Stage 1 Contract, the next research direction may
investigate a bounded non-progress recovery/follow-up policy. Until then V5-D stops here.
