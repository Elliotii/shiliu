# V3 Checkpoint 3.11B — Controlled Facet Completion and Validation

## 最终结论

```text
AUTOMATIC GATE: PASS
INDEPENDENT REVIEWER: PASS_WITH_CONCERNS
MAIN AGENT FINAL: PASS_WITH_CHANGES
```

相同 48 条受控分面赋值已经完整形成。Form 和 Object 在当前样本中表现出独立于 Domain 的筛选增量；Suggested Context 有一定增量，但填充率过高且部分值可由 Form 高度预测，暂时只适合作为高级建议筛选。

扩到 128 条之前仍需解释 Batch 4 的 100% Repair 率，并在更多真实 Entity Type 数据上验证确定性映射路径。本报告不授权 128 条、Run B/C、正式 UI 或词表演化。

## 1. Git 与 Run 血缘

| 项目 | 值 |
|---|---|
| 分支 | `feat/v3-hybrid-controlled-facets` |
| 执行 Commit | `1f722b516dcd56939485f3d05ed3302205f3d881` |
| 派生 Run | Run #21 |
| 来源 Run | Run #20 |
| Snapshot | #2 |
| Snapshot Hash | `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2` |
| Domain | 冻结 Run #12 |
| 样本 | 48，A/B/C=`22/9/17` |
| Batch size | 12 |

Run #21 Manifest 同时冻结 Run #18–#20 的完整目录 Tree Hash 和数据库状态 Hash。Quality Gate 前再次校验，历史 Run 状态、Manifest、原始响应和审计均未改变。

Run #18–#20 最终状态仍为：

```text
Run #18: retry_wait
Run #19: failed
Run #20: retry_wait
```

## 2. 输出 Schema 简化

新 Provider Schema 只允许：

```text
content_id
presentation_form
object_types
suggested_use_contexts
facet_novelty
ambiguities
```

Domain 不在模型 Schema 中；主响应与 Repair 响应的 Domain/未知字段数量均为 0。Prompt 只将 Run #12 Domain 作为只读上下文。

逐卡 Domain 决策从 Run #20 的冻结产物提取并按 Run #12 父子结构校验，随后由本地 `frozen-domain-combination-v1` 组合进最终 Assignment。48 条组合完成，Run #12 Domain Draft Hash 未变化。

## 3. 前 36 条真实复用

Run #20 Batch 1–3 均满足：

- 原始输入、成员、Snapshot、词表和 Entity 白名单一致；
- Stage 状态为 completed；
- parsed output 和文件 Hash 完整；
- Form/Object/Context 语义无需修改。

Run #21 对三个 Batch 使用 `controlled-facet-history-adapter-v1`：

- 移除旧模型响应中的 Domain 字段；
- 由本地冻结 Domain 替代；
- 不修改 Form/Object/Context/Novelty；
- 每条生成显式 Adapter 操作；
- Provider 调用数为 0。

数据库证据：Batch 1–3 的 `attempt_count=0`、`model=NULL`、`input/output tokens=NULL`。`reuse-lineage.json` 保存三个源文件 Hash、Adapter Audit Hash 和新输出 Hash。

## 4. Batch 4 调用与 Repair

Batch 4 使用相同 12 条成员，只执行：

```text
1 次主调用
+ 1 次结构 Repair
```

主响应已正确移除 Domain，但三条内容各输出 3 个不同 OT，超过最多 2 个 OT 的标签预算。Repair 只修改这三条的 Object 列表：各移除一个 OT；Form、Context、Novelty 和其他九条内容未改变。原始请求没有重放。

| 指标 | 主调用 | Repair | 合计 |
|---|---:|---:|---:|
| Prompt Tokens | 8,047 | 4,013 | 12,060 |
| Completion Tokens | 3,391 | 3,161 | 6,552 |
| Total Tokens | 11,438 | 7,174 | 18,612 |
| Provider 秒 | 28.409 | 25.846 | 54.255 |

