# ADR：V3 Domain Stability 与 Entity Typing 顺序

状态：Checkpoint 3.12 已采用。

## 决策

- Domain Run A/B/C 继续使用冻结的 `classification_profile_v1` 和既有 Domain 语义协议。
- Presentation Form、Focus Object Type、Suggested Use Context 不参与 Domain 发现、跨运行归并或 Draft A 判断。
- Entity Typing 不在 Checkpoint 3.12 实现。它必须在剩余 80 条受控分面赋值之前，以独立 Spike 验证后接入。
- Repair 后的任何字段变化都写入 `repair-semantic-diff.json`；预算导致的候选删除属于语义选择或语义移除，不得伪装为纯格式修复。
- Object Type 超过两个时依据内容中心性、置信度和证据强度选择，未选择项进入 `overflow_object_type_candidates`，禁止按输出顺序静默截断。

## 原因

Domain Run B/C 不依赖 Entity Type。此时引入 Entity Typing 会扩大变量范围并削弱 A/B/C 可比性。受控分面扩容则直接依赖 Entity 类型质量，因此把它设为扩容前门禁，而不是偏离当前 Domain 主线。

## 后续门禁

在剩余 80 条受控分面赋值前必须完成：

1. Entity Typing Schema 和独立调用审计；
2. 未类型化、确定性映射和模型辅助映射的 Gate Warning；
3. 小样本准确性与溢出协议回归；
4. 不修改已冻结 Run #21。

# Checkpoint 3.12C addendum: split synthesis from routing

Run B demonstrated that a single high-thinking response containing both the
complete Domain tree and every Candidate Decision is too large: the Domain
tree was complete, while the response stopped during candidate `nc_037`.

Run C must therefore use two separately recoverable provider stages:

1. **Domain Node Synthesis** produces only the frozen, at-most-two-level Domain
   tree and its canonical semantic fields.
2. **Batched Candidate Routing** routes 10--15 candidates per batch to the
   frozen tree, or downgrades/removes/marks them unresolved. Each batch performs
   `expected_candidate_ids == actual_candidate_ids` before it can complete.

Only a missing routing batch may be retried. A routing retry must not replay
Domain Node Synthesis or another completed routing batch. This is a design
record only; Checkpoint 3.12C does not implement or invoke Run C.

Minimal routing output:

```json
{
  "candidate_decisions": [
    {
      "candidate_id": "nc_001",
      "action": "merge_into_existing_domain",
      "target_id": "d_01",
      "reason": "..."
    }
  ]
}
```
