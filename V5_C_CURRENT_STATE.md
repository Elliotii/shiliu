# 拾流 V5-C Current State

```yaml
document_status: stage_4_implementation_complete_pending_v5_main_acceptance
version: V5-C
updated_at: 2026-08-10
execution_branch: codex/v5-c
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
accepted_stage_2_baseline: 95749a1d557dbbb51383b58821519e0524227566
accepted_stage_3_baseline: 68e704e56bc0ba99de0506e9e2b93176b5c978a9
accepted_stage_4_contract: 55d8e403bd19049534ddb8b4a6078f0ed1e4b457
main_stage_4_contract_authority: 3a085c5e082a522c0c3b46cad686b60a0fc2674d
main_stage_4_contract_decision: V5D-20260810-029
active_formal_stage: V5_C_stage_4_implementation_pending_main_acceptance
stage_1_status: accepted_by_v5_main
stage_2_status: accepted_by_v5_main
stage_3_status: accepted_by_v5_main
stage_4_contract_status: accepted_by_v5_main
stage_4_implementation_status: complete_pending_v5_main_acceptance
stage_4_self_accepted: false
stage_5_entered: false
schema_source_version: 14
schema_table_index_migration_delta: 0
live_database_access_this_stage: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
external_JIT_research_performed: false
```

## 1. Authority 与 accepted baseline

V5 Main 在 `codex/v5-main@3a085c5e082a522c0c3b46cad686b60a0fc2674d` / Decision
`V5D-20260810-029` 接受 Stage 4 Contract
`55d8e403bd19049534ddb8b4a6078f0ed1e4b457`，无 bounded docs rework，并授权同一 V5-C Session 实施
Knowledge Progress and Bounded Assistance。Main authority 仅只读引用，没有 cherry-pick/merge 到执行分支。

Stage 1–3 accepted baseline 保持不变。本轮只实施 Stage 4 frozen vertical slice，不进入 Stage 5，不修改 Program
Current State/Ledger，不访问 live DB、Provider 或 credential/Keychain，不 push/merge/tag，也不自我接受。

## 2. Stage 4 实现状态

Existing Research/Workspace surface 现在 additive 返回并展示一个 request-time、pull-only
`KnowledgeAssistanceProjection`：

- Knowledge Progress：`learned|understood|mastered|familiar` 仅接受 current principal 的 exact
  `user_asserted=true` user-authored/user-confirmed record；watched/searched/collected/transcript/research activity
  仍是 evidence-backed observation，永不进入 mastery；
- Staleness：直接只读 existing persisted Fact state 与 current Artifact/Page fact lineage，最多两张 card；不调用会
  ensure initial heads 的 high-level lifecycle projection，也不 revalidate 或修改 Fact/Page；
- Collection Delta：仅对用户本次给出的 same-scope immutable baseline/current taxonomy snapshots，在逐卡 hash
  与 current read-only preview 重验通过后形成最多三条 added/removed/changed observation；
- Early Project Radar：每次最多一条；必须有 exactly one confirmed Current Focus、verified added delta、managed
  current raw transcript/ASR file、current lexical sync identity 与 deterministic NFKC/casefold exact token/phrase match；
  title/description/summary 不能单独触发；
- Control：off/page load/refresh/session dismiss 零写。Durable dismiss 只在用户点击时通过 existing Workspace
  endpoint 追加 exact `progress_observation` control；projection 重验 principal、payload、current source hashes 与
  matching candidate boundary；expiry 恢复，tombstone 阻止 old boundary 自动复活，corrected `dismissed=false`
  以新 revision 恢复。

`mastered` 是唯一 existing enum 窄扩展。没有新 schema/table/index/migration、record kind、authority store、endpoint
type、dependency、Prompt、Provider、background worker、scheduler、notification、rules、generic inbox、telemetry、
eval 或 agent loop。

## 3. Authority 与 non-interference

Projection 的 authority 均为 presentation/candidate only：

- Workspace revision 仍是唯一 durable user-state authority；projected card 默认不持久化；
- activity、collection、transcript presence 与 Research action 不代表用户理解或兴趣；
- Staleness 只是 persisted revalidation candidate，不是 Verifier 结论；Delta 只是 collection observation；
- Radar 不创建/运行 Research，不自动 Search/ASR/Provider，不修改 Profile、Prompt、Route、Skill、Fact 或 Page；
- Citation、Verifier、Search baseline、Stage 1 answer presentation、Stage 2 Corpus composition、Stage 3 advisory routing
  与 Fast/Deep/Research/ArtifactRoute/ASR execution contracts 未改变；
- absent/incomplete/malformed/conflicting/expired/drifted/unsafe input deterministic baseline 或 fail closed。

## 4. Directed + affected evidence

所有测试均为 temp DB/no-provider：

- Stage 4 directed matrix：`4 passed`；
- Stage 4 + affected V5-B Workspace/Lifecycle + accepted Stage 1–3：`31 passed`；
- existing Stage 1 Node DOM non-interference：`2 passed`；
- `py_compile`、`node --check`、`git diff --check`：通过；
- warning 仅为既有 Starlette/httpx deprecation。

按 Main 冻结的优化纪律，本 Stage 没有材料共享核心风险，因此没有重复完整 default no-provider suite；完整套件保留
到 V5-C closeout。

## 5. Live/JIT 与未证明项

Main 明确禁止本 Stage 访问 live DB，因此没有打开、查询、写入或 hash live DB；本 Stage live hash 为
`not_observed_by_authority`。Main 在 Stage 3 验收窗口记录的历史 hash
`d07037d112c3835e0c2ceb06fd165596a16934684c540610958bd920183c0ce9` 不冒充本轮观测。Fixture/temp DB 仅证明
mechanics，不证明 live 用户掌握、Focus、collection delta 或帮助收益。

本地 accepted evidence 足以实现，无材料性外部 JIT、upstream report/adoption proposal、网络浏览、下载、新依赖或
source/test/Prompt/UI copy。

未证明：真实用户 progress/radar 帮助收益与 relevance quality、真实 collection delta 规模/latency、large
Workspace/multi-process ordering、Provider 主观质量、distinct Translation route，以及 Stage 5 integrated
journey/evaluation。

下一动作仅为等待 V5 Main 对 Stage 4 implementation 做有限验收。Main 接受前不进入 Stage 5，不做 live
migration/mainline/push/merge/tag 或自我接受。
