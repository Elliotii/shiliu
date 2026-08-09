# 拾流 V5-B Stage 5 Implementation and Closeout Report

```yaml
stage: V5-B Stage 5
title: Product Completion, Relations and Evaluation
report_status: implementation_complete_pending_v5_main_acceptance
branch: codex/v5-b
accepted_contract_commit: 5b7c96ca277fb303a4307e7a25b8f136c3d68ca1
implementation_authorization_record: cbe605dc76ed04842f9acc48b437c049b1376e68_on_codex_v5_main_not_cherry_picked
implementation_commit: this_integrated_commit_resolved_by_git_after_commit
schema_source_version: 14
new_sqlite_tables: 0
provider_runs_performed: false
provider_cost_usd: 0
credentials_or_keychain_accessed: false
live_database_sqlite_opened_or_mutated: false
self_accepted: false
```

> 本报告与产品代码、测试及状态同步位于同一个integrated commit；commit对象不能在自己的内容中预先包含自身SHA，因此上方以`this_integrated_commit_resolved_by_git_after_commit`标记，提交后的实际SHA由Git和最终acceptance request明确给出。V5-B Session只请求验收，不自我接受。

## 1. Implemented product closeout

Stage 5把已接受的Stage 1–4路径组合为现有Topic/Knowledge Workspace中的一个收口旅程：

```text
published Topic Page + current L1 citations
→ bounded related Page navigation
→ explainable ArtifactRoute
→ reuse-first
   or incremental/seed research-change
→ Candidate review + immutable revision + explicit publish for new content
→ advisory Feedback Event + CommandReceipt
→ derived durable observability
```

### Reuse-first evidence

- exact scope、explicit-aspect completeness、current Fact head与current L1 citation继续由Stage 3 Gate决定；Stage 5不重算或放宽Gate；
- completed `direct_reuse`只返回既有`ArtifactRevision`，不创建Fact、Artifact或Page revision；
- closeout projection显示latest completed route、exact authority hash与existing outcome revision；
- Feedback绑定exact PageRevision或ArtifactRoute record，不改变route、page或publish状态。

### Research-change evidence

- bounded gap沿Stage 3 `incremental_refresh`建立child Research Task，只研究enumerated gap；
- outcome保留parent Artifact、reused/new/dropped contribution与Fact→L1 citation；
- no-hit/scope mismatch/substantial gap或unsafe override继续fail closed到`research_seed`；old Artifact只是candidate context，open retrieval保持独立；
- 新内容仍须Stage 1/2 Candidate review后才形成immutable Artifact/Page revision并显式publish；Stage 5没有自动promotion或publish入口。

## 2. Lean implementation shape

| Surface | Delivered |
|---|---:|
| schema version | unchanged at 14 |
| new SQLite tables / indexes / migrations | 0 / 0 / 0 |
| new adapter | 1 `ResearchProductCloseoutService` |
| new public endpoint types | 1 feedback command |
| read projection | extends existing Knowledge Workspace GET |
| UI | one additive group inside existing Knowledge Workspace |
| queue / scheduler / graph / eval platform | 0 |
| new dependencies / upstream copy | 0 |

The adapter has only three responsibilities: derived relations, bounded existing-record observability/two-path summary, and atomic feedback Event/Receipt. It does not own canonical Page/Fact/Route/operation state.

## 3. Relations and authority

Relations are computed on read from published PageRevision lineage:

- `shared_current_fact`: exact shared current FactRevision only;
- `confirmed_conflict`: exact accepted `confirmed_conflict` observation between current Fact heads;
- source/target pair is deterministic, self-links are removed, backlink is derived, each page is capped at 8 with total/truncated metadata;
- support returns FactRevision identity, claim, content hash and current L1 citations/transcript links;
- stale/retired/superseded head, pending/rejected conflict and lexical similarity produce no relation.

Every relation explicitly reports `navigation_only=true` and false for citation authority, verifier, hard filter, route authority and promotion authority. No relation record is persisted and relations never enter retrieval or route inputs.

## 4. Feedback and observability authority

`POST /api/research/product/tasks/{task_id}/knowledge/feedback` accepts:

- exact `topic_page_revision` + content hash, or exact `artifact_route` record + authority hash;
- `helpful | needs_fix`, one bounded reason code and an optional 500-character note;
- command identity, principal and expected hash.

The transaction appends existing `research_events` and `research_command_receipts` only. Duplicate returns the prior response; payload mismatch, wrong hash, cross-task target and simulated fault fail closed. Feedback has `advisory_only=true`, `automatic_action=false`, and cannot trigger research/update/publish/Workspace/Experience/Skill/Policy/runtime changes.

Observability is a bounded read composition over Event, Trace, Receipt, BuildRun, Stage 2 operation, ArtifactRoute and Page review records. It creates no second authority or operation state. The accepted Stage 4 non-interference harness now excludes this additive observability projection while continuing to compare Search, Ask, core Research, ArtifactRoute Gates and open-corpus results exactly.

