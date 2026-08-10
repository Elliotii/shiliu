# 拾流 V5-C Version Charter

```yaml
document_status: proposed_pending_v5_main_acceptance
version: V5-C
title: Personalized Research Agent
proposal_authority: V5-C Version Session
acceptance_authority: V5 Main Session
created_at: 2026-08-09
execution_branch: codex/v5-c
required_starting_ref: codex/v5-main
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
accepted_code_baseline_merge: 7d9af9009926c13cd94e149b9e54c87cdf2ffc9d
live_schema_observed: 14
active_formal_stage: startup_and_JIT_docs_only
stage_1_contract_status: proposed_pending_v5_main_acceptance
implementation_authorized: false
product_implementation_started: false
provider_runs_authorized: false
live_database_migration_authorized: false
self_acceptance: forbidden
```

> 本 Charter 是 V5-C Session 的版本提案，不是接受记录或产品实施授权。V5 Main 只在版本/Stage
> 边界接受；V5-C Session 负责版本内部设计、实现、普通修复、测试和 Stage 内集成，但不能正式接受
> 自己的 Charter、Stage 或版本。

## 1. 版本使命

V5-C 将 V5-B 已存在但不影响产品行为的个人/语料状态，转化为一个用户可见、可控制、可解释、
可修正和可回滚的 Personalized Research Agent：

```text
Feedback / Explicit Input / Corpus and Knowledge Observations
→ Candidate or Confirmed Authority
→ Versioned Personalization Context / Current Focus
→ Personalized Answer
→ Corpus-aware Search
→ Personalized Route Recommendation
→ Knowledge Progress / Staleness / Collection Delta / Early Project Radar
→ Explain / Correct / Disable / Roll Back
```

成功不是“拥有 Memory”。成功是同一任务可以机械比较无 Profile baseline、已确认 treatment、
disabled/rollback 和无关输入负例；用户能看见采用了什么、为什么采用、如何撤销，并且事实、引用、
Verifier、开放搜索和用户显式选择的权威没有被个性化状态取代。

## 2. 已确认起点与不可冒充项

### 2.1 可复用的已接受基线

- schema 14 的 immutable `research_workspace_records`，含 explicit memory、inferred candidate、
  focus、progress、corpus observation 和 system experience 的 typed authority/status；
- `confirm/correct/reject/expire/tombstone/invalidate/diagnose` append-only revision 语义、expiry
  projection、source-boundary validation 与 old-boundary no-resurrection；
- exact-target advisory Feedback Event + CommandReceipt；
- L1 current transcript/ASR evidence、L2 Grounded Fact、L3 Artifact/Page revision 与 currentness；
- ArtifactRoute 的 independent open-corpus lane、authority gates 和 direct/incremental/seed；
- Fast/Deep Ask、Product Search、durable deterministic Research、ASR pipeline 的当前显式路径；
- V5-B 已接受的 fixed-commit DeepTutor/WeKnora reference-only 研究结论。

### 2.2 当前不能声称

- live Research/Feedback/Workspace 均为 cold start；fixture 只证明机制，不是用户历史；
- frozen taxonomy snapshot 的存在不等于已有用户 Profile 或已证明 corpus personalization；
- Workspace、Feedback 和 corpus prior 当前不被 Search、Ask、Research、ArtifactRoute、Prompt、
  budget 或 runtime 消费；
- ArtifactRoute 只决定 Artifact direct reuse / incremental refresh / research seed，不是 Fast/Deep/
  Research/ASR/Translation 的通用 Router；
- 当前没有独立 Translation service/queue/route。英文字幕仅在现有付费 transcript cleanup 阶段保留
  英文原文并产出中文整理结果；不得把它冒充独立可选 Translation route；
- V5-A compound long-query grounded completion、真实用户个性化收益、规模/延迟和 Provider 主观质量
  均未证明，也不自动成为 V5-C Stage 1 backlog。

## 3. 权威模型

V5-C 不新建平行的“Profile truth store”。`WorkspaceRecord` revision 继续是长期用户状态的唯一正式来源；
`PersonalizationContext` 只是按 consumer whitelist 生成的只读、可重建投影，带输入 revision/content hash
和 projection policy version，不获得 Citation 或 Verifier 权威。

### 3.1 输入到行为的完整映射

