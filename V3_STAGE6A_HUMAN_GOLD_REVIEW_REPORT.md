# V3 Stage 6A Human Gold Review Report

**Artifact:** `V3_STAGE6A_HUMAN_GOLD_REVIEW_REPORT.md`  
**Decision file:** `eval_gold_review.decisions.jsonl`  
**Review status:** Human semantic and interval adjudication complete  
**Final classification:** **Ready to Lock Gold with Follow-up**

## 1. Executive decision

The human review has approved the 24-query set, completed semantic adjudication for the complete 452-row pooled candidate set, confirmed both negative controls, approved all ten proposed raw-subtitle interval candidates, and resolved the Q06 query-type disagreement.

The Gold must **not** be locked until one deterministic follow-up gate is completed against the immutable Stage 6A snapshot:

1. verify `archived=false` and `ignored=false` for every candidate;
2. verify exact explicit-filter eligibility for Q19, Q20, and Q22–Q24;
3. move any violating candidate to `out_of_scope_due_to_filter` without changing its human semantic judgment;
4. re-run coverage and positive-query consistency checks;
5. stop and report any mismatch before creating the locked Gold.

The exported pool does not contain enough row-level metadata to perform this gate independently in the review session.

## 2. Reviewed inputs

- `V3_GOLD_REVIEW_PACKET(1).md`
- `eval_queries.candidate(1).jsonl`
- `eval_gold_candidates(1).jsonl`
- `eval_pool_candidates(1).jsonl`
- `V3_EVAL_PROTOCOL(1).md`
- `V3_STAGE6A_RECOVERY_CORPUS_AND_GOLD_CANDIDATE_REPORT(2).md`

Verified input totals:

- Queries: **24**
- Complete pooled Query–Video rows: **452**
- Held-out queries: **20**
- Negative controls: **2** — Q14 and Q18
- Queries with interval candidates: **10**
- Duplicate Query IDs: **0**
- Missing query pools: **0**

## 3. Human adjudication model

### 3.1 Search eligibility precedes semantic relevance

A candidate failing an explicit structured filter or the default eligibility rule is `out_of_scope_due_to_filter`. It is neither Relevant nor Not Relevant.

Default eligibility:

```text
archived=false
ignored=false
```

### 3.2 Video-level labels

- `R_evidence`: reviewable transcript/body evidence substantively supports the Query.
- `R_title`: no reviewable transcript; the title directly and clearly establishes video-level relevance.
- `N`: evidence establishes non-relevance or only incidental/adjacent mention.
- `U_title`: no reviewable transcript and the title is insufficient; final status is `unjudged_due_to_missing_content`.
- `out_of_scope_due_to_filter`: deterministic eligibility failure.

Video-discovery relevance is:

```text
R_evidence + R_title
```

Evidence-retrieval relevance is:

```text
R_evidence only
```

`R_title` and `U_title` cannot create interval, window, anchor, or evidence-citation Gold.

### 3.3 Interval standard

An approved interval is a useful jump target for the Query and must derive from authoritative raw subtitle segment boundaries. It need not independently explain the entire Query. A direct topic entry is valid; unrelated keyword mention is not.

## 4. Aggregate human decisions

- `R_evidence`: **102**
- `R_title`: **6**
- `N`: **335**
- `U_title / unjudged_due_to_missing_content`: **9**
- Current `out_of_scope_due_to_filter`: **0 pending snapshot metadata validation**
- Total: **452 / 452**

All 452 pooled rows appear exactly once in the current semantic ledger.

## 5. Query Set decisions

Q01–Q24 are approved. Q06 is the only Query-field revision:

```text
Q06 original expected_query_type = mixed_entity
Q06 final expected_query_type    = semantic_question
actual Planner query type        = semantic_question
Planner modification authorized  = false
```

