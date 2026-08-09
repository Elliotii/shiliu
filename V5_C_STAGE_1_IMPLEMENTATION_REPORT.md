# 拾流 V5-C Stage 1 Integrated Implementation Report

```yaml
report_status: complete_pending_limited_v5_main_acceptance
stage: V5-C Stage 1
title: Confirmed Personalized Answer Presentation
version_session: Shiliu V5-C Version Session
report_date: 2026-08-09
execution_branch: codex/v5-c
stage_starting_commit: 2429debf9be426d825c6847e80030a537cc991a9
main_acceptance_and_implementation_authority: 272affa0e6ed2f0bc6f14d002a4d36dc26094430
implementation_commit: git_commit_containing_this_integrated_report
contract_status: accepted_by_v5_main
implementation_status: complete_pending_v5_main_acceptance
self_accepted: false
schema_source_version: 14
schema_table_index_migration_delta: 0
dependency_prompt_provider_background_worker_delta: 0
provider_runs_performed: false
credentials_or_keychain_accessed: false
live_database_mutated: false
stage_2_entered: false
```

> Main authority commit `272affa` 只读引用，没有 cherry-pick/merge 到 `codex/v5-c`；Program Current State
> 与 Decision Ledger 未修改。本报告与实现同 Commit，文件不能稳定自引用其最终 hash；实际 Commit 由
> final handoff 报告。

## 1. 实现结果

Stage 1 已形成一条真实、低风险、用户可见的纵切：

```text
Explicit preference ───────────────────────────────────────────────┐
Exact structured Feedback Events → reviewed Candidate → confirm ──┤
Explicit Current Focus ────────────────────────────────────────────┤
                                                                  ↓
                 read-only versioned PersonalizationContext
                                                                  ↓
Existing Research answer + limitations → before/after presentation + explanation
                                                                  ↓
                  session off / correct / expire / tombstone / restore-as-new
```

唯一 effect key 仍为：

```text
answer.presentation.limitations_position = before_answer | after_answer
```

`before_answer` 只把既有 limitations DOM container 移到 answer blocks 前；`after_answer` 保持当前
baseline。答案文字/顺序、limitations 内容、citation/evidence identity/currentness、Research state、
Search、ArtifactRoute、Prompt、budget 和 Provider 均不变化。

## 2. Authority 与数据流

### 2.1 PersonalizationContext

新增唯一一个 `PersonalizationContextProjection`，它只读取现有 Workspace effective revisions，不写
状态、不生成第二个 Profile store：

- policy：`v5-c-stage1-personalization-context-v1`；
- exact consumer whitelist：只认上述 semantic key 和两个 enum values；
- explicit path：`explicit_memory + user_authored + current`；
- candidate path：`inferred_candidate + user_confirmed + confirmed`；
- candidate/unconfirmed、expired、rejected、tombstoned、unknown、malformed、conflicting 和 unrelated
  全部 fail closed；
- 多个 confirmed records 值冲突时不按 timestamp 猜测，返回
  `confirmed_preference_conflict_fail_closed`；相同值才可 deterministic 选择 explanation revision；
- Current Focus 只进入 explanation；多个有效 Focus 时省略并报告 reason，不改答案；
- `context_hash` 覆盖 policy/enabled/effect/preference/focus/reasons，供 restart/diagnostic 比较，不获得
  Citation、Verifier 或 durable identity authority。

Workspace response 只把实际 selected revision 标记 `product_behavior_effect=true`；所有其他 record 继续
为 false。filter 只影响返回的 record list，不改变 Context 对完整 effective workspace 的投影。

### 2.2 Structured Feedback → Candidate

现有 `SubmitKnowledgeFeedbackRequest` 仅增加 optional strict object：

```json
{
  "candidate_preference": {
    "semantic_key": "answer.presentation.limitations_position",
    "proposed_value": "before_answer"
  }
}
```

没有该字段的 legacy request/payload hash/response shape 保持兼容。存在时，它仍只进入 existing
`v5b_product_feedback_recorded` Event + CommandReceipt，authority 仍是
`advisory_feedback_only`、`automatic_action=false`。

用户在 existing Research surface 明确点击“Create candidate for review”后，现有 Workspace create
endpoint 才尝试创建 Candidate。服务器对每个 source Event 重新验证：

