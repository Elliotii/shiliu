# 拾流 V5-C Current State

```yaml
document_status: stage_4_accepted_stage_5_contract_proposed
version: V5-C
updated_at: 2026-08-10
execution_branch: codex/v5-c
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
accepted_stage_2_baseline: 95749a1d557dbbb51383b58821519e0524227566
accepted_stage_3_baseline: 68e704e56bc0ba99de0506e9e2b93176b5c978a9
accepted_stage_4_baseline: b9a07004267b2131121d558f5343063e5293db24
main_stage_4_acceptance: 31f4075da06626ba4251aa7375919f676bf98bf9
main_stage_4_decision: V5D-20260810-030
active_formal_stage: V5_C_stage_5_contract_preparation
stage_1_status: accepted_by_v5_main
stage_2_status: accepted_by_v5_main
stage_3_status: accepted_by_v5_main
stage_4_status: accepted_by_v5_main
stage_5_contract_status: proposed_pending_v5_main_acceptance
stage_5_implementation_authorized: false
stage_5_implementation_started: false
version_closeout_started: false
schema_source_version: 14
live_database_access_this_contract_round: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
external_JIT_research_performed: false
```

## 1. Authority 与 accepted baseline

V5 Main 在 `codex/v5-main@31f4075da06626ba4251aa7375919f676bf98bf9` / Decision
`V5D-20260810-030` 正式接受 Stage 4 implementation
`b9a07004267b2131121d558f5343063e5293db24`，无 bounded rework；只授权同一 V5-C Session 准备精简
Stage 5 Integrated Personalized Research Journey and Evaluation Contract 与材料性 JIT 判断。

Main 独立证据为 Stage 1–4 directed matrix `16 passed`，live DB SHA-256 在其测试窗口前后均为
`2a695deae36965462c5202b6d68d7f89cca5efe98d04f287225154afeba0b93f`，V5-C worktree clean，Program
authority unchanged。该 hash 仅是 Main 验收证据；本 Contract round 没有访问或重新 hash live DB。

当前唯一 formal Stage 是 Stage 5 Contract preparation。Stage 5 产品实施、版本 closeout、mainline/live migration
均未开始；未进入 V5-D，未修改 Program authority，未访问 Provider/credential，未 push/merge/tag 或自我接受。

## 2. Accepted Stage 1–4 boundary

- Stage 1：exact confirmed limitations-position 只改变 existing Research answer presentation；Feedback/candidate 未确认
  前零行为；
- Stage 2：task/principal/snapshot-bound Corpus soft prior 只在 unchanged Search baseline pool 上做 bounded display
  composition，保留 independent open/counterexample lane；
- Stage 3：confirmed route preference 只产生 advisory recommendation；explicit choice、permission/cost 与
  ArtifactRoute authority gates 优先，CTA 不自动执行；
- Stage 4：pull-only explicit mastery、persisted staleness、same-scope collection delta 与 transcript-bound Radar；
  activity 不等于 mastery，Radar 不自动 Research，exact durable dismiss 复用 append-only Workspace；
- 四者都不授予 Profile/Corpus/Workspace Citation、Verifier、fact、Prompt、Provider 或 execution authority。

## 3. Proposed Stage 5 final slice

`V5_C_STAGE_5_CONTRACT.md` 提议只做两项收口：

1. 在 existing Research Task/Workspace 增加一个纯组合 journey rail，显示 Answer、explicit Search deep-link、Next
   path、Progress/Assistance 的已有 status/context hash 与 controls；不新建 Journey/Profile/Rules/Telemetry/Eval
   truth store，不预跑 Search 或自动执行任何 path；
2. 把 Personalized Answer 最终边界冻结为 existing limitations placement 加一个唯一新增 presentation key
   `answer.presentation.detail_level=standard|compact`。compact 只把第二个及后续原 answer blocks 按原顺序放入
   用户可展开的 `<details>`；API text/order/citation IDs、Evidence section、limitations、Verifier/currentness、Prompt
   与 Provider 均不变。

Shared explain/all-off/correct/rollback 只组合 existing Stage 1–4 contexts/toggles/Workspace actions。Session all-off
零写；Search 仍需用户在 existing surface 输入并提交 query；explicit Search/route/permission/budget 永远优先。

## 4. Closeout evidence contract

Stage 5 implementation 必须冻结 integrated cold/treatment/off/per-consumer-off/rollback/unrelated/candidate/conflict/
drift/override/restart/non-interference matrix，并分层报告：

- cold-start：只证明 absence/fail-closed/no-write；
- seeded fixture：只证明 deterministic mechanics、visible paired effect 与 authority；
- real-user：只有明确授权的 live/user evidence 才可声称；缺失必须列为 unproven，不能由 fixture 冒充。

Stage 5 implementation 将运行一次完整 default no-provider suite 作为 V5-C closeout mechanical evidence；此前 Stage
的 full suite 不补跑。Stage 5 integrated implementation report 与 version closeout request 合并为单一
`V5_C_FINAL_CLOSEOUT.md`，但 V5-C 不能宣布 Stage/版本 accepted。

## 5. JIT、复杂度与未证明项

本地 accepted Stage 1–4 contracts、源码、tests 与 reports 已关闭最终 Contract 缺口。Answer detail-level 可由
existing answer blocks 做 deterministic DOM composition，不需要外部机制、Prompt、Provider 或依赖。因此没有材料性
外部 JIT、不新增 upstream report/adoption proposal，也不提出 Provider comparison。

默认预算为零 schema/table/index/migration/dependency/Prompt/Provider/background worker/scheduler/notification/graph/
rules/journey/telemetry/eval platform；最多扩展一个 existing PersonalizationContext、增加一个纯组合 journey view 和
一个 answer presentation behavior。若 DOM composition 无法维持 block/citation invariant，implementation 必须停止并
请求 bounded clarification，不得转向 Prompt engine。

仍未证明：真实用户个性化收益、真实 Corpus recall/latency、route recommendation 质量、Radar relevance、large
Workspace/multi-process ordering、Provider 主观质量、distinct Translation route、Stage 5 integrated mechanics 与
最终完整 suite。

下一动作仅为等待 V5 Main 对 Stage 5 Contract、final Answer boundary、integrated matrix、closeout evidence 与无材料性
JIT 判断做有限审阅。Main 接受并明确授权前不实施 Stage 5、不执行 version closeout、不访问 live DB/Provider/
credential、不修改 Program authority、不 push/merge/tag，也不进入 V5-D。
