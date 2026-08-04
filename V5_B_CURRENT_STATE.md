# 拾流 V5-B Current State

```yaml
document_status: stage_2_implementation_submission_pending_v5_main_review
version: V5-B
version_session: Shiliu V5-B Version Session
updated_at: 2026-08-04
branch: codex/v5-b
version_starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
stage_1_accepted_commit: abe002ab95025b38565464e69ca8b3abe651f1ae
stage_1_acceptance_record: 2f4dabf_on_codex_v5_main_not_cherry_picked
stage_2_contract_commit: a931e2863f3ae245205c1f64bad7e45d25f03225
stage_2_acceptance_and_authorization_record: c6317a5_on_codex_v5_main_not_cherry_picked
charter_status: accepted_by_v5_main
stage_1_implementation_status: accepted_by_v5_main
stage_2_contract_status: accepted_by_v5_main
stage_2_implementation_authorized: true
stage_2_implementation_status: implemented_pending_v5_main_acceptance
schema_source_version: 12
provider_runs_performed: false
credentials_or_keychain_accessed: false
live_database_migrated_by_this_session: false
```

## 1. 当前一句话状态

V5-B Stage 2 已依 `codex/v5-main@c6317a5` 的授权完成 no-provider/temp-DB 实施并通过提交边界验证，现请求一次 limited V5 Main acceptance review；没有自我验收、没有启动 Stage 3。

## 2. 已完成用户路径

```text
changed SourceVersion / explicit revalidation
→ append-only current-Evidence observation
→ visible Fact/Artifact/Page stale projection
→ durable update Candidate（never auto-applied）
→ user correction / retire / supersede review
→ new immutable FactRevision
→ synchronous claimed durable refresh operation
→ new immutable ArtifactRevision + PageRevision draft
→ Page edit/history/diff/revert-as-new
→ explicit publish-or-return
→ preserved transcript citation drill-down
```

Stage 1 的 Candidate-only、L1 authority、initial immutable revisions、receipt 和 explicit publish 均保持。新 Evidence 与 late result 不会自动改 Fact 或 published Page。

## 3. Concrete Stage 2 state

- schema source 12：追加 Fact state/revalidation/update candidate/lifecycle decision/conflict observation/update operation/Page revision decision/export records；immutable records 受 update/delete trigger 保护。
- source-version revalidation 保存 append-only observation，并以 current/stale projection显示 affected Fact/Artifact/Page；stale 只表示当前 grounding 失效，不宣称 claim 为 false。
- correction/supersede 仅在 server-owned current Evidence eligibility 通过后创建新 FactRevision；不受支持的 edited claim 保持 `needs_revalidation`；retire 不删除 history。
- temporal/viewpoint `unknown` 保守 overlap；scope 明确不重叠不进入 conflict eligibility；confirmed conflict 需要两个可追踪 current-grounded Fact 与显式用户决定。
- Page family 分离 latest working revision 与 published revision；edit 和 revert 均创建新 draft revision，diff 为 derived projection，只有 explicit publish 移动 published pointer。
- 专用 SQLite durable operation 保存 intent、dedup、claim generation/lease、bounded retry、dead-letter、needs-user、cancel/superseded 与 output；recovery 只扫描本产品表，不建设 general queue。
- finalize 同事务写 Artifact/Page outputs、links、working head、terminal operation、Event、Receipt；head/source/claim fence 拒绝 late result。
- revision-ID/content-hash addressed Markdown/JSON export 已交付；temp + fsync + replace，失败独立可观察且不污染/回滚 canonical SQLite，同 revision/command 可安全重试。
- minimal API/UI 已覆盖 revalidate、update review、operation recovery/resolve、Page edit/history/diff/revert、export 与 lifecycle 状态。

## 4. 验证状态

开发定向验证：

```text
PYTHONPATH=src <project-venv>/python -m pytest -q \
  tests/test_v5_b_stage1_knowledge_workspace.py \
  tests/test_v5_b_stage2_knowledge_lifecycle.py
→ 17 passed
```

Stage 2 + affected Search/Ask/Research regression：`154 passed`。提交边界只运行一次 default filtered no-provider suite：

```text
PYTHONPATH=src <project-venv>/python -m pytest -q
→ 1703 passed, 4 deselected, 7 warnings in 144.74s
```

repository filter 为 `not external_artifact and not live_provider`。最后补强 restart 实例化后的 operation recovery 单例再次通过。`node --check`、相关 Python `py_compile` 和 `git diff --check` 通过；warnings 均为既有 TestClient/httpx 与 multiprocessing fork deprecation。

## 5. Live DB / Provider 非动作与 sentinel 分类

- 所有实施测试通过显式 pytest `app_paths` / temporary database；代码搜索未发现测试以默认 `Application()` 或默认 `create_web_app()` 打开 live paths。
- 本 Session 未运行 live schema migration、未修改 live content、未读取 credential/Keychain、未调用 Provider/paid service、未增加依赖。
- 初始只读 live SHA-256 为 `fc828d4cba9c9320c6dbeb1a345b1c8a604a9018b8f062f5ca4f43f8754191cd`；完整套件后为 `b156448d688c37efbf496948d6ebfc43a685858cac54398fe1e05a9787ffe55d`，因此“同一观察窗口 hash 相等”证据分类为 `infrastructure-invalid`，不伪报通过。
- 只读诊断证明变化来自测试外并发的已运行 `app.shiliu.sync`：live `sync_runs` id 376 在本地 16:57:18–16:58:37 完成并更新 retrieval/video state；live DB 仍为 schema 10、无 Stage 2 tables、无 `pre-v12` backup。未停止、恢复或改动该外部服务/数据库。

## 6. Honest limits

- `not exercised`：actual live schema-10→12 migration 未授权、未执行。
- `unproven`：multi-process Stage 2 claim/head race stress；当前证据为 SQLite transaction/unique/CAS/claim-generation 与 restart/fault mechanics。
- `not exercised`：真实浏览器视觉/可访问性专项；已有 HTTP/static contract 与 JavaScript syntax evidence。
- `not exercised`：Provider validator/生成质量；Stage 2 mechanical acceptance 不依赖 Provider。
- `bounded limitation`：自动语义 conflict suggestion 未实现；只有 deterministic scope gate + explicit user-confirmed candidate。
- `bounded limitation`：无常驻 background worker；durable intent + explicit/startup-compatible bounded recovery 是 Contract core。
- `excluded`：Artifact retrieval/reuse/research seed、personal/corpus workspace、relations/product evaluation、V5-C/V5-D 仍属 Stage 3–5/后续版本。
- `infrastructure-invalid`：live DB before/after hash equality window被外部定时 sync 干扰；已有正向 no-migration证据，但不能声称 hash unchanged。

## 7. 当前 Gate

```yaml
charter_accepted: true
stage_1_main_acceptance: accepted_at_2f4dabf
stage_2_contract_accepted: accepted_at_c6317a5
stage_2_implementation_authorized: true
stage_2_self_accepted: false
stage_2_implementation_status: implemented_pending_v5_main_acceptance
stage_3_implementation_authorized: false
next_action: limited_v5_main_stage_2_acceptance_review
```

实施和验证的完整证据以 `V5_B_STAGE_2_IMPLEMENTATION_REPORT.md` 为准。