Reasoning Tokens 为 unknown；thinking=false。Batch 4 主响应 Repair 率为 100%，作为扩容前 Warning。

## 5. 可审计 OT 聚合

Repair 后仍保留一条同内容、同 OT ID 的两个对象项。本地规则只在：

```text
same content_id + same OT ID
```

时执行聚合。实际发生一次：`C071 + OT07`。

聚合结果：

- `original_item_count=2`；
- 两个来源 Entity 按首次出现顺序合并；
- 两条 evidence 合并；
- 原始 confidence 均为 high；
- 最终 confidence 按冻结 max 规则为 high；
- 最终只占一个 OT 标签预算。

`normalization-audit.json` 保存原始项、合并字段、confidence、版本和时间。没有合并不同 OT，没有接受白名单外 Entity，`silent_normalization_count=0`。报告不记录真实 Entity 名称。

## 6. 完整 48 条结果

```text
Assignment: 48 / 48
非法 PF/OT/UC: 0
标签预算违规: 0
Model Domain 字段: 0
具体 Entity 写入 OT 词表: 0
Runtime active 词条: 0
Novelty 自动发布: 0
Silver 输入: 0
历史 Run 修改: 0
```

平均总标签数为 `3.771`，包含 Domain、Form、Object 和 Context。

## 7. Presentation Form

| PF | Primary 支持量 |
|---|---:|
| PF01 | 8 |
| PF02 | 1 |
| PF03 | 6 |
| PF04 | 11 |
| PF06 | 1 |
| PF07 | 11 |
| PF08 | 6 |
| PF11 | 3 |
| unknown | 1 |

```text
unknown: 1 / 48 = 2.08%
form_novelty: 0
secondary Form: 0
最大 Primary 覆盖: 11 / 48 = 22.92%
```

主要 Form 具有跨 Domain 支持：PF01/PF04/PF08 分别覆盖 5/4/4 个一级 Domain；PF03 覆盖 3 个。仅有单样本支持的 PF02/PF06 暂不证明长期价值，但它们是全局受控词条的当前支持，不是开放发现产生的碎片节点。

在同一 Domain 结果集中继续选择 Form，实际支持组合的平均缩减为 `68.75%`，中位缩减约 `77.78%`。因此 Form 在当前 48 条上具有独立检索价值。

## 8. Focus Object Type 与 Entity 来源

| OT | 支持量 |
|---|---:|
| OT01 | 17 |
| OT02 | 7 |
| OT03 | 5 |
| OT07 | 5 |

```text
Object 空值: 24 / 48 = 50.00%
平均 Object: 0.708 / 条
deterministic_entity_mapping_count: 0
model_assisted_object_assignment_count: 34
untyped_entity_count: 122
untyped_entity_with_no_object_count: 68
```

Object 没有被强制填满。四个实际使用 OT 均跨多个 Domain 和 Form：OT01 覆盖 6 个 Domain/6 个 Form；其余三个分别覆盖 3～4 个 Domain、3～4 个 Form。

在同一 Domain 结果集中继续选择 Object，实际支持组合的平均缩减为 `66.64%`，中位约 `75%`。支持量至少 3 的标签对中，没有 Object 与 Domain/Form 双向条件概率同时超过 0.9。因此 Object 当前具有独立检索价值。

限制：122 个 Entity 全部 untyped，本轮只验证了 model-assisted/empty 路径；确定性 Entity Type 映射尚无真实数据证据。

## 9. Suggested Use Context

| UC | 支持量 |
|---|---:|
| UC01 | 26 |
| UC02 | 11 |
| UC03 | 1 |
| UC04 | 2 |
| UC05 | 5 |
| UC06 | 5 |
| UC07 | 2 |

```text
Context 空值: 1 / 48 = 2.08%
平均 Context: 1.083 / 条
confidence: high=29, medium=22, low=1
```