1. 至少两个 distinct refs，全部是 `v5b_product_feedback_recorded`；
2. same Task；
3. committed `v5b_product_feedback` CommandReceipt；
4. immutable TopicPageRevision/ArtifactRoute exact target 仍存在且 hash 精确一致；
5. exact semantic key 和 proposed value；
6. Event authority/advisory/automatic flags；
7. Event `principal_id` 等于当前 create operation principal。

结果只形成 `behavioral_candidate/candidate`。确认操作再次对 source Events 运行同一 principal fence；
确认前 projection 必须 baseline。显式 correction 是新的用户权威，可以把已确认值改为另一个 enum，仍以
append-only revision 记录，不被旧隐式 sources 否决。

### 2.3 Explain / disable / rollback

- explanation 显示 policy、enabled/applied、effect scope、preference record/revision/version/hash/
  authority、Current Focus、reason codes、context hash；
- existing Workspace GET 增加 optional `personalization_enabled=false`，只改变 read projection，不写
  Workspace/Event/Receipt；
- UI toggle 关闭时 DOM 回到 `after_answer` baseline；
- correct/expire/tombstone 继续使用 existing decision endpoint/CAS/immutable history；
- Workspace history projection 增加每个 revision 的 payload，UI 的“restore previous”实际提交 existing
  `correct`，reason=`restore_previous_value:vN`，形成新 revision，不复活或覆盖旧 revision。

## 3. Lean diff scope

### Product files：10

- `src/shiliu/research/personalization.py`：唯一 read-only adapter；
- `src/shiliu/research/knowledge_contracts.py`：optional strict Feedback preference；
- `src/shiliu/research/product_closeout.py`：保持 legacy hash，按需写 structured Event payload；
- `src/shiliu/research/personal_workspace.py`：projection composition、history payload、Feedback source/
  receipt/target/key/value/principal fence；
- `src/shiliu/research/knowledge_service.py`、`src/shiliu/web.py`：existing Workspace GET 的 optional
  enabled 参数；
- `src/shiliu/static/research-personalization.js`：纯 DOM placement helper；
- `src/shiliu/static/research-personalization.css`：既有 surface 的 compact explanation 样式；
- `src/shiliu/static/research.js`、`src/shiliu/templates/research.html`：structured Feedback selector、
  candidate review button、explanation/off/restore 和唯一 presentation effect。

### Test files：2

- `tests/test_v5_c_stage1_personalized_answer_presentation.py`；
- `tests/js/test_v5_c_stage1_personalization.mjs`。

### Version docs：3

- 本报告；
- `V5_C_CURRENT_STATE.md`；
- `V5_C_DECISION_LEDGER.md`。

没有修改 `V5_C_VERSION_CHARTER.md`、`V5_C_STAGE_1_CONTRACT.md`、Program authority、Prompt、schema、
dependency 配置、ASR/Translation、Search/Ask/Router 或 background runtime。

```yaml
new_tables: 0
new_indexes: 0
new_migrations: 0
schema_version_change: 0
new_authority_stores: 0
projection_adapters: 1
new_endpoint_types: 0
new_dependencies: 0
new_prompt_versions: 0
new_background_workers_or_schedulers: 0
```

## 4. Paired mechanical matrix

| Case | Input authority | Expected/observed effect | Explanation/control |
| --- | --- | --- | --- |
| no-profile baseline | no Workspace rows | `after_answer`，product payload unchanged | `no_confirmed_preference` |
| unrelated negative | confirmed `answer density` | baseline | unrelated key never enters whitelist |
| malformed/unknown | exact key + invalid shape/value | baseline | `malformed_or_unauthorized_preference` |
| confirmed conflict | explicit before + confirmed candidate after | baseline | `confirmed_preference_conflict_fail_closed` |
| unconfirmed candidate | two exact Feedback Events → candidate | baseline | `candidate_not_confirmed` |
| explicit treatment | user-authored/current before | limitations before answer | selected revision/version/hash |
| confirmed treatment | candidate + matching-principal confirm | limitations before/after | `confirmed_preference_applied` |
| session disabled | valid confirmed preference + GET/toggle off | baseline；0 durable writes | `personalization_disabled` |
| correct | confirmed before → after | only position changes | new immutable revision |
| restore | after → previous before payload | only position changes | restore is a new revision |
| expire/tombstone/reject | terminal effective head | baseline | terminal reason；history retained |
| principal negative | other-principal Feedback sources + current local operation | candidate create/confirm rejected | exact principal mismatch error |
| Current Focus | one explicit confirmed focus | answer unchanged | focus revision visible only |
| multiple Focus | multiple active records | answer unchanged；focus omitted | `multiple_current_focus_omitted` |