| Query | 查询 | Action | 最终类型 | R_evidence | R_title | N | U_title | Interval |
|---|---|---|---|---:|---:|---:|---:|---:|
| Q01 | MCP | approve | `exact_entity` | 16 | 0 | 16 | 0 | 1 |
| Q02 | RAG | approve | `exact_entity` | 12 | 1 | 12 | 1 | 1 |
| Q03 | MemoryOS | approve | `exact_entity` | 2 | 0 | 18 | 0 | 1 |
| Q04 | LoRA | approve | `exact_entity` | 2 | 0 | 20 | 0 | 1 |
| Q05 | OpenSpec | approve | `exact_entity` | 1 | 0 | 19 | 0 | 0 |
| Q06 | MCP 与 Function Calling 的区别 | revise | `semantic_question` | 1 | 0 | 19 | 0 | 1 |
| Q07 | Claude Code 记忆机制 | approve | `mixed_entity` | 1 | 1 | 13 | 5 | 1 |
| Q08 | RAG 项目怎么做工业优化 | approve | `semantic_question` | 7 | 0 | 13 | 0 | 1 |
| Q09 | Pi Agent 插件与配置 | approve | `mixed_entity` | 3 | 1 | 15 | 1 | 0 |
| Q10 | 为什么复杂 Agent 使用 DAG Workflow 而不是 ReAct 循环？ | approve | `semantic_question` | 1 | 0 | 19 | 0 | 1 |
| Q11 | Agent 长期记忆为什么越总结越可能有害？ | approve | `semantic_question` | 2 | 0 | 18 | 0 | 0 |
| Q12 | 如何设计企业智能客服 Agent？ | approve | `semantic_question` | 2 | 0 | 18 | 0 | 0 |
| Q13 | AI 编程中的测试循环如何提高交付质量？ | approve | `semantic_question` | 8 | 0 | 12 | 0 | 0 |
| Q14 | 量子纠错表面码阈值如何计算？ | approve | `semantic_question` | 0 | 0 | 20 | 0 | 0 |
| Q15 | 哪个视频解释了 CLI 相比 MCP 的优势？ | approve | `semantic_question` | 1 | 0 | 19 | 0 | 1 |
| Q16 | 哪些内容讨论了 Agent 评测信号设计？ | approve | `semantic_question` | 3 | 0 | 17 | 0 | 0 |
| Q17 | 哪里讲了 SFT 和 LoRA 微调动漫人格？ | approve | `semantic_question` | 1 | 0 | 19 | 0 | 1 |
| Q18 | 如何为 Kubernetes Pod 排查 CrashLoopBackOff？ | approve | `semantic_question` | 0 | 0 | 20 | 0 | 0 |
| Q19 | Agent | approve | `exact_entity` | 24 | 0 | 2 | 0 | 0 |
| Q20 | vibe coding | approve | `exact_entity` | 1 | 0 | 0 | 0 | 0 |
| Q21 | 记忆 | approve | `keyword_phrase` | 3 | 0 | 3 | 0 | 0 |
| Q22 | Agent | approve | `exact_entity` | 5 | 2 | 3 | 1 | 0 |
| Q23 | Claude Code | approve | `exact_entity` | 3 | 0 | 11 | 1 | 0 |
| Q24 | 模型微调 | approve | `keyword_phrase` | 3 | 1 | 9 | 0 | 0 |

## 6. Complete per-query video decisions

### Q01 — MCP

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [6, 7, 12, 34, 39, 43, 47, 71, 78, 80, 83, 88, 93, 100, 111, 113]
- `R_title`: [—]
- `N`: [29, 33, 56, 67, 73, 76, 86, 90, 96, 97, 99, 103, 108, 114, 120, 144]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 78 / `BV1G29EBGE8b` / `62.960–72.700s`

### Q02 — RAG

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [5, 26, 30, 65, 71, 77, 99, 102, 111, 122, 124, 136]
- `R_title`: [142]
- `N`: [12, 39, 57, 73, 80, 95, 96, 103, 113, 121, 130, 139]
- `U_title / unjudged_due_to_missing_content`: [3]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 77 / `BV1JLN2z4EZQ` / `170.900–180.560s`
- Note: Video 3 remains unjudged because the frozen review assets expose no reviewable transcript and the title does not establish substantive RAG coverage.

### Q03 — MemoryOS

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [39, 40]
- `R_title`: [—]
- `N`: [33, 38, 50, 57, 58, 59, 67, 88, 90, 91, 93, 99, 114, 115, 119, 122, 124, 137]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 40 / `BV1oa6uBXE8J` / `6.880–10.440s`
- Note: Video 137 was set to N after the human reviewer confirmed from full-video viewing that MemoryOS is not mentioned.

### Q04 — LoRA

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [115, 117]
- `R_title`: [—]
- `N`: [15, 30, 32, 39, 48, 73, 75, 76, 90, 91, 93, 96, 103, 111, 118, 119, 122, 123, 124, 130]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 117 / `BV1UaPmzrESw` / `119.230–125.650s`
- Note: Asset inconsistency: eval_gold_candidates and the Review Packet reference Video 125 as possible for Q04, but Video 125 is absent from the complete Q04 pool. It is not adjudicated under Q04.

