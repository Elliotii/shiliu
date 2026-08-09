# 拾流 V5-C Startup / JIT / Charter Report

```yaml
report_status: submitted_for_limited_v5_main_review
version_session: Shiliu V5-C Version Session
report_date: 2026-08-09
execution_branch: codex/v5-c
required_starting_ref: codex/v5-main
starting_head: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
submission_commit: git_commit_containing_this_integrated_report_set
active_formal_stage: startup_and_JIT_docs_only
startup_assignment_complete: true
charter_accepted: false
stage_sequence_accepted: false
stage_1_contract_accepted: false
stage_1_implementation_authorized: false
product_implementation_started: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
live_database_mutated: false
external_research_performed: false
upstream_adoption_proposal: none
directed_no_provider_tests: 18_passed
decision_ledger_jsonl: 12_valid
docs_whitespace_check: passed
```

> Git Commit 不能在其自己的文件内容中可靠自引用；`submission_commit` 的实际 hash 由本报告提交后的
> final handoff 给出。该 Commit 必须只包含本报告列出的五份 docs-only 文件。

## 1. 交付结果

本轮完成 V5-C docs-only startup/JIT package，没有实施产品：

1. `V5_C_VERSION_CHARTER.md`
2. `V5_C_CURRENT_STATE.md`
3. `V5_C_DECISION_LEDGER.md`
4. `V5_C_STAGE_1_CONTRACT.md`
5. `V5_C_STARTUP_REPORT.md`

没有材料性外部研究，因此没有新增 `V5_C_UPSTREAM_*_RESEARCH_REPORT.md`。没有修改
`V5_PROGRAM_CURRENT_STATE.md`、`V5_PROGRAM_DECISION_LEDGER.md` 或其他 Program authority。

## 2. Branch / HEAD / working tree gate

编辑前的实际状态：

```text
initial branch: detached HEAD
initial HEAD: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
codex/v5-main: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
initial working tree: clean
codex/v5-c existed: no
action before edits: git switch -c codex/v5-c
post-switch branch: codex/v5-c
post-switch HEAD: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
post-switch working tree: clean
```

因此真实起点与用户要求一致。早期 planning 文档中的旧 starting hash 没有覆盖本次明确 authority。

## 3. 必读材料完成情况

已完整阅读并交叉核对：

- `V5_C_STARTUP_AND_EXECUTION_PLAN.md`；
- `V5_C_STARTUP_PACKAGE.md`；
- `V5_PROGRAM_CURRENT_STATE.md`；
- `V5_PROGRAM_DECISION_LEDGER.md`；
- `拾流_V5主Codex交接包_2026-07-30/拾流_V5及后续版本规划_现阶段整合版.md`；
- `拾流_V5主Codex交接包_2026-07-30/001_拾流V5开发研究与证据治理规范.md`；
- `拾流_V5主Codex交接包_2026-07-30/00_拾流V5主Codex角色权限与Session治理.md`；
- `拾流_V5主Codex交接包_2026-07-30/03_拾流V5上游项目与研究资料注册表.yaml`；
- `拾流_V5主Codex交接包_2026-07-30/04_拾流V5上游研究活动日志.jsonl`；
- `V5_B_FINAL_CLOSEOUT.md`。

另完整/定向阅读了 V5-B Workspace、Feedback、ArtifactRoute 的 schema/contracts/services/Web/UI 和三份
主要 directed test files，以及 Product Search、Fast/Deep Ask、Research runner、ASR/pipeline/Prompt 的
真实路径。审计不是从 roadmap 反推实现，而是以当前 source/test 为准。

## 4. Live schema 14 只读审计

数据库：`/Users/elliot/Library/Application Support/Shiliu/shiliu.db`。

安全边界：只使用 `sqlite3 -readonly` + URI `mode=ro&immutable=1` + `PRAGMA query_only=ON`；未调用
`Application()` 或 `Database.initialize()`，因为它们具备 migration/write 行为。审计窗口前后核对
SHA-256/size/mtime。

```yaml
schema_version: 14
integrity_check: ok
foreign_key_violations: 0
videos: 157
completed_videos: 140
sync_runs: 436
active_sync_runs: 0
research_tasks: 0
research_events: 0
workspace_record_revisions: 0
artifact_route_records: 0
topic_page_revisions: 0
feedback_events_v5b_product_feedback_recorded: 0
frozen_taxonomy_snapshots: 2
latest_snapshot:
  snapshot_id: 2
  snapshot_hash: 1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2
  memberships: 131
  content_rows: 131
  discovery_eligible: 128
  trial_assignment: 3
database_size_bytes: 94588928
database_sha256_before: 50a56953d5d3da3afa80a72f3aa070a6fd197ce656a4fb7cc02f8a69a7c5b697
database_sha256_after: 50a56953d5d3da3afa80a72f3aa070a6fd197ce656a4fb7cc02f8a69a7c5b697
database_mutated_by_session: false
```

