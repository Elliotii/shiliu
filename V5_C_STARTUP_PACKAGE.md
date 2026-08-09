# Shiliu V5-C Startup Package

> Prepared by: Shiliu V5 Main Codex Session
> Date: 2026-08-09
> Startup authorization: user_authorized
> Assignment status: ready_for_V5_C_version_session
> Product implementation authorized: false

---

# 1. Assignment

Create one persistent Shiliu V5-C Version Session to lead the complete Personalized
Research Agent subversion.

The first assignment is startup and JIT planning only:

1. audit the accepted V5-A/V5-B baseline relevant to personalization;
2. inspect current Profile/Workspace, Feedback, Corpus, Artifact, Search, Ask and Research paths;
3. assess existing research inputs and perform only material JIT upstream research;
4. draft the V5-C Version Charter and lean full-version Stage sequence;
5. draft the first formal Stage Contract;
6. establish compact V5-C Current State and Decision Ledger;
7. submit one integrated startup report for limited V5 Main Session review.

Do not begin V5-C product implementation before the Charter and first Stage Contract are accepted.

# 2. Accepted starting baseline

```yaml
repository:
  branch: codex/v5-main
  accepted_head: 7cb5a8c0a716900e073aa519efe289dfe887531a
  working_tree_before_startup_docs: clean
runtime:
  source_schema: 14
  live_schema: 14
  integrity_check: ok
  foreign_key_violations: 0
  videos: 157
  completed_videos: 140
  sync_runs: 435
  active_sync_runs: 0
  live_research_tasks: 0
  live_research_events: 0
  live_workspace_records: 0
  live_artifact_routes: 0
  live_topic_pages: 0
  live_feedback_events: 0
  web_service: running
  scheduled_sync: running
  readonly_http_smoke: 5_of_5_200
startup_directed_tests:
  selected: 61
  passed: 61
  failed: 0
  provider_runs: 0
  live_database_hash_before_and_after: a8246965f81a035a1b5be72418cb657840bcf42405e271b64501a904c89495c9
```

The first test invocation stopped during collection because repository-root imports required
`PYTHONPATH=.`. The corrected invocation passed all 61 tests. This was a harness invocation
issue, not a product failure, and no live product data was written.

# 3. Entry decision and cold-start boundary

```yaml
V5_C_entry:
  artifact_reuse_path_exists: true
  feedback_event_mechanism_exists: true
  explicit_memory_confirm_and_correct_exists: true
  corpus_model_readable_as_soft_prior: true
  comparable_product_paths_exist: true
  live_feedback_population_exists: false
  live_profile_population_exists: false
  status: startup_authorized_with_cold_start_input_gap
```

Deterministic temporary fixtures may be used for contracts and early implementation. They must
not enter the live database or be reported as actual user history or proven personalization benefit.
No-profile and disabled-profile behavior must remain the existing product baseline.

# 4. Version objective and preserved capabilities

V5-C must deliver a user-visible, user-controlled Personalized Research Agent:

```text
Feedback / Explicit Input
→ Candidate
→ User-confirmed Versioned Profile / Current Focus
→ Personalized Answer
→ Corpus-aware Search
→ Personalized Route Recommendation
→ Progress / Staleness / Collection Delta Assistance
→ Explain / Correct / Disable / Roll Back
```

The full accepted planning boundary is `V5_C_STARTUP_AND_EXECUTION_PLAN.md`.

Specific Schema, framework, file layout, Stage count and internal order are not frozen. The
Version Session may refine them while preserving all long-term functional goals.

# 5. Authority and safety boundaries

- Explicit user state and behavioral/inferred Candidate must remain distinct.
- Implicit feedback cannot directly change Prompt, Router, Skill or verified user state.
- Profile/Workspace/Artifact/Corpus objects cannot become Citation or Verifier authority.
- Corpus state is a soft prior and cannot suppress open search or counterexamples.
- Personalization must be explainable, disableable, correctable and rollbackable.
- Collection/search/watch behavior cannot be equated with mastery or permanent preference.
- Cold-start or uncertain state must fail closed to the existing non-personalized path.
- V5-D Active Skill, policy promotion and self-modification remain out of scope.
- Do not build generic MemoryOS, GraphRAG, scheduler, notification, rules or telemetry platforms.
- Do not mutate the live database, access credentials, call a Provider, push, merge or tag.
- Do not update Program authority files or self-accept the Charter, Stage or version.

# 6. JIT research rule

Start with local accepted evidence:

- Program Registry and Research Log;
- `local_memo_self_evolution` and `survey_what_when_how_self_evolving` only as boundary/eval input;
- V5-B DeepTutor/WeKnora fixed-commit reports;
- current Shiliu WorkspaceRecord, Feedback, ArtifactRoute, Search, Ask and Research code/tests.

Do not perform decorative upstream research. If a specific unresolved design or testing gap remains,
select the smallest relevant official source, pin identity, verify License, inspect relevant source/tests,
and record an explicit adopt/reimplement/reject proposal. Download is not adoption; research is not
implementation authorization.

# 7. Session operating rules

```yaml
V5_C_session:
  owns_version_internal_design: true
  owns_stage_breakdown: true
  fixes_ordinary_bugs_autonomously: true
  may_run_no_provider_temporary_db_tests: true
  may_create_bounded_specialist_sessions: true
  may_commit_to_execution_branch: true
  may_formally_accept_own_work: false
main_session:
  reviews_each_small_commit: false
  performs_stage_acceptance: true
  handles_mainline_and_live_migration: true
limits:
  active_subversion: 1
  active_formal_stage_or_goal: 1
```

Keep planning and reports compact. Do not create nested Gate documents for ordinary fixes. Goal mode
may be used for a coherent multi-step Stage when it reduces coordination overhead; it does not expand
authority.

# 8. Required startup outputs

```text
V5_C_VERSION_CHARTER.md
V5_C_CURRENT_STATE.md
V5_C_DECISION_LEDGER.md
V5_C_STAGE_1_CONTRACT.md
V5_C_STARTUP_REPORT.md
```

Only add an upstream research report when the episode materially affects a design, rejection or test
decision. Reports must distinguish verified local/upstream facts, proposals, rejected mechanisms,
not-exercised paths and unproven assumptions.

# 9. Submission boundary

The startup report requests only:

- Charter and lean Stage sequence acceptance/revision;
- first Stage Contract acceptance/revision;
- any material upstream adoption decisions;
- Stage 1 product implementation authorization.

Until V5 Main accepts those requests:

```yaml
product_implementation_started: false
provider_runs_performed: false
credentials_accessed: false
live_database_migrated: false
program_state_modified: false
merge_push_or_tag_performed: false
```