| Input | Candidate / confirmed authority | Consumer | 可见效果 | 解释 | Disable / rollback |
| --- | --- | --- | --- | --- | --- |
| 用户明确回答偏好 | `explicit_memory:user_authored/current`，或已确认 candidate | Stage 1 Research answer presentation；后续 bounded answer policy | 只改变已生成内容的展示策略；Stage 1 为 limitations 前/后位置 | semantic key、值、record/revision/version、scope、fallback reason | 单次 `off` 回 baseline；tombstone/expire 持久关闭；correct 到旧值形成新 revision |
| 用户明确 Current Focus | `focus_state:user_authored/confirmed` | Stage 1 explanation；Stage 4 progress/help | 显示当前 Focus 与其版本；Stage 1 不据此改事实答案 | focus record/version/source/reason | correct/expire/tombstone；恢复旧值须 append 新 revision |
| 结构化 Feedback | exact-target advisory Event；本身不是 Profile | Stage 1 candidate intake | 两个一致、distinct 且同 task 的反馈可供用户创建 candidate；创建/确认前零行为效果 | target/hash/event refs 与候选理由 | dismiss/reject candidate；反馈不自动删除目标或改变产品 |
| 隐式/行为信号 | `inferred_candidate:behavioral_candidate/candidate`，至少两个 distinct Event refs | review surface only，确认前无 product consumer | 只出现候选卡 | evidence refs、confidence、expiry、boundary | reject/expire/tombstone；旧 boundary 不复活 |
| frozen Corpus observation | `corpus_observation:corpus_soft_prior` | Stage 2 query expansion/rerank only | 显示 corpus cue 与独立 open lane | snapshot id/hash、cue、lane contribution | per-query lane off；invalidate/tombstone；open lane 永不关闭 |
| current Fact/Artifact/Page | 各自既有 L1/L2/L3 authority；不是 Profile | 既有 ArtifactRoute；Stage 3 route recommendation input | direct/incremental/seed reason；未来与其他真实路径并列建议 | currentness、coverage、citations、authority hash | 用户选同等或更安全 route；source drift fail closed/reassess |
| explicit route/budget choice | 用户当次选择，优先于 personalization | Stage 3 recommender | 推荐与用户覆盖并列显示；不自动升级高成本路径 | cost/currentness/coverage/permission reason | `off` 保持当前显式选择；用户 override |
| progress observation | 用户自述可为 authority；watched/collection 仅 evidence-backed observation | Stage 4 Progress | learned/understood/familiar 仅来自 user assertion；观看不等于掌握 | source/type/time/uncertainty | correct/expire/tombstone；不做永久推断 |
| staleness / collection delta | current source/taxonomy delta observation；先为 candidate/observation | Stage 4 bounded inbox | 可关闭的更新/缺口卡；不自动重写 Page/Profile | source old/new version、delta、why-now | dismiss/expire/tombstone；同 boundary no-resurrection |
| bounded Early Project Radar | current Evidence + confirmed Focus 的候选提醒 | Stage 4 pull/inbox projection | 有证据、低频、用户可见的候选；无后台自主 Agent | triggering sources、focus version、frequency cap | 全局/单类 off、dismiss、expiry、rollback |
| System Experience | `experience_candidate` | V5-D only | V5-C 中不改变 Skill/Prompt/Policy | Trace/Result/environment fingerprint | diagnose/reject/invalidate；V5-C 无 promotion |

### 3.2 绝对边界

- `user_authored` / `user_confirmed` 与 behavioral candidate 永远分离；
- 隐式信号只能形成 Candidate，不能直接改变 Prompt、Router、Skill 或确认态 Profile；
- Profile/Workspace/Artifact/Corpus 不成为 Citation、Verifier 或外部事实 authority；
- corpus prior 不是 hard filter，不能压制 open search、counterexample 或 no-profile baseline；
- consumer 必须使用 semantic-key whitelist；无关、未知、冲突、过期或不确定输入 fail closed；
- 用户当次明确选择、预算、credential/provider permission、currentness 和 evidence coverage gate 优先；
- correction/rollback 只追加 revision，不物理删除、不覆盖历史、不把旧终态 revision 重新激活；
- V5-D Active Skill/policy promotion/self-modification 完全越界。

## 4. 精简 Stage 序列

一次只保持一个 formal Stage；后一个 Stage Contract 只能在前一 Stage 被 Main 接受或明确关闭后进入。

### Stage 1 — Confirmed Personalized Answer Presentation

- 复用现有 Feedback/Workspace；结构化反馈只产生 candidate；
- 建立 versioned `PersonalizationContext` 只读投影和 user-confirmed Current Focus；
- 一个低风险 Research answer presentation 效果：确认态
  `answer.presentation.limitations_position = before_answer|after_answer`；
- 不改答案文本、Prompt、检索、证据、引用、route、budget 或 Provider；
- 完整 explain/correct/expire/disable/rollback/no-resurrection；
- paired no-profile、candidate、confirmed、disabled/rollback、unrelated negative tests。

### Stage 2 — Corpus-aware Search

- folder semantics、topic aliases、uploader/series、language/source availability 等只作 soft prior；
- 一条独立 open-corpus/counterexample lane 始终执行；
- corpus cue 可解释、可关闭，profile absent/uncertain 保持现有 Search baseline；
- Corpus Model 不成为 Citation、Verifier、hard filter 或事实来源。

