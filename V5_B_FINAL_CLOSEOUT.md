# Shiliu V5-B Final Closeout

> Date: 2026-08-09
> Authority: Shiliu V5 Main Codex Session
> Decision: accepted_with_known_limits

---

# 1. Outcome

V5-B 已完成版本级验收。Evidence-backed Personal Knowledge and Corpus Workspace 的五个
Stage 均已接受，产品代码已集成到 `codex/v5-main`，live SQLite 已从 schema 10
迁移到 schema 14，服务已恢复，机械回归与只读 live smoke 通过。

```yaml
V5_B:
  status: accepted_with_known_limits
  successful: true
  goal_met: true
  mainline_integrated: true
  live_schema_migrated: true
  product_runtime_running: true
  provider_runs_performed: false
  pushed: false
  tagged: false
```

# 2. Mainline integration

- Main pre-merge HEAD: `0c232e358896f56df2c75cfa619db7a919b1229d`.
- Accepted V5-B HEAD: `27c8c30d2704dcb3d0a792e53bfc96f2e1a1c930`.
- Merge base: `b85340540cb92c2e46bfb8619598e7aa987171d4`.
- Preflight divergence: Main 11 / V5-B 11；双方修改文件重叠数为 0。
- Merge preview tree: `00e5cfc3301df206e512c8f3476cac26eae47253`.
- Main merge commit: `7d9af9009926c13cd94e149b9e54c87cdf2ffc9d`.
- Merge commit tree 与 preview tree 完全一致，两个输入 HEAD 均为其祖先。

Push 和 Tag 均未执行。

# 3. Migration preflight and recovery

迁移前 Web 与每小时 sync LaunchAgent 均已卸载，且没有 active sync run。live DB
稳定现场为：

```yaml
schema: 10
sha256: 986593c4807748723ad40be63d187c0358c2aa59a9b0a1735cd4fa78bdad415d
integrity_check: ok
foreign_key_violations: 0
videos: 157
completed_videos: 140
sync_runs: 434
active_sync_runs: 0
research_tasks: 0
```

可恢复备份：

| Backup | SHA-256 | Schema | Integrity | FK |
| --- | --- | ---: | --- | ---: |
| `/Users/elliot/Library/Application Support/Shiliu/backups/shiliu.v5-b-pre-v14-20260809T171926+0800.db` | `f36386eef8c48a78cf4982bf89b0b6d311da1bcf381934e41cf016401e17093f` | 10 | ok | 0 |
| `/Users/elliot/Library/Application Support/Shiliu/shiliu.pre-v14.backup.db` | `bb87bad24124041302d8c6dc8635a0fb84db0bde70d98e444e0a2ed95797f843` | 10 | ok | 0 |

第一份为只读时间戳备份；第二份由合并后的 `Database.initialize()` 在 live migration
前自动生成。两份均保留 157 videos、140 completed videos、434 sync runs 和 0
research tasks。

时间戳备份的工作副本先完成 schema 10→14 演练；第一次和第二次 initialize 后的
SHA-256 均为
`56add17153069ba1fac67a5b9f77bcdeb0f26d021fc2b809394082b81cc217f3`，证明迁移在该
真实现场副本上可重入且不改变材料性业务计数。

# 4. Live schema 14 migration

迁移由 Main Session 使用已合并代码中的 `Database.initialize()` 执行。

| Check | Before | After |
| --- | ---: | ---: |
| schema | 10 | 14 |
| videos | 157 | 157 |
| completed videos | 140 | 140 |
| sync runs | 434 | 434 |
| active sync runs | 0 | 0 |
| research tasks | 0 | 0 |
| FK violations | 0 | 0 |
| integrity | ok | ok |

迁移后 live DB SHA-256：

```text
5455c4a071f70f3873047652c85d31f4284066491a61e34a98ccfa5ce4f3ec13
```