## 5. Mechanical evidence

### Compact six-case Stage 5 matrix

`tests/test_v5_b_stage5_product_closeout.py`: `6 passed`.

1. direct reuse, restart-stable closeout, Page/Route feedback duplicate and public API/UI;
2. incremental child research, reused/new lineage and unchanged explicit-publish boundary;
3. no-hit seed, unsafe-direct rejection, candidate-only context and no canonical mutation;
4. shared-current and confirmed-conflict navigation, backlink/L1/limit/fail-closed semantics;
5. exact-hash/cross-task/payload/fault fences with no Event/Receipt orphan;
6. schema-14 zero-table proof and seeded Workspace + Feedback non-interference across Search/Ask/core Research/ArtifactRoute/open retrieval.

### Directed and affected regression

```text
Stage 1–5 directed: 35 passed
Affected Search/Ask/Research/ArtifactRoute/Page/Workspace/library/taxonomy: 241 passed
```

Affected coverage includes public Search and Ask APIs, V5-A Stage 1–4 Research, V5-B Stage 1–5, library and taxonomy. All migration/reentry/fault fixtures used pytest temporary databases.

### Default no-provider submission run

```text
1721 passed, 4 deselected, 1 warning in 434.96s
```

This was the only default filtered no-provider suite run at the Stage 5 submission boundary. The four deselections are the configured `external_artifact`/`live_provider` exclusions; the warning is the existing Starlette/httpx deprecation warning.

### Static validation

- Python `py_compile`: passed;
- `node --check src/shiliu/static/research.js`: passed;
- `git diff --check`: passed;
- Decision Ledger JSONL/docs references: pending final validation.

## 6. Provider evaluation

`not_exercised`, USD 0. Mechanical cases answered the concrete product question—whether the two paths preserve distinct authority/mutation behavior—without a model judgment. A DeepSeek A/B run would add subjective output but no mechanical authority, so no credential reference, Keychain access, network Provider call or retry was performed.

## 7. Live DB non-action window

Live path: `/Users/elliot/Library/Application Support/Shiliu/shiliu.db`.

```text
before_sha256=99ff1cfe03c44621f4d378f5832572c92ae7dd3764bf767543102dcc0b07867a
before_size=94588928
before_mtime=2026-08-09T16:00:55+0800
after_sha256=99ff1cfe03c44621f4d378f5832572c92ae7dd3764bf767543102dcc0b07867a
after_size=94588928
after_mtime=2026-08-09T16:00:55+0800
```

The Session uses file hash/stat only and does not open live SQLite, call `Database.initialize()`, migrate schema or mutate content. An existing local `shiliu serve` process was visible before the window; it was not stopped or modified. Equality of the final hash is the Stage 5 non-action evidence; if external activity changes it, the window will be classified honestly rather than asserted clean.

## 8. Failure and limitation classification

```yaml
core_failure: none_at_report_preparation
bounded_limitation:
  - relations_are_per_task_published_page_navigation_not_corpus_wide_graph
  - relation_projection_limit_is_8_per_page
implementation_failure: none_at_report_preparation
provider_failure: not_applicable_provider_not_exercised
infrastructure_invalid: none_at_report_preparation
not_exercised:
  - optional_DeepSeek_product_comparison
  - live_DB_migration_backup_smoke
  - manual_relation_annotations_or_draft_preview
unproven:
  - subjective_provider_rubric_quality_on_real_user_cases
  - large_real_corpus_relation_latency_beyond_bounded_temp_fixtures
  - multi_process_UI_polling_order_beyond_database_fences
```

The known V5-A compound-query retrieval limitation was not encountered as a Stage 5 blocker and was not modified.

## 9. Preliminary V5-C Entry Gate evidence

Stage 5 provides preliminary, not self-accepted, evidence for Main to evaluate:

- the full V5-B lifecycle has one public Workspace journey and mechanical no-provider coverage;
- user/corpus Workspace records remain stored/displayed but non-interfering;
- relations and feedback remain advisory/non-authoritative;
- two route paths preserve L1/Candidate/publish boundaries and durable lineage;
- schema remains 14 with zero Stage 5 migration delta;
- V5-C personalization behavior, prompt/budget changes and proactive use remain absent.

This does not authorize V5-C. Main must accept Stage 5 and V5-B, own Program closeout, and decide any V5-C Entry Gate.

## 10. Requested Main decisions

V5-B requests one limited version-level review of the integrated commit:

1. accept or return Stage 5 implementation against Contract `5b7c96c…`;
2. accept or return V5-B version completion and preliminary V5-C Entry Gate evidence;
3. if accepted, perform Main-owned Program state/ledger/Registry updates, merge and version-level Git;
4. separately decide live backup/migration/smoke and any V5-C/V5-D authorization.

No push, merge, tag, live migration, Provider call, V5-C/V5-D implementation or self-acceptance was performed.
