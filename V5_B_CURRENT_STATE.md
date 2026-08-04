# 拾流 V5-B Current State

```yaml
document_status: startup_submission_pending_v5_main_review
version: V5-B
version_session: Shiliu V5-B Version Session
updated_at: 2026-08-04
branch: codex/v5-b
starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
bounded_main_review_correction: applied_docs_only
charter_status: draft_pending_v5_main_acceptance
stage_1_contract_status: draft_pending_v5_main_acceptance
stage_1_implementation_authorized: false
product_implementation_started: false
provider_runs_performed: false
live_database_mutated: false
```

## 1. 当前一句话状态

V5-B startup/JIT research/Charter 已完成；V5 Main 对使命、五 Stage、权威/存储/跨版本边界和上游 reference-only 提案已原则接受，要求的 Stage 1 docs-only 收窄修订已应用。Charter/Stage 1 仍待最终接受与明确授权，尚未实施任何 V5-B 产品 schema/runtime/API/UI/tests。

## 2. Branch 与 Baseline

- Worktree 最初为 detached HEAD，但 HEAD 正确位于 `b85340540cb92c2e46bfb8619598e7aa987171d4`，working tree clean。
- `codex/v5-b` 当时未被其他 worktree 占用，已安全切换；切换后 branch/HEAD/clean status 重新核验通过。
- 已接受 V5-A 产品代码基线是 `04e5c5bbb94311a00f6efafa142908fd7b2b97de`。
- 从该代码基线到 V5-B 起点只有 closeout/Program/startup 文档变化，没有产品代码变化。
- schema 10、V5-A Gate C passed、V5-A 状态 `accepted_with_known_retrieval_limitation`。
- V5-A compound-query retrieval limitation 保持已知未证明边界，不自动进入 V5-B。

## 3. 已完成的 Startup 工作

### Authority intake

已阅读 V5-B Startup Package/Execution Plan、V5 Program Current State/Decision Ledger、V5-A Current State/Gate C Closeout、V5-B 与跨版本规划、Session 治理、研究与证据规范、DeepTutor/WeKnora Registry/Research Log，以及相关 V5-A implementation reports/source/tests。

### V5-A baseline audit

已独立确认：

- EvidenceIdentity global immutable；EvidenceUse task/attempt scoped；Provenance/Validation append-only；
- provisional artifact immutable；source drift 追加 observation 而不改 identity/artifact；
- Candidate Delta 是 bounded Event snapshot + CommandReceipt，不是 long-term store；
- four delta kinds 全部 candidate-only；Knowledge item 回到 artifact answer blocks/citations；
- Candidate snapshot fault rollback、restart exact-once、cross-task isolation 有测试；
- HumanDecision 仅在显式决策范围有权威；
- SQLite + filesystem ArtifactStore pattern 已存在，但 V5-B 必须避免双主。

### Upstream research

| 上游 | 固定身份 | License | 深度 | 提议 |
| --- | --- | --- | --- | --- |
| DeepTutor | `HKUDS/DeepTutor@44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8`, tag `v1.5.8` | Apache-2.0；Memory scope 未触及 CSSwitch OAuth notice | P0 source + tests source review；test execution not proven | reimplement/test/product reference；no copy/dependency |
| WeKnora | `Tencent/WeKnora@fcc4cd6a9f29a94818e481b3a604f44ce51c55e2`; release `v0.7.1@c64a486...` 另行核验 | 主项目 MIT + listed third-party | bounded P1 page/queue/UI/source/tests；2 pure tests passed | product/reimplement/test reference；no copy/dependency |

## 4. 已提出的架构

