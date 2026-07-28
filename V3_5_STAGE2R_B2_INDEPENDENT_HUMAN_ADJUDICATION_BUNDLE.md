# Shiliu V3.5 Stage 2R-B2 — Independent Human Adjudication Bundle

用途：  
本文件仅用于对两个 V3.5 Evidence Sufficiency Case 进行人工裁决。

裁决者：  
用户是最终决策者；WebGPT 仅作为独立裁决辅助者。

禁止：  
不得根据标签配额、项目进度或 Reviewer 多数票裁决。

本文件自包含全部裁决规则、两侧冻结 Review、Mechanical Agreement，以及唯一证据权威——完整共享 Raw Transcript。无需仓库、外部路径、其他报告或历史对话。

## Frozen Adjudication Rules

- `sufficient`：完整 Raw Transcript 足以支持 Evidence Question 的全部必要方面。
- `partial`：至少一个重要方面被支持，但至少一个重要方面仍缺失。
- `insufficient`：Source 可读，但没有足够证据支持信息需求。
- `unverifiable`：Source 不可用、不可解析或无法可靠验证。

Raw Subtitle / Raw ASR 是唯一证据和时间权威。Title、Description、AI Summary、Search Result 不得作为 Gold Evidence。Evidence Groups 之间是 OR；同一 Evidence Group 内 Required Spans 是 AND。

Mechanical Agreement 只负责发现差异，不代表语义多数票或自动 Gold。

### Frozen Versions

- Query Projection: `v3.5-query-projection-v1`
- Canonical Review: `v3.5-annotation-review-v2`
- Agreement: `v3.5-annotation-agreement-v2`

## Case — V2C_B2P00001

### 1. Case Identity

- `case_id`: `V2C_B2P00001`
- `original_query`: RAG
- `evaluation_view`: `single_video_topic_evidence`
- `evidence_question`: 该视频的完整原字幕是否实质讨论了 RAG？
- `projection_policy_version`: `v3.5-query-projection-v1`
- `source_video`: `BV1o87764Ebs`
- `source_type`: `raw_subtitle`
- `source_language`: `zh`
- `source_version`: `sha256:087e661d7af23a3bf535f65fdec5f66402ccb781bd5db8698dd5c1ee912a1e5b`
- `timeline_run`: `timeline_087e661d7af23a3b`
- `transcript_segment_count`: `374`
- `transcript_start`: `0.060s`
- `transcript_end`: `866.840s`
- `packet_sha256`: `95077479bb6ee15b4f79fedc21f9c21b589c2df2146418888045dbfe30aada56`
- Complete evidence authority: see **Appendix A — Complete Shared Raw Transcript**.

### 2. Primary Review

- `status`: `insufficient`
- `required_aspects`:
```json
[{"aspect_id":"A1","description":"视频的完整原字幕是否实质讨论RAG。"}]
```
- `supported_aspects`: `[]`
- `missing_aspects`: `["A1"]`
- `evidence_groups`:
```json
[]
```
- `optional_context`:
```json
[]
```
- `reason_codes`: `["TOPIC_NOT_SUBSTANTIALLY_DISCUSSED"]`
- `confidence`: `high`
- `boundary_notes`: 完整字幕主要讨论AI agent开发中的自动化验证、前后端分离、回归测试和LLM裁判，未实质讨论RAG。
- `required_spans`:

  - None.

### 3. Secondary Review

- `status`: `insufficient`
- `required_aspects`:
```json
[{"aspect_id":"A1","description":"视频原字幕包含对RAG的实质讨论"}]
```
- `supported_aspects`: `[]`
- `missing_aspects`: `["A1"]`
- `evidence_groups`:
```json
[]
```
- `optional_context`:
```json
[]
```
- `reason_codes`: `["no_mention_of_RAG"]`
- `confidence`: `high`
- `boundary_notes`: The transcript discusses AI agent development, testing and verification methodology, but never mentions RAG (Retrieval-Augmented Generation).
- `required_spans`:

  - None.

### 4. Mechanical Agreement

Mechanical Agreement 只负责发现差异，不代表语义多数票或自动 Gold。

- `label_agreement`: `True`
- `required_aspect_agreement`: `{"details": {"method": "deterministic_token_overlap"}, "score": 0.0, "state": "unresolved"}`
- `supported_aspect_agreement`: `{"details": {}, "score": 1.0, "state": "agree"}`
- `missing_aspect_agreement`: `{"details": {}, "score": 0.0, "state": "disagree"}`
- `evidence_group_agreement`: `{"details": {}, "score": 1.0, "state": "agree"}`
- `required_span_iou`: `{"details": {"optional_context_iou": 1.0, "optional_context_state": "agree", "primary_recall": 1.0, "secondary_recall": 1.0}, "score": 1.0, "state": "agree"}`
- `time_region_agreement`: `{"details": {}, "score": 1.0, "state": "agree"}`
- `source_agreement`: `True`
- `reason_code_agreement`: `{"details": {"boundary_notes_equal": false}, "score": 0.0, "state": "disagree"}`
- `mandatory_human_review_triggers`: `["required_aspect_unresolved", "missing_aspect_disagreement", "boundary_notes_difference", "reason_code_disagreement"]`

### 5. Questions for the Human Adjudicator

1. 完整字幕是否实质讨论了 RAG？
2. 是否批准 `insufficient`？
3. Required Aspect 应采用 Primary 还是 Secondary 的表达？
4. 是否需要保留 Boundary Note？
5. Reason Code 应采用哪一版？
6. 最终应批准 Primary、批准 Secondary、合并修改，还是拒绝双方？

### 6. Simplified Decision Block

Allowed `human_action`: `approve_primary`, `approve_secondary`, `merge_and_revise`, or `reject_both`.
For `merge_and_revise`, add `base_review` (`primary` or `secondary`) and a finite `changes` object. Do not copy a complete Canonical Review. For `reject_both`, provide the reason and do not create Gold.

```json
{"case_id":"V2C_B2P00001","human_action":"","adjudication_reason":""}
```

## Case — V2C_B2P00002

### 1. Case Identity

- `case_id`: `V2C_B2P00002`
- `original_query`: vibe coding
- `evaluation_view`: `single_video_topic_evidence`
- `evidence_question`: 该视频的完整原字幕是否实质讨论了 vibe coding？
- `projection_policy_version`: `v3.5-query-projection-v1`
- `source_video`: `BV1o87764Ebs`
- `source_type`: `raw_subtitle`
- `source_language`: `zh`
- `source_version`: `sha256:087e661d7af23a3bf535f65fdec5f66402ccb781bd5db8698dd5c1ee912a1e5b`
- `timeline_run`: `timeline_087e661d7af23a3b`
- `transcript_segment_count`: `374`
- `transcript_start`: `0.060s`
- `transcript_end`: `866.840s`
- `packet_sha256`: `db7d5e61f49da763a6386c5b64f147db76ab2e280bb6b3f78a37d87cb55d1c8a`
- Complete evidence authority: see **Appendix A — Complete Shared Raw Transcript**.

### 2. Primary Review

- `status`: `sufficient`
- `required_aspects`:
```json
[{"aspect_id":"A1","description":"视频是否实质讨论了 vibe coding。"}]
```
- `supported_aspects`: `["A1"]`
- `missing_aspects`: `[]`
- `evidence_groups`:
```json
[{"alternative_expression_notes":"以 AI/coding agent 参与并自动化代码开发、回归测试和迭代的具体流程，实质性讨论了 vibe coding 相关主题。","group_id":"G1","required_aspect_ids":["A1"],"required_span_ids":["S1"]}]
```
- `optional_context`:
```json
[]
```
- `reason_codes`: `["SUBSTANTIVE_TOPIC_DISCUSSION"]`
- `confidence`: `high`
- `boundary_notes`: 字幕未直接出现“vibe coding”这一术语，但围绕使用 Codex 等 coding agent 进行代码开发、测试和迭代的工作流展开。
- `required_spans`:

  - `span_id`: `S1`
    - `segment_ids`: `["BV1o87764Ebs_seg_000296", "BV1o87764Ebs_seg_000297", "BV1o87764Ebs_seg_000298", "BV1o87764Ebs_seg_000299", "BV1o87764Ebs_seg_000300", "BV1o87764Ebs_seg_000301", "BV1o87764Ebs_seg_000302", "BV1o87764Ebs_seg_000303", "BV1o87764Ebs_seg_000304", "BV1o87764Ebs_seg_000305", "BV1o87764Ebs_seg_000306", "BV1o87764Ebs_seg_000307", "BV1o87764Ebs_seg_000308", "BV1o87764Ebs_seg_000309", "BV1o87764Ebs_seg_000310", "BV1o87764Ebs_seg_000311", "BV1o87764Ebs_seg_000312"]`
    - `start_time`: `665.870s`
    - `end_time`: `717.500s`
    - `raw_text`: 我们可以在codex里面去做这样一件事情就是当他需要开发新的功能的时候它不仅仅考虑这个代码怎么写它需要首先先去设计回归测试其次去设计这样的一个开关然后呢去进行代码的编写编写完之后在开关开启和开关结束的时候同样的去跑一遍这样的一个回归测试通过回归测试的结果进行一个反馈再去修改代码直到最终的代码改成能够符合回归测试要求的这样的一个版本那在整个这样的一套体系里面人是没有参与的而codex这种coding agent通过我们设计的这种可验证体系把这一切都连成了一个闭环
    - `supported_aspects`: `["A1"]`
    - `source_identity`: `{"video_id":"BV1o87764Ebs","source_artifact_id":"raw_subtitle:BV1o87764Ebs:p1","source_version":"sha256:087e661d7af23a3bf535f65fdec5f66402ccb781bd5db8698dd5c1ee912a1e5b","timeline_run_id":"timeline_087e661d7af23a3b","source_language":"zh","source_type":"raw_subtitle"}`

