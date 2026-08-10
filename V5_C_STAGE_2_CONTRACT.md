# 拾流 V5-C Stage 2 Contract

```yaml
stage: V5-C Stage 2
title: Corpus-aware Search
contract_status: proposed_pending_v5_main_acceptance
proposal_authority: V5-C Version Session
acceptance_authority: V5 Main Session
created_at: 2026-08-10
execution_branch: codex/v5-c
local_stage_1_execution_head: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
main_stage_1_acceptance_authority: 36338515db001fb86af1c653c1241efc313cfa4e
schema_source_at_contract: 14
implementation_authorized: false
implementation_started: false
provider_runs_authorized: false
live_database_access_authorized: false
self_acceptance: forbidden
```

> 本 Contract 只冻结 Stage 2 的产品、authority、mechanical matrix 与复杂度边界。V5 Main 明确接受并
> 授权前不得实施；V5-C Session 不能接受自己的 Contract 或 Stage。

## 1. Stage 使命与唯一纵切

用现有 frozen taxonomy snapshot 与 `corpus_observation`，在现有 Product Search 页面交付一个可解释、
可关闭、fail-closed 的 soft-prior result composition。Stage 2 只允许改变既有 Search candidate 的展示
顺序与 lane 标注，不改变原 query、mode、filters、raw retrieval、Evidence 或任何事实判断。

```text
Original ProductSearch request
        │
        ├── independent open lane: current Search executes unchanged ──────────────┐
        │                                                                          │
        └── optional task-scoped CorpusSearchContext                               │
              └── current corpus_observation + exact frozen snapshot               │
                    └── bounded deterministic soft-prior lane ─────────────────────┤
                                                                                   ↓
             deduplicated bounded merge + counterexample reservation + explanation
                                                                                   ↓
                       per-request off / invalidate / tombstone / correct
```

选择 post-retrieval composition，而不是 query expansion。这样可以机械证明 open retrieval 仍是原产品、
语料只在同一 baseline candidate pool 内产生有限 presentation effect，也避免先建立新检索平台。

## 2. 输入与 authority

### 2.1 显式 task context

Corpus-aware treatment 只在请求明确携带一个现有 Research `task_id` 时可尝试。没有 task context、Task
不存在、Task boundary 不可验证或当前 principal 不匹配时，必须返回原 Product Search baseline。
不得扫描其他 Task、猜测“最近 Task”或建立全局 Profile。

实现可在现有 `/api/search` strict request 中增加一个 optional task-context field，并复用现有 Search
surface；不得新增 endpoint type。显式 `mode`、filters、scope、result limit 和用户当次选择始终优先。

### 2.2 唯一可消费记录

只有同时满足下列条件的 effective revision 才可成为 soft prior：

- `record_kind=corpus_observation`；
- `authority_class=corpus_soft_prior` 且 `effective_status=current`；
- payload 仍符合现有 exact shape `{"observation_type": ..., "value": ...}`；
- observation type 属于现有 whitelist；Stage 2 首个纵切只消费能被 exact frozen card 字段重验的
  `folder|topic|uploader|series|search_term|limitation`，`source_availability` 也只有在 frozen card 已有
  exact field 时才可消费；
- source refs 恰好一个 `taxonomy_snapshot`，其 snapshot ID、snapshot hash、Workspace boundary hash 与
  frozen cards 均可只读重验；
- revision/content hash 与 projection policy version 进入 explanation/context hash。

Candidate、behavioral inference、explicit memory、Current Focus、progress、system experience 不能冒充
Corpus prior。`invalidated|tombstoned|expired|superseded`、unknown type、blank/malformed value、missing/drifted
snapshot、冲突或无法确定适用性的输入全部 fail closed。多个合法 prior 可以形成 bounded cue set，但同一
normalized semantic key 的矛盾值使整个 treatment fail closed，不能按 timestamp 猜测。

