# 拾流 V5-C Stage 4 Integrated Implementation Report

```yaml
report_status: complete_pending_limited_v5_main_acceptance
stage: V5-C Stage 4
title: Knowledge Progress and Bounded Assistance
report_date: 2026-08-10
execution_branch: codex/v5-c
stage_starting_commit: 55d8e403bd19049534ddb8b4a6078f0ed1e4b457
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
accepted_stage_2_baseline: 95749a1d557dbbb51383b58821519e0524227566
accepted_stage_3_baseline: 68e704e56bc0ba99de0506e9e2b93176b5c978a9
main_contract_acceptance_and_implementation_authority: 3a085c5e082a522c0c3b46cad686b60a0fc2674d
main_decision: V5D-20260810-029
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
stage_5_entered: false
```

> Main authority `3a085c5e082a522c0c3b46cad686b60a0fc2674d` 仅作只读引用，没有 cherry-pick/merge
> 到 `codex/v5-c`。本报告与实现位于同一个 Commit，不能稳定自引用最终 hash；实际 Commit 由 final handoff
> 报告。Program Current State 与 Program Decision Ledger 未修改。

## 1. 实现结果

Stage 4 在 existing Research Task/Workspace response 与页面交付一个 request-time、pull-only、bounded
Knowledge Progress & Assistance panel：

```text
current-principal Workspace heads
        + persisted Fact/Artifact/Page lineage
        + explicit immutable taxonomy snapshot pair/current preview
        + managed current transcript + lexical sync identity
                              ↓
          one read-only fail-closed projection
                              ↓
 progress(≤5) / staleness(≤2) / delta(≤3) / radar(≤1)
          explanation + off/session dismiss + explicit durable dismiss
               (all product/execution authority false)
```

Panel 本身不持久化 card，不调 Provider，不启动 Search/Research/ASR/background task，也不修改 Fact、Page、Profile、
Prompt、Route、Skill 或 accepted consumer。

## 2. Progress：显式 mastery 与 activity observation

Existing `progress_observation` validator 只新增 `mastered` 到与 learned/understood/familiar 相同的
self-assessment 白名单。四个 mastery state 都必须是 exact `{topic,state,user_asserted:true}`、零 inferred refs、
current principal、`user_authored|user_confirmed/current` 才显示。

Evidence-linked observation 必须是 task-scoped current source refs、`evidence_backed_observation/current`、exact
`{topic,state,observation_type}`，且 observation type 与 non-mastery state 都在 Contract 白名单。watched、searched、
collected、transcript availability、research activity 或 fact status 无论出现多少次都不会转成 mastery。

## 3. Staleness、Collection Delta 与 Radar

Staleness adapter 直接读取 existing `research_knowledge_fact_states` 及 current Artifact/Page fact links。它不调用
可能 ensure/write initial heads 的 lifecycle projection，不执行 revalidation；card 只报告 persisted
lifecycle/currentness、affected lineage 与 exact source refs。

Collection Delta 必须同时提供 baseline/current frozen snapshot ID：

- selected source IDs 必须完全相同；
- snapshot row、stored card、discovery view 与 aggregate hash 全部重验；
- current snapshot 必须与本次 read-only `taxonomy.preview` hash 相同；
- 只生成 deterministic added/removed/changed observation；缺一 snapshot、跨 scope、malformed 或 preview drift
  返回该 lane fail closed。

Radar 只从 verified `added` item 中选一条，并要求 exactly one current-principal confirmed/user-authored Focus、managed
raw transcript/ASR file、matching video path、current lexical sync identity，以及 Focus 对 Evidence excerpt 的
NFKC/casefold exact phrase/token overlap。Candidate identity 绑定 Focus revision/content hash、snapshot delta、content
key、video active revision、raw subtitle SHA-256 与 sync state version。Title/description/summary 不参与 relevance
判定；无 Focus、candidate/unconfirmed Focus、conflict、无 current transcript、无 exact match 或 drift 均保持 baseline。

## 4. Explain、dismiss、expiry 与 no-resurrection

Response 给出 lane status/reason、card/candidate/boundary/context hash、source refs、truncated count 与全部 false authority。
页面支持 request off、snapshot pair、refresh、session dismiss 和 durable dismiss expiry：

- off/page load/refresh/session dismiss 不写 DB；
- durable dismiss 只有用户点击才 POST existing Workspace create endpoint；
- exact control 复用 `progress_observation`，payload 为 topic/state/user_asserted/control/dismissed/candidate_id/
  candidate_kind/boundary_hash；不新建 record kind/table；
- server 与 projection 都重验 current principal、exact payload、current fact/artifact/snapshot source hashes 与 matching
  candidate boundary；
- unexpired `dismissed=true` 抑制 exact candidate；expiry 到期恢复；tombstoned old boundary 继续抑制；显式
  `correct` 为 `dismissed=false` 的新 revision 才恢复；new Evidence/snapshot/Focus boundary 形成新 ID，不被旧 control
  跨 boundary 静默屏蔽；
- assistance control 被明确排除在 progress/mastery display 之外，也不获得其他产品 authority。

## 5. Lean diff scope

### Product files：8

