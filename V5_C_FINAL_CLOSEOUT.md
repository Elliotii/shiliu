# 拾流 V5-C Final Closeout

```yaml
version: V5-C
stage: Stage 5 - Integrated Personalized Research Journey and Evaluation
report_role: main_integrated_v5_c_final_closeout
report_status: accepted_with_known_limits
execution_branch: codex/v5-c
accepted_contract: 68419dd822d2a3531155b16d75c6ca06c0e72c1b
main_authority: 151709b9d6135c324d88460a4264a8831df244df
main_decision: V5D-20260810-031
implementation_commit: e6c13d72dc064abcaefdb5360e1a775153d7803d
closeout_docs_correction: bdc0812836dac08644f05dea946d6e51f287a68d
main_execution_acceptance: f36b4e75cbd47bf98fa033879806ee16d1949838
mainline_merge: 8904e27df07becebae13110f9be17cd829373b20
main_final_decision: V5D-20260810-033
schema_version: 14
stage_5_accepted: true
v5_c_accepted: true
mainline_integrated: true
live_migration_performed: false
readonly_live_smoke_passed: true
self_acceptance: forbidden
```

V5-C 已完成并由 V5 Main 正式收口。Stage 5 在 existing Research Task 页面增加只读 Journey rail，组合 Stage 1 Answer、Stage 2 Search 入口、Stage 3 Routing 与 Stage 4 Progress/Assistance；唯一新增 Answer behavior 是 confirmed `answer.presentation.detail_level=standard|compact`。执行分支没有自我接受；Main 已完成有限验收、mainline merge、风险导向集成验证与无迁移的只读 live smoke。

## 1. 实现结果与 diff scope

实现保持一个窄 projection extension、一个只读 composition view 和既有 surface：

- `PersonalizationContextProjection` 升级到 `v5-c-stage5-personalized-answer-context-v2`，分别对白名单 `limitations_position` 与 `detail_level` 解码、冲突和 fail-closed；projection 在传入 principal 时只使用 current principal records。
- `answer.presentation.detail_level` 只接受 `standard|compact`。`compact` 复用原 answer block DOM 节点：首块保持展开，第二块起移动到默认折叠的 `<details>`；off/unknown/candidate/terminal/conflict 回到 standard。
- structured Feedback 窄扩展到 detail key/value，并继续复用 two distinct same-Task、exact target/hash/key/value、current-principal Event 检查；Feedback 只形成 Candidate，显式 confirm 前无 effect。
- `IntegratedJourneyProjection` 只组合既有 personalization/routing/assistance status、context hash 和 inert href；不读写第二个 truth store。Search step 始终是 `explicit_query_required`，链接仅预填 `corpus_task_id` 与 `corpus_aware`，不执行 Search。
- Research 页面 session all-off 只同步现有 answer/routing/assistance 开关与 Search link mode；explain/correct/rollback 只聚焦 existing Workspace control，不触发其 action。
- existing Workspace GET 增加 request-local `journey_enabled` 和 additive `integrated_journey`；无新 endpoint type。

Integrated commit 的预期文件范围是 13 个文件：10 个 product/source 文件、2 个 Stage 5 test 文件与本 closeout。未修改任何 Program authority 文件。

## 2. Frozen paired matrix 结果

