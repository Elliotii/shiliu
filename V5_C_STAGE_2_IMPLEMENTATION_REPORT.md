# 拾流 V5-C Stage 2 Integrated Implementation Report

```yaml
report_status: complete_pending_limited_v5_main_acceptance
stage: V5-C Stage 2
title: Corpus-aware Search
report_date: 2026-08-10
execution_branch: codex/v5-c
stage_starting_commit: 20aca5b726c0c5585f5066e72778b30dcc2f32b5
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
main_contract_acceptance_and_implementation_authority: 108d28bac218d76c84e4279f10791f4d902fe115
implementation_commit: git_commit_containing_this_integrated_report
contract_status: accepted_by_v5_main
implementation_status: complete_pending_v5_main_acceptance
self_accepted: false
schema_source_version: 14
schema_table_index_migration_delta: 0
dependency_prompt_provider_background_worker_delta: 0
live_database_access_this_stage: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
stage_3_entered: false
```

> Main authority `108d28b` 仅作只读引用，没有 cherry-pick/merge 到 `codex/v5-c`。本报告与实现位于
> 同一个 Commit，文件不能稳定自引用最终 hash；实际 Commit 由 final handoff 报告。Program Current
> State 与 Program Decision Ledger 未修改。

## 1. 实现结果

Stage 2 在现有 Product Search 交付一个 task-scoped、用户可关闭且可解释的 Corpus soft-prior 展示纵切：

```text
original query/mode/filters/scope
        └── existing planner/raw retrieval/consolidated baseline pool (unchanged)
                    ├── reserved open lane + highest nonmatch counterexample
                    └── current task-scoped snapshot-bound corpus matches
                                  ↓
                     deterministic bounded presentation composition
                                  ↓
                  lane/rank/hash explanation + per-request off
```

原 query、normalized query、mode、filters、scope、planner、raw top-k、retriever、raw hits、scores、fallback、
index identity、Evidence windows 和 consolidated candidate pool 都先按现有路径独立执行。Corpus 只在该 pool
内影响最多 `floor(N/2)` 个展示槽；至少 `ceil(N/2)` 个槽保留 open lane，最高 baseline corpus-nonmatching
结果保留为 `open_counterexample`。无合法可重排 match 时保持 baseline。

## 2. Authority 与 fail-closed projection

新增且仅新增一个只读 `CorpusSearchContextProjection`：

- policy：`v5-c-stage2-corpus-search-v1`；
- 只读取请求显式给出的 existing Research Task，不扫描其他 Task 或猜测最近 Task；
- 当前 operation principal 必须与 Workspace revision 的 `principal_id` 完全一致；
- 只消费 effective head 为 `current`、kind 为 `corpus_observation`、authority 为 `corpus_soft_prior` 的记录；
- payload 必须是 exact `observation_type/value`，type 必须属于现有 frozen-card 可重验白名单；
- source refs 必须恰好绑定一个 taxonomy snapshot；Workspace source/content hash、snapshot boundary/hash、
  frozen stored/discovery card hash、card count 与 discovery eligibility 都在读取时重验；
- query relevance 与 card match 仅使用 deterministic NFKC/casefold exact phrase/token overlap，不使用模型、
  embedding、alias 推断或 transcript text；
- absent/no prior/unrelated/terminal 返回 baseline；disabled 返回 baseline 且不写 Workspace；principal mismatch、
  malformed、conflict、snapshot/card/boundary drift 以 `fail_closed` explanation 返回同一 baseline；
- Context 与 Result 分别产生 versioned deterministic hash；每个 corpus contribution 列出 Workspace record/
  revision、snapshot ID/hash、cue type/value、baseline/displayed rank。

所有 context 与 contribution 均明确：`citation_authority=false`、`verifier_authority=false`、
`fact_authority=false`、`hard_filter=false`、`route_authority=false`。Corpus 不新增、删除 raw candidate，不改
Evidence/Citation/currentness，不进入 Ask/Research/ArtifactRoute/Stage 1 projection。

## 3. 用户可见 surface 与控制

复用既有 `/api/search` 与 Search 页面：

- optional `corpus_task_id` 提供显式 Task context；legacy request 序列化在不使用新字段时保持原 shape；
- `corpus_aware=false` 是单次关闭，不写 personal state；
- response 增加 `corpus_context` 与 `result_contributions`；
- UI 展示 baseline/applied/disabled/fail-closed 状态、open/corpus/counterexample lane、原/display rank 及完整
  soft-prior explanation；
- persistent correct/invalidate/tombstone 继续复用 existing Workspace append-only decision，restore 是新 revision；
- Workspace authority 文案更新为 Stage 1 answer + Stage 2 task-scoped Search presentation-only，单独的
  Workspace GET 不声称某条 corpus record 已对某个 query 生效。

## 4. Lean diff scope

### Product files：7

- `src/shiliu/retrieval/corpus_search.py`：唯一 read-only projection 与 bounded composition；
- `src/shiliu/retrieval/product_search.py`：在 unchanged consolidated pool 后接入可选 composition；
- `src/shiliu/web.py`：只有显式 Task context 时传入 current principal；
- `src/shiliu/research/personal_workspace.py`：更新已过时的 product authority 描述；
- `src/shiliu/templates/search.html`、`src/shiliu/static/search.js`、`src/shiliu/static/search.css`：复用 Search
  surface 提供 Task context、off、lane 与 explanation。

