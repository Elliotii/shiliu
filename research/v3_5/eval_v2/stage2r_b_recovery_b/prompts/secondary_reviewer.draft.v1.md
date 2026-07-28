# Blind Secondary Reviewer Draft Contract v1

独立标注唯一一个合成 Preflight Packet。必须阅读完整 Raw Subtitle／Raw ASR Segment 序列，Packet 是唯一证据权威。禁止使用工具、网络、外部常识、标题、摘要、搜索结果、候选窗口、Safe Projection、Case Mining Notes、系统预测、Gold、Agreement、其他 Reviewer 输出、Review 或 Adjudication 资产。

只返回一个符合 `reviewer_draft.v1.schema.json` 的 JSON 对象。

- `required_aspects` 和 `required_spans` 均按数组顺序从 0 开始编号；
- 所有 Aspect／Span 引用只能使用范围内的整数索引；
- `segment_ids` 只能来自 Packet；
- 禁止生成、复制或输出 `A1`、`S1`、`G1` 等正式内部主键；
- 禁止输出 Quote、Timestamp、Video／Source Identity、Source Version 或 Timeline Run，这些由本地确定性代码重建；
- Evidence Group 之间是 OR，同一 Group 内 Required Span 是 AND，每个 Group 至少包含一个 Required Span；
- Optional Context 不计入充分性。

先定义 Required Aspects，再判断 supported／missing。完整支持全部 Aspect 且存在完整证据路径时才使用 `sufficient`；同时存在 supported 与 missing 时才使用 `partial`；可读 Raw Source 没有实质支持时使用 `insufficient`；只有 Source 权威或完整性无法确认时才使用 `unverifiable`。

返回前阅读全部 Segment。完整字幕与首尾 Segment 由本地 Compiler 根据 Packet 确定，不由模型复制。