### 3. Secondary Review

- `status`: `insufficient`
- `required_aspects`:
```json
[{"aspect_id":"A1","description":"该视频的完整原字幕实质讨论了vibe coding。"}]
```
- `supported_aspects`: `[]`
- `missing_aspects`: `["A1"]`
- `evidence_groups`:
```json
[]
```
- `optional_context`:
```json
[]
```
- `reason_codes`: `["vibe coding not found in transcript"]`
- `confidence`: `high`
- `boundary_notes`: (empty)
- `required_spans`:

  - None.

### 4. Mechanical Agreement

Mechanical Agreement 只负责发现差异，不代表语义多数票或自动 Gold。

- `label_agreement`: `False`
- `required_aspect_agreement`: `{"details": {"method": "deterministic_token_overlap"}, "score": 0.25, "state": "unresolved"}`
- `supported_aspect_agreement`: `{"details": {}, "score": 0.0, "state": "disagree"}`
- `missing_aspect_agreement`: `{"details": {}, "score": 0.0, "state": "disagree"}`
- `evidence_group_agreement`: `{"details": {}, "score": 0.0, "state": "disagree"}`
- `required_span_iou`: `{"details": {"optional_context_iou": 1.0, "optional_context_state": "agree", "primary_recall": 0.0, "secondary_recall": 1.0}, "score": 0.0, "state": "disagree"}`
- `time_region_agreement`: `{"details": {}, "score": 0.0, "state": "disagree"}`
- `source_agreement`: `False`
- `reason_code_agreement`: `{"details": {"boundary_notes_equal": false}, "score": 0.0, "state": "disagree"}`
- `mandatory_human_review_triggers`: `["label_disagreement", "required_aspect_unresolved", "supported_aspect_disagreement", "missing_aspect_disagreement", "evidence_group_disagreement", "evidence_region_difference", "extreme_label_disagreement", "source_disagreement", "boundary_notes_difference", "reason_code_disagreement"]`

### 5. Questions for the Human Adjudicator

1. 字幕是否实质讨论了 `vibe coding`？
2. 描述 Coding Agent Workflow 是否足以等价为讨论 `vibe coding`？
3. 是否必须明确提及术语或概念边界？
4. Primary 选择的 296–312 段是否构成直接支持？
5. 应判 `sufficient`、`partial` 还是 `insufficient`？
6. 最终应批准 Primary、批准 Secondary、合并修改，还是拒绝双方？

### 6. Simplified Decision Block

Allowed `human_action`: `approve_primary`, `approve_secondary`, `merge_and_revise`, or `reject_both`.
For `merge_and_revise`, add `base_review` (`primary` or `secondary`) and a finite `changes` object. Do not copy a complete Canonical Review. For `reject_both`, provide the reason and do not create Gold.

```json
{"case_id":"V2C_B2P00002","human_action":"","adjudication_reason":""}
```

## Appendix A — Complete Shared Raw Transcript

The two Cases use the same complete 374-Segment Raw Subtitle. The following JSONL preserves every Segment in original order without summarization, deletion, merging, or text correction.

