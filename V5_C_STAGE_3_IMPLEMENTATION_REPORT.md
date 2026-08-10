# 拾流 V5-C Stage 3 Integrated Implementation Report

```yaml
report_status: complete_pending_limited_v5_main_acceptance
stage: V5-C Stage 3
title: Personalized Routing
report_date: 2026-08-10
execution_branch: codex/v5-c
stage_starting_commit: 4368f39c90767f29ffb38efcafe4533be3aa816f
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
accepted_stage_2_baseline: 95749a1d557dbbb51383b58821519e0524227566
main_contract_acceptance_and_implementation_authority: 87179ea94f513126d830301c8ec4a5d10d0ecda9
main_decision: V5D-20260810-027
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
stage_4_entered: false
```

> Main authority `87179ea94f513126d830301c8ec4a5d10d0ecda9` 仅作只读引用，没有 cherry-pick/merge
> 到 `codex/v5-c`。本报告与实现位于同一个 Commit，不能稳定自引用最终 hash；实际 Commit 由 final handoff
> 报告。Program Current State 与 Program Decision Ledger 未修改。

## 1. 实现结果

Stage 3 在既有 Research Task/Workspace surface 交付一个 task-scoped、advisory-only 的 “Next path
recommendation” panel：

```text
confirmed task/principal-bound default-path preference
                         +
explicit current choice / request-local permission and cost
                         +
existing ArtifactRoute / Ask / Research / exact-video ASR state
                         ↓
             read-only fail-closed projection
                         ↓
 recommendation + reason + capability matrix + inert CTA
              (execution authority always false)
```

唯一 preference key 是 `research.routing.default_path=fast|deep|research`。它只为推荐展示提供理由，不改
UI selection、Ask mode、request payload、query/filter、Research budget、permission 或 execution authority。
无 confirmed preference 时保持 baseline。

## 2. 真实 capability 与 precedence

Projection 只承认已有 capability：

- ArtifactRoute `direct_reuse|incremental_refresh|research_seed`；
- Ask `fast|deep`；
- explicit durable Research；
- exact-video manual ASR prerequisite。

新增的 ArtifactRoute read-only assessment method 从 sole active assessment 读取 persisted query/retrieval/gates，
重验 independent open lane、hard-filter=false 与既有 late authority fence；不 proceed、不写 route。安全的现有
ArtifactRoute gate 优先于 Profile：direct 只建议聚焦已有 route control，incremental/seed 还必须满足本次
durable-cost permission。stale/currentness/citation/coverage/open-lane/hash drift 返回 fail closed。

Fast 需要本次 `allow_provider_answer=true`；Deep 还需要 `allow_high_cost_or_durable=true`；Research 与
incremental/seed 需要 durable-cost permission。manual ASR 必须有 exact video、缺 current transcript、无 active
job 且本次明确允许；projection 只查状态，不读 Keychain/credential、不 POST、不创建 job。

distinct Translation route 不存在，response 明确显示
`translation.status=not_implemented` / `reason=not_a_distinct_route`，没有伪造 route。

## 3. 显式选择、explanation 与控制

Workspace GET 的 additive request-local inputs 默认全部拒绝权限：

```yaml
routing_enabled: true
current_explicit_path: null
allow_provider_answer: false
allow_high_cost_or_durable: false
allow_manual_asr: false
asr_video_id: null
```

当 `current_explicit_path` 非空时，panel 返回 `overridden`、`explicit_choice_preserved=true`，不会改 DOM 或
request。session off 返回 `disabled` 且零 Workspace write。Context 显示 Task/Goal、preference record/revision/
version/content hash、settings、各 capability status、reason code、context hash 和全部 false authority 标记。

CTA 均为惰性：Fast/Deep 只链接到既有 `/ask` query/mode prefill；ArtifactRoute/Research button 只 scroll/focus
已有 control；manual ASR 只打开 exact transcript inspection。CTA handler 不调用 `fetch`、`.click()`、Provider、
Research create/run、ArtifactRoute proceed 或 ASR endpoint，真实执行仍需用户在既有 control 明确操作。

## 4. Fail-closed authority

- 只消费 task-scoped effective head 为 `explicit_memory + user_authored + current` 且 current principal 完全匹配
  的 exact key/value；
- payload/source refs/source boundary/content hash/policy version 在读取时重验；
- candidate/unconfirmed、unrelated Profile、Current Focus、Corpus、Experience 与 terminal record 不进入 route
  consumer；
- wrong principal、unknown value、malformed/content drift、多个 confirmed value conflict 返回 fail closed；
- correct/tombstone 使用既有 append-only Workspace decision；terminal revision 不复活；
- preference 明确无 Citation、Verifier、fact、budget、permission、route 或 execution authority；
- provider/task/route/job/background/workspace side-effect counters 固定为 0，并由 temp-DB counts 与调用即失败
  monkeypatch 验证。

## 5. Lean diff scope

### Product files：7

- `src/shiliu/research/routing_recommendation.py`：唯一 read-only recommendation projection；
- `src/shiliu/research/knowledge_reuse.py`：窄的 ArtifactRoute current assessment read-only revalidation；
- `src/shiliu/research/knowledge_service.py`：在既有 Workspace response additive 接入 context；
- `src/shiliu/web.py`：既有 Workspace GET 增加 request-local read-only query inputs；
- `src/shiliu/templates/research.html`、`src/shiliu/static/research.js`、`src/shiliu/static/research.css`：panel、
  explanation、session off/override/permission 与 inert CTA。

