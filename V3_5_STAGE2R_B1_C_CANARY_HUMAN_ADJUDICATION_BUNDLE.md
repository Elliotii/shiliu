# Shiliu V3.5 Stage 2R-B1-C — Canary Human Adjudication Bundle

This bundle combines the two frozen Canary reviews for human adjudication. It is not Final Gold and contains no automatic Human Decision.

## Case — V2C_B1A00001

### Case Information

- `case_id`: `V2C_B1A00001`
- `original_query`: MCP
- `evaluation_view`: `single_video_topic_evidence`
- `evidence_question`: 该视频的完整原字幕是否实质讨论了 MCP？
- Source / video: `BV1zDTX6eEGu`
- Source type: `raw_subtitle`
- Source language: `zh`
- Transcript boundaries: `BV1zDTX6eEGu_seg_000001` → `BV1zDTX6eEGu_seg_000106`
- Packet hash: `0b975c6b5eb91e2223b226e8896269a32b07354eae2f91299c323147375c33a0`
- Original Human Packet: `research/v3_5/eval_v2/stage2r_b1_b_canary/B1B_V2C_B1A00001_0b975c6b5eb9/human_review_packet.md`

### Primary Review

- Status: `insufficient`
- Required aspects: `{'A1': '视频完整原字幕是否实质讨论MCP。'}`
- Supported aspects: `[]`
- Missing aspects: `[('A1', '视频完整原字幕是否实质讨论MCP。')]`
- Evidence groups: `[]`
- Reason codes: `['query_topic_not_discussed']`
- Confidence: `high`
- Boundary notes: 完整可读字幕围绕名为“大圆”的AI工作助手、工作上下文、群聊信息汇总及创意展开，未出现或实质讨论MCP。
- Required spans:

  - None.
- Optional context spans:

  - `[]`

### Secondary Review

- Status: `insufficient`
- Required aspects: `{'A1': '该视频的完整原字幕实质性讨论 MCP'}`
- Supported aspects: `[]`
- Missing aspects: `[('A1', '该视频的完整原字幕实质性讨论 MCP')]`
- Evidence groups: `[]`
- Reason codes: `['topic_not_discussed']`
- Confidence: `high`
- Boundary notes: (none)
- Required spans:

  - None.
- Optional context spans:

  - `[]`

### Mechanical Agreement

- Label agreement: `True`
- Aspect agreement: `{'state': 'unresolved', 'score': 0.0, 'details': {'method': 'deterministic_token_overlap'}}`
- Supported aspect agreement: `{'state': 'agree', 'score': 1.0, 'details': {}}`
- Missing aspect agreement: `{'state': 'disagree', 'score': 0.0, 'details': {}}`
- Evidence-group agreement: `{'state': 'agree', 'score': 1.0, 'details': {}}`
- Span IoU: `{'state': 'agree', 'score': 1.0, 'details': {'optional_context_iou': 1.0, 'optional_context_state': 'agree', 'primary_recall': 1.0, 'secondary_recall': 1.0}}`
- Time-region agreement: `{'state': 'agree', 'score': 1.0, 'details': {}}`
- Source agreement: `True`
- Reason-code agreement: `{'state': 'disagree', 'score': 0.0, 'details': {'boundary_notes_equal': False}}`
- Mandatory Human Review triggers: `['required_aspect_unresolved', 'missing_aspect_disagreement', 'boundary_notes_difference', 'reason_code_disagreement']`

### Human Focus Questions

1. 是否批准 `insufficient`？
2. Required Aspect 应采用哪种规范表达？
3. Missing Aspect 如何表达？
4. Reason Code 和 Boundary Note 如何处理？

### Blank Human Decision Template

```yaml
human_decision:
  action:  # choose one: approve_primary | approve_secondary | merge_and_revise | reject_both
  final_status:
  final_required_aspects:
  final_supported_aspects:
  final_missing_aspects:
  final_evidence_groups:
  final_required_spans:
  final_optional_context:
  final_reason_codes:
  final_boundary_notes:
  adjudication_reason:
```

## Case — V2C_B1A00002

### Case Information

- `case_id`: `V2C_B1A00002`
- `original_query`: 哪个视频解释了 CLI 相比 MCP 的优势？
- `evaluation_view`: `single_video_claim_evidence`
- `evidence_question`: 该视频的完整原字幕是否实质解释了 CLI 相比 MCP 的优势？
- Source / video: `BV1o87764Ebs`
- Source type: `raw_subtitle`
- Source language: `zh`
- Transcript boundaries: `BV1o87764Ebs_seg_000001` → `BV1o87764Ebs_seg_000374`
- Packet hash: `fe057eee3b4a5809749a549734ab0915a4868409950f1dbd92ae8c63b8096e6d`
- Original Human Packet: `research/v3_5/eval_v2/stage2r_b1_b_canary/B1B_V2C_B1A00002_fe057eee3b4a/human_review_packet.md`

### Primary Review

