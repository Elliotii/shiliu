# Reviewer Draft Repair v1

最多执行一次。Repair 只能接收原 Packet、当前 Reviewer 自己的原始输出、Reviewer Draft Schema 和 Validation Errors。保持原语义意图，仅修复 Schema、索引、Segment、Source/Version/Timeline 或状态一致性错误。

禁止接收或使用另一个 Reviewer 输出、Agreement、Gold、Adjudication、系统预测、Safe Projection、Case Mining Notes 或外部知识。只返回一个 Draft JSON 对象。继续只使用数组索引；禁止生成 `A*`、`S*`、`G*` 正式主键。Repair 后仍无法通过确定性 Compiler 时记录 `invalid_after_repair`，不得第二次 Repair。