| Case | 机械结果 |
| --- | --- |
| cold baseline | 无 confirmed detail record 时 `standard`；Journey Answer baseline、Search `explicit_query_required`、Routing/Assistance 保持各自 baseline；projection 零写。 |
| confirmed treatment | current-principal explicit/confirmed `compact` 应用；Journey 只把 Answer 标为 treatment；existing Product 字段不变。 |
| all off | Answer 回 standard，Routing/Assistance disabled，Search href 为 `corpus_aware=false`；显式 path/permission settings 保留；DB counts 不变。 |
| per-consumer off | Journey 保持开启时，各既有 toggle 独立控制自身 context；重新打开单项不会执行 consumer action。 |
| rollback | append-only `correct compact -> standard` 产生新 revision/context hash；旧 revision 历史保留。 |
| unrelated | 非白名单 answer key 不改变 detail projection 或 Journey Answer status。 |
| candidate | exact Feedback pair 创建的 detail Candidate 在 confirm 前 `detail_applied=false`；confirm 后才获得 effect。 |
| conflict | limitations 与 detail 分别解码；冲突 key 自身 fail closed，另一 key 只凭自己的 confirmed authority；Journey 不授予 fallback。 |
| wrong principal | projection 排除其他 principal record；Feedback→Candidate 的 create/confirm 保持 current-principal fence。 |
| drift/malformed | unknown key/value、malformed record 与原 Stage 1–4 drift path保持 baseline/fail-closed；Journey 只反映 status。 |
| explicit override | all-off comparison 保留 `current_explicit_path=fast` 与 request-local permission values；推荐仍无 execution authority。 |
| restart/dedup | temp DB reopen 后 detail context hash 稳定；read-only Workspace/Journey projection 不增加 Event/Receipt/Task/ASR rows。 |
| non-interference | Product 除合法 append-only Workspace audit trace 外所有字段恒等；answer blocks/text/count/order、limitations、citations、Evidence identities、currentness、Verifier/termination/budget/control 均不变。 |
| DOM standard/compact/off | 既有 block object、text、citation marker 与顺序保持；Evidence fixture 不进入 compact container；0–1 block 不显示 details。 |

Stage 1–4 authority 保持：Corpus 仍不是 Citation/Verifier/hard filter；Profile 不执行 route；activity 不升级 mastery；Radar 不自动 Research；ArtifactRoute、Fast/Deep/Research、ASR、Search、Provider 均无自动执行。

## 3. 测试与静态证据

所有测试使用 temp DB/no-provider；未连接 live DB：

```yaml
stage_5_directed_python:
  result: 4 passed
  file: tests/test_v5_c_stage5_integrated_journey.py
stage_5_and_stage_1_dom_node:
  result: 4 passed
  files:
    - tests/js/test_v5_c_stage1_personalization.mjs
    - tests/js/test_v5_c_stage5_answer_detail.mjs
affected_python_risk_set:
  result: 28 passed
  coverage:
    - V5-C Stage 1-5
    - Personal Workspace and Feedback
    - Product Search
    - ArtifactRoute and product closeout
    - ASR non-interference
full_default_no_provider_suite:
  invocation_count_in_stage_5: 1
  result: 1741 passed, 4 deselected, 1 warning
  duration: 243.02s
  deselection: external_artifact and live_provider markers
  warning: existing StarletteDeprecationWarning for TestClient/httpx compatibility
static_checks:
  py_compile: passed
  node_check_research_js: passed
  node_check_personalization_js: passed
  git_diff_check: passed
```

完整 default suite 首次即通过，没有第二次 full-suite run。Directed 阶段曾把 Product 全对象恒等错误地包含 append-only Workspace audit trace；测试 harness 随即收敛为排除合法 trace、比较其余全部 Product fields，并有界复跑通过。该修正不改变产品实现或 authority。

## 4. 零增量与 non-actions 审计

```yaml
schema_table_index_migration_delta: 0
dependency_delta: 0
prompt_delta: 0
provider_calls: 0
new_endpoint_types: 0
background_worker_scheduler_notification_delta: 0
journey_profile_rules_telemetry_eval_truth_store_delta: 0
fact_page_skill_search_route_authority_delta: 0
live_database_reads_or_writes: 0
live_database_migration: 0
credential_or_keychain_access: 0
external_jit_or_bulk_download: 0
program_authority_edits: 0
push_merge_tag: 0
v5_d_work: 0
```

V5-C Session 依授权没有访问 live DB，因此其实现轮没有 live DB SHA-256；历史 Stage hash 未被复用或冒充 Stage 5 证据。Main 随后在独立 closeout authority 下完成备份、mainline integration 与只读 smoke/hash。未运行 Provider comparison，原因仍是本 Stage 的 DOM/authority 产品问题已由本地机械证据回答。