### Q05 — OpenSpec

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [68]
- `R_title`: [—]
- `N`: [4, 7, 9, 12, 22, 56, 62, 78, 88, 90, 91, 93, 94, 95, 103, 104, 113, 114, 123]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q06 — MCP 与 Function Calling 的区别

- `query_action`: `revise`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [83]
- `R_title`: [—]
- `N`: [7, 33, 39, 65, 71, 73, 74, 76, 78, 80, 90, 91, 93, 96, 99, 100, 108, 109, 111]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 83 / `BV1qTYizcEN3` / `5.740–9.379s`
- Note: Human decision revises final expected_query_type from mixed_entity to semantic_question. Planner output remains unchanged.

### Q07 — Claude Code 记忆机制

- `query_action`: `approve`
- `final_expected_query_type`: `mixed_entity`
- `R_evidence`: [38]
- `R_title`: [137]
- `N`: [39, 40, 48, 57, 58, 59, 65, 88, 90, 104, 122, 124, 128]
- `U_title / unjudged_due_to_missing_content`: [44, 45, 93, 108, 112]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 38 / `BV1z6SXBzEYh` / `3.420–15.350s`
- Note: A transient ledger entry placed Video 33 in Q07 N, but Video 33 is not in the Q07 pool. It was removed during consistency review.

### Q08 — RAG 项目怎么做工业优化

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [5, 26, 30, 77, 99, 102, 136]
- `R_title`: [—]
- `N`: [35, 55, 65, 71, 73, 90, 95, 103, 111, 113, 114, 135, 140]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 30 / `BV11wEb6uEwB` / `28.230–32.960s`

### Q09 — Pi Agent 插件与配置

- `query_action`: `approve`
- `final_expected_query_type`: `mixed_entity`
- `R_evidence`: [7, 43, 47]
- `R_title`: [49]
- `N`: [13, 20, 24, 29, 54, 56, 67, 83, 88, 96, 97, 100, 109, 111, 140]
- `U_title / unjudged_due_to_missing_content`: [23]
- `out_of_scope_due_to_filter`: [—]

### Q10 — 为什么复杂 Agent 使用 DAG Workflow 而不是 ReAct 循环？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [135]
- `R_title`: [—]
- `N`: [13, 26, 29, 30, 35, 55, 71, 90, 92, 93, 95, 96, 100, 109, 111, 122, 124, 136, 140]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 135 / `BV1Up756vEK7` / `1.120–6.300s`
- Note: Video 135 was confirmed R_evidence by the human reviewer after checking that the video fully explains the DAG Workflow versus ReAct question.

### Q11 — Agent 长期记忆为什么越总结越可能有害？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [58, 59]
- `R_title`: [—]
- `N`: [38, 39, 40, 55, 57, 88, 90, 93, 95, 96, 99, 100, 103, 111, 122, 124, 137, 140]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q12 — 如何设计企业智能客服 Agent？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [77, 136]
- `R_title`: [—]
- `N`: [24, 25, 29, 50, 54, 71, 75, 92, 96, 97, 99, 100, 109, 111, 122, 124, 127, 140]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Note: Video 140 is N: generic enterprise-Agent constraints/data-flywheel content is not direct evidence for enterprise customer-service Agent design.

### Q13 — AI 编程中的测试循环如何提高交付质量？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [6, 12, 29, 50, 51, 55, 96, 113]
- `R_title`: [—]
- `N`: [4, 9, 10, 14, 15, 36, 56, 92, 104, 106, 114, 141]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q14 — 量子纠错表面码阈值如何计算？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [—]
- `R_title`: [—]
- `N`: [6, 32, 39, 48, 50, 51, 56, 65, 73, 90, 91, 96, 103, 104, 106, 114, 116, 122, 123, 124]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q15 — 哪个视频解释了 CLI 相比 MCP 的优势？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [78]
- `R_title`: [—]
- `N`: [7, 33, 39, 65, 67, 71, 76, 80, 82, 83, 88, 90, 91, 92, 93, 105, 108, 114, 119]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 78 / `BV1G29EBGE8b` / `62.960–72.700s`

