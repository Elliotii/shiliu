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