### Test files：1

- `tests/test_v5_c_stage3_personalized_routing.py`：Stage 3 paired/authority/non-interference/API/UI matrix。

### Version docs：3

- 本报告；
- `V5_C_CURRENT_STATE.md`；
- `V5_C_DECISION_LEDGER.md`。

```yaml
new_tables_indexes_migrations: 0
schema_version_change: 0
new_authority_stores: 0
read_only_route_recommendation_projections: 1
new_endpoint_types: 0
new_dependencies: 0
new_prompt_or_provider_calls: 0
new_background_workers_or_schedulers: 0
new_general_router_rules_policy_telemetry_eval_budget_platform: 0
```

没有修改 Ask/Research/ASR/ArtifactRoute execution request/endpoint、Prompt、Provider、schema/migration、dependency
配置、Stage 1/2 consumer 或 Program authority。

## 6. Paired mechanical matrix

| Case | Observed result |
| --- | --- |
| cold/no preference | `baseline`；无 recommendation；现有 selection/request 不变 |
| confirmed treatment | exact current preference 只产生 advisory recommendation 与 explanation |
| candidate/unconfirmed | `baseline`；candidate 无 route authority |
| disabled | `disabled`；recommendation none；Workspace writes 0 |
| unrelated Focus/Corpus/Profile | `baseline`；均不能形成 route |
| wrong principal/malformed/conflict/drift | deterministic `fail_closed`；无 recommendation |
| explicit override | `overridden`；exact explicit path 原样保留 |
| safe ArtifactRoute | existing direct gate 优先；open lane/hard-filter/authority hash 保留 |
| stale/unsafe ArtifactRoute | `fail_closed`；profile 不能绕过 late authority fence |
| Fast/Deep provider denial | `blocked`；Provider entry point 未调用 |
| Deep/Research/durable-cost denial | `blocked`；不自动升级、create 或 run |
| transcript already current | manual ASR `inapplicable`；不创建 job |
| ASR denied/uncertain | `blocked`/`fail_closed`；credential 未读取，jobs 0 |
| exact manual ASR | 只建议 prerequisite inspection；jobs/POST/provider/background 0 |
| correct/tombstone | 新 revision 改 treatment；terminal head 回 baseline |
| restart/duplicate | context/reason/order/hash 稳定；零 duplicate write |
| Stage 1/2 + Fast/Deep/Research/ArtifactRoute/ASR | accepted consumers、request 与 durable counts 不变 |

Fixture/temp DB 只证明 mechanics，不代表 live 用户偏好或真实收益。

## 7. 验证证据

- Stage 3 directed matrix：`4 passed`；
- Stage 3 + Stage 1/2：`12 passed`；
- Contract capability + Stage 1/2/3 risk set：`54 passed`；
- 既有 V5-B Workspace harness + Stage 3 定向复跑：`5 passed`；
- 既有 Stage 1 Node DOM non-interference：`2 passed`；
- 完整默认 no-provider：`1733 passed, 4 deselected, 7 warnings`；
- `py_compile`、`node --check`、`git diff --check`：通过。

完整套件首次结果为 `1732 passed, 1 failed, 4 deselected`；唯一失败是既有 V5-B Workspace UI harness 固定
检查旧 baseline authority 文案。保留旧句并追加 Stage 3 exact exception 后，定向与完整套件均全绿。该普通
UI harness 兼容修正未建立 Gate/Amendment。warnings 仅为既有 Starlette/httpx 与 multiprocessing fork
deprecation。

## 8. Live DB、JIT 与未证明项

Main authority 明确禁止 Stage 3 访问 live DB，因此本轮没有打开、查询、写入或 hash live DB；live hash 本轮
为 `not_observed_by_authority`。Main 在 Stage 2 验收窗口记录的
`1ee71d2b8c3a09b8a3d814947d8fb6bab89408d3f19f83f15e275bfc1a9558d5` 仅是历史 evidence，不冒充本轮
观测。所有测试使用 temp DB；fixture 不改变 accepted live cold-start boundary。

本地 accepted evidence 已关闭实现缺口；没有外部 JIT、upstream report/adoption proposal、网络访问、下载、
新依赖或 source/test/Prompt/UI copy。未访问 Provider 或 credential/Keychain。

未证明：真实用户 routing preference 收益、真实 cost/latency/override 质量、ASR recommendation 质量、large
Workspace/multi-process ordering、Provider 主观质量、distinct Translation route、Stage 4
Progress/Staleness/Collection Delta/Early Project Radar。

## 9. Main 有限验收请求

请 V5 Main 只验收：

1. task/principal-bound confirmed preference 与 cold/candidate/unrelated/fail-closed boundary；
2. explicit choice、permission/cost 与 ArtifactRoute authority fence precedence；
3. real capability catalog、manual ASR prerequisite 与 Translation exclusion；
4. advisory explanation/off/override/correct/tombstone、inert CTA 与零自动执行；
5. Stage 1/2、Fast/Deep/Research/ArtifactRoute/ASR non-interference；
6. 零 schema/dependency/Prompt/Provider/platform 增量与测试证据。

本 Session 不自我接受 Stage 3，不请求 live migration/mainline/push/merge/tag，不进入 Stage 4。提交后停止，
等待 Main 有限验收。