### Q16 — 哪些内容讨论了 Agent 评测信号设计？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [51, 55, 99]
- `R_title`: [—]
- `N`: [6, 24, 25, 29, 48, 57, 60, 62, 73, 90, 92, 96, 103, 111, 122, 124, 140]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q17 — 哪里讲了 SFT 和 LoRA 微调动漫人格？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [117]
- `R_title`: [—]
- `N`: [24, 31, 32, 48, 55, 73, 75, 90, 91, 93, 96, 105, 115, 119, 122, 123, 124, 127, 141]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Approved interval: Video 117 / `BV1UaPmzrESw` / `175.450–183.320s`

### Q18 — 如何为 Kubernetes Pod 排查 CrashLoopBackOff？

- `query_action`: `approve`
- `final_expected_query_type`: `semantic_question`
- `R_evidence`: [—]
- `R_title`: [—]
- `N`: [5, 12, 15, 29, 30, 55, 64, 67, 76, 80, 88, 90, 93, 96, 103, 108, 109, 114, 135, 141]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q19 — Agent

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [20, 24, 25, 29, 54, 57, 59, 62, 67, 80, 88, 90, 95, 96, 97, 99, 100, 111, 122, 124, 126, 127, 136, 140]
- `R_title`: [—]
- `N`: [48, 92]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q20 — vibe coding

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [34]
- `R_title`: [—]
- `N`: [—]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q21 — 记忆

- `query_action`: `approve`
- `final_expected_query_type`: `keyword_phrase`
- `R_evidence`: [57, 58, 59]
- `R_title`: [—]
- `N`: [55, 60, 61]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]

### Q22 — Agent

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [135, 136, 139, 140, 141]
- `R_title`: [137, 143]
- `N`: [134, 138, 144]
- `U_title / unjudged_due_to_missing_content`: [142]
- `out_of_scope_due_to_filter`: [—]
- Note: Video 134 is N after full-video human inspection confirmed no substantive Agent content.

### Q23 — Claude Code

- `query_action`: `approve`
- `final_expected_query_type`: `exact_entity`
- `R_evidence`: [38, 44, 45]
- `R_title`: [—]
- `N`: [32, 33, 35, 36, 37, 39, 40, 47, 48, 49, 50]
- `U_title / unjudged_due_to_missing_content`: [41]
- `out_of_scope_due_to_filter`: [—]

### Q24 — 模型微调

- `query_action`: `approve`
- `final_expected_query_type`: `keyword_phrase`
- `R_evidence`: [115, 117, 123]
- `R_title`: [125]
- `N`: [114, 116, 118, 119, 121, 122, 124, 129, 130]
- `U_title / unjudged_due_to_missing_content`: [—]
- `out_of_scope_due_to_filter`: [—]
- Note: Video 123 is R_evidence for substantive post-training/alignment discussion relevant to model tuning.


## 7. Approved intervals

All ten Stage 6A interval candidates were approved after applying the unified “useful jump target” standard.

| Query | Video | BV | Interval (s) | Decision |
|---|---:|---|---:|---|
| Q01 | 78 | `BV1G29EBGE8b` | 62.960–72.700 | approve |
| Q02 | 77 | `BV1JLN2z4EZQ` | 170.900–180.560 | approve |
| Q03 | 40 | `BV1oa6uBXE8J` | 6.880–10.440 | approve |
| Q04 | 117 | `BV1UaPmzrESw` | 119.230–125.650 | approve |
| Q06 | 83 | `BV1qTYizcEN3` | 5.740–9.379 | approve |
| Q07 | 38 | `BV1z6SXBzEYh` | 3.420–15.350 | approve |
| Q08 | 30 | `BV11wEb6uEwB` | 28.230–32.960 | approve |
| Q10 | 135 | `BV1Up756vEK7` | 1.120–6.300 | approve |
| Q15 | 78 | `BV1G29EBGE8b` | 62.960–72.700 | approve |
| Q17 | 117 | `BV1UaPmzrESw` | 175.450–183.320 | approve |

Important human clarifications:

- Q04 is part of installing the library required for LoRA fine-tuning.
- Q06 is an accepted direct topic opening.
- Q10 was confirmed by full-video human inspection to fully match and explain the Query.
- Q15 and Q17 were both explicitly approved by the human reviewer.

## 8. Negative controls

### Q14 — 量子纠错表面码阈值如何计算？

- Relevant set: `[]`
- All 20 pooled candidates: `N`
- Assessment: approved Negative Control.

### Q18 — 如何为 Kubernetes Pod 排查 CrashLoopBackOff？

- Relevant set: `[]`
- All 20 pooled candidates: `N`
- Assessment: approved Negative Control.

