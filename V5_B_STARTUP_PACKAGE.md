# Shiliu V5-B Startup Package

> Prepared by: Shiliu V5 Main Codex Session
> Date: 2026-08-04
> Startup authorization: user_authorized
> Assignment status: ready_for_V5_B_version_session
> Product implementation authorized: false

---

# 1. Assignment

Create one Shiliu V5-B Version Session to lead the complete
Evidence-backed Personal Knowledge and Corpus Workspace subversion.

The first assignment is startup and JIT research only:

1. audit the accepted V5-A baseline relevant to V5-B;
2. perform bounded fixed-commit research on DeepTutor and WeKnora;
3. draft the V5-B Version Charter;
4. draft the first formal Stage Contract;
5. establish compact V5-B Current State and Decision Ledger;
6. submit one startup report for limited V5 Main Session review.

Do not begin V5-B product implementation before the Charter and first Stage Contract
are accepted.

# 2. Accepted starting baseline

```yaml
repository:
  branch: codex/v5-main
  accepted_head: b60e1df238294d5b3e3f06d864a9e4d026ef599e
  working_tree_before_startup_docs: clean
runtime:
  source_schema: 10
  live_schema: 10
  integrity_check: ok
  foreign_key_violations: 0
  videos: 157
  completed_videos: 140
  live_research_tasks: 0
  live_candidate_delta_events: 0
  active_sync_runs: 0
  web_service: running
V5_A:
  status: accepted_with_known_retrieval_limitation
  candidate_delta_schema: v5-a-stage5-candidate-delta-v1
  candidate_delta_authority: candidate_only_not_promoted
startup_directed_tests:
  selected: 64
  passed: 64
  failed: 0
  warning: existing_Starlette_httpx_deprecation
```

The live absence of Research Tasks and Candidate Deltas is an evaluation-input gap, not
an Entry Gate failure. Temporary deterministic fixtures may be used for early stages,
but V5-B version completion requires planned real product journeys.

# 3. Version objective

V5-B must turn V5-A research outputs into a durable, evidence-backed, user-correctable
workspace:

```text
Research Task
→ Candidate Delta
→ Grounded Fact
→ Research Artifact
→ Topic Page
→ Revalidation / Conflict / Staleness
→ Direct Reuse / Incremental Refresh / Research Seed
→ Personal and Corpus Workspace
```

The complete accepted planning boundary is
`V5_B_STARTUP_AND_EXECUTION_PLAN.md`.

# 4. Preserved capability goals

- L1 Evidence/Event authority;
- L2 Grounded Fact;
- L3 Research Synthesis and Topic Page;
- Candidate review, correction and rejection;
- Artifact retrieval, scope match and source-version revalidation;
- direct reuse, incremental refresh and research seed;
- conflict, staleness, versioning and supersede;
- Explicit User Memory and editable inferred/candidate states;
- Current Focus and Knowledge Progress;
- Corpus Model as a soft prior only;
- SystemExperienceRecord without Active Skill promotion.

Specific Schema, framework, file layout, Stage count and internal order are not frozen.

# 5. Non-goals and authority boundaries

- Do not implement V5-C personalized answer/search/routing.
- Do not implement V5-D Active Skill or policy promotion.
- Do not build a general MemoryOS, enterprise Wiki or multi-tenant platform.
- Do not use Corpus Model as Citation or hard source exclusion.
- Do not overwrite L1 Evidence with L2/L3 objects.
- Do not automatically promote V5-A Candidate Delta.
- Do not make GraphRAG a default dependency or Stage.
- Do not treat the V5-A compound-query retrieval limitation as automatic V5-B scope.
- Do not access credentials or call a Provider.
- Do not mutate the live database.
- Do not merge, push or tag.
- Do not update Program authority files.
- Do not self-accept the Charter, Stage or version.

# 6. Required JIT upstream research

## 6.1 DeepTutor

Priority: P0 before Charter/first Stage.

Required:

- official repository and current maintenance check;
- fixed Commit;
- License and third-party boundary;
- L1/L2/L3 and Memory lineage source symbols;
- read/write/update/delete and idempotency behavior;
- user correction/edit behavior;
- relevant tests and failure behavior;
- mapping to Shiliu SQLite + filesystem Artifact architecture;
- explicit adopt/reimplement/reject decisions.

## 6.2 WeKnora

Priority: bounded P1 before Topic Page implementation.

Research only:

- Topic Page/Auto-Wiki product shape;
- page generation/update/rebuild state;
- async task observability;
- inter-page relationships;
- useful frontend or test patterns.

Reject enterprise multi-tenancy, RBAC, Connector scope and any replacement of Shiliu
Fast/Deep/Evidence/Citation.

Downloading or reading an upstream does not authorize adoption. Any copied source requires
fixed identity, License evidence and an accepted Stage Contract.

# 7. Session operating rules

```yaml
V5_B_session:
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
```

Keep one active formal Stage. Specialist Sessions may serve that Stage but do not form a
second acceptance line.

# 8. Startup outputs

Required:

```text
V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md
V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md
V5_B_VERSION_CHARTER.md
V5_B_STAGE_1_CONTRACT.md
V5_B_CURRENT_STATE.md
V5_B_DECISION_LEDGER.md
V5_B_STARTUP_REPORT.md
```

Reports must distinguish verified source/test facts, design proposals, rejected upstream
mechanisms, not-exercised paths and unproven assumptions.

# 9. Submission boundary

The startup report requests only:

- Charter acceptance/revision;
- first Stage Contract acceptance/revision;
- upstream adoption decisions;
- Stage 1 product implementation authorization.

Until V5 Main accepts those requests:

```yaml
product_implementation_started: false
provider_runs_performed: false
live_database_migrated: false
program_state_modified: false
merge_push_or_tag_performed: false
```
