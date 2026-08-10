# Shiliu V5 Program Final Closeout

> Program: Shiliu V5
> Final status: `closed_with_known_limits_and_no_validated_V5_D_candidate`
> Authority: Shiliu V5 Main Codex Session under explicit user Program-closeout authorization
> Closed at: 2026-08-11
> Mainline branch: `codex/v5-main`
> V5-D evidence merge: `2d10844eee564af830bf38b4c792d2834381de63`
> Final authoritative commit: commit containing this closeout and final Program State/Ledger
> Push: not performed
> Tag: not created

---

# 1. Program Decision

Shiliu V5 Program 到此正式结束。V5-A、V5-B、V5-C 的产品目标以各自 accepted known limits 完成；V5-D
完成了受控 improvement/falsification machinery，但两个 Candidate 均被有效拒绝，没有 validated Candidate、
Held-out evaluation、active/shadow policy 或 Stage 3。

```yaml
V5_program:
  final_status: closed_with_known_limits_and_no_validated_V5_D_candidate
  active_subversion: none
  active_formal_stage: none
  further_V5_implementation_authorized: false
V5_A:
  final_status: accepted_with_known_retrieval_limitation
V5_B:
  final_status: accepted_with_known_limits
V5_C:
  final_status: accepted_with_known_limits
V5_D:
  final_status: closed_no_validated_candidate
  validated_candidate: false
```

# 2. Final Repository and Runtime Baseline

```yaml
repository:
  branch: codex/v5-main
  accepted_product_code_head: 8904e27df07becebae13110f9be17cd829373b20
  accepted_product_src_tree: 41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01
  V5_D_accepted_execution_head: 68fd655b3e54ba2529aee8395860ed876ee88c1a
  V5_D_evidence_merge: 2d10844eee564af830bf38b4c792d2834381de63
  V5_D_merge_tree: 1992bffe9cffaeba6356d53f4afd2544c5b504fa
  final_closeout_commit: commit_containing_this_file
  push_status: not_pushed
  tag_status: not_tagged
live_runtime:
  schema: 14
  integrity_check: ok
  foreign_key_violations: 0
  videos: 157
  completed_videos: 140
  sync_runs: 456
  active_sync_runs: 0
  research_tasks: 0
  research_events: 0
  grounded_facts: 0
  knowledge_artifacts: 0
  topic_pages: 0
  workspace_records: 0
  artifact_routes: 0
  database_sha256: 1bf5d8b22bb79c9c5b97a2620aba66ce530de27c6d97a8b2949247e167e697f4
  readonly_smoke: six_of_six_HTTP_200
  web_launch_agent: running
  scheduled_sync_launch_agent: loaded
```

V5-D 没有产品 `src` 或 migration delta，因此 Program Closeout 没有停止服务、迁移数据库或写 live fixture。
只读 smoke 前后 live DB hash 相同。

# 3. V5-A — Durable Recursive Research Runtime

## 3.1 Accepted capabilities

V5-A 将 V4 的一次性 Deep graph 发展为 durable Research Runtime：

- durable `ResearchTask / Goal / Attempt / Checkpoint / Result`；
- owner lease、epoch fencing、restart/recovery 与 idempotent `CommandReceipt`；
- Provider request identity、usage/cost、hard cap 与 side-effect fail-closed；
- EvidenceUse/currentness、inner research state/action/provisional artifact；
- Outer constraint/goal audit、targeted continuation、derivation lineage 与 honest stop；
- HITL InputRequest、ControlRequest/Decision 与受控 resume/cancel；
- Research 产品页面/API、可观察 projection 和 receipt-bound Provider product path。

## 3.2 Stable interfaces

后续版本可以依赖 `ResearchTaskService`、`InnerResearchService`、`OuterResearchService`、
`ResearchControlService`、`ReceiptBoundProviderService`、Research Task/API 与 schema 14 的 durable identity、
receipt、checkpoint、trace、evidence和 control semantics。Harness 或一次性进程内 trace 不能替代这些接口。

## 3.3 Accepted limits

代表性长复合查询在 dense model not ready、lexical fallback 下得到 0 hit，没有 EvidenceUse/Citation 或
grounded completion。该问题仍为 `unclassified_policy_vs_retrieval_infrastructure`，不是 V5-A Runtime 回归，
也没有被 V5-D 证明为 policy failure。真实 SIGKILL/断电、多主机长 soak、production-scale retention 和
更多 Provider/model 组合仍未证明。

# 4. V5-B — Evidence-backed Personal Knowledge and Corpus Workspace

## 4.1 Accepted capabilities

- current Evidence validation 与 lineage-bound Grounded Fact；
- immutable Fact/Artifact/Topic Page revisions，显式 review/publish；
- correction、retire、supersede、conflict、staleness、history/diff/revert；
- durable refresh/revalidation/update operation、retry/recovery/dead-letter/needs-user；
- explainable direct reuse、bounded incremental refresh、research seed 与 ArtifactRoute；
- typed append-only Explicit User、Behavioral/Inferred candidate、Current Focus、Knowledge Progress、Corpus
  soft prior 与 System Experience records；