Negative controls must remain excluded from Recall/MRR/Hit relevant denominators and remain included in the protocol-defined zero-result and filter behavior reporting.

## 9. Missing-content unjudged items

The following nine candidates remain deliberately unjudged rather than being guessed as Relevant or Not Relevant:

```text
Q02: [3]
Q07: [44, 45, 93, 108, 112]
Q09: [23]
Q22: [142]
Q23: [41]
```

Stage 6B must disclose its unjudged-item handling alongside every result table, as required by the evaluation protocol.

## 10. Filter and eligibility validation

| Query | Filter | Export-level result | Lock requirement |
|---|---|---|---|
| All Q01–Q24 | `archived=false`, `ignored=false` | Fields absent from exported Pool | Read-only snapshot revalidation required |
| Q19 | `folder_id=3876418799` | All rows show folder `2026找工作学习`; ID absent | Validate exact folder ID in snapshot |
| Q20 | `marked=true` | Field absent; Stage 6A report records one stable filtered result | Validate Video 34 marked state |
| Q21 | `uploader=慢学AI` | All 6 rows verified | No explicit-filter follow-up beyond default eligibility |
| Q22 | `favorite_time` 2026-07-17 through 2026-07-20 UTC | Field absent | Validate inclusive timestamp bounds |
| Q23 | `favorite_time` 2026-06-01 through 2026-07-01 UTC | Field absent | Validate inclusive timestamp bounds |
| Q24 | `favorite_time` 2026-01-01 through 2026-04-01 UTC | Field absent | Validate inclusive timestamp bounds |

No candidate may be silently left in R/N/U after a deterministic filter violation is found.

## 11. Consistency findings and corrections

1. **Q07 stray ledger ID corrected:** Video 33 was temporarily written into Q07 `N`, but it is not in the Q07 complete Pool. It was removed. Q07 now covers exactly its 20 candidates.
2. **Q04 asset inconsistency:** `eval_gold_candidates.jsonl` and the Review Packet reference Video 125 as a possible Q04 candidate, but Video 125 is absent from Q04’s complete `eval_pool_candidates.jsonl` pool. It is not adjudicated under Q04. Video 125 is independently adjudicated under Q24.
3. Candidate and Query coverage after correction:
   - missing pooled IDs: **0**
   - duplicate assignments: **0**
   - extra IDs outside a Query pool: **0**
4. Every non-negative-control Query currently has at least one human-approved Relevant video.
5. Single-positive Queries: **Q05, Q06, Q10, Q15, Q17, Q20**.
6. All approved intervals belong to `R_evidence` videos.
7. Negative-control Relevant sets are empty.

## 12. Exact Codex handoff

Codex is authorized to perform only the following next actions:

1. Read this report and `eval_gold_review.decisions.jsonl`.
2. Open the immutable snapshot identified by the Stage 6A manifest in read-only mode.
3. Validate every candidate’s `archived` and `ignored` state.
4. Validate:
   - Q19 exact `folder_id=3876418799`;
   - Q20 `marked=true`;
   - Q21 `uploader=慢学AI`;
   - Q22 favorite time in `[1784246400, 1784505600]`;
   - Q23 favorite time in `[1780272000, 1782864000]`;
   - Q24 favorite time in `[1767225600, 1775001600]`.
5. For deterministic violations only, move the candidate ID from its current semantic bucket to `out_of_scope_due_to_filter`; preserve the prior semantic label in an audit field.
6. Re-run exact Pool closure, duplicate, positive-query, negative-control, and interval-to-Relevant checks.
7. Explicitly resolve/report the Q04 Video 125 asset inconsistency; do not add Video 125 to Q04 unless a new human review is requested.
8. If all gates pass, generate the separate locked Query/Gold artifacts and proceed to Stage 6B under the fixed protocol.

Codex is **not authorized** to:

- reinterpret R/N/R_title/U_title decisions;
- infer new Relevant videos;
- rewrite Query wording;
- change Planner behavior;
- tune routing, retrievers, grouping, windows, or anchors;
- replace or expand human-approved intervals;
- silently repair asset inconsistencies;
- run Stage 6B before the metadata and consistency gates pass.

## 13. Final classification

**Ready to Lock Gold with Follow-up**

The remaining work is deterministic snapshot metadata validation and artifact consistency validation, not further semantic human judgment. A filter mismatch, loss of the only Relevant video for a positive Query, or inability to verify the immutable snapshot changes the classification to **Blocked by Missing Evidence** until resolved.
