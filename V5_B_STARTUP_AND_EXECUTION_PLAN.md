# Shiliu V5-B Startup and Execution Plan

> Prepared by: Shiliu V5 Main Codex Session
> User decision: startup_execution_authorized
> Plan status: active_startup
> Product implementation authorized: false
> V5-B Version Session creation authorized: true
> V5-B Charter created: false

---

# 1. Version objective

V5-B 的正式目标是：

> 将 V5-A 产生的研究结果、Evidence、Candidate Delta、收藏库结构、用户状态和系统经验，
> 转化为可追溯、可更新、可复用、可由用户纠正的个人知识与 Corpus Workspace。

主产品形态：

```text
Evidence-backed Personal Knowledge and Corpus Workspace
```

目标用户闭环：

```text
完成 Research Task
→ 查看候选知识
→ 审核并保存为 Grounded Fact / Artifact
→ 形成 Topic Page
→ 新 Evidence 出现时检测 Stale / Conflict
→ 相似问题直接复用、局部刷新或重新研究
→ 用户管理关注状态、显式记忆和收藏库理解
```

V5-A 让研究能够可靠持续；V5-B 让研究成果能够长期存在并再次发挥作用。

# 2. Starting baseline

```yaml
starting_baseline:
  repository_branch: codex/v5-main
  repository_head: b60e1df
  working_tree_at_planning: clean
  live_schema: 10
  V5_A_status: accepted_with_known_retrieval_limitation
  V5_B_status: not_started
  active_subversion: none
  V5_B_entry_gate: satisfied
```

V5-A 已提供：

- Durable ResearchTask；
- Goal / Attempt / Checkpoint / Result；
- EvidenceUse、Stable Citation 和 Source Version；
- provisional artifact；
- 四类 Task-scoped Candidate Delta；
- durable Trace/Event；
- Research 产品入口和用户控制路径。

当前 live DB 没有 Research Task。这不阻塞 V5-B 启动，但意味着正式产品验收需要有计划
地产生真实 Research Task、Candidate Delta 和知识晋升样本，不能只依赖合成 fixture。

# 3. Explicit non-goals

V5-B 不负责：

- 系统性个性化搜索、回答和路由；这些属于 V5-C；
- 将经验自动晋升为 Search Skill；这些属于 V5-D；
- 通用 MemoryOS、企业知识平台、RBAC、多租户或复杂 Connector；
- 默认实现 GraphRAG；
- 自动将 V5-A Candidate Delta 晋升为长期事实；
- 自动修改 Runtime、Verifier、Prompt 或 Tool Contract；
- 自动修复 V5-A 遗留的任意长复合查询召回问题，除非该问题明确阻塞 V5-B
  Artifact Retrieval 的受控验收 Case；
- 提前宣称 V5-C personalized behavior 或 V5-D active skill 已完成。

# 4. V5-A lessons applied

## 4.1 One Version Session owns the subversion

```text
V5 Main Session
→ one V5-B Version Session
→ optional bounded specialist Sessions
```

不为每个 Stage 创建新的长期 Session。V5-B Version Session 主导整个子版本的研究、
设计、实现、普通 Bug 修复、测试和 Stage 内集成。

## 4.2 Main Session reviews stage boundaries, not small commits

主 Session 只在以下边界介入：

- Version Charter 和正式 Stage 目标；
- Stage acceptance；
- 材料性产品或 authority 问题；
- Provider、费用或凭据授权；
- 高风险 License / Data 边界；
- live migration、mainline integration 和 closeout。

普通 projection、fixture、test harness 和低风险实现错误，由 V5-B Session 在当前
Contract 内自主修复和复跑。

## 4.3 Build a vertical product path early

V5-B Stage 1 必须尽早完成：

```text
V5-A Candidate
→ Evidence-bound Fact
→ Artifact
→ Topic Page
→ User Review
```

不先连续建设多个纯后台 Stage，最后才接 UI 和真实产品路径。

## 4.4 Prove projections and runners before paid runs

真实 Provider 前必须依次完成：

1. deterministic/no-network dry run；
2. public product projection contract test；
3. Keychain 只读预检；
4. run-wide budget、receipt、cost cap 和 immutable recovery root；
5. 一个最小真实 Case；
6. 通过后才扩大 Case。

用户批准明确预算包后，V5-B Session 可以自主修复小型 harness 问题，并在同一总预算
和冻结 Case 范围内重跑。