```jsonl
{"segment_id":"BV1o87764Ebs_seg_000001","start_time":0.06,"end_time":0.46,"raw_text":"Hello"}
{"segment_id":"BV1o87764Ebs_seg_000002","start_time":0.46,"end_time":1.06,"raw_text":"大家好啊"}
{"segment_id":"BV1o87764Ebs_seg_000003","start_time":1.06,"end_time":4.54,"raw_text":"我统计了一下我最近做AIA证开发的时间"}
{"segment_id":"BV1o87764Ebs_seg_000004","start_time":4.54,"end_time":7.05,"raw_text":"结果发现了一件不太对劲的事情"}
{"segment_id":"BV1o87764Ebs_seg_000005","start_time":7.05,"end_time":8.75,"raw_text":"我真正花在写代码"}
{"segment_id":"BV1o87764Ebs_seg_000006","start_time":8.75,"end_time":10.79,"raw_text":"做设计上的时间只有10%"}
{"segment_id":"BV1o87764Ebs_seg_000007","start_time":10.79,"end_time":14.41,"raw_text":"剩下的90%全都耗在了同样一件事情上"}
{"segment_id":"BV1o87764Ebs_seg_000008","start_time":14.41,"end_time":15.9,"raw_text":"手动测试啊"}
{"segment_id":"BV1o87764Ebs_seg_000009","start_time":15.9,"end_time":17.06,"raw_text":"我得点开网页"}
{"segment_id":"BV1o87764Ebs_seg_000010","start_time":17.06,"end_time":18.62,"raw_text":"输入想要测的数据集"}
{"segment_id":"BV1o87764Ebs_seg_000011","start_time":18.62,"end_time":20.26,"raw_text":"盯着A卷一步一步的跑"}
{"segment_id":"BV1o87764Ebs_seg_000012","start_time":20.26,"end_time":21.7,"raw_text":"然后用人脑去判断"}
{"segment_id":"BV1o87764Ebs_seg_000013","start_time":21.7,"end_time":23.939,"raw_text":"这一次他到底是变好了还是变坏了"}
{"segment_id":"BV1o87764Ebs_seg_000014","start_time":23.939,"end_time":25.839,"raw_text":"而且这还不是最麻烦的"}
{"segment_id":"BV1o87764Ebs_seg_000015","start_time":25.839,"end_time":27.679,"raw_text":"最麻烦的是AI agent"}
{"segment_id":"BV1o87764Ebs_seg_000016","start_time":27.679,"end_time":29.739,"raw_text":"这个系统本身就不确定是吧"}
{"segment_id":"BV1o87764Ebs_seg_000017","start_time":29.739,"end_time":32.08,"raw_text":"我有的时候只想改一个很小的行为"}
{"segment_id":"BV1o87764Ebs_seg_000018","start_time":32.08,"end_time":33.82,"raw_text":"结果改了一句prompt"}
{"segment_id":"BV1o87764Ebs_seg_000019","start_time":33.82,"end_time":35.23,"raw_text":"他就崩掉了"}
{"segment_id":"BV1o87764Ebs_seg_000020","start_time":35.23,"end_time":36.71,"raw_text":"更让人没底的是"}
{"segment_id":"BV1o87764Ebs_seg_000021","start_time":36.71,"end_time":39.49,"raw_text":"很多时候我连他到底有没有真的坏"}
{"segment_id":"BV1o87764Ebs_seg_000022","start_time":39.49,"end_time":41.23,"raw_text":"都没有办法一眼看出来"}
{"segment_id":"BV1o87764Ebs_seg_000023","start_time":41.23,"end_time":42.43,"raw_text":"那我只能再跑一遍"}
{"segment_id":"BV1o87764Ebs_seg_000024","start_time":42.43,"end_time":44.279,"raw_text":"再跑一遍再跑一遍"}
{"segment_id":"BV1o87764Ebs_seg_000025","start_time":44.279,"end_time":46.849,"raw_text":"然后感觉他到底是不是对的啊"}
{"segment_id":"BV1o87764Ebs_seg_000026","start_time":46.884,"end_time":48.009,"raw_text":"到这一步"}
{"segment_id":"BV1o87764Ebs_seg_000027","start_time":48.009,"end_time":50.489,"raw_text":"我的工作其实已经不是在写代码"}
{"segment_id":"BV1o87764Ebs_seg_000028","start_time":50.489,"end_time":52.609,"raw_text":"而是反复的手动的去验证"}
{"segment_id":"BV1o87764Ebs_seg_000029","start_time":52.609,"end_time":54.98,"raw_text":"一个连我自己都有点快看不懂的系统"}
{"segment_id":"BV1o87764Ebs_seg_000030","start_time":54.98,"end_time":57.8,"raw_text":"这正常吗啊"}
{"segment_id":"BV1o87764Ebs_seg_000031","start_time":57.8,"end_time":61.56,"raw_text":"有没有一种办法能够把这90%的时间"}
{"segment_id":"BV1o87764Ebs_seg_000032","start_time":61.56,"end_time":63.08,"raw_text":"变成一套可重复"}
{"segment_id":"BV1o87764Ebs_seg_000033","start_time":63.08,"end_time":67.12,"raw_text":"不需要我守在屏幕前一遍一遍点的自动化体系"}
{"segment_id":"BV1o87764Ebs_seg_000034","start_time":67.21,"end_time":69.11,"raw_text":"那今天我们就来聊一聊"}
{"segment_id":"BV1o87764Ebs_seg_000035","start_time":69.11,"end_time":72.07,"raw_text":"到底是如何让AI agent的开发"}
{"segment_id":"BV1o87764Ebs_seg_000036","start_time":72.07,"end_time":74.38,"raw_text":"省去这90%的时间的"}
{"segment_id":"BV1o87764Ebs_seg_000037","start_time":74.38,"end_time":77.0,"raw_text":"欢迎大家收看我们今天新一期的视频"}
{"segment_id":"BV1o87764Ebs_seg_000038","start_time":77.0,"end_time":79.0,"raw_text":"那在聊我们怎么改进它之前"}
{"segment_id":"BV1o87764Ebs_seg_000039","start_time":79.0,"end_time":80.88,"raw_text":"其实我首先确认了一件事情啊"}
{"segment_id":"BV1o87764Ebs_seg_000040","start_time":80.88,"end_time":82.4,"raw_text":"这到底是不是我一个人的痛点"}
{"segment_id":"BV1o87764Ebs_seg_000041","start_time":82.4,"end_time":84.47,"raw_text":"是不是我一个人碰到的问题啊"}
{"segment_id":"BV1o87764Ebs_seg_000042","start_time":84.47,"end_time":85.31,"raw_text":"其实不是啊"}
{"segment_id":"BV1o87764Ebs_seg_000043","start_time":85.31,"end_time":86.63,"raw_text":"在2025年"}
{"segment_id":"BV1o87764Ebs_seg_000044","start_time":86.63,"end_time":90.55,"raw_text":"open i meta的研究员JASONWEI就提出了一个概念啊"}
{"segment_id":"BV1o87764Ebs_seg_000045","start_time":90.55,"end_time":93.53,"raw_text":"他观察到一件事情叫做验证的不对称性"}
{"segment_id":"BV1o87764Ebs_seg_000046","start_time":93.53,"end_time":96.03,"raw_text":"意思是有很多任务做出来很难"}
{"segment_id":"BV1o87764Ebs_seg_000047","start_time":96.03,"end_time":97.39,"raw_text":"但是验证他做的对不对"}
{"segment_id":"BV1o87764Ebs_seg_000048","start_time":97.39,"end_time":98.31,"raw_text":"却很容易"}
{"segment_id":"BV1o87764Ebs_seg_000049","start_time":98.31,"end_time":102.07,"raw_text":"那顺着这个他给出了一条定律叫做very fires law啊"}
{"segment_id":"BV1o87764Ebs_seg_000050","start_time":102.07,"end_time":106.77,"raw_text":"就是任何可解且易于验证的任务终将被AI解决"}
{"segment_id":"BV1o87764Ebs_seg_000051","start_time":106.77,"end_time":109.77,"raw_text":"那这件事情跟我的那个90%"}
{"segment_id":"BV1o87764Ebs_seg_000052","start_time":109.77,"end_time":111.529,"raw_text":"到底有什么关系啊"}
{"segment_id":"BV1o87764Ebs_seg_000053","start_time":111.529,"end_time":114.049,"raw_text":"我之所以90%的时间在验证"}
{"segment_id":"BV1o87764Ebs_seg_000054","start_time":114.049,"end_time":117.109,"raw_text":"恰恰就是因为对于我们所构建的这个AI"}
{"segment_id":"BV1o87764Ebs_seg_000055","start_time":117.109,"end_time":118.02,"raw_text":"A证来说"}
{"segment_id":"BV1o87764Ebs_seg_000056","start_time":118.02,"end_time":119.58,"raw_text":"生成变得很便宜"}
{"segment_id":"BV1o87764Ebs_seg_000057","start_time":119.58,"end_time":121.26,"raw_text":"但是验证还很贵"}
{"segment_id":"BV1o87764Ebs_seg_000058","start_time":121.26,"end_time":122.86,"raw_text":"这就是那个不对称"}
{"segment_id":"BV1o87764Ebs_seg_000059","start_time":122.86,"end_time":127.52,"raw_text":"也就是说如果我能把判断这个agent做的对不对"}
{"segment_id":"BV1o87764Ebs_seg_000060","start_time":127.52,"end_time":129.4,"raw_text":"这件事情从一个靠肉眼"}
{"segment_id":"BV1o87764Ebs_seg_000061","start_time":129.4,"end_time":130.4,"raw_text":"靠感觉的难题"}
{"segment_id":"BV1o87764Ebs_seg_000062","start_time":130.4,"end_time":132.64,"raw_text":"变成一道自动的可重复的验证体系"}
{"segment_id":"BV1o87764Ebs_seg_000063","start_time":132.64,"end_time":135.3,"raw_text":"那我其实就是把一个难验证的问题"}
{"segment_id":"BV1o87764Ebs_seg_000064","start_time":135.3,"end_time":137.6,"raw_text":"亲手改造成一个容易验证的问题"}
{"segment_id":"BV1o87764Ebs_seg_000065","start_time":137.6,"end_time":139.06,"raw_text":"一旦它变得容易验证"}
{"segment_id":"BV1o87764Ebs_seg_000066","start_time":139.06,"end_time":140.08,"raw_text":"按照这条定律"}
{"segment_id":"BV1o87764Ebs_seg_000067","start_time":140.08,"end_time":141.87,"raw_text":"剩下的就应该交给AI了"}
{"segment_id":"BV1o87764Ebs_seg_000068","start_time":141.87,"end_time":143.89,"raw_text":"那我的角色就变成了"}
{"segment_id":"BV1o87764Ebs_seg_000069","start_time":143.89,"end_time":147.26,"raw_text":"如何去制造这个可验证的架构"}
{"segment_id":"BV1o87764Ebs_seg_000070","start_time":147.26,"end_time":149.54,"raw_text":"这个话听起来其实很抽象啊"}
{"segment_id":"BV1o87764Ebs_seg_000071","start_time":149.54,"end_time":151.08,"raw_text":"但其实在另外一个行业"}
{"segment_id":"BV1o87764Ebs_seg_000072","start_time":151.08,"end_time":153.88,"raw_text":"30年前就做过同样的事情"}
{"segment_id":"BV1o87764Ebs_seg_000073","start_time":153.88,"end_time":157.54,"raw_text":"而这个行业就是我现在正在从事的行业"}
{"segment_id":"BV1o87764Ebs_seg_000074","start_time":157.54,"end_time":159.38,"raw_text":"芯片的设计与验证"}
{"segment_id":"BV1o87764Ebs_seg_000075","start_time":159.38,"end_time":163.25,"raw_text":"我先讲一个你可能没有想到过的冷知识"}
{"segment_id":"BV1o87764Ebs_seg_000076","start_time":163.25,"end_time":167.65,"raw_text":"写芯片代码的人往往比验证芯片代码的人要少"}
{"segment_id":"BV1o87764Ebs_seg_000077","start_time":167.65,"end_time":169.77,"raw_text":"在芯片真正流片之前"}
{"segment_id":"BV1o87764Ebs_seg_000078","start_time":169.77,"end_time":172.31,"raw_text":"花在验证上的人力啊"}
{"segment_id":"BV1o87764Ebs_seg_000079","start_time":172.31,"end_time":175.76,"raw_text":"经常是设计的两倍三倍或者更多"}
{"segment_id":"BV1o87764Ebs_seg_000080","start_time":175.76,"end_time":177.0,"raw_text":"为什么会这样"}
{"segment_id":"BV1o87764Ebs_seg_000081","start_time":177.0,"end_time":179.3,"raw_text":"因为芯片一旦流片啊"}
{"segment_id":"BV1o87764Ebs_seg_000082","start_time":179.3,"end_time":180.14,"raw_text":"如果出错"}
{"segment_id":"BV1o87764Ebs_seg_000083","start_time":180.14,"end_time":182.69,"raw_text":"那就是几百万美金直接打水漂啊"}
{"segment_id":"BV1o87764Ebs_seg_000084","start_time":182.69,"end_time":183.81,"raw_text":"没有改一个bug"}
{"segment_id":"BV1o87764Ebs_seg_000085","start_time":183.81,"end_time":185.61,"raw_text":"重新部署一下这种好事啊"}
{"segment_id":"BV1o87764Ebs_seg_000086","start_time":185.61,"end_time":188.45,"raw_text":"所以整个行业被现实倒逼着"}
{"segment_id":"BV1o87764Ebs_seg_000087","start_time":188.45,"end_time":191.53,"raw_text":"把大部分的精力压在了同样一件事情上"}
{"segment_id":"BV1o87764Ebs_seg_000088","start_time":191.53,"end_time":192.97,"raw_text":"就是想尽一切办法"}
{"segment_id":"BV1o87764Ebs_seg_000089","start_time":192.97,"end_time":195.13,"raw_text":"把所有可能的bug全部都找出来"}
{"segment_id":"BV1o87764Ebs_seg_000090","start_time":195.13,"end_time":197.17,"raw_text":"而干这件事情的核心"}
{"segment_id":"BV1o87764Ebs_seg_000091","start_time":197.17,"end_time":199.79,"raw_text":"其实不是说你会写芯片代码就行了啊"}
{"segment_id":"BV1o87764Ebs_seg_000092","start_time":199.79,"end_time":202.71,"raw_text":"你是要去会设计验证的体系"}
{"segment_id":"BV1o87764Ebs_seg_000093","start_time":202.71,"end_time":205.51,"raw_text":"你怎么样去设计一套回归测试啊"}
{"segment_id":"BV1o87764Ebs_seg_000094","start_time":205.51,"end_time":207.06,"raw_text":"主动把bug暴露出来"}
{"segment_id":"BV1o87764Ebs_seg_000095","start_time":207.06,"end_time":209.0,"raw_text":"在哪些地方埋下检查点"}
{"segment_id":"BV1o87764Ebs_seg_000096","start_time":209.0,"end_time":212.29,"raw_text":"又怎么样去衡量自己到底测的够不够全"}
{"segment_id":"BV1o87764Ebs_seg_000097","start_time":212.29,"end_time":213.17,"raw_text":"讲到这"}
{"segment_id":"BV1o87764Ebs_seg_000098","start_time":213.17,"end_time":214.49,"raw_text":"你大概已经发现"}
{"segment_id":"BV1o87764Ebs_seg_000099","start_time":214.49,"end_time":216.69,"raw_text":"这跟我们今天做AIA证的开发"}
{"segment_id":"BV1o87764Ebs_seg_000100","start_time":216.69,"end_time":218.32,"raw_text":"几乎是同样一个形状"}
{"segment_id":"BV1o87764Ebs_seg_000101","start_time":218.32,"end_time":220.92,"raw_text":"当AI把写代码变得越来越便宜"}
{"segment_id":"BV1o87764Ebs_seg_000102","start_time":220.92,"end_time":222.9,"raw_text":"就像当年的EDA工具"}
{"segment_id":"BV1o87764Ebs_seg_000103","start_time":222.9,"end_time":225.529,"raw_text":"让写VLOG这件事情变容易了一样"}
{"segment_id":"BV1o87764Ebs_seg_000104","start_time":225.529,"end_time":228.129,"raw_text":"你的价值就不仅仅在设计上面了"}
{"segment_id":"BV1o87764Ebs_seg_000105","start_time":228.129,"end_time":229.97,"raw_text":"它出现了一套新的价值点"}
{"segment_id":"BV1o87764Ebs_seg_000106","start_time":229.97,"end_time":232.51,"raw_text":"你能不能设计出来一套体系"}
{"segment_id":"BV1o87764Ebs_seg_000107","start_time":232.51,"end_time":236.459,"raw_text":"让AI的每一次改动都可以被验证"}
{"segment_id":"BV1o87764Ebs_seg_000108","start_time":236.459,"end_time":239.739,"raw_text":"那么我具体是怎么基于我们自己的AI agent"}
{"segment_id":"BV1o87764Ebs_seg_000109","start_time":239.739,"end_time":241.43,"raw_text":"把这件事情做出来的呢"}
{"segment_id":"BV1o87764Ebs_seg_000110","start_time":241.43,"end_time":244.01,"raw_text":"第一步可能跟你想的有点不太一样啊"}
{"segment_id":"BV1o87764Ebs_seg_000111","start_time":244.01,"end_time":246.579,"raw_text":"我要做的第一件事不是写测试"}
{"segment_id":"BV1o87764Ebs_seg_000112","start_time":246.579,"end_time":250.179,"raw_text":"而是把我们的AI agent改造成一个"}
{"segment_id":"BV1o87764Ebs_seg_000113","start_time":250.179,"end_time":252.94,"raw_text":"对别的AI agent友好的系统"}
{"segment_id":"BV1o87764Ebs_seg_000114","start_time":252.94,"end_time":254.16,"raw_text":"我解释一下"}
{"segment_id":"BV1o87764Ebs_seg_000115","start_time":254.16,"end_time":256.04,"raw_text":"我手上其实有两套系统"}
{"segment_id":"BV1o87764Ebs_seg_000116","start_time":256.04,"end_time":258.71,"raw_text":"一个是我们自己写的那个AI agent"}
{"segment_id":"BV1o87764Ebs_seg_000117","start_time":258.71,"end_time":262.33,"raw_text":"另一套呢是我用来写代码的coding工具"}
{"segment_id":"BV1o87764Ebs_seg_000118","start_time":262.33,"end_time":264.11,"raw_text":"比如说codex啊"}
{"segment_id":"BV1o87764Ebs_seg_000119","start_time":264.11,"end_time":267.39,"raw_text":"那我之前测试为什么那么痛苦"}
{"segment_id":"BV1o87764Ebs_seg_000120","start_time":267.39,"end_time":270.09,"raw_text":"因为我那套系统的入口是一个网页"}
{"segment_id":"BV1o87764Ebs_seg_000121","start_time":270.09,"end_time":270.97,"raw_text":"是一个UI"}
{"segment_id":"BV1o87764Ebs_seg_000122","start_time":270.97,"end_time":272.16,"raw_text":"是给人用的"}
{"segment_id":"BV1o87764Ebs_seg_000123","start_time":272.16,"end_time":276.38,"raw_text":"要测它就得有个人在那点一下梳一下是吧"}
{"segment_id":"BV1o87764Ebs_seg_000124","start_time":276.38,"end_time":277.52,"raw_text":"那从第一天起"}
{"segment_id":"BV1o87764Ebs_seg_000125","start_time":277.52,"end_time":280.69,"raw_text":"他就是为人的眼睛和手去设计的"}
{"segment_id":"BV1o87764Ebs_seg_000126","start_time":280.69,"end_time":284.21,"raw_text":"现在大家都在讲面向AIA证的开发"}
{"segment_id":"BV1o87764Ebs_seg_000127","start_time":284.21,"end_time":287.89,"raw_text":"这件事情的真正核心在于三个问题啊"}
{"segment_id":"BV1o87764Ebs_seg_000128","start_time":287.89,"end_time":292.149,"raw_text":"第一你的系统在脱离了人的眼睛和UI之后"}
{"segment_id":"BV1o87764Ebs_seg_000129","start_time":292.149,"end_time":293.72,"raw_text":"他还能跑得起来吗"}
{"segment_id":"BV1o87764Ebs_seg_000130","start_time":293.72,"end_time":295.88,"raw_text":"第二它运行的过程中"}
{"segment_id":"BV1o87764Ebs_seg_000131","start_time":295.88,"end_time":299.04,"raw_text":"那些中间状态有没有留下足够的信息"}
{"segment_id":"BV1o87764Ebs_seg_000132","start_time":299.04,"end_time":301.12,"raw_text":"让另外一个AIA证能看懂"}
{"segment_id":"BV1o87764Ebs_seg_000133","start_time":301.12,"end_time":304.07,"raw_text":"第三你有没有专门设计接口"}
{"segment_id":"BV1o87764Ebs_seg_000134","start_time":304.07,"end_time":307.03,"raw_text":"让AI能够自主的去拿到这些信息"}
{"segment_id":"BV1o87764Ebs_seg_000135","start_time":307.03,"end_time":309.09,"raw_text":"举一个具体的例子啊"}
{"segment_id":"BV1o87764Ebs_seg_000136","start_time":309.09,"end_time":311.25,"raw_text":"我们在运行一个AI agent的时候"}
{"segment_id":"BV1o87764Ebs_seg_000137","start_time":311.25,"end_time":315.29,"raw_text":"我需要让codex能够看到整条workflow长什么样"}
{"segment_id":"BV1o87764Ebs_seg_000138","start_time":315.29,"end_time":317.33,"raw_text":"中间调用了哪些工具"}
{"segment_id":"BV1o87764Ebs_seg_000139","start_time":317.33,"end_time":319.27,"raw_text":"每一步拿回了什么数据"}
{"segment_id":"BV1o87764Ebs_seg_000140","start_time":319.27,"end_time":322.51,"raw_text":"如果这些信息一旦离开UI就消失"}
{"segment_id":"BV1o87764Ebs_seg_000141","start_time":322.51,"end_time":325.29,"raw_text":"或者说整个workflow离开UI"}
{"segment_id":"BV1o87764Ebs_seg_000142","start_time":325.29,"end_time":326.289,"raw_text":"它就停止"}
{"segment_id":"BV1o87764Ebs_seg_000143","start_time":326.289,"end_time":327.57,"raw_text":"后端就瘫了"}
{"segment_id":"BV1o87764Ebs_seg_000144","start_time":327.57,"end_time":330.77,"raw_text":"那只能说明我们这一方设计的接口"}
{"segment_id":"BV1o87764Ebs_seg_000145","start_time":330.77,"end_time":333.75,"raw_text":"到现在为止还是为人去设计的"}
{"segment_id":"BV1o87764Ebs_seg_000146","start_time":333.75,"end_time":337.44,"raw_text":"不是为了AI去设计的啊"}
{"segment_id":"BV1o87764Ebs_seg_000147","start_time":337.44,"end_time":338.66,"raw_text":"那么怎么改啊"}
{"segment_id":"BV1o87764Ebs_seg_000148","start_time":338.66,"end_time":340.71,"raw_text":"其实有两条比较现成的路"}
{"segment_id":"BV1o87764Ebs_seg_000149","start_time":340.71,"end_time":343.51,"raw_text":"一条呢就是说啊那我们调用MCP是吧"}
{"segment_id":"BV1o87764Ebs_seg_000150","start_time":343.51,"end_time":344.57,"raw_text":"模拟网页的操作"}
{"segment_id":"BV1o87764Ebs_seg_000151","start_time":344.57,"end_time":345.87,"raw_text":"模拟人的操作"}
{"segment_id":"BV1o87764Ebs_seg_000152","start_time":345.87,"end_time":348.2,"raw_text":"让AI agent的直接去独立的网页"}
{"segment_id":"BV1o87764Ebs_seg_000153","start_time":348.2,"end_time":350.78,"raw_text":"靠多模态去进行一个观察"}
{"segment_id":"BV1o87764Ebs_seg_000154","start_time":350.78,"end_time":354.3,"raw_text":"那另一条呢就是把前后端彻底拆开啊"}
{"segment_id":"BV1o87764Ebs_seg_000155","start_time":354.3,"end_time":357.17,"raw_text":"后端变成一个能独立运行的AIA卷"}
{"segment_id":"BV1o87764Ebs_seg_000156","start_time":357.17,"end_time":359.99,"raw_text":"所有的调用都能做成命令行的控制形式"}
{"segment_id":"BV1o87764Ebs_seg_000157","start_time":359.99,"end_time":361.81,"raw_text":"看前端呢退到一边"}
{"segment_id":"BV1o87764Ebs_seg_000158","start_time":361.81,"end_time":365.12,"raw_text":"只负责把后端的信息这个监控出来"}
{"segment_id":"BV1o87764Ebs_seg_000159","start_time":365.12,"end_time":366.16,"raw_text":"给人们去看啊"}
{"segment_id":"BV1o87764Ebs_seg_000160","start_time":366.16,"end_time":367.48,"raw_text":"让人进行操作"}
{"segment_id":"BV1o87764Ebs_seg_000161","start_time":367.48,"end_time":369.82,"raw_text":"我选的其实就是第二条路啊"}
{"segment_id":"BV1o87764Ebs_seg_000162","start_time":369.82,"end_time":371.22,"raw_text":"前后段分离啊"}
{"segment_id":"BV1o87764Ebs_seg_000163","start_time":371.22,"end_time":373.58,"raw_text":"原因是在于我用MCP"}
{"segment_id":"BV1o87764Ebs_seg_000164","start_time":373.58,"end_time":376.34,"raw_text":"我的确能够看到网页上面的一些操作"}
{"segment_id":"BV1o87764Ebs_seg_000165","start_time":376.34,"end_time":378.75,"raw_text":"但是呢在这个authorization呐"}
{"segment_id":"BV1o87764Ebs_seg_000166","start_time":378.75,"end_time":380.67,"raw_text":"或者在一些具体的corner case"}
{"segment_id":"BV1o87764Ebs_seg_000167","start_time":380.67,"end_time":382.05,"raw_text":"包括效率上面啊"}
{"segment_id":"BV1o87764Ebs_seg_000168","start_time":382.05,"end_time":385.35,"raw_text":"没有前后端分离来的这么直接来的这么快"}
{"segment_id":"BV1o87764Ebs_seg_000169","start_time":385.35,"end_time":386.69,"raw_text":"而且说实话啊"}
{"segment_id":"BV1o87764Ebs_seg_000170","start_time":386.69,"end_time":388.87,"raw_text":"就是做前后端这一步啊"}
{"segment_id":"BV1o87764Ebs_seg_000171","start_time":388.87,"end_time":390.72,"raw_text":"我们也花了不少力气啊"}
{"segment_id":"BV1o87764Ebs_seg_000172","start_time":390.72,"end_time":391.24,"raw_text":"原因在于"}
{"segment_id":"BV1o87764Ebs_seg_000173","start_time":391.24,"end_time":394.3,"raw_text":"我们之前其实是重度使用了这个VERCEL的"}
{"segment_id":"BV1o87764Ebs_seg_000174","start_time":394.3,"end_time":395.69,"raw_text":"A i s d k"}
{"segment_id":"BV1o87764Ebs_seg_000175","start_time":395.69,"end_time":398.39,"raw_text":"他在最开始用的时候的确很好用"}
{"segment_id":"BV1o87764Ebs_seg_000176","start_time":398.39,"end_time":400.85,"raw_text":"但是在前后端分离这件事情上"}
{"segment_id":"BV1o87764Ebs_seg_000177","start_time":400.85,"end_time":402.53,"raw_text":"你的确是需要花一些功夫"}
{"segment_id":"BV1o87764Ebs_seg_000178","start_time":402.53,"end_time":404.869,"raw_text":"才能把它做到一个比较好的程度啊"}
{"segment_id":"BV1o87764Ebs_seg_000179","start_time":404.869,"end_time":406.829,"raw_text":"我们把它变成了一个能脱离前端"}
{"segment_id":"BV1o87764Ebs_seg_000180","start_time":406.829,"end_time":409.789,"raw_text":"然后自己在后台长时间稳定跑下去的"}
{"segment_id":"BV1o87764Ebs_seg_000181","start_time":409.789,"end_time":411.18,"raw_text":"这样的一个系统是吧"}
{"segment_id":"BV1o87764Ebs_seg_000182","start_time":411.18,"end_time":412.54,"raw_text":"而做完这一步"}
{"segment_id":"BV1o87764Ebs_seg_000183","start_time":412.54,"end_time":414.22,"raw_text":"我们再回过头去看是吧"}
{"segment_id":"BV1o87764Ebs_seg_000184","start_time":414.22,"end_time":417.03,"raw_text":"有没有人跟我们踩了一样的坑呢"}
{"segment_id":"BV1o87764Ebs_seg_000185","start_time":417.03,"end_time":419.79,"raw_text":"普林斯顿的这个s we agent"}
{"segment_id":"BV1o87764Ebs_seg_000186","start_time":419.79,"end_time":421.99,"raw_text":"那篇论文里面提到过一个概念"}
{"segment_id":"BV1o87764Ebs_seg_000187","start_time":421.99,"end_time":425.25,"raw_text":"叫做agent computer interface a aci啊"}
{"segment_id":"BV1o87764Ebs_seg_000188","start_time":425.25,"end_time":428.91,"raw_text":"他们的观点就是说AI agent是一类全新的用户"}
{"segment_id":"BV1o87764Ebs_seg_000189","start_time":428.91,"end_time":429.89,"raw_text":"他和人不一样"}
{"segment_id":"BV1o87764Ebs_seg_000190","start_time":429.89,"end_time":431.73,"raw_text":"所以你得专门给他设计接口"}
{"segment_id":"BV1o87764Ebs_seg_000191","start_time":431.73,"end_time":436.059,"raw_text":"而且呃这个实验的结果发现接口设计的好不好"}
{"segment_id":"BV1o87764Ebs_seg_000192","start_time":436.059,"end_time":438.079,"raw_text":"对于agent的表现影响"}
{"segment_id":"BV1o87764Ebs_seg_000193","start_time":438.079,"end_time":440.539,"raw_text":"甚至大过你换一个更强的模型"}
{"segment_id":"BV1o87764Ebs_seg_000194","start_time":440.539,"end_time":442.939,"raw_text":"所以我们每天听到啊"}
{"segment_id":"BV1o87764Ebs_seg_000195","start_time":442.939,"end_time":444.019,"raw_text":"面向AIA证的编程"}
{"segment_id":"BV1o87764Ebs_seg_000196","start_time":444.019,"end_time":445.239,"raw_text":"面向AIA证的服务"}
{"segment_id":"BV1o87764Ebs_seg_000197","start_time":445.239,"end_time":448.32,"raw_text":"它的核心从来不是某一个具体的技术"}
{"segment_id":"BV1o87764Ebs_seg_000198","start_time":448.32,"end_time":451.88,"raw_text":"其实是在于你所做的这样的一个东西"}
{"segment_id":"BV1o87764Ebs_seg_000199","start_time":451.88,"end_time":455.6,"raw_text":"能不能被另外一个AI或者说是简单一点"}
{"segment_id":"BV1o87764Ebs_seg_000200","start_time":455.6,"end_time":457.2,"raw_text":"能不能够被codex"}
{"segment_id":"BV1o87764Ebs_seg_000201","start_time":457.2,"end_time":461.18,"raw_text":"快速的主动地拿到他需要的信息"}
{"segment_id":"BV1o87764Ebs_seg_000202","start_time":461.18,"end_time":463.94,"raw_text":"做完了前面那部接下来就很直接了"}
{"segment_id":"BV1o87764Ebs_seg_000203","start_time":463.94,"end_time":465.86,"raw_text":"我们要开始构建测试"}
{"segment_id":"BV1o87764Ebs_seg_000204","start_time":465.86,"end_time":468.38,"raw_text":"说穿了它就是一个回归测试啊"}
{"segment_id":"BV1o87764Ebs_seg_000205","start_time":468.38,"end_time":470.54,"raw_text":"regression test概念不复杂"}
{"segment_id":"BV1o87764Ebs_seg_000206","start_time":470.54,"end_time":471.66,"raw_text":"复杂的是"}
{"segment_id":"BV1o87764Ebs_seg_000207","start_time":471.66,"end_time":475.65,"raw_text":"怎么样为一个不确定的系统去构建它啊"}
{"segment_id":"BV1o87764Ebs_seg_000208","start_time":475.65,"end_time":479.56,"raw_text":"在这个地方我就拿我们给AIASION加功能来举例"}
{"segment_id":"BV1o87764Ebs_seg_000209","start_time":479.56,"end_time":482.64,"raw_text":"当我想要给AI agent新加一个工具的时候"}
{"segment_id":"BV1o87764Ebs_seg_000210","start_time":482.64,"end_time":484.9,"raw_text":"我心里其实是有一个明确的预期的"}
{"segment_id":"BV1o87764Ebs_seg_000211","start_time":484.9,"end_time":487.0,"raw_text":"比如说在什么条件下啊"}
{"segment_id":"BV1o87764Ebs_seg_000212","start_time":487.0,"end_time":488.37,"raw_text":"这个工具会被触发"}
{"segment_id":"BV1o87764Ebs_seg_000213","start_time":488.37,"end_time":489.49,"raw_text":"触发之后啊"}
{"segment_id":"BV1o87764Ebs_seg_000214","start_time":489.49,"end_time":492.84,"raw_text":"整个AI的工作流我又应该怎么走啊"}
{"segment_id":"BV1o87764Ebs_seg_000215","start_time":492.84,"end_time":495.14,"raw_text":"那这个我期待他怎么走的路径"}
{"segment_id":"BV1o87764Ebs_seg_000216","start_time":495.14,"end_time":497.06,"raw_text":"我们把它叫做快乐路线啊"}
{"segment_id":"BV1o87764Ebs_seg_000217","start_time":497.06,"end_time":501.46,"raw_text":"happy path它就是一个新功能的验收标准"}
{"segment_id":"BV1o87764Ebs_seg_000218","start_time":501.46,"end_time":502.78,"raw_text":"从架构上来说"}
{"segment_id":"BV1o87764Ebs_seg_000219","start_time":502.78,"end_time":505.18,"raw_text":"我们要先解决一个棘手的问题"}
{"segment_id":"BV1o87764Ebs_seg_000220","start_time":505.18,"end_time":506.69,"raw_text":"谁来当裁判"}
{"segment_id":"BV1o87764Ebs_seg_000221","start_time":506.69,"end_time":509.57,"raw_text":"A阵的输出是一大段自然语言啊"}
{"segment_id":"BV1o87764Ebs_seg_000222","start_time":509.57,"end_time":510.87,"raw_text":"是一条运行的路径"}
{"segment_id":"BV1o87764Ebs_seg_000223","start_time":510.87,"end_time":512.89,"raw_text":"它不是一个直接相减的数字"}
{"segment_id":"BV1o87764Ebs_seg_000224","start_time":512.89,"end_time":516.06,"raw_text":"所以传统那种过或者不过啊"}
{"segment_id":"BV1o87764Ebs_seg_000225","start_time":516.06,"end_time":518.38,"raw_text":"这种分类的系统其实是不够用的"}
{"segment_id":"BV1o87764Ebs_seg_000226","start_time":518.38,"end_time":519.54,"raw_text":"我的办法是啊"}
{"segment_id":"BV1o87764Ebs_seg_000227","start_time":519.54,"end_time":522.25,"raw_text":"把这个裁判呢拆成两层"}
{"segment_id":"BV1o87764Ebs_seg_000228","start_time":522.25,"end_time":525.03,"raw_text":"能确定的交给确定性的裁判啊"}
{"segment_id":"BV1o87764Ebs_seg_000229","start_time":525.03,"end_time":527.35,"raw_text":"那些模糊的交给AI裁判"}
{"segment_id":"BV1o87764Ebs_seg_000230","start_time":527.35,"end_time":530.19,"raw_text":"那这个第一层就是确定性的断言"}
{"segment_id":"BV1o87764Ebs_seg_000231","start_time":530.19,"end_time":531.11,"raw_text":"Assertion"}
{"segment_id":"BV1o87764Ebs_seg_000232","start_time":531.11,"end_time":533.63,"raw_text":"这一层其实就是一组硬性的检查"}
{"segment_id":"BV1o87764Ebs_seg_000233","start_time":533.63,"end_time":535.65,"raw_text":"比如说跑这个测试的时候"}
{"segment_id":"BV1o87764Ebs_seg_000234","start_time":535.65,"end_time":537.15,"raw_text":"工具是否触发呀"}
{"segment_id":"BV1o87764Ebs_seg_000235","start_time":537.15,"end_time":538.69,"raw_text":"跑到某一步的时候"}
{"segment_id":"BV1o87764Ebs_seg_000236","start_time":538.69,"end_time":540.87,"raw_text":"这个中间状态啊有多少条记录呀"}
{"segment_id":"BV1o87764Ebs_seg_000237","start_time":540.87,"end_time":542.4,"raw_text":"覆盖到哪些情况呀"}
{"segment_id":"BV1o87764Ebs_seg_000238","start_time":542.4,"end_time":544.96,"raw_text":"这层的特点就是它绝对可靠啊"}
{"segment_id":"BV1o87764Ebs_seg_000239","start_time":544.96,"end_time":547.27,"raw_text":"然后确定性并且零成本"}
{"segment_id":"BV1o87764Ebs_seg_000240","start_time":547.27,"end_time":550.31,"raw_text":"第二层呢就是一个LLM的裁判啊"}
{"segment_id":"BV1o87764Ebs_seg_000241","start_time":550.31,"end_time":551.57,"raw_text":"我把它叫做supervisor"}
{"segment_id":"BV1o87764Ebs_seg_000242","start_time":551.57,"end_time":555.829,"raw_text":"他是专门处理第一层那些卡不住模糊的部分"}
{"segment_id":"BV1o87764Ebs_seg_000243","start_time":555.829,"end_time":557.749,"raw_text":"那这方有几个关键细节啊"}
{"segment_id":"BV1o87764Ebs_seg_000244","start_time":557.749,"end_time":561.029,"raw_text":"这个大圆模型的上下文必须是干净的啊"}
{"segment_id":"BV1o87764Ebs_seg_000245","start_time":561.029,"end_time":562.109,"raw_text":"他不参与任何的开发"}
{"segment_id":"BV1o87764Ebs_seg_000246","start_time":562.109,"end_time":563.829,"raw_text":"他不知道你代码的来龙去脉"}
{"segment_id":"BV1o87764Ebs_seg_000247","start_time":563.829,"end_time":567.989,"raw_text":"他的这个眼睛里面只有对正确的预期啊"}
{"segment_id":"BV1o87764Ebs_seg_000248","start_time":567.989,"end_time":569.29,"raw_text":"而第二点呢"}
{"segment_id":"BV1o87764Ebs_seg_000249","start_time":569.29,"end_time":573.03,"raw_text":"然后面对那些没有标准答案的输出"}
{"segment_id":"BV1o87764Ebs_seg_000250","start_time":573.03,"end_time":575.11,"raw_text":"我们不让他去判断对和错"}
{"segment_id":"BV1o87764Ebs_seg_000251","start_time":575.11,"end_time":577.33,"raw_text":"而是让他去做一个量化的打分"}
{"segment_id":"BV1o87764Ebs_seg_000252","start_time":577.33,"end_time":581.05,"raw_text":"通过分数去判断最终的结果是好了多少"}
{"segment_id":"BV1o87764Ebs_seg_000253","start_time":581.05,"end_time":581.849,"raw_text":"差了多少"}
{"segment_id":"BV1o87764Ebs_seg_000254","start_time":581.849,"end_time":584.549,"raw_text":"那如果你做过芯片的验证"}
{"segment_id":"BV1o87764Ebs_seg_000255","start_time":584.549,"end_time":587.16,"raw_text":"其实你觉得整套系统还是比较眼熟的"}
{"segment_id":"BV1o87764Ebs_seg_000256","start_time":587.16,"end_time":589.68,"raw_text":"比如说啊我们借用了这个assertion的概念"}
{"segment_id":"BV1o87764Ebs_seg_000257","start_time":589.68,"end_time":591.04,"raw_text":"借用了coverage的概念啊"}
{"segment_id":"BV1o87764Ebs_seg_000258","start_time":591.04,"end_time":592.6,"raw_text":"借用了school board的概念"}
{"segment_id":"BV1o87764Ebs_seg_000259","start_time":592.6,"end_time":594.89,"raw_text":"只不过相比于硬件来说"}
{"segment_id":"BV1o87764Ebs_seg_000260","start_time":594.89,"end_time":598.27,"raw_text":"这个AI agent它本身就存在一定的模糊地带"}
{"segment_id":"BV1o87764Ebs_seg_000261","start_time":598.27,"end_time":599.71,"raw_text":"存在一定的不确定性啊"}
{"segment_id":"BV1o87764Ebs_seg_000262","start_time":599.71,"end_time":601.519,"raw_text":"所以他对于这种不确定性的"}
{"segment_id":"BV1o87764Ebs_seg_000263","start_time":601.519,"end_time":602.95,"raw_text":"容忍程度要更高一点"}
{"segment_id":"BV1o87764Ebs_seg_000264","start_time":602.95,"end_time":606.19,"raw_text":"那解决了谁来当裁判的问题之后呢"}
{"segment_id":"BV1o87764Ebs_seg_000265","start_time":606.19,"end_time":609.64,"raw_text":"第二步啊就是不停的攒案例"}
{"segment_id":"BV1o87764Ebs_seg_000266","start_time":609.64,"end_time":610.4,"raw_text":"上面"}
{"segment_id":"BV1o87764Ebs_seg_000267","start_time":610.4,"end_time":611.36,"raw_text":"我们做的事情"}
{"segment_id":"BV1o87764Ebs_seg_000268","start_time":611.36,"end_time":614.61,"raw_text":"是基于这个happy path的快乐路径进行的开发"}
{"segment_id":"BV1o87764Ebs_seg_000269","start_time":614.61,"end_time":616.53,"raw_text":"那我开发的功能越多是吧"}
{"segment_id":"BV1o87764Ebs_seg_000270","start_time":616.53,"end_time":618.69,"raw_text":"我就慢慢慢慢把这些happy path能够"}
{"segment_id":"BV1o87764Ebs_seg_000271","start_time":618.69,"end_time":620.2,"raw_text":"一条一条的固化下来"}
{"segment_id":"BV1o87764Ebs_seg_000272","start_time":620.2,"end_time":621.26,"raw_text":"除此之外呢"}
{"segment_id":"BV1o87764Ebs_seg_000273","start_time":621.26,"end_time":622.8,"raw_text":"我们可以从真实的用户"}
{"segment_id":"BV1o87764Ebs_seg_000274","start_time":622.8,"end_time":624.16,"raw_text":"从测试里面去捞"}
{"segment_id":"BV1o87764Ebs_seg_000275","start_time":624.16,"end_time":626.16,"raw_text":"那些我们自己根本就没有设计过的"}
{"segment_id":"BV1o87764Ebs_seg_000276","start_time":626.16,"end_time":627.72,"raw_text":"五花八门的输入啊"}
{"segment_id":"BV1o87764Ebs_seg_000277","start_time":627.72,"end_time":629.92,"raw_text":"把它们放到我们这样的一个测试集里面"}
{"segment_id":"BV1o87764Ebs_seg_000278","start_time":629.92,"end_time":631.56,"raw_text":"那这两类回归测试啊"}
{"segment_id":"BV1o87764Ebs_seg_000279","start_time":631.56,"end_time":635.04,"raw_text":"能够保证我们的系统在不停更改的状态下"}
{"segment_id":"BV1o87764Ebs_seg_000280","start_time":635.04,"end_time":636.77,"raw_text":"依旧没有退步啊"}
{"segment_id":"BV1o87764Ebs_seg_000281","start_time":636.77,"end_time":639.17,"raw_text":"同时保证尽量的没有盲区"}
{"segment_id":"BV1o87764Ebs_seg_000282","start_time":639.17,"end_time":641.97,"raw_text":"还有一个我自己觉得特别关键的时间"}
{"segment_id":"BV1o87764Ebs_seg_000283","start_time":641.97,"end_time":643.81,"raw_text":"就是每加一个新功能"}
{"segment_id":"BV1o87764Ebs_seg_000284","start_time":643.81,"end_time":645.05,"raw_text":"我都会给他配一个开关"}
{"segment_id":"BV1o87764Ebs_seg_000285","start_time":645.05,"end_time":646.04,"raw_text":"一个flag"}
{"segment_id":"BV1o87764Ebs_seg_000286","start_time":646.04,"end_time":646.92,"raw_text":"有了开关"}
{"segment_id":"BV1o87764Ebs_seg_000287","start_time":646.92,"end_time":649.56,"raw_text":"我就有这个开和关的两个版本"}
{"segment_id":"BV1o87764Ebs_seg_000288","start_time":649.56,"end_time":651.8,"raw_text":"当他们去跑同样一套回归测试的时候"}
{"segment_id":"BV1o87764Ebs_seg_000289","start_time":651.8,"end_time":653.32,"raw_text":"我就能够清楚地看到"}
{"segment_id":"BV1o87764Ebs_seg_000290","start_time":653.32,"end_time":655.44,"raw_text":"新功能到底带来了什么东西"}
{"segment_id":"BV1o87764Ebs_seg_000291","start_time":655.44,"end_time":656.74,"raw_text":"哪些变好了"}
{"segment_id":"BV1o87764Ebs_seg_000292","start_time":656.74,"end_time":658.94,"raw_text":"哪些被悄悄的弄坏了"}
{"segment_id":"BV1o87764Ebs_seg_000293","start_time":658.94,"end_time":661.3,"raw_text":"那有了上面这套架构之后"}
{"segment_id":"BV1o87764Ebs_seg_000294","start_time":661.3,"end_time":662.62,"raw_text":"最妙的一步来了"}
{"segment_id":"BV1o87764Ebs_seg_000295","start_time":662.62,"end_time":665.87,"raw_text":"我们如何把这一切形成一个闭环啊"}
{"segment_id":"BV1o87764Ebs_seg_000296","start_time":665.87,"end_time":669.19,"raw_text":"我们可以在codex里面去做这样一件事情"}
{"segment_id":"BV1o87764Ebs_seg_000297","start_time":669.19,"end_time":672.17,"raw_text":"就是当他需要开发新的功能的时候"}
{"segment_id":"BV1o87764Ebs_seg_000298","start_time":672.17,"end_time":674.54,"raw_text":"它不仅仅考虑这个代码怎么写"}
{"segment_id":"BV1o87764Ebs_seg_000299","start_time":674.54,"end_time":678.68,"raw_text":"它需要首先先去设计回归测试"}
{"segment_id":"BV1o87764Ebs_seg_000300","start_time":678.68,"end_time":681.78,"raw_text":"其次去设计这样的一个开关"}
{"segment_id":"BV1o87764Ebs_seg_000301","start_time":681.78,"end_time":685.02,"raw_text":"然后呢去进行代码的编写"}
{"segment_id":"BV1o87764Ebs_seg_000302","start_time":685.02,"end_time":689.1,"raw_text":"编写完之后在开关开启和开关结束的时候"}
{"segment_id":"BV1o87764Ebs_seg_000303","start_time":689.1,"end_time":692.18,"raw_text":"同样的去跑一遍这样的一个回归测试"}
{"segment_id":"BV1o87764Ebs_seg_000304","start_time":692.18,"end_time":696.2,"raw_text":"通过回归测试的结果进行一个反馈"}
{"segment_id":"BV1o87764Ebs_seg_000305","start_time":696.2,"end_time":697.89,"raw_text":"再去修改代码"}
{"segment_id":"BV1o87764Ebs_seg_000306","start_time":697.89,"end_time":703.65,"raw_text":"直到最终的代码改成能够符合回归测试要求的"}
{"segment_id":"BV1o87764Ebs_seg_000307","start_time":703.65,"end_time":704.66,"raw_text":"这样的一个版本"}
{"segment_id":"BV1o87764Ebs_seg_000308","start_time":704.66,"end_time":707.66,"raw_text":"那在整个这样的一套体系里面"}
{"segment_id":"BV1o87764Ebs_seg_000309","start_time":707.66,"end_time":709.29,"raw_text":"人是没有参与的"}
{"segment_id":"BV1o87764Ebs_seg_000310","start_time":709.29,"end_time":711.69,"raw_text":"而codex这种coding agent"}
{"segment_id":"BV1o87764Ebs_seg_000311","start_time":711.69,"end_time":714.39,"raw_text":"通过我们设计的这种可验证体系"}
{"segment_id":"BV1o87764Ebs_seg_000312","start_time":714.39,"end_time":717.5,"raw_text":"把这一切都连成了一个闭环"}
{"segment_id":"BV1o87764Ebs_seg_000313","start_time":717.5,"end_time":720.3,"raw_text":"那到这一步你会发现我们已经不再写代码"}
{"segment_id":"BV1o87764Ebs_seg_000314","start_time":720.3,"end_time":721.54,"raw_text":"我们也不再手动测试"}
{"segment_id":"BV1o87764Ebs_seg_000315","start_time":721.54,"end_time":724.599,"raw_text":"我们做的就是把什么算对定义清楚"}
{"segment_id":"BV1o87764Ebs_seg_000316","start_time":724.599,"end_time":727.15,"raw_text":"剩下的就是这个闭环自己在收敛"}
{"segment_id":"BV1o87764Ebs_seg_000317","start_time":727.15,"end_time":730.89,"raw_text":"而这正好就是我们开头那篇文章所讲到的"}
{"segment_id":"BV1o87764Ebs_seg_000318","start_time":730.89,"end_time":733.17,"raw_text":"如果你能验证一个解"}
{"segment_id":"BV1o87764Ebs_seg_000319","start_time":733.17,"end_time":736.65,"raw_text":"就等价于能给AI造就一个环境"}
{"segment_id":"BV1o87764Ebs_seg_000320","start_time":736.65,"end_time":740.57,"raw_text":"让它去趋近90%的手动验证"}
{"segment_id":"BV1o87764Ebs_seg_000321","start_time":740.57,"end_time":743.96,"raw_text":"到这里就真的变成自动的了"}
{"segment_id":"BV1o87764Ebs_seg_000322","start_time":744.44,"end_time":745.72,"raw_text":"那最后聊一下"}
{"segment_id":"BV1o87764Ebs_seg_000323","start_time":745.72,"end_time":749.26,"raw_text":"就是今天我们做的这套前后端分离回归测试"}
{"segment_id":"BV1o87764Ebs_seg_000324","start_time":749.26,"end_time":751.41,"raw_text":"其实都是抛砖引玉啊"}
{"segment_id":"BV1o87764Ebs_seg_000325","start_time":751.41,"end_time":753.33,"raw_text":"我并不是想让大家说"}
{"segment_id":"BV1o87764Ebs_seg_000326","start_time":753.33,"end_time":754.93,"raw_text":"你照着我这个东西这样做"}
{"segment_id":"BV1o87764Ebs_seg_000327","start_time":754.93,"end_time":757.23,"raw_text":"我更多的是想让大家看见"}
{"segment_id":"BV1o87764Ebs_seg_000328","start_time":757.23,"end_time":759.97,"raw_text":"为什么我们做出这样的技术决定"}
{"segment_id":"BV1o87764Ebs_seg_000329","start_time":759.97,"end_time":762.71,"raw_text":"说实话像前后端分离虎威测试"}
{"segment_id":"BV1o87764Ebs_seg_000330","start_time":762.71,"end_time":764.87,"raw_text":"在很多的技术博文里面都有"}
{"segment_id":"BV1o87764Ebs_seg_000331","start_time":764.87,"end_time":767.4,"raw_text":"为什么我们今天还是要反复去提"}
{"segment_id":"BV1o87764Ebs_seg_000332","start_time":767.4,"end_time":769.04,"raw_text":"我们想让大家看见的是"}
{"segment_id":"BV1o87764Ebs_seg_000333","start_time":769.04,"end_time":771.36,"raw_text":"为什么我们做出这样的基础决定啊"}
{"segment_id":"BV1o87764Ebs_seg_000334","start_time":771.36,"end_time":774.64,"raw_text":"如果不是那个90%的效率的浪费"}
{"segment_id":"BV1o87764Ebs_seg_000335","start_time":774.64,"end_time":776.44,"raw_text":"把我逼到了墙角是吧"}
{"segment_id":"BV1o87764Ebs_seg_000336","start_time":776.44,"end_time":779.28,"raw_text":"我觉得我可能不会做这样的技术决定"}
{"segment_id":"BV1o87764Ebs_seg_000337","start_time":779.52,"end_time":784.58,"raw_text":"所以这套解法真正想让大家思考的是"}
{"segment_id":"BV1o87764Ebs_seg_000338","start_time":784.58,"end_time":788.359,"raw_text":"在你自己的工程里面有没有类似的瓶颈"}
{"segment_id":"BV1o87764Ebs_seg_000339","start_time":788.359,"end_time":790.659,"raw_text":"有没有正在悄悄吃掉你的时间"}
{"segment_id":"BV1o87764Ebs_seg_000340","start_time":790.659,"end_time":792.039,"raw_text":"或者说让你觉得很烦躁"}
{"segment_id":"BV1o87764Ebs_seg_000341","start_time":792.039,"end_time":793.54,"raw_text":"很重复的问题"}
{"segment_id":"BV1o87764Ebs_seg_000342","start_time":793.54,"end_time":798.41,"raw_text":"如果有你用你自己的方式去解就好啊"}
{"segment_id":"BV1o87764Ebs_seg_000343","start_time":798.41,"end_time":800.85,"raw_text":"一年前大家都在争是吧"}
{"segment_id":"BV1o87764Ebs_seg_000344","start_time":800.85,"end_time":802.31,"raw_text":"我要不要用AI写代码"}
{"segment_id":"BV1o87764Ebs_seg_000345","start_time":802.31,"end_time":803.49,"raw_text":"你如果用了AI写代码"}
{"segment_id":"BV1o87764Ebs_seg_000346","start_time":803.49,"end_time":804.96,"raw_text":"你可能比别人的效率高"}
{"segment_id":"BV1o87764Ebs_seg_000347","start_time":804.96,"end_time":807.32,"raw_text":"在今天没有人争这个问题了"}
{"segment_id":"BV1o87764Ebs_seg_000348","start_time":807.32,"end_time":808.75,"raw_text":"因为大家都在用"}
{"segment_id":"BV1o87764Ebs_seg_000349","start_time":808.75,"end_time":810.83,"raw_text":"那这个时候你需要思考的是"}
{"segment_id":"BV1o87764Ebs_seg_000350","start_time":810.83,"end_time":815.06,"raw_text":"你怎么样使用AI才能比别人的效率更高啊"}
{"segment_id":"BV1o87764Ebs_seg_000351","start_time":815.06,"end_time":817.86,"raw_text":"如果说你用这个AI原来10分钟左右的事情"}
{"segment_id":"BV1o87764Ebs_seg_000352","start_time":817.86,"end_time":819.86,"raw_text":"你用了AI干了两个小时啊"}
{"segment_id":"BV1o87764Ebs_seg_000353","start_time":819.86,"end_time":820.69,"raw_text":"结果是一样的"}
{"segment_id":"BV1o87764Ebs_seg_000354","start_time":820.69,"end_time":822.45,"raw_text":"那这个地方没有效率的提升是吧"}
{"segment_id":"BV1o87764Ebs_seg_000355","start_time":822.45,"end_time":824.37,"raw_text":"你用了AI效率反而下降了"}
{"segment_id":"BV1o87764Ebs_seg_000356","start_time":824.37,"end_time":825.97,"raw_text":"这就是本末倒置啊"}
{"segment_id":"BV1o87764Ebs_seg_000357","start_time":825.97,"end_time":828.81,"raw_text":"所以不要把我说的这样的一个解法"}
{"segment_id":"BV1o87764Ebs_seg_000358","start_time":828.81,"end_time":831.37,"raw_text":"就当做是哦是很好的一件事情"}
{"segment_id":"BV1o87764Ebs_seg_000359","start_time":831.37,"end_time":833.83,"raw_text":"但可能对于你来说一文不值吧"}
{"segment_id":"BV1o87764Ebs_seg_000360","start_time":833.83,"end_time":837.3,"raw_text":"我想给的只是一种启发"}
{"segment_id":"BV1o87764Ebs_seg_000361","start_time":837.3,"end_time":838.62,"raw_text":"你看完我们的视频之后"}
{"segment_id":"BV1o87764Ebs_seg_000362","start_time":838.62,"end_time":841.72,"raw_text":"哎你能够回过头去看看你自己的工程啊"}
{"segment_id":"BV1o87764Ebs_seg_000363","start_time":841.72,"end_time":843.5,"raw_text":"去发现有没有类似的问题"}
{"segment_id":"BV1o87764Ebs_seg_000364","start_time":843.5,"end_time":846.37,"raw_text":"然后你脑子里如果有了一些新的解法哦"}
{"segment_id":"BV1o87764Ebs_seg_000365","start_time":846.37,"end_time":847.71,"raw_text":"我就非常的开心"}
{"segment_id":"BV1o87764Ebs_seg_000366","start_time":847.71,"end_time":848.86,"raw_text":"好吧啊"}
{"segment_id":"BV1o87764Ebs_seg_000367","start_time":848.86,"end_time":851.92,"raw_text":"所以祝大家都能把属于你的"}
{"segment_id":"BV1o87764Ebs_seg_000368","start_time":851.92,"end_time":856.579,"raw_text":"那90%的效率重新拿回到自己的手里啊"}
{"segment_id":"BV1o87764Ebs_seg_000369","start_time":856.579,"end_time":858.719,"raw_text":"那以上就是我们这期视频的全部内容"}
{"segment_id":"BV1o87764Ebs_seg_000370","start_time":858.719,"end_time":860.639,"raw_text":"如果你觉得我们的视频做的还不错的话呢"}
{"segment_id":"BV1o87764Ebs_seg_000371","start_time":860.639,"end_time":862.84,"raw_text":"欢迎点赞收藏转发订阅评论我们的频道"}
{"segment_id":"BV1o87764Ebs_seg_000372","start_time":862.84,"end_time":864.62,"raw_text":"这对我们来说非常的重要"}
{"segment_id":"BV1o87764Ebs_seg_000373","start_time":864.62,"end_time":865.82,"raw_text":"感谢你的收看"}
{"segment_id":"BV1o87764Ebs_seg_000374","start_time":865.82,"end_time":866.84,"raw_text":"祝你学习顺利"}
```

