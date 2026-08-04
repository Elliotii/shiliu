# Shiliu V5-A Gate C and Closeout Report

> Date: 2026-08-04
> Authority: Shiliu V5 Main Codex Session
> Decision: accept_with_known_retrieval_limitation

---

# 1. Outcome

V5-A 已通过 Gate C 并完成版本级验收。V5-A 的 Durable Recursive Research Runtime
目标成立；Gate B 留下的长复合查询召回限制被明确记录，不被误写为 grounded
completion 已证明，也不再扩大为 V5-A 返工。

```yaml
V5_A:
  status: accepted_with_known_retrieval_limitation
  successful: true
  mainline_integrated: true
  live_schema_migrated: true
  product_runtime_running: true
  representative_grounded_completion_proven: false
```

# 2. Mainline integration

- `codex/v5-main` 原 HEAD：
  `9b2725f6ebe3db25828c72174f34bd1b91388368`
- `codex/v5-a` 验收输入 HEAD：
  `04e5c5bbb94311a00f6efafa142908fd7b2b97de`
- 关系：main HEAD 是 V5-A HEAD 的祖先，差异为 `0 behind / 42 ahead`。
- 集成：`git merge --ff-only codex/v5-a`，无冲突。
- Push、Tag：均未执行。

# 3. Migration preflight and recovery

迁移前 live DB 为 schema 9，`integrity_check=ok`、外键违规 0、active sync 0。
Web 与每小时 sync LaunchAgent 均在迁移窗口临时卸载，确认没有进程持有数据库文件，
且 DB SHA-256 在稳定窗口内保持：

```text
2247326b91c41dc5522c4ab3c3e3371efe9a5c16caa617cf3794b23951aa7638
```

迁移前建立两份独立、已验证的 schema 9 备份：

| Backup | SHA-256 | Integrity | FK |
| --- | --- | --- | --- |
| `/Users/elliot/Library/Application Support/Shiliu/backups/shiliu.gate-c-pre-v10-20260804T134024+0800.db` | `8c31308dd03f63aa96afdb797e71d19ea1bdcdfd17d66b6953833aebc74aeb96` | ok | 0 |
| `/Users/elliot/Library/Application Support/Shiliu/shiliu.pre-v10.backup.db` | `76f595c4fb1efe4a43594f51460f82de35086a784ca055a7e51f9eafff4e9ee8` | ok | 0 |

两份备份均含 157 条 videos、140 条 completed videos、373 条 sync runs、
0 条 research tasks。恢复时应先停止两个 LaunchAgent，保留故障现场文件，用任一已验证
备份恢复到 schema 9，重新执行完整性/外键与行数核验后再恢复服务。

# 4. Live schema 10 migration

迁移由主 Session 使用合并后的 `Database.initialize()` 执行。结果：

| Check | Before | After |
| --- | ---: | ---: |
| schema | 9 | 10 |
| videos | 157 | 157 |
| completed videos | 140 | 140 |
| sync runs | 373 | 373 |
| research tasks | 0 | 0 |
| research attempts | 0 | 0 |
| research checkpoints | 0 | 0 |
| FK violations | 0 | 0 |
| integrity | ok | ok |

`research_tasks.control_generation` 已存在，8 张 Stage 4 control/HITL/derivation
表均已创建。迁移后 DB SHA-256 为：

```text
3f7592c400120ea568f5bf7bb251f56d26febdc76f03ed47ee5785ad98ca1f13
```

# 5. Verification

```yaml
default_test_suite:
  command: .venv/bin/python -m pytest -q
  selected: 1686
  passed: 1686
  deselected_external_or_live_provider: 4
  failed: 0
  warnings:
    count: 7
    material: false
    types:
      - existing_Starlette_httpx_deprecation
      - multiprocessing_fork_deprecation
integration_smoke:
  live_research_page_http: 200
  live_research_list_api_http: 200
  response_ok: true
  live_test_tasks_created: 0
  provider_calls: 0
services:
  web_launch_agent: restored_and_running
  scheduled_sync_launch_agent: restored_not_running_between_intervals
```

# 6. Gate B bounded acceptance

接受以下证据：

- durable provider request identity、receipt、usage/cost 与 hard cap；
- provider failure、product-quality failure 与 honest stop 的可追踪分类；
- receipt-bound Deep 输出进入 durable artifact/checkpoint/audit/Result 或 current
  InputRequest；
- 重复 navigation 被阻止，首次空 navigation 最多转为一次 global transcript search；
- mechanical、fault、race、restart 和产品投影回归。

不接受为已证明：

- 任意或代表性长复合查询的稳定 grounded completion；
- dense model not ready 时 lexical fallback 的充分召回；
- 由 0 hit 路径产生 EvidenceUse/citation 或 grounded final answer。

这些限制候选归入 V5-C personalized research agent 与 V5-D controlled search-policy
improvement 的 JIT 设计输入；V5-B 不自动承担，除非其 Corpus Workspace 目标确实需要。

# 7. Final decision

```yaml
final_decision:
  decision: accept_with_known_retrieval_limitation
  V5_A_goal_met: true
  stage_5_gate_A: accepted
  stage_5_gate_B: partial_accept_with_known_retrieval_limitation
  stage_5_gate_C: passed
  live_schema: 10
  product_implementation_complete: true
  program_next_action: prepare_V5_B_startup_plan_and_entry_audit
  active_subversion_after_closeout: none
  push_performed: false
  tag_created: false
```