- L1：复用 V5-A Evidence/Event authority；不采用 JSONL trace authority。
- L2：stable GroundedFact family + immutable FactRevision + exact Evidence links。
- L3：stable ResearchArtifact/TopicPage family + immutable revisions；逐 fact 回到 L1。
- V5-A Candidate snapshot 保持不可变来源；V5-B 单独建立长期 Candidate review identity/lifecycle。
- V5-B 全局采用 append-only Decision/Event 与 immutable revisions；Stage 1 只实现 Candidate Accept/Reject/Edit-as-new-candidate 和初始 Fact/Artifact/Page revisions，Fact/Page 后续 correction/retire/supersede/edit/revert 产品命令进入 Stage 2。
- SQLite 是 canonical authority；filesystem 是 revision/hash 定址、可重建的不可变 export/cache。
- Stage 1 的持久 BuildRun 只覆盖同步 deterministic artifact/page build；Stage 2 才覆盖 update/rebuild、后台恢复和 async late-result fencing。process/SSE/Redis 只可投影/唤醒。
- Stage 1 只允许 KnowledgeDelta → Fact；其他 delta kinds 保持 candidate-only 到后续 Stage。

## 5. 拟议 Stage

1. Evidence-backed Topic Page Vertical Slice。
2. Knowledge Lifecycle, Revalidation and Durable Refresh。
3. Artifact Retrieval, Reuse and Research Continuation。
4. Personal and Corpus Workspace。
5. Product Completion, Relations and Evaluation。

全部 V5-B 能力目标均保留；Stage 数/顺序来自当前 baseline 与固定 Commit 上游证据。Stage 1 以早期 vertical path 为首，不先建设抽象 MemoryOS/Graph/queue platform。

## 6. 验证状态

### 已执行

- 拾流定向 no-provider / temp-DB：
  - `tests/test_v5_a_stage2_inner_loop.py`
  - `tests/test_v5_a_stage4_operational_control.py`
  - `tests/test_v5_a_stage5_product_completion.py`
  - 结果：`73 passed`；唯一 warning 是既有 FastAPI TestClient/httpx deprecation。
- WeKnora fixed-commit pure Node：
  - `frontend/src/views/knowledge/wikiStatusRefresh.test.ts`
  - 结果：`2 passed`。

### 尝试但未执行

- DeepTutor 六个 Memory test files：临时 sparse checkout 的 package import chain 缺少非 Memory 模块，在 collection 阶段停止；没有测试体或 Provider 运行。

### 未执行

- default full Shiliu suite；当前 assignment 只需 planning assumption 的定向验证。
- DeepTutor/WeKnora 完整测试、Go build、LLM generation、Provider evaluation。
- live DB migration/read-write、live content mutation。

## 7. 产出文件

- `V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md`
- `V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md`
- `V5_B_VERSION_CHARTER.md`
- `V5_B_STAGE_1_CONTRACT.md`
- `V5_B_CURRENT_STATE.md`
- `V5_B_DECISION_LEDGER.md`
- `V5_B_STARTUP_REPORT.md`

只有上述 startup/research/planning artifacts 属于本轮提交范围。

## 8. 未证明与开放项

- edited candidate 的 server-owned grounded validator 尚未实现；Stage 1 Contract 要求没有 validator 时保持 `needs_revalidation`。
- 具体 schema names/limits/API routes/UI layout 尚未实现，允许在 Contract 不变量内调整。
- Stage 1 只有同步 deterministic BuildRun；async worker/queue、late-result fencing 和通用 update/rebuild 在 Stage 2。
- Page edit/history/diff/revert、Fact correction/retire/supersede、filesystem export command/failure matrix 均不是 Stage 1 gate，进入 Stage 2。
- conflict detection、stale propagation、reuse/refresh/seed、personal/corpus workspace 均未实现。
- upstream runtime behavior 未通过完整 upstream test execution 证明。
- Provider 产品质量与 live migration 全部未授权/未证明。

## 9. 当前 Gate 与下一动作

```yaml
startup_artifacts: prepared
limited_main_review_requested: true
charter_accepted: false
stage_1_contract_accepted: false
stage_1_implementation_authorized: false
next_action: V5_main_limited_review_of_targets_boundaries_adoption_and_stage_1_authority
```

在 V5 Main 明确接受/修订 Charter 与 Stage 1 Contract 并授权前，V5-B Session 不实施产品代码。
