# V3 Checkpoint 3.12C：Candidate Decision Tail Completion and Domain Evidence Contract v2

状态：`PASS_WITH_CHANGES`。本轮在 Run C 之前停止。

## 1. Git 与历史现场冻结

- 分支：`feat/v3-domain-evidence-contract`
- 起点 Commit：`2ee3364ec5bae65f8c47ede343ada225029ca9f4`
- 冻结 Tag：`checkpoint/v3.12b-missing-tail-decisions`
- Run #22：48 个文件；数据库保持 `retry_wait / domain_consolidation / invalid_model_output`，8 个 Stage。
- Run #22 现行 `_tree_hash()`：`9edde35792bccf3db6b0282b1ef95f0277c61a01d31d8029acbabc604cf593a5`。
- 3.12B 报告历史声明值：`361e2e3ff8657865570d51db04da5ca81d9a56bc2197ced5bb991ba1104ff17b`。

历史值与现行算法值不同，但 Run #22 最后文件时间早于 3.12B 报告生成时间，且本轮前后文件数、现行 Tree Hash、四个关键文件 Hash、数据库状态与更新时间均未变化。3.12B 没有保存其 Hash 算法，因此本轮保留两个值，不把它们伪装成同一算法的结果。

## 2. Tail Completion 输入边界

请求只包含：

- `nc_037–nc_040` 的冻结 Candidate 字段；
- 4 条代表内容的短 ID、证据等级、标题和已有短摘要/简介；
- 9 个冻结一级 Domain 及其二级节点的语义字段；
- `nc_001–nc_036` 的 action/target 只读摘要；
- 允许动作和严格 Schema。

请求共 9,036 字符。未读取完整 128 卡、字幕、Silver Reference、受控分面、收藏夹名称或用户人工分类。

## 3. Provider 调用与成本

本轮只有一次 Tail Completion 语义调用：

```text
model: deepseek-v4-pro
thinking: high
finish_reason: stop
elapsed: 53.223 s
prompt_tokens: 3,364
completion_tokens: 3,224
reasoning_tokens: 2,501
total_tokens: 6,588
repair_count: 0
```

首次终端轮询曾在响应落盘前返回空输出，但原进程随后在同一调用目录正常完成。恢复保护检测到完成状态并拒绝重发，因此没有第二次 Provider 请求。

历史 Run B 成本保持独立：

```text
historical_total_tokens: 64,488
historical_provider_seconds: 443.977
historical_consolidation_reasoning_tokens: 13,261
```

## 4. 四条 Tail Decision

| Candidate | Action | Target | Confidence |
|---|---|---|---|
| `nc_037 算法与数据结构` | `unresolved_requires_new_domain` | `null` | high |
| `nc_038 自动化演示文稿生成` | `downgrade_to_topic` | `d_08_03`（归属参考） | medium |
| `nc_039 语音交互系统` | `unresolved_requires_new_domain` | `null` | medium |
| `nc_040 间隔重复系统` | `unresolved_requires_new_domain` | `null` | medium |

模型没有修改冻结 Domain。三条 unresolved 表示现有 9 个 Domain 无法安全容纳候选，不等于已经创建新正式 Domain。

## 5. Decision 血缘与 40/40 Coverage

- `nc_001–nc_036`：逐字段保留原 Consolidation Decision，`decision_source=original_consolidation`。
- `nc_037–nc_040`：`decision_source=tail_completion`。
- 每条保存 `source_attempt` 和 `source_response_hash`。
- 合并后顺序严格为 `nc_001–nc_040`，无遗漏、重复或静默替换。

## 6. Domain Evidence Contract v2

Run A 与 Run B 使用同一个纯函数 Adapter，均生成：

- `canonical_includes / canonical_excludes`：完整保留模型语义；
- `display_includes / display_excludes`：最多 5 条；
- `source_candidate_ids / source_batch_ids / source_run_id`；
- `model_selected_evidence_ids / evidence_pool_ids / representative_ids`。
- 每个节点的 `contract_version / evidence_stats`；
- 顶层 `source_stage_id / source_attempt / raw_response_hash / candidate_table_hash / adapter_version / derived_output_hash`。

