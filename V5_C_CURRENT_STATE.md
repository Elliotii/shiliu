# 拾流 V5-C Current State

```yaml
document_status: stage_3_accepted_stage_4_contract_proposed
version: V5-C
updated_at: 2026-08-10
execution_branch: codex/v5-c
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
accepted_stage_2_baseline: 95749a1d557dbbb51383b58821519e0524227566
accepted_stage_3_baseline: 68e704e56bc0ba99de0506e9e2b93176b5c978a9
main_stage_3_acceptance: ba167b3c9b9309df244b3770b347e22698c2187c
main_stage_3_decision: V5D-20260810-028
active_formal_stage: V5_C_stage_4_contract_preparation
stage_1_status: accepted_by_v5_main
stage_2_status: accepted_by_v5_main
stage_3_status: accepted_by_v5_main
stage_4_contract_status: proposed_pending_v5_main_acceptance
stage_4_implementation_authorized: false
stage_4_implementation_started: false
stage_5_entered: false
schema_source_version: 14
live_database_access_this_contract_round: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
external_JIT_research_performed: false
```

## 1. Authority 与 accepted baseline

V5 Main 在 `codex/v5-main@ba167b3c9b9309df244b3770b347e22698c2187c` / Decision
`V5D-20260810-028` 正式接受 Stage 3 implementation
`68e704e56bc0ba99de0506e9e2b93176b5c978a9`，无 bounded rework；只授权同一 V5-C Session 准备精简
Stage 4 Knowledge Progress and Bounded Assistance Contract 与材料性 JIT 判断。Main authority 仅作只读引用，
没有 cherry-pick/merge 到执行分支。

Main 独立证据为 Stage 1–3 directed matrix `12 passed`，live DB SHA-256 在其测试窗口前后均为
`d07037d112c3835e0c2ceb06fd165596a16934684c540610958bd920183c0ce9`，V5-C worktree clean，Program
authority unchanged。本 Contract round 没有再次访问或 hash live DB。

当前唯一 active formal Stage 是 Stage 4 Contract preparation。Stage 4 产品实现未开始；未进入 Stage 5，
未修改 Program authority，未 push/merge/tag 或自我接受。

## 2. Accepted Stage 1–3 boundary

- Stage 1：confirmed/user-authored limitations-position 只改变 Research answer presentation；Feedback candidate
  未确认前零行为；
- Stage 2：task/principal/snapshot-bound Corpus soft prior 只对 unchanged Product Search baseline pool 做 bounded
  presentation composition，保留 independent open/counterexample lane；
- Stage 3：task/principal-bound confirmed route preference 只产生 advisory recommendation；显式选择、
  permission/cost 与 ArtifactRoute authority fence 优先，CTA 不自动执行；
- 三者都不授予 Profile/Corpus/Workspace Citation、Verifier、fact、Prompt、Provider 或 execution authority。

## 3. Stage 4 local audit

- Existing `progress_observation` 已区分 `user_authored|user_confirmed` 与
  `evidence_backed_observation`，并机械拒绝“带事件来源的 learned”；learned/understood/familiar 需要 explicit
  `user_asserted=true`；`mastered` 尚未在 validator enum，若获 implementation authority 只需同白名单窄增量，
  不需 schema；
- Existing Workspace revision 支持 exact source refs/boundary/content hash、principal、expiry、correct、tombstone、
  restore-as-new 和 same-boundary no-resurrection；schema-14 CHECK 已足以复用 progress record 承载 exact
  assistance control，不新增 record kind/table；
- Frozen taxonomy snapshots 包含 selected source IDs、snapshot/card/discovery hashes，read-only `preview` 可重建
  current membership/card boundary；同 scope snapshot pair 可形成 added/removed/changed observation；
- Existing Fact state 与 Artifact/Page lineage 已给出 current/stale/potential-conflict/conflicted 和 affected IDs；
  但 high-level lifecycle projection 会确保/补写 initial heads，Stage 4 read-only projection 不得调用该路径，
  应直接读 existing persisted heads；
- Current Focus 已有 confirmed/user-authored Workspace authority。Early Project Radar 必须再绑定 added delta 的
  current transcript/ASR Evidence，title/description/summary 单独不足。

## 4. Proposed Stage 4 slice

`V5_C_STAGE_4_CONTRACT.md` 提议在 existing Research Task/Workspace surface 增加一个 pull-only panel，最多显示
5 条 progress、2 条 staleness、3 条 collection delta 和 1 条 Radar candidate。一个只读 projection 同时处理：

- mastery 仅来自显式 user assertion；watch/search/collection/transcript presence 永远只作 observation；
- persisted Fact/Artifact/Page non-current boundary 只生成 revalidation candidate，不自动改知识；
- 用户显式给出的 same-scope baseline/current snapshot pair 经 current preview 重验后只生成 bounded delta；
- Radar 只从 added delta 中，在 exactly one confirmed Focus + current L1 transcript/ASR Evidence + deterministic
  exact overlap 时形成一条 candidate；无 Focus/证据或 drift 返回 baseline；
- per-request/session off/dismiss 零写；durable dismiss 必须用户明确点击并复用 exact append-only
  `progress_observation` control，支持 expiry/tombstone/correct/restore-as-new/no-resurrection。

默认预算为零 schema/table/index/migration/dependency/Prompt/Provider/background worker/scheduler/notification/
rules/telemetry/generic inbox/agent-loop 平台，最多一个 read-only `KnowledgeAssistanceProjection`，无新 endpoint
type。唯一预期窄 product validator change 是加入 explicit-only `mastered` state。

## 5. JIT、测试纪律与未证明项

本地 accepted Workspace/Focus、taxonomy snapshot、Knowledge lifecycle/currentness 与 Stage 1–3 evidence 已关闭
Contract 缺口，因此没有材料性外部研究，不新增 upstream report/adoption proposal，未浏览网络、下载上游、
引入依赖或复制 source/test/Prompt/UI。

按 Main 优化后的纪律，本 Contract round 只复跑四项材料相关 temp-DB/no-provider tests：explicit progress /
watched-not-learned、candidate expiry/no-resurrection、immutable taxonomy snapshot delta、Fact/Page staleness
append-only，结果 `4 passed`；未重复完整 default suite。

未证明：真实用户 progress/radar 帮助收益、真实 collection delta 规模/延迟、Focus-to-Evidence relevance 质量、
large Workspace/multi-process ordering、Provider 主观质量、独立 Translation route，以及 Stage 5 integrated
journey/evaluation。

下一动作仅为等待 V5 Main 对 Stage 4 Contract、zero-schema vertical slice、dismiss/no-resurrection 和无材料性
JIT 判断做有限审阅。Main 接受并明确授权前不实施 Stage 4，不访问 live DB/Provider/凭据，不修改 Program
authority，不 push/merge/tag，也不进入 Stage 5。
