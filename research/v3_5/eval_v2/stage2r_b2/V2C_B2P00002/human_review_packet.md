# Human Review Packet — V2C_B2P00002

- Original Query: vibe coding
- Evaluation View: `single_video_topic_evidence`
- Evidence Question: 该视频的完整原字幕是否实质讨论了 vibe coding？
- Projection Status: `annotatable`
- Source / Video: `BV1o87764Ebs`
- Source Type / Language: `raw_subtitle` / `zh`
- Transcript boundaries: `BV1o87764Ebs_seg_000001` → `BV1o87764Ebs_seg_000374`
- Segment count / duration: `374` / `866.780s`
- Full Transcript Reference: `/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/subtitle-raw.txt`

## Primary

- Status: `valid`
- Query grounding: `valid`
- Repair count: `0`
- Attempts: `[{'provider': 'openai', 'case_id': 'V2C_B2P00002', 'reviewer_role': 'primary', 'attempt_index': 1, 'attempt_type': 'initial_draft', 'selected_for_final': True, 'http_status': 'unavailable', 'model_body_returned': True, 'input_tokens': 76120, 'output_tokens': 1386, 'cached_tokens': 0, 'provider_latency_ms': 20961, 'end_to_end_latency_ms': 20973, 'safe_error_category': 'none', 'payload_fingerprint': '7af8819c88eec512b25d6b3090e33925b345a57d2042fb0f495a10be3eec5f4d'}]`
- Proposed status: `sufficient`
- Required aspects: `[{'aspect_id': 'A1', 'description': '视频是否实质讨论了 vibe coding。'}]`
- Supported / Missing: `['A1']` / `[]`
- Evidence groups: `[{'group_id': 'G1', 'required_aspect_ids': ['A1'], 'required_span_ids': ['S1'], 'alternative_expression_notes': '以 AI/coding agent 参与并自动化代码开发、回归测试和迭代的具体流程，实质性讨论了 vibe coding 相关主题。'}]`
- Reason codes: `['SUBSTANTIVE_TOPIC_DISCUSSION']`
- Confidence: `high`
- Boundary notes: 字幕未直接出现“vibe coding”这一术语，但围绕使用 Codex 等 coding agent 进行代码开发、测试和迭代的工作流展开。
- Selected Raw Transcript Regions:
  - `S1` `665.870s` → `717.500s`, segments `['BV1o87764Ebs_seg_000296', 'BV1o87764Ebs_seg_000297', 'BV1o87764Ebs_seg_000298', 'BV1o87764Ebs_seg_000299', 'BV1o87764Ebs_seg_000300', 'BV1o87764Ebs_seg_000301', 'BV1o87764Ebs_seg_000302', 'BV1o87764Ebs_seg_000303', 'BV1o87764Ebs_seg_000304', 'BV1o87764Ebs_seg_000305', 'BV1o87764Ebs_seg_000306', 'BV1o87764Ebs_seg_000307', 'BV1o87764Ebs_seg_000308', 'BV1o87764Ebs_seg_000309', 'BV1o87764Ebs_seg_000310', 'BV1o87764Ebs_seg_000311', 'BV1o87764Ebs_seg_000312']`
    - Raw text: 我们可以在codex里面去做这样一件事情 就是当他需要开发新的功能的时候 它不仅仅考虑这个代码怎么写 它需要首先先去设计回归测试 其次去设计这样的一个开关 然后呢去进行代码的编写 编写完之后在开关开启和开关结束的时候 同样的去跑一遍这样的一个回归测试 通过回归测试的结果进行一个反馈 再去修改代码 直到最终的代码改成能够符合回归测试要求的 这样的一个版本 那在整个这样的一套体系里面 人是没有参与的 而codex这种coding agent 通过我们设计的这种可验证体系 把这一切都连成了一个闭环

## Secondary

- Status: `valid`
- Query grounding: `valid`
- Repair count: `0`
- Attempts: `[{'provider': 'deepseek', 'case_id': 'V2C_B2P00002', 'reviewer_role': 'secondary', 'attempt_index': 1, 'attempt_type': 'initial_draft', 'selected_for_final': True, 'http_status': 'unavailable', 'model_body_returned': True, 'input_tokens': 52472, 'output_tokens': 1250, 'cached_tokens': 'unavailable', 'provider_latency_ms': 22292, 'end_to_end_latency_ms': 22308, 'safe_error_category': 'none', 'payload_fingerprint': '53d330a8934c9f3296d0d7d95ae36737f7ef1ae72661091a02dd4d45593eabec'}]`
- Proposed status: `insufficient`
- Required aspects: `[{'aspect_id': 'A1', 'description': '该视频的完整原字幕实质讨论了vibe coding。'}]`
- Supported / Missing: `[]` / `['A1']`
- Evidence groups: `[]`
- Reason codes: `['vibe coding not found in transcript']`
- Confidence: `high`
- Boundary notes: (none)
- Selected Raw Transcript Regions:
  - None.

## Mechanical Agreement

- Status: `mandatory_human_review`
- Metrics: `{'agreement_version': 'v3.5-annotation-agreement-v2', 'case_id': 'V2C_B2P00002', 'case_input_sha256': 'a3d593b24a3c01a10d0a750c6ed9143a9f4d405a5415051adb36bc5d810c878a', 'status': 'mandatory_human_review', 'label_exact_agreement': False, 'required_aspect_agreement': {'state': 'unresolved', 'score': 0.25, 'details': {'method': 'deterministic_token_overlap'}}, 'supported_aspect_agreement': {'state': 'disagree', 'score': 0.0, 'details': {}}, 'missing_aspect_agreement': {'state': 'disagree', 'score': 0.0, 'details': {}}, 'evidence_group_agreement': {'state': 'disagree', 'score': 0.0, 'details': {}}, 'required_span_overlap': {'state': 'disagree', 'score': 0.0, 'details': {'primary_recall': 0.0, 'secondary_recall': 1.0, 'optional_context_state': 'agree', 'optional_context_iou': 1.0}}, 'time_region_overlap': {'state': 'disagree', 'score': 0.0, 'details': {}}, 'source_agreement': False, 'reason_code_agreement': {'state': 'disagree', 'score': 0.0, 'details': {'boundary_notes_equal': False}}, 'confidence_difference': 0, 'mandatory_triggers': ['label_disagreement', 'required_aspect_unresolved', 'supported_aspect_disagreement', 'missing_aspect_disagreement', 'evidence_group_disagreement', 'evidence_region_difference', 'extreme_label_disagreement', 'source_disagreement', 'boundary_notes_difference', 'reason_code_disagreement'], 'human_adjudication_required': True, 'spot_check_status': 'not_selected'}`

## Blank Human Decision

```yaml
human_decision:
  action:
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

Human decision is pending. This packet is not Final Gold.
