# 拾流 V5-C Current State

```yaml
document_status: stage_2_accepted_stage_3_contract_proposed
version: V5-C
updated_at: 2026-08-10
execution_branch: codex/v5-c
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
accepted_stage_2_baseline: 95749a1d557dbbb51383b58821519e0524227566
main_stage_2_acceptance: cd2eda1a116ca3308daba3e72b8018133b0c00b0
main_stage_2_decision: V5D-20260810-026
active_formal_stage: V5_C_stage_3_contract_preparation
stage_1_status: accepted_by_v5_main
stage_2_status: accepted_by_v5_main
stage_3_contract_status: proposed_pending_v5_main_acceptance
stage_3_implementation_authorized: false
stage_3_implementation_started: false
stage_4_entered: false
schema_source_version: 14
live_database_access_this_contract_round: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
external_JIT_research_performed: false
```

## 1. Authority 与 accepted baseline

V5 Main 在 `codex/v5-main@cd2eda1a116ca3308daba3e72b8018133b0c00b0` / Decision
`V5D-20260810-026` 正式接受 Stage 2 implementation
`95749a1d557dbbb51383b58821519e0524227566`，无 bounded rework；只授权同一 V5-C Session 准备精简
Stage 3 Personalized Routing Contract 与材料性 JIT 判断。Main authority 仅作只读引用，没有 cherry-pick/
merge 到执行分支。

Main 独立证据为 Stage 2/Product Search API/Page/Stage 1 风险集 `33 passed`，live DB SHA-256 在其测试窗口
前后均为 `1ee71d2b8c3a09b8a3d814947d8fb6bab89408d3f19f83f15e275bfc1a9558d5`，V5-C worktree clean，
Program authority unchanged。本 Contract round 没有再次访问或 hash live DB。

当前唯一 active formal Stage 是 Stage 3 Contract preparation。Stage 3 产品实现未开始；未进入 Stage 4，
未修改 Program authority，未 push/merge/tag 或自我接受。

## 2. Accepted Stage 1–2 boundary

- Stage 1：confirmed/user-authored limitations-position 只改变 Research answer presentation；Feedback candidate
  保持 same-task/exact-target/hash/key/value/principal fence，确认前零行为；
- Stage 2：task/principal/snapshot-bound Corpus soft prior 只对 unchanged Product Search baseline pool 做 bounded
  presentation composition；至少一半 open lane，最高 nonmatch counterexample 保留；
- 两者均不修改 Citation/Verifier/fact/currentness、Prompt、Provider、ArtifactRoute、route/budget/permission。

## 3. Stage 3 capability audit

- ArtifactRoute 真实 route 仅 `direct_reuse|incremental_refresh|research_seed`；direct 需要 exact scope、complete
  coverage、current Facts/citations，incremental 只允许 current usable core + 最多两个 bounded gaps，用户只
  能选择同等或更安全 route，proceed 时有 late authority hash fence；
- Fast/Deep 是 existing `AskRequest.mode` 的用户显式选择；两者最终只引用 current transcript/ASR，Deep 有
  bounded decision/tool/time/evidence budgets；
- Research 是独立 durable Task/create/run/control path，UI create 当前可显式启动 background run；route
  recommendation 不得代替该点击；
- ASR 是真实 Provider-backed durable job，有 manual/automatic trigger、retry/review 与 explicit endpoint；
  recommendation 只能显示 manual prerequisite，不得自动 POST、读 credential 或启动 background job；
- distinct Translation route 不存在。English transcript cleanup→Chinese output 是现有组合能力，不能被包装
  成独立 path。

## 4. Proposed Stage 3 slice

`V5_C_STAGE_3_CONTRACT.md` 提议在 existing Research Task/Workspace surface 增加 advisory-only panel。唯一
个性化 key 为 task-scoped user-authored/current
`research.routing.default_path=fast|deep|research`；它只影响 recommendation/highlight，不改变当前 UI
selection 或任何 request。

ArtifactRoute/currentness/citation/open-lane/authority hash、request-local permission/cost 与用户显式选择均
优先。Corpus、Current Focus、candidate/unconfirmed、Experience 不是 route authority。manual ASR 只有 exact
video gap + explicit permission 时可显示为 prerequisite，仍需用户点击 existing endpoint。off、override、
correct/expire/tombstone/restore-as-new 均保持可解释和可回滚。

默认实现预算为 0 schema/table/index/migration/dependency/Prompt/Provider/background worker/general router/
rules/policy/telemetry/eval/budget platform，最多一个 read-only recommendation projection，复用 existing
endpoint/surface。

## 5. JIT 与未证明项

本地 accepted ArtifactRoute、Ask Fast/Deep、Research、ASR、Stage 1/2 source/tests 已关闭 Contract 缺口；
因此没有材料性外部研究，不新增 upstream report/adoption proposal，未浏览网络、下载上游、引入依赖或复制
source/test/Prompt/UI。独立 Translation、learned routing、外部 authority、Provider eval 与自动 cost
optimization 明确留待以后，不能先实现。

本 Contract round 以 temp DB/no-provider 复跑 ArtifactRoute、Fast Ask、Deep Search 与 ASR mechanics，结果
`42 passed`；这不是 Stage 3 implementation 或真实用户收益测试。

未证明：真实用户 route preference 收益、真实 cost/latency/override 质量、ASR recommendation 质量、large
Workspace/multi-process UI ordering、Stage 4 Progress/Staleness/Delta/Radar、Provider 主观质量和 V5-A
compound long-query limitation。

下一动作仅是等待 V5 Main 对 Stage 3 Contract、capability precedence、paired matrix 和无材料性 JIT 判断做
有限审阅。Main 接受并明确授权前不实施 Stage 3，不访问 live DB/Provider/凭据，不修改 Program authority，
不 push/merge/tag，也不进入 Stage 4。