- bounded related Page navigation、Feedback Event、existing Event/Trace/Receipt-derived observability；
- integrated Knowledge Workspace，同时保持 Search/Ask/Research authority 不变。

## 4.2 Stable interfaces

后续版本可以依赖 `ResearchKnowledgeService`、`ResearchKnowledgeLifecycleService`、
`ResearchArtifactRouteService`、`ResearchPersonalWorkspaceService` 及其 currentness、review、publish、revision、
route、authority-class、append-only correction 和 lineage contracts。Facts/Artifacts/Pages 可以被复用，但只有
current Evidence/Citation authority 能支持事实 Claim；User/Corpus/Experience records 不能升级为事实。

## 4.3 Accepted limits

Page relation 是 per-Task、每页最多 8 条的 navigation-only projection，不是 corpus-wide GraphRAG。大
corpus latency、多进程 UI polling order、optional Provider product comparison 未专项证明。live Research/
Feedback/Workspace/knowledge population 仍为 0，不能宣称已有真实长期知识使用数据。

# 5. V5-C — Personalized Research Agent

## 5.1 Accepted capabilities

- confirmed/revisable Answer presentation 与 `standard|compact` detail behavior；
- task/principal/snapshot-bound Corpus soft prior，只做 bounded Search presentation，并保留 open/counterexample
  lane；
- confirmed preference 形成 advisory-only route recommendation，显式选择、权限、成本与 ArtifactRoute Gate
  优先；
- explicit mastery、activity observation、persisted Staleness、same-scope Collection Delta 与 transcript-bound
  bounded Project Radar；
- pull-only Knowledge Assistance 与 read-only Integrated Journey；
- explain/correct/disable/rollback、principal fence、conflict/drift fail-closed。

## 5.2 Stable authority boundary

`PersonalizationContextProjection`、`RouteRecommendationProjection`、`KnowledgeAssistanceProjection` 与
`IntegratedJourneyProjection` 是只读或 presentation/advisory consumers。Explicit confirmed authority 可以
产生有界效果；inferred/candidate 状态在确认前无 effect。Corpus 不是 Citation/Verifier/hard filter，Profile
不执行 route，activity 不等于 mastery，Radar 不自动 Research，Journey 不自动 Search/Provider/ArtifactRoute。

## 5.3 Accepted limits

Search 仍需用户显式 query；assistance 为 pull-only，无 scheduler/notification/background agent。live 个性化
输入为 cold start，真实用户收益、长期纠错行为、大 Workspace 顺序与 Provider 主观对比未证明；独立
Translation route 未实现。

# 6. V5-D — Controlled Experience-driven Search Policy Improvement

V5-D 的正式结果是 `closed_no_validated_candidate`。它保留了：

- Experience/Trace → repeated Failure Family；
- Step-level Attribution 与 alternative-cause boundary；
- Falsifiable Hypothesis 与 versioned Candidate lifecycle；
- frozen Baseline/Treatment/Evaluator/Experiment identity；
- Provider/token/tool/USD hard-cap accounting；
- implementation/infrastructure invalid-run 与 Candidate-effectiveness failure 分离；
- rejection、promotion protection、sealed Reserve 与 contamination boundary。

Candidate v1.0 在 D02 增加有限 Citation 后仍没有 required-aspect/source-diversity/recovery-stop success，正式
`rejected`。Re-attribution 后的 v1.1 经 R1-E1 合法机械修正，改变了局部 recovery/stop 行为但没有产生
Evidence/Citation/source/aspect improvement，也正式 `rejected`。

Reserve 从未打开、分配或运行；Held-out related/unrelated、negative transfer 与 Stage 3 均未到达。详见
`V5_D_FINAL_CLOSEOUT.md`。

# 7. V5 → Future Version Inheritance Boundary

## 7.1 Stable inherited capabilities

- V4/V5 的 Search、Fast/Deep、Shared Grounding、Evidence/Citation/Verifier 与 shared finalization；
- V5-A durable Task/Goal/Attempt/Checkpoint/Result、goal audit、continuation、HITL、receipt、budget、trace、
  side-effect 与 restart/recovery contracts；
- V5-B Evidence→Fact→Artifact→Topic Page、refresh/revalidation/reuse、ArtifactRoute、Personal/Corpus/Focus/
  Progress/Experience Workspace 与 append-only authority lifecycle；
- V5-C confirmed personalization、Corpus-aware presentation、advisory routing、pull-only progress/staleness/
  assistance/Journey 与 explicit-over-inferred authority；
- V5-D Experiment identity、frozen paired evaluation、budget/invalid-run/contamination/promotion-protection
  methodology as evaluation machinery only。

