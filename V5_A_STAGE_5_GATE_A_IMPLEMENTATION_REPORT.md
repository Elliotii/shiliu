# 拾流 V5-A Stage 5 Gate A Implementation Report

```yaml
stage: V5-A Stage 5
gate: A_mechanical_product_wiring_ui_trace_reliability
report_authority: Shiliu V5-A Version Session
acceptance_authority: V5 main session
as_of: 2026-08-03
branch: codex/v5-a
implementation_baseline: 4366f6309caa624c6219573d8ffec7cab4dfc1eb
implementation_commit: 230af22a91f67e12239515bd6938607c45857b61
gate_A_status: submitted_for_main_acceptance
gate_A_self_accepted: false
stage_5_complete: false
v5_a_complete: false
provider_quality_gate_status: not_authorized_not_exercised
mainline_integration_gate_status: not_authorized_not_exercised
provider_runs_performed: false
credentials_or_keychain_accessed: false
live_database_migration_performed: false
source_schema_version: 10
live_database_schema_observed: 9
```

## 1. 结果摘要

Gate A 已在 `codex/v5-a` 完成并提交：拾流现在具有长期 Research 的产品导航、创建/
列表/稳定链接/详情入口、无 Provider 的有界本地 runner、用户可理解的状态与三维结果
taxonomy、Evidence/Citation、四类 Candidate Delta、持久 trace，以及 Stage 4 当前允许的
input/control/derivation/unknown-effect resolution 交互。

产品 projection 只读取已提交的 durable truth；所有 mutation 继续经过 Stage 1–4
service、transaction、receipt、owner/control fence。Gate A 没有新增 schema 或 migration，
Candidate Delta 使用有界 append-only Event + CommandReceipt，明确保持
`candidate_only_not_promoted`，不创建长期知识、Profile/Memory、System Experience 或
Active Skill authority。

本报告只请求 V5 主 Session 验收 Gate A。Gate B 和 Gate C 尚未授权、尚未执行，因此
不请求 Stage 5/V5-A 完整 `accept`。

## 2. 实现范围

- `ResearchProductService`：有界、去敏的 Task projection；active-Attempt-scoped
  EvidenceUse/Citation；durable trace；四类 Task-scoped Candidate Delta；本机
  cooperative runner。
- `CreateProductResearchRequest` / `RunProductResearchRequest`：严格 extra-forbid、服务端
  目标/约束/step 上限与 command identity 边界。
- `/research`、`/research/{task_id}` 与 `/api/research/product/tasks...`：产品入口、稳定
  链接、列表/详情、异步本地推进。
- Research 页面：shared Evidence renderer、currentness、answer/limitation、状态/停止原因、
  Candidate Delta、摘要/高级 trace、InputRequest、interrupt/cancel/resume、retry、
  branch/replay 与 unknown SideEffect resolution。
- Runner：单 Task 进程内互斥加 SQLite owner lease/epoch fence；claim/takeover、同 Attempt
  restart continuation、每四个动作续租、inner/outer 有界推进、准确 waiting/terminal/
  stopped boundary、exact-once boundary receipt。
- 观察修复：浏览器 JIT 验收发现 freshly-created `ready` Task 的首个 projection 可能早于
  background claim；UI 现同时轮询 `ready`/`running`，自动收敛到下一 durable boundary。

未修改 Prompt、model choice、Tool Contract、既有 Evidence authority 或正式产品 schema。

## 3. Contract 满足矩阵

| Contract 维度 | Gate A 证据 | 结论 |
| --- | --- | --- |
| Product entry | 导航、create/list/detail/stable URL、empty/loading/error；public API 与真实浏览器旅程 | pass |
| Status projection | running/waiting/blocked/terminal；answer status、termination reason、failure class、phase/budget/reason 分离 | pass |
| Trace | Event/Checkpoint/Action/Audit/Receipt/Control 有界投影；安全字段白名单；raw secret 对抗测试 | pass |
| Evidence/Citation | shared renderer；稳定 identity、active Attempt use/currentness；跨 Task shared identity/use 隔离 | pass |
| Control | 当前 Input、interrupt/resume/cancel、unknown resolution 由 Stage 4 allowed operations 与 fence 驱动 | pass |
| Derivation | UI 仅经 Stage 4 retry/branch/replay API；既有 child/source/sibling immutable 测试继续通过 | pass |
| Candidate Delta | 四类均存在或有 empty reason；绑定 Task/Goal/Attempt/Result/Checkpoint、EvidenceUse/Trace；candidate-only | pass |
| Idempotency | create/run/delta receipt replay、payload hash、同 command race、Stage 1–4 replay/CAS 回归 | pass |
| Recovery | Candidate transaction fault rollback、service restart、lease expiry/takeover、同 Attempt continuation | pass |
| Concurrency | 同 runner command race single receipt；Stage 4 multiprocess interrupt CAS one-winner | pass |
| Compatibility | Stage 1–5 + Evidence/Citation + `/search` + `/ask` 联合 199；默认无 Provider 1,642 | pass |
| Boundary | Provider/credential/Keychain 0；live migration 0；Prompt/Tool Contract 0；schema unchanged | pass |