### Test files：2

- `tests/test_v5_c_stage2_corpus_aware_search.py`：Stage 2 paired/authority/non-interference matrix；
- `tests/test_search_page.py`：静态资源 cache version 与新增 UI shape 的 existing harness 同步。

### Version docs：3

- 本报告；
- `V5_C_CURRENT_STATE.md`；
- `V5_C_DECISION_LEDGER.md`。

```yaml
new_tables_indexes_migrations: 0
schema_version_change: 0
new_authority_stores: 0
read_only_projection_adapters: 1
new_endpoint_types: 0
new_dependencies: 0
new_prompt_or_provider_calls: 0
new_background_workers_or_schedulers: 0
new_vector_reranker_graph_eval_telemetry_platform: 0
```

没有修改 Contract/Charter、Program authority、Prompt、Provider、ASR/Translation、Ask、Research runner、
ArtifactRoute gate、schema/migration/dependency 配置。

## 5. Paired mechanical matrix

| Case | Observed result |
| --- | --- |
| no Task / no prior | 原 baseline order；`no_corpus_task_context` / `no_current_corpus_prior` |
| valid treatment | raw plan/hits/pool 相同；只重排 bounded display slots并解释 |
| disabled | 与 baseline 相同；Workspace durable write count 为 0 |
| unrelated | 与 baseline 相同；`unrelated_corpus_prior` |
| wrong kind / unconfirmed source | 不进入 corpus consumer，baseline |
| invalidated / tombstoned | terminal head 不生效，baseline |
| correction / restore | 新 append-only revision 生效；旧终态不复活 |
| malformed / same-key conflict | `fail_closed`，baseline |
| wrong principal | `fail_closed`，baseline |
| snapshot hash / boundary drift | 只读重验失败，`fail_closed`，baseline |
| counterexample | 最高 baseline nonmatch 保留；open slots 至少一半 |
| explicit mode/filter | lexical mode 与 uploader filter 的 raw plan/calls/hits 与 treatment 前一致 |
| duplicate/restart | selected IDs 去重；context/result hash 与 order 稳定 |
| no-task Search | legacy response 的决定性 Search 内容保持稳定 |
| Ask / Research / ArtifactRoute | treatment 前后稳定；ArtifactRoute open lane/hard-filter boundary 不变 |
| Stage 1 | `PersonalizationContext` 前后稳定；confirmed answer presentation 不受影响 |

fixture/temp DB 只证明 mechanics，不代表 live 用户偏好或收益。

## 6. 验证证据

### Directed / affected

- Stage 2 directed matrix：`4 passed`；
- Stage 2 + existing Search UI：`11 passed`；
- Stage 2 + V5-B Workspace + Stage 1：`14 passed`；
- 既有 Search/Product/Ask/Research/ArtifactRoute/Stage 1 受影响集合：`114 passed`；
- 完整默认 no-provider：`1729 passed, 4 deselected, 7 warnings`；
- `py_compile`、`node --check`、`git diff --check`：通过。

完整套件 warnings 仅为既有 Starlette/httpx 与 multiprocessing fork deprecation。第一次完整复跑只发现
两个既有 Search page harness 仍冻结旧 JS asset version/旧单行字符串。同步 JS/CSS cache version 与行为
断言后，同一 Search UI + Stage 2 集合 `11 passed`，完整套件再跑为上述全绿结果；该普通 harness 修正未
建立 Gate/Amendment。

## 7. Live DB、JIT 与未证明项

Main authority 明确禁止本 Stage 访问 live DB，因此本轮没有打开、查询、写入或 hash live DB，也没有
声称 Stage 1 的历史 hash 是当前观测。Stage 1 已接受现场记录仍为 schema 14，且当时 Research/Feedback/
Workspace 是 cold start；Stage 2 fixture 不能改变这一证据边界。所有测试均使用 temp DB。

本地 accepted Workspace/snapshot/Product Search/ArtifactRoute 证据足以实现 Contract；没有具体材料性
缺口，因此未访问外部网络、未新增 upstream report/adoption proposal、未下载上游、未引入依赖或复制
source/test/prompt/UI。实现为 Shiliu-native reimplementation。

未证明：真实用户 Corpus prior 的质量收益、真实集合 recall/latency/counterexample 体验、large Workspace
与多进程 ordering、Provider 主观质量、Personalized Routing、Progress/Staleness/Delta/Radar、独立
Translation route，以及 V5-A compound long-query limitation。

## 8. Main 有限验收请求

请 V5 Main 只验收：

1. unchanged independent retrieval 与 bounded presentation composition；
2. task/principal/snapshot authority、open-slot/counterexample invariant 与 fail closed；
3. explanation/off/correct/terminal/restore-as-new；
4. Search/Ask/Research/ArtifactRoute/Stage 1 non-interference；
5. 零 schema/dependency/Prompt/Provider/platform 增量与测试证据。

本 Session 不自我接受 Stage 2，不请求 live migration/mainline/push/merge/tag，不进入 Stage 3。提交后停止，
等待 Main 有限验收。
