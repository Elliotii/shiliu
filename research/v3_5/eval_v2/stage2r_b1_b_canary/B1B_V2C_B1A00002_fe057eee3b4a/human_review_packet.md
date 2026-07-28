# Human Review Packet — V2C_B1A00002

- Review Run: `B1B_V2C_B1A00002_fe057eee3b4a`
- Query: 哪个视频解释了 CLI 相比 MCP 的优势？
- Evaluation view: `single_video_claim_evidence`
- Evidence question: 该视频的完整原字幕是否实质解释了 CLI 相比 MCP 的优势？
- Projection policy: `v3.5-query-projection-v1`
- Query family: `evidence_lookup_cli_vs_mcp`
- Leakage group: `LGV2_VIDEO_BV1O87764EBS`
- Source / Video: `BV1o87764Ebs`
- Transcript boundaries: `BV1o87764Ebs_seg_000001` → `BV1o87764Ebs_seg_000374`
- Segment count: 374
- Duration: 866.780s
- Full transcript reference: `/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/subtitle-raw.txt`

## Primary

- Path status: `valid`
- Query grounding: `valid`
- Query grounding findings: `[]`
- Proposed status: `sufficient`
- Required aspects: `{'A1': '解释 CLI 相比 MCP 的优势，即保留 CLI 与 MCP 两个对象及其优势比较关系。'}`
- Supported aspects: `[('A1', '解释 CLI 相比 MCP 的优势，即保留 CLI 与 MCP 两个对象及其优势比较关系。')]`
- Missing aspects: `[]`
- Evidence groups: `[{'group_id': 'G1', 'required_aspect_ids': ['A1'], 'required_span_ids': ['S1', 'S2'], 'alternative_expression_notes': '该组说明 CLI 方案通过前后端分离和命令行控制实现独立运行，并明确比较 MCP 在授权、边缘情况及效率上不如该方案直接、快速。'}]`
- Optional context: `[]`
- Reason codes: `['COMPARATIVE_EXPLANATION_SUPPORTED', 'CLI_ADVANTAGE_OVER_MCP_SUPPORTED']`
- Confidence: `high`
- Notes: `将前后端拆分并把后端调用做成命令行控制的方案，与随后对 MCP 在授权、边缘情况和效率方面的比较合并判读，构成对 CLI 相比 MCP 优势的完整解释。`

### Required Evidence

- `S1` — `350.780s` → `366.160s`; segments `['BV1o87764Ebs_seg_000154', 'BV1o87764Ebs_seg_000155', 'BV1o87764Ebs_seg_000156', 'BV1o87764Ebs_seg_000157', 'BV1o87764Ebs_seg_000158', 'BV1o87764Ebs_seg_000159']`; source `BV1o87764Ebs` / `raw_subtitle:BV1o87764Ebs:p1` / `sha256:087e661d7af23a3bf535f65fdec5f66402ccb781bd5db8698dd5c1ee912a1e5b` / `timeline_087e661d7af23a3b`
  - Raw text: 那另一条呢就是把前后端彻底拆开啊 后端变成一个能独立运行的AIA卷 所有的调用都能做成命令行的控制形式 看前端呢退到一边 只负责把后端的信息这个监控出来 给人们去看啊
- `S2` — `367.480s` → `385.350s`; segments `['BV1o87764Ebs_seg_000161', 'BV1o87764Ebs_seg_000162', 'BV1o87764Ebs_seg_000163', 'BV1o87764Ebs_seg_000164', 'BV1o87764Ebs_seg_000165', 'BV1o87764Ebs_seg_000166', 'BV1o87764Ebs_seg_000167', 'BV1o87764Ebs_seg_000168']`; source `BV1o87764Ebs` / `raw_subtitle:BV1o87764Ebs:p1` / `sha256:087e661d7af23a3bf535f65fdec5f66402ccb781bd5db8698dd5c1ee912a1e5b` / `timeline_087e661d7af23a3b`
  - Raw text: 我选的其实就是第二条路啊 前后段分离啊 原因是在于我用MCP 我的确能够看到网页上面的一些操作 但是呢在这个authorization呐 或者在一些具体的corner case 包括效率上面啊 没有前后端分离来的这么直接来的这么快

