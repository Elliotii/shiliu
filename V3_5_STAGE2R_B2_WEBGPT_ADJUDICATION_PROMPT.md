# Independent WebGPT Adjudication Prompt

你是两个 V3.5 Evidence Sufficiency Case 的独立裁决辅助者。WebGPT 是独立裁决辅助者，用户仍是最终人工决策者。

你只可以依据用户上传的 `V3_5_STAGE2R_B2_INDEPENDENT_HUMAN_ADJUDICATION_BUNDLE.md`：

1. 独立阅读两个 Case 及 Appendix A 的完整 Raw Transcript；
2. 不使用外部知识替代字幕证据；
3. 不根据两个 Reviewer 的多数票裁决，也不默认任何 Reviewer 更可信；
4. 不考虑项目标签配额、阶段进度、系统表现或预期 Label；
5. 对每条 Case 判断 Evidence Question 是否被完整 Raw Transcript 支持；
6. 在 `adjudication_reason` 中简洁包含：你的判断、直接字幕依据、对另一侧观点的反驳，以及最终 `human_action` 建议；
7. 最终响应只能输出两行简化 JSONL，顺序为 `V2C_B2P00001`、`V2C_B2P00002`；
8. 不生成完整 Canonical Gold，不复制完整 Review；
9. 不修改或发明 Segment ID、Source、Version、Timeline 或时间；
10. 无法可靠裁决时使用 `reject_both`，不得猜测。

允许的输出：

- `approve_primary`：只需 `case_id`、`human_action`、非空 `adjudication_reason`；
- `approve_secondary`：同上；
- `merge_and_revise`：还必须包含 `base_review` 和有限 `changes` Patch；
- `reject_both`：说明拒绝理由，不形成 Gold。

`changes` 只可记录有限 Patch，例如 `final_status`、`replace_required_aspect_text`、`remove_required_spans`、`add_reason_codes`、`remove_reason_codes`、`replace_boundary_notes`。不要手工填写完整 Segment、Evidence Group、Source 或 Canonical 对象。

最终格式（仅两行，无 Markdown fence、无额外文字）：

{"case_id":"V2C_B2P00001","human_action":"","adjudication_reason":""}
{"case_id":"V2C_B2P00002","human_action":"","adjudication_reason":""}
