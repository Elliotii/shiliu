Result classification: **Held-out Isolation Violation Risk**

已按 Stop Condition 停止执行，未修改仓库、未实现 Stage 3A、未运行测试。

### Major escalation

**Original Assumption**

每个 Development Gold required span 可以由一个满足以下硬限制的 `EvidenceCandidate` 完整覆盖：

- 最多 6 个连续 Raw Segments
- 最长 60 秒

**Local Fact**

4 个 Evidence-bearing Development Cases 中，3 个至少包含一个无法由合法 Candidate 覆盖的必要 span：

| Case | Required span | Segments | Duration | Result |
|---|---:|---:|---:|---|
| CASE_001 | G1_S1 | 5 | 11.72s | 可覆盖 |
| CASE_002 | G1_S1 | 23 | 63.73s | 不可覆盖 |
| CASE_003 | G1_S1 | 19 | 52.53s | 不可覆盖 |
| CASE_005 | G1_S1 | 10 | 57.89s | 不可覆盖 |
| CASE_005 | G1_S2 | 8 | 51.40s | 不可覆盖 |

由于 Group 内 Required Spans 是 AND 关系，CASE_005 也无法完整覆盖。

**Evidence**

冻结 Coverage 定义要求：

> 对每个 Required Gold Span，至少存在一个 Candidate，其 Segment 集合完整覆盖该 Span。

这不能通过多个合法 micro-windows 的 union 满足。因此，CASE_002、CASE_003、CASE_005 是结构性 miss，达到“2 个或以上 Evidence-bearing Dev Case 缺失完整 Gold Group”的强制停止条件。

**Impact**

即使 Builder 正确实现，最大 Candidate Builder Case Coverage 也只有 `1/4`。继续实现或调参无法解决，除非违反以下至少一项：

- Candidate 硬预算
- 冻结 coverage semantics
- 禁止修改 Gold
- 禁止 case-specific exceptions

**Options**

1. 推荐：将 span coverage 修订为“一个或多个有效 Candidates 的 union 完整覆盖 required span”。
2. 放宽 Candidate hard limits，使单个 Candidate 能包含最长 Gold span。
3. 重新标注 Gold span；当前 Stage 3A 无权执行。

**V3.5 Session Recommendation**

由 V3.5 Version Session 选择并冻结方案 1，然后启动全新的、隔离的 Stage 3A Session。

**Decision Needed**

需要明确：

- Coverage 是否允许多个 Candidates 联合覆盖一个 Required Span；
- 若不允许，Candidate segment/duration hard limits 应调整到什么范围。

### Isolation audit issue

三个明确禁止的 Gold 文件没有被打开：

- `heldout_gold.10_cases.locked.jsonl`
- `master_gold.18_cases.locked.jsonl`
- `review_decisions.master.18_cases.adjudicated.jsonl`

但验证过程中打开了不在 Allowed Inputs 清单内的：

- `research/v3_5/gold/gold_lock_manifest.json`
- `research/v3_eval/eval_queries.locked.jsonl`

前者暴露了聚合 Held-out label distribution，后者包含 query-level held-out metadata。因此本 Session 不能诚实地产出预期的全 false isolation audit，也不应继续成为正式 Stage 3A implementation session。

### Repository accounting

- Pre-existing Changes：保持不变。
- Stage 3A Intended Changes：无。
- Unexpected Changes：无。
- External audit note：[prework_audit.txt](/tmp/shiliu_v3_5_stage3a_before/prework_audit.txt)

未创建 Stage 3A 报告、代码、评测资产或测试，以免把受污染 Session 的结果写入正式仓库。
