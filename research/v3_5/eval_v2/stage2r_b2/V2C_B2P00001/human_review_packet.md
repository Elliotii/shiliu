# Human Review Packet — V2C_B2P00001

- Original Query: RAG
- Evaluation View: `single_video_topic_evidence`
- Evidence Question: 该视频的完整原字幕是否实质讨论了 RAG？
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
- Attempts: `[{'provider': 'openai', 'case_id': 'V2C_B2P00001', 'reviewer_role': 'primary', 'attempt_index': 1, 'attempt_type': 'initial_draft', 'selected_for_final': True, 'http_status': 'unavailable', 'model_body_returned': True, 'input_tokens': 76104, 'output_tokens': 471, 'cached_tokens': 0, 'provider_latency_ms': 8925, 'end_to_end_latency_ms': 9610, 'safe_error_category': 'none', 'payload_fingerprint': '4416d1c6bf387e6f87e3284bd2f5defe3f0c83d25391e940f1a2300123cc9d99'}]`
- Proposed status: `insufficient`
- Required aspects: `[{'aspect_id': 'A1', 'description': '视频的完整原字幕是否实质讨论RAG。'}]`
- Supported / Missing: `[]` / `['A1']`
- Evidence groups: `[]`
- Reason codes: `['TOPIC_NOT_SUBSTANTIALLY_DISCUSSED']`
- Confidence: `high`
- Boundary notes: 完整字幕主要讨论AI agent开发中的自动化验证、前后端分离、回归测试和LLM裁判，未实质讨论RAG。
- Selected Raw Transcript Regions:
  - None.

## Secondary

- Status: `valid`
- Query grounding: `valid`
- Repair count: `0`
- Attempts: `[{'provider': 'deepseek', 'case_id': 'V2C_B2P00001', 'reviewer_role': 'secondary', 'attempt_index': 1, 'attempt_type': 'initial_draft', 'selected_for_final': True, 'http_status': 'unavailable', 'model_body_returned': True, 'input_tokens': 52461, 'output_tokens': 1897, 'cached_tokens': 'unavailable', 'provider_latency_ms': 30524, 'end_to_end_latency_ms': 30567, 'safe_error_category': 'none', 'payload_fingerprint': '20a1735684387d90a84f96a55be7929232d19f0ae9c465215b7d1ae455ba445e'}]`
- Proposed status: `insufficient`
- Required aspects: `[{'aspect_id': 'A1', 'description': '视频原字幕包含对RAG的实质讨论'}]`
- Supported / Missing: `[]` / `['A1']`
- Evidence groups: `[]`
- Reason codes: `['no_mention_of_RAG']`
- Confidence: `high`
- Boundary notes: The transcript discusses AI agent development, testing and verification methodology, but never mentions RAG (Retrieval-Augmented Generation).
- Selected Raw Transcript Regions:
  - None.

## Mechanical Agreement

- Status: `mandatory_human_review`
- Metrics: `{'agreement_version': 'v3.5-annotation-agreement-v2', 'case_id': 'V2C_B2P00001', 'case_input_sha256': '600a264ef2f305fe948116b736293bf38668ed72e7cf2bd70369a5cf64567445', 'status': 'mandatory_human_review', 'label_exact_agreement': True, 'required_aspect_agreement': {'state': 'unresolved', 'score': 0.0, 'details': {'method': 'deterministic_token_overlap'}}, 'supported_aspect_agreement': {'state': 'agree', 'score': 1.0, 'details': {}}, 'missing_aspect_agreement': {'state': 'disagree', 'score': 0.0, 'details': {}}, 'evidence_group_agreement': {'state': 'agree', 'score': 1.0, 'details': {}}, 'required_span_overlap': {'state': 'agree', 'score': 1.0, 'details': {'primary_recall': 1.0, 'secondary_recall': 1.0, 'optional_context_state': 'agree', 'optional_context_iou': 1.0}}, 'time_region_overlap': {'state': 'agree', 'score': 1.0, 'details': {}}, 'source_agreement': True, 'reason_code_agreement': {'state': 'disagree', 'score': 0.0, 'details': {'boundary_notes_equal': False}}, 'confidence_difference': 0, 'mandatory_triggers': ['required_aspect_unresolved', 'missing_aspect_disagreement', 'boundary_notes_difference', 'reason_code_disagreement'], 'human_adjudication_required': True, 'spot_check_status': 'not_selected'}`

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