当前 accepted observation whitelist 和 frozen card 没有独立冻结的 `language` cue，也没有任意 topic-alias
authority。本 Contract 不伪造二者：language、未冻结 alias 或无法映射到 exact card field 的 cue 一律
baseline。以后若它们成为 Corpus-aware Search 的材料性缺口，只能由 Main 接受有界 Contract clarification；
不得先加通用 taxonomy/alias/metadata 平台。

### 2.3 query relevance

prior 必须与当次 normalized query 有 deterministic lexical relevance 才能进入 treatment。只允许
normalized exact phrase/token overlap 与 frozen card 的现有 metadata crosswalk；不得调用模型、embedding
或模糊推断“潜在兴趣”。unrelated prior 等于 baseline。

## 3. 冻结 Search 行为

### 3.1 Independent open lane

现有 Product Search 必须先按原 request 独立执行：

- raw query、normalized query、query type、requested/effective mode、fallback；
- filters、scope、raw top-k、lexical/dense/hybrid candidate counts；
- raw hits、index identity、consolidation、Evidence windows/currentness。

以上输出在 empty、treatment、disabled、unrelated 与 counterexample cases 中必须逐字段一致（仅允许
timing、trace ID/time 等既有非决定性字段不同）。Corpus context 不能改变 planner/router、请求 mode、
embedding invocation、retrieval filters、raw score、candidate inclusion 或 fallback。

### 3.2 Bounded soft-prior lane

soft-prior lane 只能对 independent open lane 已产生的 consolidated candidate pool 做 deterministic stable
composition：

- cue match 只看 exact frozen card identity 及该 card 实际冻结的 title/uploader/folder/declared
  topic-or-series/source-availability metadata；字段不存在即 fail closed，不得读取 transcript text 作为
  Profile 证明；
- 每个 promoted result 必须列出匹配的 Workspace revision、snapshot ID/hash、cue type/value 与原 baseline
  rank；相同 cue score 保持 baseline order；
- 不得新增、删除或伪造 raw hit、Evidence window、citation、result content 或 metadata；
- 不得把 corpus match 表述为“更真实”“已验证”或用户已掌握，只能标为 `soft_prior_match`；
- composition 必须 deterministic、deduplicated，并由 versioned bounded policy 生成 context/result hash。

### 3.3 Open/counterexample reservation

对展示上限 `N`：

- 至少 `ceil(N/2)` 个可用展示槽来自 baseline open-lane 顺序，不能由 corpus match 覆盖；
- corpus lane 最多影响其余 `floor(N/2)` 个槽；无合法 match 时全部回 baseline；
- 若 baseline pool 存在不匹配 corpus cue 的结果，最高排名的该结果必须保留在展示集并标为
  `open_counterexample`；
- dedup 或 pool 太小时按 baseline 顺序补齐，绝不扩大检索或隐藏反例。

上述是 lane invariant，不要求建立通用 reranker。实现可以使用一个窄的 read-only
`CorpusSearchContext` projection 与现有 Product Search 内部的 bounded merge；不得新增通用 scoring DSL、
rank-learning、vector store、graph 或 index。

## 4. 用户可见解释与控制

复用现有 Search response/surface，展示：

- `baseline|applied|disabled|fail_closed`；
- open/corpus/counterexample lane contribution；
- task ID、record/revision/version/content hash、snapshot ID/hash、cue type/value；
- baseline rank 与 displayed rank、policy/context/result hash；
- fallback reason，如 no task、no prior、unrelated、disabled、conflict、snapshot drift 或 malformed input；
- 明示 `citation_authority=false`、`verifier_authority=false`、`hard_filter=false`。

当次 `Corpus-aware off` 只关闭 composition，不写 DB，结果必须等于 baseline。持久 correct/invalidate/
tombstone 继续使用 existing Workspace append-only decision；恢复旧值必须形成新 revision，不复活旧终态。

## 5. Paired acceptance matrix

