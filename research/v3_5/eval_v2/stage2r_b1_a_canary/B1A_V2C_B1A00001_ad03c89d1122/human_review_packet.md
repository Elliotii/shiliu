# Human Review Packet — V2C_B1A00001

- Review Run: `B1A_V2C_B1A00001_ad03c89d1122`
- Query: MCP
- Query family: `exact_entity_mcp`
- Leakage group: `LGV2_VIDEO_BV1ZDTX6EEGU`
- Source / Video: `BV1zDTX6eEGu`
- Transcript boundaries: `BV1zDTX6eEGu_seg_000001` → `BV1zDTX6eEGu_seg_000106`
- Segment count: 106
- Duration: 277.480s
- Full transcript reference: `/Users/elliot/Documents/Shiliu/videos/BV1zDTX6eEGu/subtitle-raw.txt`

## Primary

- Path status: `provider_error`
- Provider error: `transport_exhausted_or_non_retryable`

## Secondary

- Path status: `valid`
- Proposed status: `sufficient`
- Required aspects: `{'A1': '戚薇上线了一个名为“大元”的AI助手。', 'A2': '好的想法来源于日常的细碎观察、思考和与人对话。', 'A3': 'WAIC大会（世界人工智能大会）于7月17日至19日在上海举行。'}`
- Supported aspects: `[('A1', '戚薇上线了一个名为“大元”的AI助手。'), ('A2', '好的想法来源于日常的细碎观察、思考和与人对话。'), ('A3', 'WAIC大会（世界人工智能大会）于7月17日至19日在上海举行。')]`
- Missing aspects: `[]`
- Evidence groups: `[{'group_id': 'G1', 'required_aspect_ids': ['A1'], 'required_span_ids': ['S1'], 'alternative_expression_notes': ''}, {'group_id': 'G2', 'required_aspect_ids': ['A2'], 'required_span_ids': ['S2'], 'alternative_expression_notes': ''}, {'group_id': 'G3', 'required_aspect_ids': ['A3'], 'required_span_ids': ['S3'], 'alternative_expression_notes': ''}]`
- Optional context: `[]`
- Reason codes: `[]`
- Confidence: `high`
- Notes: ``

### Required Evidence

- `S1` — `9.650s` → `14.539s`; segments `['BV1zDTX6eEGu_seg_000006', 'BV1zDTX6eEGu_seg_000007']`; source `BV1zDTX6eEGu` / `raw_subtitle:BV1zDTX6eEGu:p1` / `sha256:f8e66789b120495738e2d0c9223107ffea348b70f0882a6f5f2c4ae27600361a` / `timeline_f8e66789b1204957`
  - Raw text: 戚薇不是上线了一个AI助手吗 他的名字叫大元啊
- `S2` — `90.090s` → `100.830s`; segments `['BV1zDTX6eEGu_seg_000036', 'BV1zDTX6eEGu_seg_000037', 'BV1zDTX6eEGu_seg_000038', 'BV1zDTX6eEGu_seg_000039']`; source `BV1zDTX6eEGu` / `raw_subtitle:BV1zDTX6eEGu:p1` / `sha256:f8e66789b120495738e2d0c9223107ffea348b70f0882a6f5f2c4ae27600361a` / `timeline_f8e66789b1204957`
  - Raw text: 然后那好的想法从哪儿来呢 我觉得其实就是从这种细碎的一点一点的 非常细枝末节的这种观察中 就可以产生一些很好的想法
- `S3` — `248.880s` → `253.570s`; segments `['BV1zDTX6eEGu_seg_000094', 'BV1zDTX6eEGu_seg_000095']`; source `BV1zDTX6eEGu` / `raw_subtitle:BV1zDTX6eEGu:p1` / `sha256:f8e66789b120495738e2d0c9223107ffea348b70f0882a6f5f2c4ae27600361a` / `timeline_f8e66789b1204957`
  - Raw text: 就是在7月17到19号 上海世界人工智大会上

## Mechanical Agreement

Agreement unavailable because fewer than two valid Canonical Reviews were produced.

## Review Questions

- [ ] 最终 Label 是否正确？
- [ ] Required Aspects 是否完整？
- [ ] Evidence Groups 是否可接受？
- [ ] Required Spans 是否足够且不过宽？
- [ ] 是否漏掉互补证据？
- [ ] 是否需要修正？

Human decision: **pending**. This packet is not final Gold.
