# 拾流 V5-C Current State

```yaml
document_status: stage_2_implemented_pending_v5_main_acceptance
version: V5-C
updated_at: 2026-08-10
execution_branch: codex/v5-c
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
startup_commit: 2429debf9be426d825c6847e80030a537cc991a9
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
main_stage_1_acceptance: 36338515db001fb86af1c653c1241efc313cfa4e
stage_2_contract_commit: 20aca5b726c0c5585f5066e72778b30dcc2f32b5
main_stage_2_authority: 108d28bac218d76c84e4279f10791f4d902fe115
active_formal_stage: V5_C_stage_2_implementation_pending_acceptance
stage_1_status: accepted_by_v5_main
stage_2_contract_status: accepted_by_v5_main
stage_2_implementation_status: complete_pending_v5_main_acceptance
stage_3_entered: false
schema_source_version: 14
live_database_access_this_stage: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
external_JIT_research_performed: false
```

## 1. Authority 与 Git 状态

`codex/v5-c` 从指定 `5fbe164` 启动。Stage 1 的真实 accepted object 是
`9e83ff078dee0ad038f012d197d812ff0e87a6f5`；Main 已在 append-only Decision
`V5D-20260810-025` 更正先前不存在的完整 identifier，Stage 1 验收结论不变。

V5 Main 在 `codex/v5-main@108d28bac218d76c84e4279f10791f4d902fe115` 接受 Contract
`20aca5b726c0c5585f5066e72778b30dcc2f32b5` 并授权同一 V5-C Session 实施 Stage 2。Main authority 只读
引用，未 cherry-pick/merge 到本分支。当前唯一 active formal Stage 是 Stage 2 implementation pending
Main acceptance；未进入 Stage 3，未修改 Program authority，未 push/merge/tag 或自我接受。

## 2. Stage 1 accepted baseline

Stage 1 保持一个只读、可重建 `PersonalizationContextProjection`。只有 user-authored/current 或
user-confirmed/confirmed 的 `answer.presentation.limitations_position` 能改变 Research limitations panel
前/后位置；答案、Evidence、Citation、Search、route、Prompt、budget、Provider 均不变。Feedback sources
仍须 same Task、exact target/hash、exact semantic key/value、committed receipt 和 current principal，且隐式
输入只形成 Candidate，确认前不改变行为。

## 3. Stage 2 implemented boundary

Stage 2 新增唯一一个 read-only `CorpusSearchContextProjection`，只消费显式 Research Task 内 current、
snapshot-bound `corpus_observation`。Product Search 的 query/mode/filters/planner/raw retrieval/consolidated
candidate pool 不变；Corpus 只在该 pool 上做 deterministic bounded presentation composition。

- 至少 `ceil(N/2)` 个槽是 open lane；
- Corpus 最多占 `floor(N/2)` 个槽；
- 最高 baseline corpus-nonmatching counterexample 必须保留；
- no task/no prior/unrelated/terminal/disabled 返回 baseline；
- principal mismatch、malformed/conflict、Workspace/snapshot/card drift fail closed 到 baseline；
- Citation/Verifier/fact/hard-filter/route authority 全为 false；
- UI 复用 `/api/search` 和 Search page，提供 explicit Task context、per-request off、lane/rank/hash explanation；
- correct/invalidate/tombstone/restore-as-new 继续复用 existing append-only Workspace decisions。

实现增量：0 schema/table/index/migration/dependency/Prompt/Provider/background worker/platform；1 个只读
adapter；0 个新 endpoint type。

## 4. 验证与现场边界

Stage 2 directed matrix `4 passed`；Stage 2 + Search UI `11 passed`；Stage 2 + Workspace + Stage 1
`14 passed`；受影响 Python 集合 `114 passed`。完整默认 no-provider 结果与静态检查见
`V5_C_STAGE_2_IMPLEMENTATION_REPORT.md`；最终为 `1729 passed, 4 deselected, 7 warnings`。

本 Stage 遵循 Main 禁令，没有访问、查询、写入或 hash live DB，也没有访问 Provider、credential 或
Keychain。Stage 1 已接受历史观测是 schema 14，且当时 live Research/Feedback/Workspace/Profile 为 cold
start；两份 frozen taxonomy snapshots 是 corpus state，但不是个性化输入。Stage 2 temp-DB fixture 只证明
mechanics，不冒充真实用户数据或收益。

## 5. JIT 与未证明项

本地 accepted evidence 足以关闭实现缺口，因此没有材料性外部研究、upstream report、依赖或 source/test/
prompt/UI copy。未证明项包括真实用户 Corpus prior 收益、真实集合 latency/recall/counterexample UX、large
Workspace ordering、Provider 主观质量、Stage 3 Personalized Routing、Progress/Staleness/Collection Delta/
Early Radar、独立 Translation route 和 V5-A compound long-query limitation。

下一动作仅是等待 V5 Main 对一个 integrated Stage 2 implementation commit 做有限验收。未获新 authority
前不进入 Stage 3，不访问 live DB/Provider/凭据，不修改 Program authority，不 push/merge/tag。