## 4.5 Avoid nested Gate and document proliferation

Provider Eval、live migration 和 mainline integration 保持独立授权，但不预设
Gate A/B/C 套娃。普通返工进入同一 Stage Report 或 Git 历史，不为每轮创建新的
Amendment/Recovery/Final-v2 文件。

## 4.6 Preserve honest limits

验收必须区分：

- core product failure；
- bounded product-quality limitation；
- implementation failure；
- Provider failure；
- infrastructure-invalid run；
- not exercised；
- unproven。

不因一个非核心 Case 无限延长版本，也不能把未证明项写成成功。

## 4.7 Keep authority state compact

V5-B 默认只维护：

```text
V5_B_VERSION_CHARTER.md
V5_B_CURRENT_STATE.md
V5_B_DECISION_LEDGER.md
V5_B_STAGE_N_CONTRACT.md
V5_B_STAGE_N_IMPLEMENTATION_REPORT.md
V5_B_FINAL_CLOSEOUT.md
```

只有材料性研究才新增独立 Upstream Research Report。

# 5. Session and authority model

```yaml
main_session:
  owns:
    - startup_boundary
    - stage_acceptance
    - program_state
    - mainline_merge
    - live_migration
    - version_closeout
  implements_product: false

V5_B_session:
  owns:
    - JIT_research
    - charter_draft
    - stage_design
    - implementation
    - ordinary_bug_fixes
    - tests_and_eval
    - stage_integration
  may_formally_accept_own_stage: false
  may_start_V5_C: false

specialist_sessions:
  optional: true
  report_to: V5_B_session
  create_second_acceptance_line: false

concurrency:
  active_subversion_limit: 1
  active_formal_stage_or_goal_limit: 1
```

专项 Session 可用于：

- DeepTutor 固定 Commit 源码研究；
- WeKnora Topic Page / async update 研究；
- Migration Spike；
- 独立 Eval / Review；
- Held-out 或污染隔离；
- 显著过长的有界上下文。

专项 Session 的结果必须先回到 V5-B Session，由其整合后提交主 Session验收。

# 6. Phase 0 — Main-session startup audit

Owner: V5 Main Session.

执行：

1. 核对 `codex/v5-main`、HEAD、工作树和远端关系；
2. 只读复核 live schema 10、Research 表、Candidate Delta、EvidenceUse 和 Artifact；
3. 检查 V5-A Candidate Delta 的实际对象合同、bounds 和幂等语义；
4. 核对 Citation/SourceVersion、provisional artifact 和 Research Product API；
5. 记录 live DB 的真实 Research Task/Evidence/Delta baseline；
6. 确认 V5-A known retrieval limitation 不自动成为 V5-B Backlog；
7. 形成精简 V5-B Startup Package；
8. 创建明确的 V5-B execution branch/worktree；
9. 创建并唤起一个 V5-B Version Session。

本 Phase 不实施产品、不迁移 live DB、不调用 Provider。

# 7. Phase 1 — JIT research and Version Charter

Owner: V5-B Version Session.

## 7.1 DeepTutor P0 research

在 Version Charter / Stage 1 前：

- 固定官方 Commit；
- 核验 License 和第三方边界；
- 审计 L1/L2/L3、Memory lineage、read/write/update/delete；
- 检查幂等写入、用户修正和相关测试；
- 判断 SQLite + filesystem Artifact 映射；
- 明确 adopt/reimplement/reject 的机制。

## 7.2 WeKnora bounded P1 research

只研究：

- Topic Page / Wiki 页面结构；
- 页面生成、更新和重建状态；
- 异步任务可观察性；
- 页面关系和前端交互。

不采用：

- 企业多租户；
- RBAC / Connector；
- 通用 RAG 底座；
- 用 Wiki 语义替代拾流 Evidence/Citation。

## 7.3 Startup outputs

```text
V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md
V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md
V5_B_VERSION_CHARTER.md
V5_B_STAGE_1_CONTRACT.md
V5_B_CURRENT_STATE.md
V5_B_DECISION_LEDGER.md
```

Charter 可以调整 Stage 数和顺序，但不能删除 Topic Page、Artifact Reuse、
User/Corpus Workspace 和 System Experience Store 等长期目标。

# 8. Stage 1 — Evidence-backed Topic Page vertical slice

## 8.1 User value

用户可以从一个 V5-A Research Task/Candidate Delta 创建并审核长期知识资产：