- `src/shiliu/research/knowledge_assistance.py`：唯一 read-only Stage 4 projection；
- `src/shiliu/research/personal_workspace.py`：`mastered` 窄扩展与 exact assistance control/principal validation；
- `src/shiliu/research/knowledge_service.py`、`src/shiliu/app.py`：在 existing Workspace response additive 接入；
- `src/shiliu/web.py`：existing Workspace GET 增加 request-local assistance/snapshot inputs；
- `src/shiliu/templates/research.html`、`src/shiliu/static/research.js`、`src/shiliu/static/research.css`：bounded panel、
  explanation、off/session/durable controls。

### Test files：1

- `tests/test_v5_c_stage4_knowledge_assistance.py`：Stage 4 paired/authority/restart/API/UI/zero-write matrix。

### Version docs：3

- 本报告；
- `V5_C_CURRENT_STATE.md`；
- `V5_C_DECISION_LEDGER.md`。

```yaml
new_tables_indexes_migrations: 0
schema_version_change: 0
new_record_kinds_or_authority_stores: 0
read_only_assistance_projections: 1
existing_progress_enum_additions: [mastered]
new_endpoint_types: 0
new_dependencies: 0
new_prompt_or_provider_calls: 0
new_background_workers_schedulers_notifications: 0
new_rules_generic_inbox_telemetry_eval_agent_loop_platform: 0
```

## 6. Paired mechanical matrix

| Case | Observed result |
| --- | --- |
| cold baseline | 四 lane empty baseline；projection/load 零写 |
| explicit progress | user-asserted mastered 显示为 mastery |
| watched-not-learned | watched 只显示 observation；mastery 集合不增加 |
| valid staleness | persisted stale Fact + current Artifact/Page lineage 形成一张 candidate；Fact 状态不变 |
| valid collection delta | same-scope snapshot pair + current preview 形成 bounded added observation |
| candidate/no-focus/unrelated | Delta 可独立显示；Radar baseline，candidate Focus 无 authority |
| Radar treatment | confirmed Focus + added item + current transcript exact token match 形成一条 candidate |
| drift | current preview 与 frozen current snapshot 不同，Delta fail closed、Radar baseline |
| disabled | whole panel disabled；Workspace/Event/Receipt counts 不变 |
| session dismiss | 仅 browser session Set 隐藏；不 POST |
| durable dismiss | 只有 click handler POST exact existing Workspace endpoint |
| expiry | expired control 不抑制 exact candidate |
| tombstone/no-resurrection | tombstoned old boundary 保持隐藏 |
| correct/restore-as-new | `dismissed=false` append revision 恢复；历史保留 |
| restart/dedup | card order/IDs/context hash 稳定；零 duplicate authority |
| Stage 1–3/Workspace/Lifecycle | affected matrix 全绿；accepted behavior 与 execution contracts 不变 |

Fixture/temp DB 只证明 mechanics，不代表 live 用户掌握、Focus、兴趣或真实帮助收益。

## 7. 验证证据

- Stage 4 directed matrix：`4 passed`；
- Stage 4 + affected V5-B Workspace/Lifecycle + accepted Stage 1–3：`31 passed`；
- existing Stage 1 Node DOM non-interference：`2 passed`；
- `py_compile`、`node --check`、`git diff --check`：通过；
- warnings：仅既有 Starlette/httpx deprecation。

按 accepted Contract 的测试优化纪律，本 Stage 没有修改 schema/migration/dependency/Prompt/Provider 或 execution
shared core，未出现材料共享核心风险，因此未运行完整 default no-provider suite；完整套件保留到 V5-C closeout。

## 8. Live DB、JIT 与未证明项

Main authority 明确禁止 Stage 4 访问 live DB，因此本轮没有打开、查询、写入或 hash live DB；live hash 为
`not_observed_by_authority`。Main 在 Stage 3 验收窗口记录的历史 hash
`d07037d112c3835e0c2ceb06fd165596a16934684c540610958bd920183c0ce9` 仅作历史 evidence，不冒充本轮观测。

本地 accepted evidence 已关闭实现缺口；没有 external JIT、upstream report/adoption proposal、网络访问、下载、
新依赖或 source/test/Prompt/UI copy。未访问 Provider 或 credential/Keychain。

未证明：真实用户 progress/radar 帮助收益、Focus-to-Evidence relevance quality、真实 collection delta 规模/延迟、
large Workspace/multi-process ordering、Provider 主观质量、distinct Translation route 与 Stage 5 integrated journey/
evaluation。

## 9. Main 有限验收请求

请 V5 Main 只验收：

1. explicit mastery 与 evidence-linked non-mastery observation 的严格分离；
2. persisted Staleness、same-scope Collection Delta 与 current-preview fail-closed boundary；
3. confirmed Focus + verified added delta + current transcript/index identity 的 bounded Radar；
4. request/session off、explanation、exact durable dismiss、expiry/tombstone/correct/no-resurrection；
5. Stage 1–3、Workspace/Lifecycle 与非个性化 consumer non-interference；
6. 零 schema/dependency/Prompt/Provider/background/platform 增量与 directed + affected evidence。

本 Session 不自我接受 Stage 4，不请求 live migration/mainline/push/merge/tag，不进入 Stage 5。提交后停止，等待
Main 有限验收。