在同一 Domain 结果集中选择 Context，实际支持组合平均缩减为 `53.76%`，低于 Form/Object。UC01 占 54.17%；所有 PF04 内容均带 UC01，即 `P(UC01 | PF04)=1.0`，但反向并不成立，因此没有触发双向 0.9 冗余 Gate。

结论：Context 有部分筛选增量，但当前填充过满且存在较强 Form 可预测性，应保留为高级、可选的 AI 建议筛选，不应提升为核心分类或 Blocking Gate。

## 10. Novelty

```text
Form Novelty: 0
Object Novelty: 0
Context Novelty: 0
Runtime promotion: 0
```

当前样本没有提出词表缺口；这不代表受控词表已经在所有收藏夹中完备。

## 11. Dynamic Faceting

语义：同分面 OR、跨分面 AND。只模拟真实点击路径，不枚举完整笛卡尔积。

| 指标 | 结果 |
|---|---:|
| 有支持的一级 Domain | 7 |
| 第一步结果数中位数 | 11 |
| 第一步可用 Form 中位数 | 4 |
| 第一步可用 Object 中位数 | 4 |
| 第一步可用 Context 中位数 | 3 |
| 第二步实际路径 | 49 |
| 第二步结果数中位数 | 2 |
| 第二步 singleton 比例 | 46.94% |
| 第二步仍可细分比例 | 100% |
| 三分面实际路径 | 121 |
| 暴露零支持选项 | 0 |

系统动态隐藏了当前路径下无支持的值；受控词表的全局零支持项不会在点击路径中展示。

## 12. 跨分面冗余

对支持量至少 3 的标签对计算双向条件概率。结果：

```text
near_duplicate_cross_facet_count: 0
```

没有标签对同时满足 `P(B|A)>0.9` 和 `P(A|B)>0.9`。这支持 Form/Object 没有简单复制 Domain；Context 仍有单向高可预测关系，已作为产品 Warning 保留。

## 13. Derived Filters

共生成 12 个只读报告级建议：

```text
Form + Object: 4
Form + Context: 8
```

每项支持量至少 3，保存底层 AND 查询表达式和支持 IDs；`status=report_only`，没有写入基础受控词表。

## 14. 与 Checkpoint 3.10 的公平对比

| 指标 | 3.10 开放分面 | 3.11B 受控分面 |
|---|---:|---:|
| 完整 Assignment | 48/48 | 48/48 |
| Form/Object/Context 词表容量 | 28/28/29 | 11/9/8 |
| 开放发现单样本节点 | 78/85 | 不适用；受控词表零支持项不算碎片 |
| 实际使用 Form/Object/Context | 大量 draft | 8/4/7 |
| 平均总标签 | 3.479 | 3.771 |
| Form unknown | 4 | 1 |
| Object 空值 | 4（8.33%） | 24（50.00%） |
| Context 空值 | 17（35.42%） | 1（2.08%） |
| Novelty | 0 | 0 |
| 跨分面完全共现 | 141 组覆盖较小侧 | 双向 >0.9 为 0 |
| 动态筛选 | 两分面笛卡尔空结果 80.84% | 实际点击路径零暴露 0 |
| 已返回模型响应 | 8 + 1 interrupted | 1 主调用 + 1 Repair |
| Total Tokens | 166,357 | 18,612 增量 |
| Provider 秒 | 428.460 | 54.255 增量 |
| 主调用结构 Repair | 多阶段发生 | Batch 4 为 100% |

3.11B 增量成本只包含最后 12 条；前 36 条为零调用复用。若把 Checkpoint 3.11 的三次失败诊断也计入累计探索成本，则 3.11+3.11B 共 `188,458 Tokens / 462.230 秒`。产品扩容估算不应把历史失败成本伪装成单次稳定流水线成本，但工程复盘必须保留。

## 15. Automatic Quality Gate

```text
PASS
Blocking Issues: 0
```

硬门禁通过：48/48、受控 ID、标签预算、Form 覆盖、Domain/词表/历史 Hash、Silver 隔离、Novelty 不发布和动态零结果均正常。

