# 拾流 V5-C Current State

```yaml
document_status: stage_3_implemented_pending_limited_v5_main_acceptance
version: V5-C
updated_at: 2026-08-10
execution_branch: codex/v5-c
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
accepted_stage_2_baseline: 95749a1d557dbbb51383b58821519e0524227566
accepted_stage_3_contract: 4368f39c90767f29ffb38efcafe4533be3aa816f
main_stage_3_contract_acceptance: 87179ea94f513126d830301c8ec4a5d10d0ecda9
main_stage_3_decision: V5D-20260810-027
active_formal_stage: V5_C_stage_3_implementation_pending_main_acceptance
stage_1_status: accepted_by_v5_main
stage_2_status: accepted_by_v5_main
stage_3_contract_status: accepted_by_v5_main
stage_3_implementation_status: complete_pending_v5_main_acceptance
stage_4_entered: false
schema_source_version: 14
live_database_access_this_stage: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
external_JIT_research_performed: false
```

## 1. Authority 与 accepted baseline

V5 Main 在 `codex/v5-main@87179ea94f513126d830301c8ec4a5d10d0ecda9` / Decision
`V5D-20260810-027` 接受 Stage 3 Contract
`4368f39c90767f29ffb38efcafe4533be3aa816f`，无 bounded docs rework，并授权同一 V5-C Version Session
自主实施 Contract 冻结的 advisory-only Personalized Routing slice。Main authority 仅作只读引用，没有
cherry-pick/merge 到 `codex/v5-c`。

当前唯一 active formal Stage 是 Stage 3 implementation pending Main acceptance。Stage 3 已实现但未自我接受；
未进入 Stage 4，未修改 Program authority，未 push/merge/tag。

## 2. Stage 3 implementation state

现有 Research Task/Workspace surface 增加 task-scoped “Next path recommendation” panel：

- 唯一个性化输入为 task/principal-bound `explicit_memory + user_authored + current` exact key
  `research.routing.default_path=fast|deep|research`；
- recommendation projection 只读重验 Workspace revision/content/source hash、current Task/Goal、request-local
  permission/cost、exact-video transcript/ASR state 与现有 ArtifactRoute authority fence；
- panel 显示 baseline/recommended/disabled/overridden/blocked/fail_closed、capability state、reason/hash、零执行
  authority 与 inert CTA；
- Fast/Deep CTA 只打开既有 Ask prefill，Research/ArtifactRoute CTA 只聚焦 existing control，manual ASR CTA
  只打开 exact transcript inspection；任何真实执行仍需用户显式操作；
- distinct Translation route 明确为 `not_implemented/not_a_distinct_route`，没有新增伪 capability。

没有修改 Ask、Research、ASR 或 ArtifactRoute execution contract。ArtifactRoute direct/incremental/seed 的
currentness/citation/coverage/open-lane/late-hash fence 继续优先；用户已明确选择时只解释并保持该选择。
permission/cost denial 不会被 Profile 绕过。

## 3. Authority 与 fail-closed boundary

- cold/no preference、candidate/unconfirmed、unrelated Focus/Corpus/Experience、terminal preference 保持 baseline；
- principal mismatch、unknown value、malformed/content drift、confirmed conflict 与 unsafe ArtifactRoute fail closed；
- session off 返回 disabled 且零 Workspace write；correct/tombstone 继续复用 append-only Workspace decision；
- Corpus、Focus、candidate 与 Experience 均无 route authority；preference 无 Citation、Verifier、fact、budget、
  permission 或 execution authority；
- manual ASR 仅在 exact video 缺 current transcript、无 active job 且 request-local permission=true 时显示
  prerequisite；projection 不读取 credential，不访问 Provider，不创建 ASR job；
- Context hash 由 policy、Task/Goal、preference revision、request-local settings、capability state 与理由确定，
  restart/duplicate 结果稳定。

## 4. Lean shape 与验证

实现新增一个 `RouteRecommendationProjection`，并在既有 ArtifactRoute service 增加一个只读 current
assessment revalidation method。复用 Workspace GET 与 Research surface；没有新 endpoint type、store、table、
index、migration、dependency、Prompt、Provider、worker、scheduler 或 general router/rules/policy/telemetry/eval/
budget platform。

Temp DB/no-provider evidence：

- Stage 3 directed paired matrix：`4 passed`；
- Stage 3 + Stage 1/2：`12 passed`；
- ArtifactRoute/Fast/Deep/ASR + Stage 1/2/3 risk set：`54 passed`；
- 既有 Stage 1 Node DOM non-interference：`2 passed`；
- 完整默认套件：`1733 passed, 4 deselected, 7 warnings`；
- `py_compile`、`node --check`、`git diff --check`：通过。

第一次完整复跑仅发现既有 V5-B Workspace UI harness 固定检查旧 baseline 文案；保留该原句并追加 Stage 3
窄例外说明后，定向 `5 passed`，完整套件全绿。warnings 仅为既有 Starlette/httpx 与 multiprocessing fork
deprecation。

## 5. Live/JIT、未证明项与 next action

本 Stage authority 明确禁止访问 live DB，因此本轮没有打开、查询、写入或 hash live DB，也不把 Main 在
Stage 2 验收窗口观测的历史 hash 当作本轮结果。已接受的 live cold-start boundary 不因 temp fixture 改变。
未访问 Provider、网络或 credential/Keychain。

本地 accepted evidence 足以完成实现；没有材料性外部缺口，所以没有外部 JIT、upstream report、下载、
dependency 或 source/test/Prompt/UI copy。

未证明：真实用户 routing preference 的收益、真实 cost/latency/override 质量、ASR recommendation 质量、
large Workspace/multi-process ordering、Provider 主观质量、独立 Translation route，以及 Stage 4
Progress/Staleness/Collection Delta/Early Project Radar。

下一动作仅为等待 V5 Main 对 Stage 3 implementation 做有限验收。本 Session 不自我接受，不进入 Stage 4，
不访问 live DB/Provider/凭据，不修改 Program authority，也不 push/merge/tag。