## 4. 定向、故障与浏览器证据

### 4.1 Gate A 定向测试

`tests/test_v5_a_stage5_product_completion.py`：`7 passed`。

覆盖：

1. 页面/公共 API 从 create 到诚实 `waiting_user`，含 open Input、四类 Delta、trace；
2. 服务器注册 evaluator 的确定性 terminal grounded journey、lease renewal、run replay；
3. 两个 Task 共享 EvidenceIdentity，但 EvidenceUse/Candidate snapshot 严格隔离；
4. Candidate Delta Event 后 fault rollback，restart 后 exact-once materialize；
5. lease 未过期 takeover fail closed，过期后 epoch 递增且延续同 Attempt；
6. 两个并发同 command 只有一个 runner boundary receipt；
7. 公共 Input/control interrupt/resume 与 projection secret redaction；Goal revision 后旧
   Attempt citation 不进入新 Attempt projection。

Stage 4 的 27 项 suite 继续提供 current pause lineage、expiry/cancel、unknown effect、
derivation race 与 multiprocess CAS 证据；Stage 1–3 suites 继续提供 transaction、owner、
checkpoint、Evidence authority 与 outer evaluator authority 证据。

### 4.2 联合与完整回归

- Stage 1–5、Evidence/Citation、`/search`、`/ask` 联合定向：`199 passed`；
- 默认无 Provider 全回归：`1642 passed, 4 deselected, 7 warnings in 46.25s`；
- `node --check src/shiliu/static/research.js`：通过；
- `python -m compileall -q src ...`：通过；
- `git diff --check`：通过。

警告只有既有 Starlette/httpx TestClient deprecation 1 项和 multiprocessing/fork
deprecation 6 项。`ruff` 在当前 venv 未安装，标记为 tooling `not_available`，未用作
通过声明；最终没有失败测试。

### 4.3 Browser-facing 旅程

使用隔离临时 AppPaths/SQLite 和 in-app Browser 实际打开 `/research`：

- 创建 `MCP` Task；
- 本地 runner 完成 plan/navigation/transcript search/provisional synthesis/outer audit；
- 在无 corpus evidence 时准确显示 `valid_insufficient / needs_user_input / none`；
- 展示 open clarification、四类 Delta（含 empty reason）与 12 条 durable Event/Receipt；
- 提交当前用户决定，创建 Goal revision 2，再推进到新的 current Input lineage；
- UserModelDelta 只从显式决定产生，未晋升长期 authority；
- 页面未暴露 owner epoch/fence token，控制操作来自 server projection。

该浏览器验收使用 `/tmp` 临时库；未启动 live `Application`。

## 5. Live DB 稳定性

实施启动时观察到 live DB 已被 V5-A 之外的进程在规划基线后更新；本轮采用更新后的
只读 baseline，并在最终完整回归稳定窗口前后复核：

```yaml
path: /Users/elliot/Library/Application Support/Shiliu/shiliu.db
schema: 9
sha256: 8413958d911b2c6391b3d22bc718bc5c0b582657e353b155cb6c20dc19426f76
size_bytes: 94588928
mtime: 2026-08-03T03:06:53+0800
integrity_check: ok
foreign_key_violations: 0
videos: 157
completed: 140
```

前后 SHA/size/mtime 完全一致。V5-A 只用 immutable/read-only SQLite 核验，没有初始化
live Application；source schema 仍为 10，live schema 仍为 9。

## 6. 未证明项与请求

`not_exercised`：真实 Provider/model/Prompt 产品质量、费用/延迟、credentials/Keychain、
live schema 10 migration/rollback、主线集成 smoke、真实网络 external SideEffect。

`unproven`：真实 SIGKILL/断电、多主机长期 lease soak、production-scale retention/
performance、正式 RBAC/多设备协作，以及 Gate B 的代表性真实产品质量。

请求 V5 主 Session 对 Gate A 作有限决定：
`accept / partial_accept / rework / pause / reject`。即使 Gate A 获 accept，Stage 5/V5-A
仍未完整交付；下一动作只能由 Gate B 或 Gate C 的单独授权产生。

```yaml
gate_A_status: submitted_for_main_acceptance
gate_A_self_accepted: false
stage_5_status: mechanical_gate_submitted_only
stage_5_self_accepted: false
provider_runs_performed: false
live_database_migration_performed: false
next_action: V5_main_session_gate_A_acceptance
```