### Stage 3 — Personalized Routing

- 基于真实存在的 ArtifactRoute、Fast、Deep、Research 和 ASR 能力给出 recommendation；
- 当前英文 transcript cleanup/translation 组合能力必须明确标注，不得伪造独立 Translation route；若要
  新建独立 route，须在 Stage 3 Contract 单独证明 authority、预算、Provider 和恢复语义；
- 冷启动/不确定时保持用户当前显式选择；不自动触发 ASR、Provider 或高成本 Research；
- 用户可 override，ArtifactRoute 的 currentness/citation/open-lane gate 不被绕过。

### Stage 4 — Knowledge Progress and Bounded Assistance

- user-confirmed Current Focus、Knowledge Progress、Staleness、Collection Delta；
- bounded Early Project Radar 只作为有证据、低频、用户可见、可 dismiss 的候选；
- 不把 watch/search/collection 等同掌握或永久兴趣；
- 不建设通用 scheduler、notification/rules/telemetry 或无人值守后台 Agent。

### Stage 5 — Integrated Personalized Research Journey and Evaluation

- 将 Personalized Answer 从 Stage 1 presentation slice 收口到已证明安全的 bounded answer behavior；
- 串联 answer/search/route/progress/help 的 explanation、disable 与 rollback；
- 冻结 baseline/treatment/off/rollback/unrelated matrix 和 cold-start/seeded/真实信号分层报告；
- Provider 产品比较只有在回答具体剩余问题时才另提冻结低预算方案，且不替代 mechanical Gate；
- 提交 V5-C closeout 给 Main；V5-C 不自我接受、不做 mainline/live migration。

## 5. Stage 级测试纪律

每个行为至少有以下机械配对：

1. no-profile baseline 等于进入 V5-C 前的当前产品；
2. candidate/unconfirmed 等于 baseline；
3. confirmed treatment 只改变 Contract 明列字段；
4. per-request/session disabled 等于 baseline；
5. tombstone/expiry/rollback 恢复 baseline 或先前已确认投影；
6. unrelated/unknown semantic key 不影响该 consumer；
7. source drift、冲突、过期、malformed payload fail closed；
8. duplicate/restart/fault 不产生双份 authority 或部分行为；
9. citations、currentness、Verifier、open lane、budget、explicit choice 不漂移。

真实用户行为收益必须与 fixture mechanical evidence 分开报告。cold start 不阻塞实现机制，但阻止
“已证明个性化有效”的结论。

## 6. JIT upstream 结论

本轮没有材料性外部研究缺口，故不新增 `V5_C_UPSTREAM_*_RESEARCH_REPORT.md`：

- Program Registry/Research Log 的 `local_memo_self_evolution` 与
  `survey_what_when_how_self_evolving` 足以提供 retention/generalization/regression 边界，但不导出架构；
- DeepTutor `44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8`（Apache-2.0）和 WeKnora
  `fcc4cd6a9f29a94818e481b3a604f44ce51c55e2`（MIT + listed third-party）已有 accepted
  fixed-commit reports，继续仅作 reference-only baseline；
- 当前 Workspace/Feedback/Search/Ask/Research/ArtifactRoute 源码与测试足以定义 Stage 1。

结论：`reimplement_shiliu_native_from_local_accepted_contracts`；本轮无新 adopt proposal，无依赖、
checkout、下载、源码/测试/Prompt/UI 复制。若未来提出新 personalization inference、独立 Translation
route、外部 corpus authority 或代码复制，再按材料性规则重新固定官方来源/Commit/License/源码/测试。

## 7. 版本复杂度与禁区

默认复用 schema 14、Event/Receipt、Workspace revision、既有 route 和 surface。任何新表、migration、
后台执行器、Provider 或依赖必须由对应 Stage Contract 以不可由现有结构满足的 invariant 证明；不能先建
MemoryOS、Rules、GraphRAG、Scheduler、Notification、Telemetry 或 Eval 平台再寻找用途。

V5-C 不实施 V5-D/Post-V5，不修复未被 Stage material gate 触发的 V5-A limitation，不迁移 live DB，
不读取 credential/Keychain，不 push/merge/tag。

## 8. Main 有限决策请求

本启动包只请求 V5 Main 决定：

1. 是否接受本 Version Charter；
2. 是否接受五 Stage 序列；
3. 是否接受 `V5_C_STAGE_1_CONTRACT.md`；
4. 是否同意“无材料性 upstream adoption proposal”的 JIT 结论；
5. 是否授权 V5-C Session 开始 Stage 1 产品实施。

在 Main 明确接受并授权前，`implementation_authorized=false`，V5-C Session 停止在 docs-only startup。