- Status: `sufficient`
- Required aspects: `{'A1': '解释 CLI 相比 MCP 的优势，即保留 CLI 与 MCP 两个对象及其优势比较关系。'}`
- Supported aspects: `[('A1', '解释 CLI 相比 MCP 的优势，即保留 CLI 与 MCP 两个对象及其优势比较关系。')]`
- Missing aspects: `[]`
- Evidence groups: `[{'group_id': 'G1', 'required_aspect_ids': ['A1'], 'required_span_ids': ['S1', 'S2'], 'alternative_expression_notes': '该组说明 CLI 方案通过前后端分离和命令行控制实现独立运行，并明确比较 MCP 在授权、边缘情况及效率上不如该方案直接、快速。'}]`
- Reason codes: `['COMPARATIVE_EXPLANATION_SUPPORTED', 'CLI_ADVANTAGE_OVER_MCP_SUPPORTED']`
- Confidence: `high`
- Boundary notes: 将前后端拆分并把后端调用做成命令行控制的方案，与随后对 MCP 在授权、边缘情况和效率方面的比较合并判读，构成对 CLI 相比 MCP 优势的完整解释。
- Required spans:

  - `S1` — `350.780s` → `366.160s`
    - Segment IDs: `['BV1o87764Ebs_seg_000154', 'BV1o87764Ebs_seg_000155', 'BV1o87764Ebs_seg_000156', 'BV1o87764Ebs_seg_000157', 'BV1o87764Ebs_seg_000158', 'BV1o87764Ebs_seg_000159']`
    - Required Aspect IDs: `['A1']`
    - Raw transcript text: 那另一条呢就是把前后端彻底拆开啊 后端变成一个能独立运行的AIA卷 所有的调用都能做成命令行的控制形式 看前端呢退到一边 只负责把后端的信息这个监控出来 给人们去看啊
  - `S2` — `367.480s` → `385.350s`
    - Segment IDs: `['BV1o87764Ebs_seg_000161', 'BV1o87764Ebs_seg_000162', 'BV1o87764Ebs_seg_000163', 'BV1o87764Ebs_seg_000164', 'BV1o87764Ebs_seg_000165', 'BV1o87764Ebs_seg_000166', 'BV1o87764Ebs_seg_000167', 'BV1o87764Ebs_seg_000168']`
    - Required Aspect IDs: `['A1']`
    - Raw transcript text: 我选的其实就是第二条路啊 前后段分离啊 原因是在于我用MCP 我的确能够看到网页上面的一些操作 但是呢在这个authorization呐 或者在一些具体的corner case 包括效率上面啊 没有前后端分离来的这么直接来的这么快
- Optional context spans:

  - `[]`

### Secondary Review

- Status: `sufficient`
- Required aspects: `{'A1': '该视频解释了CLI相比MCP的优势'}`
- Supported aspects: `[('A1', '该视频解释了CLI相比MCP的优势')]`
- Missing aspects: `[]`
- Evidence groups: `[{'group_id': 'G1', 'required_aspect_ids': ['A1'], 'required_span_ids': ['S1'], 'alternative_expression_notes': ''}]`
- Reason codes: `[]`
- Confidence: `high`
- Boundary notes: (none)
- Required spans:

  - `S1` — `340.710s` → `385.350s`
    - Segment IDs: `['BV1o87764Ebs_seg_000149', 'BV1o87764Ebs_seg_000150', 'BV1o87764Ebs_seg_000154', 'BV1o87764Ebs_seg_000155', 'BV1o87764Ebs_seg_000156', 'BV1o87764Ebs_seg_000163', 'BV1o87764Ebs_seg_000164', 'BV1o87764Ebs_seg_000165', 'BV1o87764Ebs_seg_000166', 'BV1o87764Ebs_seg_000167', 'BV1o87764Ebs_seg_000168']`
    - Required Aspect IDs: `['A1']`
    - Raw transcript text: 一条呢就是说啊那我们调用MCP是吧 模拟网页的操作 那另一条呢就是把前后端彻底拆开啊 后端变成一个能独立运行的AIA卷 所有的调用都能做成命令行的控制形式 原因是在于我用MCP 我的确能够看到网页上面的一些操作 但是呢在这个authorization呐 或者在一些具体的corner case 包括效率上面啊 没有前后端分离来的这么直接来的这么快
- Optional context spans:

  - `[]`

### Mechanical Agreement

- Label agreement: `True`
- Aspect agreement: `{'state': 'unresolved', 'score': 0.0, 'details': {'method': 'deterministic_token_overlap'}}`
- Supported aspect agreement: `{'state': 'disagree', 'score': 0.0, 'details': {}}`
- Missing aspect agreement: `{'state': 'agree', 'score': 1.0, 'details': {}}`
- Evidence-group agreement: `{'state': 'disagree', 'score': 0.0, 'details': {}}`
- Span IoU: `{'state': 'agree', 'score': 0.5625, 'details': {'optional_context_iou': 1.0, 'optional_context_state': 'agree', 'primary_recall': 0.6428571428571429, 'secondary_recall': 0.8181818181818182}}`
- Time-region agreement: `{'state': 'agree', 'score': 0.7744175627240147, 'details': {}}`
- Source agreement: `True`
- Reason-code agreement: `{'state': 'disagree', 'score': 0.0, 'details': {'boundary_notes_equal': False}}`
- Mandatory Human Review triggers: `['required_aspect_unresolved', 'supported_aspect_disagreement', 'evidence_group_disagreement', 'multiple_required_spans', 'boundary_notes_difference', 'reason_code_disagreement']`

### Human Focus Questions

1. 是否批准 `sufficient`？
2. 应采用一个宽 Span，还是两个互补 Required Spans？
3. CLI 架构说明是否属于必要证据？
4. MCP 的授权、边界情况和效率说明是否必须同时存在？
5. Required Aspect 的最终规范表达是什么？
6. Reason Code 是否保留？

### Blank Human Decision Template

```yaml
human_decision:
  action:  # choose one: approve_primary | approve_secondary | merge_and_revise | reject_both
  final_status:
  final_required_aspects:
  final_supported_aspects:
  final_missing_aspects:
  final_evidence_groups:
  final_required_spans:
  final_optional_context:
  final_reason_codes:
  final_boundary_notes:
  adjudication_reason:
```

## Bundle Guardrails

- No majority vote or automatic adjudication was applied.
- No Final Gold was produced.
- No third Case was selected or reviewed.
- Remaining Pilot authorization remains false pending both Human Decisions.