派生输出 Hash（Hash 字段自身不参与计算）：

```text
Run A: 801f7dac68200bd6932ddae9548419ddd5a4275a99e5cead8c43865992537bfc
Run B: d4da5ceba9f6fe0d89fcb9625510f6a0eea23a65fed2d3aed4057c284a94e2c9
```

父节点会确定性汇总二级节点的来源候选血缘，但这不是 Assignment。输出不包含 `direct_assigned_ids`、`descendant_assigned_ids` 或 `scope_assigned_ids`。

Run B 的 `d_08` 完整保留 35 条模型选择证据，包含 `C106`、`C128`、`C117`。没有应用旧的 32 条上限，也没有静默删除或替换证据。

## 7. Parent/Child v2

硬校验覆盖 parent 存在、最多两级、无循环、父子不同 ID、规范化名称不同、父 excludes 不排除子节点、节点具备来源候选和真实发现证据。

旧规则 `child.supporting_ids ⊆ parent.supporting_ids` 已移除。Evidence Pool 零重合、子证据未被父节点显式选择等只产生 Warning；本轮不自动移动节点。

Run A、Run B 均无 Parent/Child v2 Blocking Finding。

Gate 会重新计算两份 `derived_output_hash`，并硬校验 Adapter 版本、顶层血缘、节点契约版本和 Evidence Stats。实现还会从截断的主 raw 中确定性解析 36 个完整 Decision，并断言它们与 Repair 保存的前 36 条逐字段一致。

## 8. Run B Quality Gate

```text
candidate decisions: 40/40
tail repair: 0
blocking findings: 0
unresolved_requires_new_domain: 3
gate: PASS_WITH_CHANGES
```

非阻塞警告包括三条 unresolved、历史 Consolidation `finish_reason=length`、历史 reasoning token 过高，以及旧协议将 Domain Tree 与全部 Candidate Decisions 放入同一响应。

## 9. Run C 前置设计

ADR 已记录但未实现：

1. `Domain Node Synthesis` 单独生成冻结 Domain Tree；
2. `Batched Candidate Routing` 每批 10–15 个候选；
3. 每批强制 `expected_candidate_ids == actual_candidate_ids`；
4. 缺失时只补对应 Routing Batch，不重放 Tree 或其他批次。

## 10. 独立只读 Reviewer

最终结论：`PASS_WITH_CONCERNS`。

Reviewer 首轮发现 v2 节点及顶层派生血缘字段不完整；本地补齐后，第二轮又发现 Gate 没有充分验证 Adapter 版本和 Evidence Stats 回归。两项均用纯本地确定性修复完成，没有新增 Provider 调用。最终 Reviewer 确认：

- 原四个 Blocking Findings 已全部清零；
- A/B Adapter 版本被硬校验为同一规定常量；
- 每个节点的五项 Evidence Stats 均由 Gate 独立重算；
- 负向测试能阻止错误 Adapter 与错误 Stats；
- 当前 Gate `PASS_WITH_CHANGES / blocking=[]` 可复现。

Concern 仅为 `nc_037 / nc_039 / nc_040` 仍是 unresolved，因此 Reviewer 不给纯 PASS。

## 11. 测试与停止位置

```text
PYTHONPATH=src:. .venv/bin/pytest -q
228 passed
```

唯一警告是既有 Starlette/httpx deprecation warning。

本轮没有启动 Run C、Cross-run Merge、Hierarchy Validator、Draft A、Trial Assignment、Revision 或 Taxonomy 发布。

## 12. 结论

```text
PASS_WITH_CHANGES
Run B 的 40 条 Candidate Decision 与 Evidence Contract v2 已完整落盘，
无 Blocking Finding；但 nc_037、nc_039、nc_040 被明确判为需要新领域，
因此不能宣称纯 PASS。Run C 前必须采用拆分后的 Node Synthesis + Batched Routing 协议，
并把三条 unresolved 保持隔离。
```