```text
Research Task
→ Candidate Delta Inbox
→ Evidence Review
→ Accept / Edit / Reject
→ Grounded Fact
→ Research Artifact
→ Topic Page
→ Transcript Citation Drill-down
```

## 8.2 Required implementation boundary

- V5-A Candidate Delta 的有界、幂等 intake；
- Candidate/accepted/rejected/superseded lifecycle；
- L1 Evidence/Event 引用，不复制或改写字幕 authority；
- L2 Grounded Fact 绑定 EvidenceUse/SourceVersion；
- L3 Artifact/Topic Page 只引用允许的 Fact；
- 用户审核和修正 Event；
- Topic Page 显示事实、不同观点、冲突、局限和未解决问题；
- 页面刷新和应用重启后状态稳定；
- 重复提交不产生重复 Fact/Artifact；
- forged cross-Task/cross-Evidence reference fail closed。

## 8.3 Evidence

- temporary DB migration tests；
- deterministic Task/Delta fixtures；
- service/API/UI 三层测试；
- 至少一条完整 no-provider journey；
- Search/Ask/Research affected regression。

Stage 1 不要求 live migration 或真实 Provider。

# 9. Stage 2 — Knowledge lifecycle, conflict and staleness

## 9.1 User value

知识能够更新、冲突、失效和被用户纠正，而不是一次写入后永久正确。

## 9.2 Required implementation boundary

- Source Version/Citation revalidation；
- 新字幕版本或 Evidence 变化触发 stale；
- Grounded Fact conflict group；
- 不同视频观点并存；
- temporal scope 和 viewpoint evolution；
- Artifact/Topic Page version lineage；
- supersede 而不是静默覆盖；
- 用户 approve/edit/reject update；
- correction 形成 append-only Decision/Event；
- 旧链接和旧版本仍可审计。

## 9.3 Acceptance cases

1. SourceVersion 不变，revalidation 仍 valid；
2. SourceVersion 改变，Artifact 标记 stale；
3. 新 Evidence 支持旧 Fact，形成 update candidate；
4. 新 Evidence 冲突，保留双方和 conflict lineage；
5. 用户拒绝更新，不改变既有 authority history；
6. 并发或重复更新只有一个有效 disposition。

# 10. Stage 3 — Artifact retrieval and reuse

## 10.1 User value

相似问题能够安全判断直接复用、局部刷新还是重新研究。

```text
Query
→ Artifact Retrieval
→ Scope Match
→ Evidence / SourceVersion Revalidation
→ Direct Reuse
  or Incremental Refresh
  or Research Seed
```

## 10.2 Routing rules

### Direct Reuse

- scope 一致；
- Artifact 对当前问题足够完整；
- Evidence current；
- Citation/SourceVersion 可验证。

不得重新运行完整 Deep/Research。

### Incremental Refresh

- 主体知识仍有效；
- 只缺新增内容、过期来源或个别 Aspect。

只搜索和更新变化部分。

### Research Seed

- scope 不匹配；
- Artifact 明显不完整；
- Evidence 严重过期；
- 新问题只与旧问题部分相关。

旧 Artifact 只提供视频、事实、冲突、未解决问题和搜索词；仍需启动新研究。

## 10.3 Required evidence

- 三条路线各至少一例；
- 记录 Artifact candidates、route reason 和 reused Fact；
- 记录需补查的 Aspect、Provider calls、latency/cost；
- 新旧 Artifact lineage；
- 与 full research 的对照；
- 错误 direct reuse 必须 fail closed。

V5-A 复合查询限制只有在阻塞这些受控 Case 时才进入有限修复。

# 11. Stage 4 — Personal and Corpus Workspace

## 11.1 User Model

- Explicit User Memory：只有用户明确确认后可使用；
- Behavioral Preference：多次行为只能生成 Candidate；
- Inferred User State：必须有 Evidence、confidence、expiry，可确认、编辑、拒绝；
- 删除或拒绝后不能通过旧事件静默恢复。

不得推断：

```text
收藏过 ≠ 学会
搜索过 ≠ 理解
看过 ≠ 掌握
没有点击 ≠ 不感兴趣
一次行为 ≠ 稳定偏好
```

## 11.2 Current Focus and Knowledge Progress

至少支持：

- currently exploring；
- user-confirmed familiar；
- needs follow-up；
- has conflict；
- temporarily not interested；
- supported/unresolved/contradicted/stale findings。

## 11.3 Corpus Model