## 7.2 Accepted known limitations

- V5-A compound-query retrieval/grounded-completion limitation；
- live Research/Knowledge/Feedback/Personalization 数据 cold start；
- large-corpus、multi-process、long-soak、真实用户 benefit 与部分 Provider comparisons 未证明；
- V5-B relations 非 corpus-wide graph；
- V5-C 无 background proactive execution，Search/route/assistance 仍受显式用户 authority 控制。

这些限制可作为未来输入，但不是 V5 未完成返工项，也不自动成为下一版本 backlog。

## 7.3 Closed experiments / negative evidence

- Candidate v1.0 rejected；
- Candidate v1.1 rejected；
- 单纯阻止 repeated search 或增加有限 Evidence/Citation，不足以证明 grounded Outcome 改善；
- Candidate 的局部 behavior change 不等于可泛化 Skill；
- frozen scaffold invalid run 必须与 Candidate failure 分离，不能在观察结果后热改并复用同一实验。

未来若提出相同 Candidate，必须说明如何面对这些 falsification；不得把 rejected artifact 注册为产品默认。

## 7.4 Deferred / reusable ideas

- Long-term Research Threads；
- Full Project Radar；
- Background Knowledge Maintenance；
- Optional Reviewer（继续 Eval-gated）；
- GraphRAG（继续 Eval-gated）；
- Youtu-Agent、SkillOS、MUSE 等未采用的 Candidate/asset patterns；
- compound-query Query Decomposition/Rewrite 等，需要先重新区分 policy 与 retrieval implementation failure。

Deferred 不表示永久无价值，也不构成下一版本 requirement。

## 7.5 Explicitly unproven claims

README、简历、面试和未来规划不得把以下内容写成已证明：

- V5-D validated Search Skill、related-task generalization、unrelated regression 或 negative-transfer safety；
- active/shadow self-improving policy、stable autonomous self-evolution；
- V5-C stable real-user personalization benefit；
- live 长期知识积累或 background companion behavior；
- GraphRAG、多 Agent Reviewer、长期 proactive Project Radar；
- 任意长复合查询稳定 grounded completion；
- production-scale multi-process/host reliability。

# 8. Original Post-V5 Direction Disposition

```yaml
Post_V5_original_direction:
  previous_role: conditional_long_term_direction
  status: superseded_as_default_next_roadmap
  implementation_authorized: false
  becomes_V6_requirements: false
  reusable_ideas:
    - Long_term_Research_Threads
    - Full_Project_Radar
    - Background_Knowledge_Maintenance
    - Optional_Reviewer_eval_gated
```

V5 完成后重新审视真实产品定位，后续不再默认把拾流继续收窄为以 Knowledge / Research Companion 为中心的
产品；下一版本将重新从更广泛的个人收藏使用场景和真实求职展示价值出发规划。

本决定不提前定义 V6 架构、功能、JD 映射或 Charter。Optional Reviewer 不因 Multi-Agent 本身进入路线；
GraphRAG 等历史 eval-gated candidates 保持原事实边界。

# 9. Final Verification and Git Closeout

V5-D merge preflight：共同基线 `98ee944…`，Main/V5-D 分叉 `10/9` commits，修改文件重叠 0；Main、V5-D
与共同基线的产品 `src` tree 均为 `41ccf576…`。`--no-ff` merge commit `2d10844…` tree 与 preview
`1992bffe…` 完全一致。

```yaml
verification:
  V5_D_directed: 34_passed
  full_default_no_provider: 1775_passed
  external_or_live_provider_calls: 0
  script_compile: passed
  Program_and_V5_D_Ledger_JSONL: passed
  whitespace: passed
  warnings:
    - existing_Starlette_httpx_deprecation
    - existing_multiprocessing_fork_deprecation
repository_actions:
  V5_D_local_merge: completed
  product_runtime_registration_of_rejected_candidate: false
  live_migration: false
  live_fixture_write: false
  push: false
  tag: false
```

# 10. Final Main Session Closeout Decision

```yaml
V5_program:
  final_status: closed_with_known_limits_and_no_validated_V5_D_candidate
  final_head: commit_containing_this_closeout

V5_A:
  final_status: accepted_with_known_retrieval_limitation

V5_B:
  final_status: accepted_with_known_limits

V5_C:
  final_status: accepted_with_known_limits

V5_D:
  final_status: closed_no_validated_candidate
  validated_candidate: false

Post_V5_original:
  status: superseded_as_default_next_roadmap

repository:
  branch: codex/v5-main
  clean: required_at_final_handoff
  final_commit: commit_containing_this_closeout
  merge_status: V5_D_merged_locally_no_ff
  push_status: not_pushed
  tag_status: not_tagged

future:
  next_version_planning_authorized: false
```

> **V5 Program 到此停止。**

V6 的产品定位、功能选择、JD 映射、技术目标和 Version Charter 由用户重新规划并单独授权。