侦察中两次 exploratory taxonomy `SELECT` 使用不存在的候选列名，SQLite 均在 prepare 阶段拒绝。
随后读取真实 table schema，用 `id/trial_assignment_only_count` 做 bounded read-only rerun；
hash/size/mtime 不变。按 assignment，这类小型 harness 调用问题不新增 Gate/Amendment。

结论：schema 14 机械健康；live Research/Feedback/Workspace/Profile/ArtifactRoute/TopicPage 是 cold
start。taxonomy snapshot 是真实 corpus state，但由于 corpus WorkspaceRecord 为 0，当前没有 live
personalization input。任何 test fixture 都不能报告为真实用户数据或已证明收益。

## 5. Source / authority audit findings

### WorkspaceRecord

- schema 14 只有一张 append-only Workspace aggregate，immutable triggers 生效；
- explicit/user-confirmed、behavioral candidate、evidence observation、corpus soft prior、experience
  candidate 分开；
- inference 至少两个 Event refs；progress 保护 watched-not-learned；corpus 绑定 frozen snapshot；
- correction/terminal/no-resurrection/expiry 都是 revision projection；
- 当前 UI/API 明确 `product_behavior_effect=false`，没有行为 consumer。

### Feedback

- 现有 Feedback 是 exact target/hash 的 advisory Event + Receipt；
- target 仅 immutable PageRevision 或 ArtifactRoute record，同 task boundary；
- duplicate/payload mismatch/fault rollback 有测试；
- 它不自动改变 Fact/Page/Profile/Prompt/Router/Skill。

### Corpus / ArtifactRoute

- Corpus observation 当前只存 soft prior；seeded fixture 测试证明 Search/Ask/Research/Route
  non-interference；
- ArtifactRoute 先独立跑 open retrieval，再做 bounded artifact gates；direct 需 exact/current/complete，
  incremental 需 usable core + bounded gaps，否则 seed；
- 用户只能选择相同或更安全路线，late authority hash 重新 fence；
- ArtifactRoute 不是 Fast/Deep/Research/ASR/Translation general router。

### Fast / Deep / Research / ASR-Translation

- Fast/Deep 由用户 `AskRequest.mode` 显式选择，均只以 current transcript/ASR 为最终引用；Navigation、
  title、description、summary 只导航；
- Product Search planner 当前仅按 query type/explicit mode 决定 lexical/hybrid；
- Research 是 durable no-provider-by-default path，V5-B Workspace/Feedback 不进入 Prompt/budget/route；
- ASR 是真实 provider-backed durable job path，并有 manual/automatic trigger；个性化不能自动触发；
- 当前无 distinct Translation route；英文 raw subtitle 仅在现有 transcript cleanup Prompt 中形成中文
  整理结果。Stage 3 必须诚实处理该 capability gap。

## 6. Input → authority → consumer → effect → control audit

精确版本见 Charter 表；本轮收敛出的关键规则：

| 输入 | 当前 authority | 首个/后续 consumer | effect gate | explanation / control |
| --- | --- | --- | --- | --- |
| explicit preference | user-authored/current | Stage 1 Research presentation | exact whitelisted key/value | revision/version/reason；off/tombstone/correct/restore-as-new |
| structured Feedback | advisory Event | candidate intake only | two compatible Events + explicit create；confirm 前零 effect | target/hash/event refs；reject/expire/no resurrection |
| implicit behavior | behavioral candidate | review only | user confirm required | confidence/source/expiry；never direct Prompt/Router/Skill |
| Current Focus | user-authored or confirmed | Stage 1 explanation；Stage 4 help | Stage 1 不改事实内容 | focus revision；correct/expire/tombstone |
| Corpus snapshot | corpus soft prior | Stage 2 Search | bounded cue + independent open lane | snapshot hash/lane contribution；per-query off/invalidate |
| Artifact/current Facts | existing L1/L2/L3 | existing route + Stage 3 recommendation | currentness/citation/coverage/user choice | gate reasons；same-or-safer override/reassess |
| Progress/delta/staleness | user assertion or observation/candidate | Stage 4 bounded inbox | no watched=learned；no auto mutation | source/time/why-now；dismiss/expiry/tombstone |
| Experience | experience candidate | V5-D only | no V5-C consumer | trace/result/env；diagnose/reject/invalidate |

## 7. Stage sequence and Stage 1 selection

提议五个 Stage：

1. Confirmed Personalized Answer Presentation；
2. Corpus-aware Search；
3. Personalized Routing；
4. Knowledge Progress and Bounded Assistance；
5. Integrated Personalized Research Journey and Evaluation。