## 5. Evidence tier 与未证明项

### Cold-start evidence

temp DB 中无 confirmed Profile/Focus/detail preference 时，Answer/Route/Assistance fail closed 到 baseline，Search 仅显示 explicit-query link，read-only projection 零写。它证明 absence mechanics，不证明真实用户收益。

### Seeded fixture evidence

固定 Task、Workspace records、Feedback Events、Topic Page 与 answer blocks 证明 treatment、off、rollback、restart、principal fence、DOM order/citations 与 non-interference。Fixture 只证明确定性机制和可见差异，不是真实用户数据，也不证明推荐质量或效用提升。

### Real-user evidence

本轮没有被授权的真实用户 Profile/Focus/Feedback、live journey observation 或 benefit measurement；真实用户采用率、compact 偏好收益、Journey 可理解性与长期纠错行为均为 **unproven**。该缺口按 accepted Contract 不阻塞机械 closeout，但不得转述为已证明产品收益。

## 6. Known limits

- Search step 从不表示 Search 已完成；用户必须进入 existing Search surface，显式输入并提交 query。
- `compact` 是客户端 presentation；它不截断或改写 API answer，0–1 个 block 与 standard 可见等价。
- Journey hash 不是 completion、telemetry 或 evaluation identity，不跨 consumer 修复 conflict/drift。
- Session all-off 不持久化；刷新后按页面默认重新读取 contexts。Durable correction/rollback 仍只能经 existing append-only Workspace decisions。
- Main 已证明 mainline integration、schema 14 无迁移与只读 live smoke/hash；live Research/Profile/Focus/Feedback/Workspace 仍为空，因此真实用户个性化收益仍未证明。

## 7. Main integration and final decision

Main 按用户一次性授权完成：

1. 固定 Main `f36b4e75cbd47bf98fa033879806ee16d1949838`、V5-C `bdc0812836dac08644f05dea946d6e51f287a68d` 与 merge base `5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084`；分叉 10/11 commits，修改文件重叠为 0；
2. 预览 tree `af6d166cb925ab7feb7c6145deec5173e43f5eb5`，`--no-ff` merge commit `8904e27df07becebae13110f9be17cd829373b20` 的 tree 完全一致，两个输入 HEAD 均为其父提交；
3. 合并后风险导向 Python 集合 `98 passed, 1 warning`，Node DOM `4 passed`，compile、JavaScript syntax、Ledger JSONL 与 whitespace checks 通过；
4. 停止 Web/scheduled sync 后建立一份时间戳备份 `/Users/elliot/Library/Application Support/Shiliu/backups/shiliu.v5-c-pre-closeout-20260810T174724+0800.db`，SHA-256 `dd9594931f2fbd6c593f055d0bcf972893d158999a2f1037d9fee4fb2f0344ad`，schema 14、integrity ok、FK 0；
5. 合并后 Web 恢复运行，scheduled sync 恢复为每小时 loaded 状态；`/`、`/search`、`/ask`、`/research`、Research Task API 与 Research JavaScript 均为 200，V5-C template/JavaScript markers 存在；
6. live DB 在 smoke 前后 SHA-256 均为 `2a695deae36965462c5202b6d68d7f89cca5efe98d04f287225154afeba0b93f`，schema 14、integrity ok、FK 0、157 videos、140 completed、447 sync runs、0 active sync、0 Research Task/Event/Workspace/Route/Page。

```yaml
final_decision:
  decision: accepted_with_known_limits
  V5_C_goal_met: true
  five_stages_accepted: true
  mainline_merge: 8904e27df07becebae13110f9be17cd829373b20
  live_schema: 14
  live_migration_performed: false
  readonly_live_smoke_passed: true
  product_runtime_running: true
  active_subversion_after_closeout: none
  provider_runs_performed: false
  credentials_accessed: false
  push_performed: false
  tag_created: false
  V5_D_started: false
```