每个 case 使用相同 temp DB corpus、相同 Search request 和可控 raw retriever fixture，比较 raw plan/hits、
候选 pool、展示结果、explanation 与 Workspace history：

| Case | 必要结果 |
| --- | --- |
| empty / no task / no prior | 与当前 Product Search baseline 相同 |
| valid treatment | 只允许 bounded display composition 与 explanation 不同 |
| disabled | 与 baseline 相同，durable write count 为 0 |
| unrelated prior | 与 baseline 相同，reason=`unrelated_corpus_prior` |
| candidate/unconfirmed or wrong kind | baseline；不能借用 Profile/Focus/Experience |
| invalidated/tombstoned/malformed/conflict | deterministic fail closed；baseline |
| snapshot missing/hash or boundary drift | fail closed；baseline；不静默改绑新 snapshot |
| counterexample | 最高 baseline nonmatch 保留并标注；open reservation 满足 |
| explicit mode/filter | planner/mode/filter/raw hits 与 baseline 完全一致 |
| duplicate/restart | context/result hash 稳定，无双份 result 或 authority |
| Workspace correction/rollback | 新 revision 生效；旧终态不复活；off 仍 baseline |
| non-interference | Ask、Research、ArtifactRoute、Stage 1 answer presentation 不变 |

验收必须至少覆盖用户要求的 empty/no-prior、treatment、disabled、unrelated、counterexample 五组机械配对。
fixture 只证明 mechanics；live cold start 不能用于声称真实个性化收益。

## 6. 复杂度、测试与禁止项

默认 implementation budget：

```yaml
schema_table_index_migration_delta: 0
new_authority_store: 0
new_endpoint_types: 0
new_dependencies: 0
new_prompt_or_provider_calls: 0
new_background_worker_or_scheduler: 0
new_vector_reranker_graph_eval_telemetry_platform: 0
read_only_projection_adapters_added_by_stage_2_max: 1
```

实现若获授权，只能使用 no-provider/temp-DB tests；不得访问或写入 live DB、credential/Keychain。不得改
Prompt、ASR/Translation、Ask Fast/Deep、Research runner、ArtifactRoute gate、Citation/Verifier/currentness。
不得以 Stage 2 名义修 V5-A compound-query limitation 或进入 Stage 3。

## 7. JIT upstream 判断

本地 accepted evidence 已覆盖本 Contract 的具体缺口：

- schema-14 Workspace 已验证 frozen snapshot-bound `corpus_observation`、revision/decision 与 soft-prior
  non-interference；
- frozen taxonomy cards 已提供 immutable snapshot/hash、video identity、folder/uploader 与 bounded metadata；
- Product Search 已提供显式 query/mode/filter/raw trace、candidate consolidation 与 presentation boundary；
- ArtifactRoute 已接受 independent open lane、`hard_filter=false` 与 counterexample authority discipline；
- V5-B Stage 4 test 已机械证明 seeded corpus observation 当前不改变 Search/Ask/Research/ArtifactRoute。

因此本轮不做外部研究，不新增 upstream report/adoption proposal：`reimplement_shiliu_native`。只有未来
提出 query expansion、learned reranking、外部 corpus authority、新 dependency/source copy，或上述本地
结构无法满足已接受 invariant 时，才触发 material JIT。

## 8. Main 有限决策请求

请 V5 Main 只决定：

1. 是否接受 task-scoped current corpus observation 的 soft-prior authority；
2. 是否接受 unchanged independent open retrieval + bounded post-retrieval composition；
3. 是否接受 open-slot/counterexample reservation 与 paired matrix；
4. 是否接受零 schema/dependency/Prompt/Provider/platform 增量和“无材料性新 upstream research”判断；
5. 是否授权同一 V5-C Session 实施 Stage 2。

本提交不请求自我接受、Stage 2 实施、live DB、Provider、mainline、push/merge/tag 或 Stage 3。提交后停止，
等待 Main 有限审阅。
