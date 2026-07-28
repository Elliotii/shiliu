# Human Review Packet — V2C_B1A00001

- Review Run: `B1B_V2C_B1A00001_0b975c6b5eb9`
- Query: MCP
- Evaluation view: `single_video_topic_evidence`
- Evidence question: 该视频的完整原字幕是否实质讨论了 MCP？
- Projection policy: `v3.5-query-projection-v1`
- Query family: `exact_entity_mcp`
- Leakage group: `LGV2_VIDEO_BV1ZDTX6EEGU`
- Source / Video: `BV1zDTX6eEGu`
- Transcript boundaries: `BV1zDTX6eEGu_seg_000001` → `BV1zDTX6eEGu_seg_000106`
- Segment count: 106
- Duration: 277.480s
- Full transcript reference: `/Users/elliot/Documents/Shiliu/videos/BV1zDTX6eEGu/subtitle-raw.txt`

## Primary

- Path status: `valid`
- Query grounding: `valid`
- Query grounding findings: `[]`
- Proposed status: `insufficient`
- Required aspects: `{'A1': '视频完整原字幕是否实质讨论MCP。'}`
- Supported aspects: `[]`
- Missing aspects: `[('A1', '视频完整原字幕是否实质讨论MCP。')]`
- Evidence groups: `[]`
- Optional context: `[]`
- Reason codes: `['query_topic_not_discussed']`
- Confidence: `high`
- Notes: `完整可读字幕围绕名为“大圆”的AI工作助手、工作上下文、群聊信息汇总及创意展开，未出现或实质讨论MCP。`

### Required Evidence


## Secondary

- Path status: `valid`
- Query grounding: `valid`
- Query grounding findings: `[]`
- Proposed status: `insufficient`
- Required aspects: `{'A1': '该视频的完整原字幕实质性讨论 MCP'}`
- Supported aspects: `[]`
- Missing aspects: `[('A1', '该视频的完整原字幕实质性讨论 MCP')]`
- Evidence groups: `[]`
- Optional context: `[]`
- Reason codes: `['topic_not_discussed']`
- Confidence: `high`
- Notes: ``

### Required Evidence


## Mechanical Agreement

- Overall: `mandatory_human_review`
- Label agreement: `True`
- Required aspects: `{'state': 'unresolved', 'score': 0.0, 'details': {'method': 'deterministic_token_overlap'}}`
- Supported aspects: `{'state': 'agree', 'score': 1.0, 'details': {}}`
- Missing aspects: `{'state': 'disagree', 'score': 0.0, 'details': {}}`
- Evidence groups: `{'state': 'agree', 'score': 1.0, 'details': {}}`
- Required span overlap: `{'state': 'agree', 'score': 1.0, 'details': {'primary_recall': 1.0, 'secondary_recall': 1.0, 'optional_context_state': 'agree', 'optional_context_iou': 1.0}}`
- Time overlap: `{'state': 'agree', 'score': 1.0, 'details': {}}`
- Source agreement: `True`
- Reason code agreement: `{'state': 'disagree', 'score': 0.0, 'details': {'boundary_notes_equal': False}}`
- Mandatory triggers: `['required_aspect_unresolved', 'missing_aspect_disagreement', 'boundary_notes_difference', 'reason_code_disagreement']`

## Review Questions

- [ ] 最终 Label 是否正确？
- [ ] Required Aspects 是否完整？
- [ ] Evidence Groups 是否可接受？
- [ ] Required Spans 是否足够且不过宽？
- [ ] 是否漏掉互补证据？
- [ ] 是否需要修正？

Human decision: **pending**. This packet is not final Gold.