V5-B Candidate/Fact/Artifact/Page lifecycle、durable update operation、ArtifactRoute 与
WorkspaceRecord 等 schema 对象均已创建；V5-B 业务行仍为 0，没有通过 migration
伪造 Task、Fact、Artifact、Page、Route 或 Workspace 数据。

# 5. Verification

V5-B Session 的最终支持证据：

```yaml
stage_5_matrix: 6_passed
stage_1_to_5_directed: 35_passed
affected_regression: 241_passed
default_no_provider: 1721_passed_4_deselected
```

Main Session 在合并前后独立确认：

- Stage 1–5 与 Search/Ask/Web/API 关键兼容集合共 108 项通过；
- Python compile、JavaScript syntax、Program/V5-B Ledger JSONL 与 whitespace 通过；
- 定向测试全部使用临时数据库，live DB hash 在测试前后不变；
- optional Provider comparison 未运行，成本 USD 0，未访问 credential 或 Keychain。

恢复服务后的只读 smoke：

```yaml
http:
  /: 200
  /search: 200
  /ask: 200
  /research: 200
  /api/research/product/tasks: 200
stage_5_template_marker: present
stage_5_javascript_marker: present
product_task_count: 0
live_test_records_created: 0
http_window_database_hash_unchanged: true
services:
  web_launch_agent: running
  scheduled_sync_launch_agent: loaded
```

# 6. Accepted product result

V5-B 现已提供：

- Candidate → current Evidence validation → immutable Fact/Artifact/Topic Page → explicit review/publish；
- append-only correction、retire、supersede、conflict、staleness 和 Page revision lifecycle；
- durable refresh/recovery/retry/dead-letter/needs-user 与 revision/hash export；
- explainable direct reuse、incremental refresh、research seed 和 contribution lineage；
- typed Explicit Memory、inferred/focus/progress、Corpus soft prior 与 Experience candidate；
- bounded related Page navigation、advisory exact-target Feedback 和 derived observability；
- 一条 integrated Knowledge Workspace 产品面，同时保持 Search/Ask/Research authority 不变。

DeepTutor 与 WeKnora 只以固定 Commit、reference-only、Shiliu-native independent
reimplementation 方式使用；没有引入依赖，也没有复制上游源码、测试、Prompt 或 UI。

# 7. Known limits

以下是诚实限制，不构成 V5-B 失败：

- related Page 目前是 per-Task published-page navigation，不是 corpus-wide graph；
- 每页 relation projection 上限为 8；
- 大规模真实 corpus 的 relation latency 与多进程 UI polling 顺序尚未专项证明；
- optional subjective Provider product comparison 未运行；
- live 数据当前有 0 个 Research Task，因此真实用户 Feedback、Workspace 和知识资产仍是 cold start；
- V5-A 的长复合查询召回限制未由 V5-B 修改或伪报解决。

# 8. V5-C Entry assessment

```yaml
V5_C_entry:
  artifact_reuse_path_exists: true
  feedback_event_mechanism_exists: true
  live_feedback_population_exists: false
  explicit_memory_confirm_and_correct_exists: true
  corpus_model_readable_as_soft_prior: true
  two_comparable_product_paths_exist: true
  status: ready_for_startup_planning_with_cold_start_input_gap
  V5_C_implementation_authorized: false
  V5_C_session_created: false
```

V5-C 可以在用户后续授权时进入 startup/JIT planning；本报告不启动 V5-C，也不把
尚未存在的真实反馈数据写成已积累。

# 9. Final decision

```yaml
final_decision:
  decision: accepted_with_known_limits
  V5_B_goal_met: true
  five_stages_accepted: true
  mainline_merge: 7d9af9009926c13cd94e149b9e54c87cdf2ffc9d
  live_schema: 14
  live_migration_verified: true
  product_runtime_running: true
  active_subversion_after_closeout: none
  provider_runs_performed: false
  credentials_accessed: false
  push_performed: false
  tag_created: false
  V5_C_started: false
```