## Secondary

- Path status: `valid_after_repair`
- Query grounding: `valid`
- Query grounding findings: `[]`
- Proposed status: `sufficient`
- Required aspects: `{'A1': '该视频解释了CLI相比MCP的优势'}`
- Supported aspects: `[('A1', '该视频解释了CLI相比MCP的优势')]`
- Missing aspects: `[]`
- Evidence groups: `[{'group_id': 'G1', 'required_aspect_ids': ['A1'], 'required_span_ids': ['S1'], 'alternative_expression_notes': ''}]`
- Optional context: `[]`
- Reason codes: `[]`
- Confidence: `high`
- Notes: ``

### Required Evidence

- `S1` — `340.710s` → `385.350s`; segments `['BV1o87764Ebs_seg_000149', 'BV1o87764Ebs_seg_000150', 'BV1o87764Ebs_seg_000154', 'BV1o87764Ebs_seg_000155', 'BV1o87764Ebs_seg_000156', 'BV1o87764Ebs_seg_000163', 'BV1o87764Ebs_seg_000164', 'BV1o87764Ebs_seg_000165', 'BV1o87764Ebs_seg_000166', 'BV1o87764Ebs_seg_000167', 'BV1o87764Ebs_seg_000168']`; source `BV1o87764Ebs` / `raw_subtitle:BV1o87764Ebs:p1` / `sha256:087e661d7af23a3bf535f65fdec5f66402ccb781bd5db8698dd5c1ee912a1e5b` / `timeline_087e661d7af23a3b`
  - Raw text: 一条呢就是说啊那我们调用MCP是吧 模拟网页的操作 那另一条呢就是把前后端彻底拆开啊 后端变成一个能独立运行的AIA卷 所有的调用都能做成命令行的控制形式 原因是在于我用MCP 我的确能够看到网页上面的一些操作 但是呢在这个authorization呐 或者在一些具体的corner case 包括效率上面啊 没有前后端分离来的这么直接来的这么快

## Mechanical Agreement

- Overall: `mandatory_human_review`
- Label agreement: `True`
- Required aspects: `{'state': 'unresolved', 'score': 0.0, 'details': {'method': 'deterministic_token_overlap'}}`
- Supported aspects: `{'state': 'disagree', 'score': 0.0, 'details': {}}`
- Missing aspects: `{'state': 'agree', 'score': 1.0, 'details': {}}`
- Evidence groups: `{'state': 'disagree', 'score': 0.0, 'details': {}}`
- Required span overlap: `{'state': 'agree', 'score': 0.5625, 'details': {'primary_recall': 0.6428571428571429, 'secondary_recall': 0.8181818181818182, 'optional_context_state': 'agree', 'optional_context_iou': 1.0}}`
- Time overlap: `{'state': 'agree', 'score': 0.7744175627240147, 'details': {}}`
- Source agreement: `True`
- Reason code agreement: `{'state': 'disagree', 'score': 0.0, 'details': {'boundary_notes_equal': False}}`
- Mandatory triggers: `['required_aspect_unresolved', 'supported_aspect_disagreement', 'evidence_group_disagreement', 'multiple_required_spans', 'boundary_notes_difference', 'reason_code_disagreement']`

## Review Questions

- [ ] 最终 Label 是否正确？
- [ ] Required Aspects 是否完整？
- [ ] Evidence Groups 是否可接受？
- [ ] Required Spans 是否足够且不过宽？
- [ ] 是否漏掉互补证据？
- [ ] 是否需要修正？

Human decision: **pending**. This packet is not final Gold.