## 5. Consolidated Gate A–F evidence

### Stage 1 directed

- Python paired/authority/API/UI matrix：`4 passed`；
- pure Node DOM order/off/unrelated matrix：`2 passed`；
- `py_compile`、`node --check`、`git diff --check`：通过。

### Affected compatibility

以下 10 个 Python files 合计 `92 passed`：

- boundaries/Web；V5-A Research API/Product Completion；
- V5-B ArtifactRoute/Workspace/Feedback closeout；
- Product Search API；Fast Ask API；Ask Page；V5-C Stage 1。

该集合覆盖 Workspace/Feedback restart/idempotency/fault、ArtifactRoute open lane、Research output、
Fast/Deep Ask、Product Search、public API 和现有 UI compatibility。

### Default no-provider

仓库默认 marker boundary 为 `not external_artifact and not live_provider`。最终结果：

```text
1725 passed, 4 deselected, 7 warnings in 175.11s
```

warnings 仅为既有 Starlette/httpx deprecation 及 multiprocessing fork deprecation。未访问网络模型或
真实 credential。`ruff` 不在既有 `.venv` 中，本 Stage 没有为 lint 新增依赖；使用 compile、Node
syntax、diff/JSONL/whitespace 与完整测试套件作为静态/机械证据。

### Harness corrections

- 初次 pytest collection 使用 existing `.venv` 的 editable install，解析到原仓库；固定
  `PYTHONPATH=src:tests` 后在当前 worktree 有界复跑；
- 首轮新增测试引用了不存在的 product projection `evidence` key，修正测试投影后复跑；
- 既有 V5-B UI test 依赖旧 non-interference 文案；新文案保留该 baseline 并明确只对白名单 confirmed
  key 形成唯一例外，随后同一 21-case 集合通过；
- 没有为这些普通问题创建独立 Gate/Amendment 文档。

## 6. Live DB 只读证据

最终观测路径：`/Users/elliot/Library/Application Support/Shiliu/shiliu.db`。

```yaml
access: sqlite_URI_mode_ro_immutable_query_only
schema: 14
integrity_check: ok
foreign_key_violations: 0
videos: 157
completed: 140
sync_runs: 437
active_sync_runs: 0
research_tasks: 0
research_events: 0
workspace_records: 0
artifact_routes: 0
topic_page_revisions: 0
feedback_events: 0
size_bytes: 94588928
sha256_before_default_suite: 23998009db116f84d424a48b45939b20b67a368dbe0fb1f9656f9b3bd416d142
sha256_after_default_suite: 23998009db116f84d424a48b45939b20b67a368dbe0fb1f9656f9b3bd416d142
mtime_unchanged_in_window: true
```

该 hash 与 startup report 的旧 hash 不同，且 `sync_runs` 从 436 增至 437；变化在本 Stage 最终测试
窗口之前，属于外部正常产品运行观测。V5-C 所有测试使用 temp DB，窗口内 live hash/size/mtime 不变。
live Research/Feedback/Workspace 仍为 cold start，fixture 只证明机械行为，不能声称真实用户收益。

## 7. 未证明与保留边界

- 真实用户是否偏好 limitations 前置、以及该展示是否提升研究质量；
- Personalized Answer 的文本/结构生成（Stage 1 只交付 presentation slice）；
- Corpus-aware Search、Personalized Routing、Progress/Staleness/Collection Delta/Early Radar；
- distinct Translation route、ASR 推荐成本收益、Provider 主观质量；
- large Workspace/multi-process UI ordering/长期行为与真实用户 correction patterns；
- V5-A compound long-query grounded completion。

Stage 1 没有进入或暗示 Stage 2；Corpus/Artifact/Experience 仍不获得新的行为、Citation、Verifier、
hard-filter、Prompt、Router 或 Skill authority。

## 8. Main 有限验收请求

请 V5 Main 只对本 integrated Stage 1 implementation 做有限验收：

1. 核对唯一 effect 与 answer/evidence/Search/Route/Prompt non-interference；
2. 核对 Feedback Event → Candidate → confirm 及 principal fence；
3. 核对 explain/off/correct/restore/terminal/no-resurrection 语义；
4. 核对零 schema/dependency/Prompt/Provider/background delta 和机械证据；
5. 接受或退回 Stage 1 implementation。

本 Session 不请求自行接受，不请求 live migration/mainline/push/tag，也不在本提交进入 Stage 2。提交后
停止，等待 Main 有限验收。