Stage 1 选择 `answer.presentation.limitations_position=before_answer|after_answer` 作为唯一 effect：它在
Research UI 中用户可见、完全 deterministic，能复用现有 Workspace/Feedback，能证明 confirm/disable/
rollback，却不修改答案、证据、Prompt、检索、route、budget 或 Provider。Current Focus 同时进入 versioned
context/explanation，behavioral feedback 只能形成 candidate。

Stage 1 默认零 schema/table/index/migration/dependency/Prompt/Provider，最多一个 narrow projection
adapter，复用现有 endpoint/surface。完整 Contract 见 `V5_C_STAGE_1_CONTRACT.md`。

## 8. JIT research decision

### 本地证据已回答的问题

- Workspace authority/status/revision/source/no-resurrection 如何成立；
- Feedback 如何 exact-target、advisory、idempotent、fault atomic；
- corpus prior 与 open lane/non-interference 的已接受边界；
- ArtifactRoute 与实际 Fast/Deep/Research/ASR/Translation capability 边界；
- Stage 1 如何在不改 Prompt/Schema/事实 authority 下形成 paired user-visible effect。

### Registry / Log 结论

- `local_memo_self_evolution` 和 `survey_what_when_how_self_evolving` 只提供 Experience/Feedback 与
  retention/generalization/regression checklist，不授予实现 authority；
- Research Log `UR-20260809-018` 的下一触发条件正是“V5-C 需要 local evidence 不支持的新机制”；
  本轮没有该缺口；
- accepted DeepTutor/WeKnora fixed-commit reports 已足够作为 reference-only baseline。

### 材料性判断

```yaml
external_research_needed: false
new_upstream_report: none
new_adoption_proposal: none
decision: reimplement_shiliu_native_from_local_accepted_contracts
network_browsing: not_performed
bulk_download_or_checkout: not_performed
dependency_or_source_test_prompt_UI_copy: not_performed
```

因此没有为“看起来完整”而做 decorative research。未来只有出现新 mechanism、distinct Translation
route、external corpus authority、dependency/copy proposal 等具体缺口才重新开材料性研究。

## 9. Mechanical evidence

本 startup 使用的已接受/本地 source-test 证据：

- `tests/test_v5_b_stage4_personal_workspace.py`：explicit/candidate/focus/progress/corpus/experience、
  correction/expiry/tombstone/no-resurrection、Search/Ask/Research/Route non-interference；
- `tests/test_v5_b_stage5_product_closeout.py`：Feedback exact-target/hash/cross-task/dedupe/fault/advisory；
- `tests/test_v5_b_stage3_artifact_reuse.py`：independent open lane、direct/incremental/seed gates、restart/fault；
- V5-B Final Closeout：Stage 1–5 accepted、schema 14 live migration、108 Main directed tests、cold start；
- 本轮以原仓库既有 `.venv` 在本 worktree 运行上述三份 directed files：`18 passed`；唯一输出是
  Starlette/httpx 的既有 deprecation warning；
- 初始 `python -m pytest` 因本机无 `python` alias、`python3 -m pytest` 因系统 Python 未安装 pytest，
  均在 collection 前失败；定位到既有 `.venv` 后有界复跑通过，没有修改代码、依赖或测试；
- 测试窗口 live DB SHA-256 前后均为
  `50a56953d5d3da3afa80a72f3aa070a6fd197ce656a4fb7cc02f8a69a7c5b697`，size/mtime 不变。

本轮没有 Provider、credential/Keychain、live migration 或 live write。产品源码、测试、schema、Prompt、
UI 也没有修改。

## 10. 未证明项

- 真实用户 personalization benefit，因为 live input 为 0；
- Stage 1 presentation 偏好以外的 personalized answer content quality；
- corpus-aware recall/counterexample/latency 的真实集合表现；
- personalized route 成本收益、ASR 推荐质量、distinct Translation route；
- Progress/Delta/Staleness/Radar 的长期频率和 UX；
- large workspace、multi-process UI ordering、Provider subjective comparison；
- V5-A compound long-query grounded completion。

这些是诚实边界，不是启动文档可以伪造或提前建设平台解决的内容。

## 11. 有限 Main review 请求

请 V5 Main 只决定：

1. 接受或退回 `V5_C_VERSION_CHARTER.md`；
2. 接受或调整五 Stage sequence；
3. 接受或退回 `V5_C_STAGE_1_CONTRACT.md`；
4. 接受“本轮无材料性 upstream adoption proposal、无需新增 report”的 JIT 判断；
5. 是否授权同一个 V5-C Session 开始 Stage 1 implementation。

本 Session 不请求 Main 逐文件实现设计，不请求 live migration/mainline/push/tag，也不请求提前接受 Stage 1
或 V5-C。提交后停止，等待有限审阅。