至少覆盖：

- folder semantics；
- topic aliases；
- uploader specialties；
- recurring series；
- source availability；
- useful search terms；
- known limitations。

Corpus Model 只能是软先验。它不能成为 Citation、替代字幕、排除其他来源或通过
自我强化不断缩窄搜索。

## 11.4 System Experience Store

```text
Raw Trace
→ observed
→ diagnosed
→ candidate_source or invalidated
```

V5-B 不得将 Experience 自动晋升为 Active Skill，也不得据此修改 Runtime、Verifier
或 Promotion Gate。

Stage 4 可由 V5-B Session 根据实际复杂度拆为 4A/4B，但仍保持一条正式验收主线。

# 12. Version-level evaluation

V5-B Session 统一准备：

- Candidate → Fact → Artifact → Topic Page；
- 新 Evidence → conflict/stale → 用户更新；
- Direct Reuse；
- Incremental Refresh；
- Research Seed；
- Explicit Memory 创建、修改和拒绝；
- Corpus Model 不成为硬过滤；
- Experience 不自动升级 Skill；
- restart、duplicate、race 和 fault rollback；
- Search/Ask/Research compatibility；
- Provider 路径的 not_exercised/unproven 清单。

测试节奏：

```text
development:
  targeted tests

stage submission:
  targeted tests
  + affected regression

major milestone / final closeout:
  full default suite

small bounded rework:
  rerun affected tests
  do not mechanically repeat the whole suite
```

真实 Provider 只在 mechanical path 通过后，以单独冻结的 Case/Model/Budget/Credential
授权包运行。

# 13. Main-session integration and closeout

Owner: V5 Main Session.

执行：

1. 有限审阅最终 Diff、报告和关键源码；
2. 独立复跑核心机械测试；
3. 核对 Provider/real Case 证据和未证明项；
4. 确认 V5-C Entry Gate：
   - Artifact Reuse 路径存在；
   - Feedback Event 已积累；
   - User Memory 可确认和修正；
   - Corpus Model 可读取；
   - 至少两条可比较产品路径；
5. 停止 Web/sync 并建立 live DB 可恢复备份；
6. 合并 `codex/v5-b`；
7. 执行获准的 live migration；
8. 完整回归和 live product smoke；
9. 更新 Program Current State / Decision Ledger；
10. 接受或形成 `V5_B_FINAL_CLOSEOUT.md`；
11. 封存 V5-B 后再考虑 V5-C，不自动提前创建 V5-C Session。

# 14. Pause and escalation rules

V5-B Session 只在以下情况暂停并请求主 Session/用户判断：

- material product or authority tradeoff；
- roadmap reconsideration；
- major scope or cost expansion；
- destructive or irreversible operation；
- high-risk License/Data boundary；
- 新的 Provider/credential authorization；
- live database migration；
- 需要第二条并行正式 Stage。

普通实现选择、Stage 内拆分、局部重构、fixture/projection/harness Bug 和授权预算内
的有界重跑，由 V5-B Session 自主处理。

# 15. Immediate startup sequence after execution approval

```text
1. Main Session performs read-only V5-B startup audit
2. Create codex/v5-b branch/worktree
3. Create compact V5-B Startup Package
4. Create and wake one V5-B Version Session
5. V5-B Session performs DeepTutor P0 and WeKnora P1 bounded research
6. V5-B Session submits Charter + Stage 1 Contract + Startup Report
7. Main Session performs one target/boundary-level limited review
8. After acceptance, V5-B Session receives Stage 1 implementation authority
9. V5-B Session autonomously implements until the formal Stage 1 review point
```

# 16. Current authorization state

```yaml
current_authorization:
  persist_this_plan: true
  perform_startup_read_only_audit: true
  create_codex_v5_b_branch: true
  create_V5_B_session: true
  perform_JIT_upstream_research: true
  implement_V5_B_product: false
  run_provider: false
  migrate_live_database: false
  merge_push_or_tag: false

next_requested_action:
  - perform_startup_read_only_audit
  - create_codex_v5_b_branch_and_worktree
  - prepare_compact_startup_package
  - create_and_wake_V5_B_version_session
```

---

本计划保留长期路线中的全部 V5-B 能力，但不冻结具体 Schema、框架、Commit、Stage
数量和内部实现方式。后续 Version Charter 和 Stage Contract 应以 live repository
audit、固定 Commit 上游研究和真实产品证据为准。