自动产物记录的 Warning 是当前样本存在未使用受控词条：PF 3 个、OT 5 个、UC 1 个。另有两个必须在产品判断中保留的工程 Warning：

1. Batch 4 主响应需要一次结构 Repair；
2. 122 个真实 Entity 全部 untyped。

## 16. 测试

```text
206 passed
1 existing Starlette/httpx deprecation warning
```

新增覆盖包括：同 OT 聚合、Entity/evidence 顺序去重、max confidence、聚合审计、不同 OT 不合并、白名单拒绝、历史 Adapter、模型 Schema 禁止 Domain、本地 Domain 组合、Form+Object/Form+Context 派生表达式、Entity 统计、48 条完整性 Gate、动态非零路径和 CLI 入口。

## 17. Independent Reviewer

```text
PASS_WITH_CONCERNS
```

Reviewer 只读取了 ADR、代码、测试、本报告、Run #21 Reviewer Bundle 和非 Silver 运行审计；没有修改代码/数据库、调用 Provider、读取 Silver 或使用 3.10 开放词表证明新结果正确。

Reviewer 确认：

- Run #18–#20 Tree Hash、数据库状态和失败状态保持不变；
- 前 36 条是真实零调用复用，移除 Domain 后三个受控分面逐字段一致；
- 只有 Batch 4 发生一次主调用和一次 Repair，原 Prompt 没有重放；
- 新模型 Schema 不含 Domain，48 条 Domain 均由本地冻结组合；
- C071 OT07 聚合范围正确、字段完整且可审计；
- 48 条完整，指标和动态点击路径均可复现；
- Form/Object 不是 Domain 的简单复制，具有独立筛选价值；
- 没有足以把 Checkpoint 判为 FAIL 的 Blocking Finding。

Reviewer 的 Non-blocking Concerns：

1. Repair 对 C041/C010/C033 各删除一个第三 OT，是有证据的语义取舍，不只是 JSON 格式修复。删除项都是原响应第三项、medium confidence，保留项为 high confidence；原始与 Repair 响应均落盘，但缺少结构化字段级 Diff。
2. Automatic Gate 没有内建 `repair_call_count`、`repair_rate`、`repair_semantic_change_count` Warning。
3. Automatic Gate 没有把 `untyped_entity_count=122`、`deterministic_entity_mapping_count=0` 显式列为 Warning。
4. Context 47/48 被填充，UC01 与 PF04 存在单向完全预测；只能作为高级建议筛选。
5. Form/Object/Context 的条件缩减结果可由 Assignment 重算，但尚未单独冻结进 Metrics JSON。

Reviewer 要求进入 128 条前：

- 新增结构化 `repair-semantic-diff.json`；
- 将 Repair 和 Entity Typing 指标写入 Quality Gate Warning；
- 固化超过两个不同 OT 时的取舍协议，可选择按证据/confidence Repair，或转为 ambiguity/overflow audit；
- 继续监控 Context 填充率、UC01 占比和 Form→Context 单向可预测性。

这些修正无需重跑或改写 Run #21，但必须在新的 128 条运行前完成。

## 18. 是否值得扩到 128 条

最终判断：

```text
PASS_WITH_CHANGES
```

架构和当前 48 条产品价值基本成立，但扩容前至少需要：

- 将 Batch 4 Repair 率和三条超 OT 预算案例列入稳定性门禁；
- 保持 Context 为高级建议筛选，并观察 128 条上是否仍接近强制填满；
- 在后续数据具备 Entity Type 时单独验证 deterministic mapping；
- 由独立 Reviewer 确认 Form/Object 的信息增量计算与点击路径可复现。

Reviewer 已确认最后一项；前三项与结构化 Repair Diff/Gate Warning 一并列为下一阶段的前置工程工作。当前 Checkpoint 到此停止，不启动 128 条或 Run B/C。
