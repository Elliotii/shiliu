# Shiliu V3.5 Stage 3R-PQS-B0 — Neutral Product Query Authoring Packet Export

你正在 Shiliu 仓库中执行：

```text
Stage 3R-PQS-B0

Freeze Product-query Authoring Contract
→ Export Neutral Product-use Scenarios
→ Export Neutral Library Content Map
→ Export Legacy Candidate Pool Separately
→ Prepare Two-pass Independent WebGPT Handoff
→ Stop
```

本轮不再尝试证明仓库中存在 20–24 条历史真实搜索原句。

当前 Product Query Set v1 的正确定位是：

> 基于拾流真实产品场景和真实收藏夹内容，由独立 WebGPT 提出、再由用户逐条确认的场景驱动 Product Query Set。

它不是：

```text
Historical Search-log Dataset
```

因为当前项目没有足够的历史真实搜索日志。

---

# 一、当前背景与决策修正

历史 Phase A / Phase A-R 已产生约 40 条 Legacy Candidate，但其中多数来自项目上下文或规划文档。

这些候选：

```text
可以作为参考提案
≠
已经批准的真实产品问题
≠
最终 Product Query Set
```

不再继续要求 Codex 从仓库中搜集足够数量的“Verbatim User Query”。

本轮重新定义三种 Authoring Origin：

```yaml
authoring_origin:
  independent_webgpt:
    meaning: 独立 WebGPT 根据中立产品与收藏夹信息提出
  legacy_codex_candidate:
    meaning: Codex 从既有项目文档提取的旧候选
  user_discussion:
    meaning: 用户与独立 WebGPT 讨论后形成或修订
```

最终进入正式 Product Query Set 的问题必须满足：

```yaml
user_validated_as_plausible: true
```

即用户明确确认：

> 这是我在拾流中真实可能会提出的问题。

不要求该问题以前已经真实输入过。

---

# 二、本轮目标

只完成以下内容：

```text
中立产品场景说明
+
中立收藏夹内容地图
+
分离的 Legacy Candidate Packet
+
独立 WebGPT 两阶段工作说明
+
空白输出模板
```

本轮不得：

* 替独立 WebGPT 生成新的 Product Query；
* 推荐最终保留哪 20–24 条；
* 根据 Query Family 缺口补题；
* 判断哪些问题最容易被系统回答；
* 判断哪些问题应该进入 Dev 或 Frozen Eval；
* 运行 Retrieval；
* 运行 Candidate Builder；
* 运行 Selector；
* 运行 Sufficiency Judge；
* 查看任何系统评测结果来设计内容地图；
* 修改 V3/V3.5 产品代码。

---

# 三、仓库与写入边界

仓库根目录：

```text
/Users/elliot/new-systems/agent-job-prep/Shiliu
```

保留历史资产不变：

```text
research/v3_5/product_query_set_v1/phase_a/**
research/v3_5/product_query_set_v1/phase_a_r/**
```

不得覆盖或改写历史 Phase A / Phase A-R 报告和候选。

新增：

```text
research/v3_5/product_query_set_v1/authoring_packet/**
```

允许新增简单导出脚本和测试：

```text
scripts/export_pqs_v1_authoring_packet.py
tests/test_pqs_v1_authoring_packet_*.py
```

如现有 Eval 工具已经足够，优先复用，不建设新的通用标注平台。

---

# 四、两阶段独立 Authoring 流程

本轮必须为后续独立 WebGPT 准备两套彼此分离的材料。

## Pass 1 — Independent Authoring

独立 WebGPT 首先只能看到：

```text
PQS_V1_PRODUCT_SCENARIO_BRIEF.md
PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md
PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md
independent_query_draft.template.jsonl
```

它不应看到 Legacy 40 条候选。

Pass 1 目标：

```text
根据产品场景和中立收藏夹内容地图
独立提出 24–30 条自然 Product Query 草案
```

这样可以降低 Legacy Candidate 对问法和主题的锚定。

## Pass 2 — Legacy Candidate Reconciliation

只有独立 WebGPT 完成 Pass 1 后，才向其提供：

```text
PQS_V1_LEGACY_CANDIDATE_PACKET.md
legacy_candidate_review.template.jsonl
```

独立 WebGPT再判断：

```yaml
legacy_action:
  absorb
  revise
  merge
  exclude
  reserve
```

它需要比较：

* Legacy Candidate 与自己独立提出的问题是否重复；
* Legacy 问法是否更自然；
* 是否存在自己遗漏的真实产品场景；
* 哪些 Legacy Candidate 过于规划化、评测化或多方面绑定；
* 哪些可以经过修订后进入统一候选池。

之后由独立 WebGPT 与用户讨论，最终形成 20–24 条，并逐条取得用户确认。

---

# 五、允许使用的材料

## 5.1 产品场景材料

允许使用：

* 产品 Brief；
* 产品 Spec / PRD；
* V3/V3.5 版本边界和功能定义；
* 搜索页和产品交互说明；
* 收藏夹搜索、导航、证据定位等真实使用需求。

只提取：

```text
用户为什么会使用拾流搜索
用户希望完成什么信息任务
拾流当前支持哪些交互形式
```

不得引用系统评测成绩。

## 5.2 收藏夹内容地图材料

允许使用已经存在的：

* 收藏夹视频元数据；
* 视频标题；
* 描述；
* 上传者；
* 收藏时间；
* 已有主题标签；
* AI Summary；
* AI Chapter Heading；
* 已有分类结果；
* 字幕语言、字幕来源类型等元数据；
* 文件中已经存在的主题归纳。

这些材料只用于：

```text
Query Authoring Navigation
```

不是 Evidence Gold，也不得被表述为事实证据权威。

## 5.3 禁止使用

不得使用：

* 原始字幕正文；
* ASR 正文；
* Gold Segment；
* Gold Group；
* Evidence Question Label；
* Sufficiency Label；
* Target Video Rank；
* SearchCandidateSet；
* Retrieval Hit/Miss；
* Auto / Lexical / Hybrid 成绩；
* Candidate Builder Failure；
* Selector Failure；
* Stress Track A Case 级结果；
* Held-out 内容；
* Final Answer 输出。

不得根据系统成功或失败来决定内容地图中的主题优先级。

---

# 六、产品使用场景 Brief

生成：

```text
PQS_V1_PRODUCT_SCENARIO_BRIEF.md
```

该文件应面向不了解项目实现细节的独立 WebGPT，简洁说明拾流的真实使用方式。

至少覆盖：

## 6.1 产品背景

```text
拾流管理和检索用户保存的 Bilibili 视频资料。
用户希望在不重新逐个观看视频的情况下，
找到相关视频、定位原字幕证据，并判断收藏夹是否足以回答问题。
```

## 6.2 自然信息任务

包括但不限于：

```yaml
product_information_tasks:
  - 查找概念或术语解释
  - 了解某技术或工具的作用
  - 查找实施流程或操作步骤
  - 比较两个方法或工具
  - 判断何时选择某个方案
  - 查找限制、风险或前置条件
  - 查找视频中是否报告实际效果
  - 查找评测、测试或质量保障方法
  - 综合多个视频中的互补信息
  - 判断收藏夹中是否缺少足够信息
```

这些是 Authoring Dimensions，不是要求凑齐的固定配额。

## 6.3 当前产品边界

明确：

* 原字幕 / ASR 是后续证据权威；
* 标题、描述、AI Summary 只用于发现和导航；
* V3.5 关注 Evidence Resolution 与 Sufficiency；
* 当前不要求独立 WebGPT 生成答案或 Evidence Gold；
* Product Query 应像普通用户搜索，而不是专门为测试某个 Label 编写。

## 6.4 Product Query 的自然性标准

Product Query 应：

```yaml
standalone_understandable: true
plausible_for_shiliu: true
natural_user_wording: true
not_written_to_match_exact_video_title: true
not_written_to_force_a_known_label: true
```

允许：

* 简单单意图问题；
* 自然的双方面或少量多方面问题；
* 单视频或多视频综合问题；
* 少量可能无答案的问题。

避免整个集合被以下问题主导：

* 证据审计式问题；
* 项目规划式问题；
* 过长的复合问题；
* 面试大纲式问题；
* 一条问题绑定四五个独立任务。

---

# 七、中立收藏夹内容地图

生成：

```text
PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md
pqs_v1_neutral_library_content_map.jsonl
```

## 7.1 目标

向独立 WebGPT说明：

```text
用户收藏夹里大致有哪些主题和内容形态
```

帮助它提出真实、Library-grounded 的问题。

不得告诉它：

* 某个问题能否回答；
* 哪个具体视频是正确答案；
* 哪些系统组件可能失败；
* 哪些主题是 Stress Case；
* 哪些问题曾经检索成功。

## 7.2 Topic Cluster

基于现有元数据和导航性材料，形成中立 Topic Cluster。

每个 Cluster 至少记录：

```json
{
  "topic_cluster_id": "PQS_TOPIC_...",
  "neutral_topic_label": "Agent 评测与回归测试",
  "neutral_topic_description": "收藏内容涉及 Agent 能力评测、稳定性、回归测试和发布门槛。",
  "approximate_item_count": 0,
  "coverage_signal": "light|medium|dense",
  "content_shapes": [
    "definition",
    "process",
    "comparison",
    "limitation",
    "reported_result",
    "evaluation"
  ],
  "single_or_multi_item_potential": "single|multi|both",
  "source_languages": ["zh"],
  "subtitle_source_types": ["official", "asr"],
  "navigation_sources_used": [
    "metadata",
    "ai_summary",
    "chapter_heading"
  ],
  "authoring_notes": "只说明内容形态，不说明可回答性。"
}
```

`content_shapes` 只能根据来源材料中明确存在的内容形态填写，不得推测。

## 7.3 建议主题覆盖

应根据真实收藏夹生成，而不是强行写死。可能包括：

* Agent / Agent Eval；
* RAG / Retrieval / Production；
* SFT / LoRA / Training；
* Coding Agent / Claude Code / Cursor；
* Memory / Context Management；
* Workflow / Harness / Automation；
* Python / 基础编程；
* Deployment / Testing / Rollback；
* Product Spec / PRD / OpenSpec；
* AI-assisted Development；
* 其他真实存在的收藏夹主题。

如果某类不存在，不得为了完整性生成。

## 7.4 去除标题锚定

Pass 1 的 `PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md` 中：

* 不展示 BV 号；
* 不展示 Video ID；
* 不展示完整精确视频标题列表；
* 不展示精确时间戳；
* 不展示完整 AI Summary；
* 不展示任何字幕原文。

可以使用宽泛、中性的主题标签，例如：

```text
SFT 中的数据格式与训练技巧
```

而不是直接复制某个视频标题。

## 7.5 内部 Provenance

为了可审计，另外生成：

```text
pqs_v1_content_map_provenance.jsonl
```

记录每个 Topic Cluster 基于哪些内部资产形成。

可以包含内部 Video ID、标题和文件路径，但该文件：

```yaml
share_with_independent_webgpt: false
```

只供当前 V3.5 Session 和 Codex审计。

不得将其并入 Pass 1 Packet。

---

# 八、Legacy Candidate Packet

生成：

```text
PQS_V1_LEGACY_CANDIDATE_PACKET.md
pqs_v1_legacy_candidates.jsonl
```

## 8.1 输入

复用 Phase A-R 最终 40 条候选。

不得重新生成或静默改写。

## 8.2 定位

Packet 开头必须明确：

> 以下问题是从历史项目文档中提取的 Legacy Candidate，仅作为第二阶段参考材料。它们不是经过批准的 Product Query，也不代表真实搜索日志。

## 8.3 每条展示

```text
Legacy Candidate ID
Raw Query
Source Type
Source Reference
Existing Query Family
Multi-aspect
```

可以展示来源类别，但不要向独立 WebGPT提供：

* 系统表现；
  -目标视频；
* Retrieval Mode；
* Gold；
* Builder / Selector 结果；
* Codex 对是否应入选的建议。

## 8.4 Legacy Review Template

生成：

```text
legacy_candidate_review.template.jsonl
```

格式：

```json
{
  "legacy_candidate_id": "PQS_CAND_...",
  "legacy_action": "",
  "related_independent_draft_ids": [],
  "proposed_revision": "",
  "reason": ""
}
```

允许动作：

```yaml
legacy_action:
  absorb:
    meaning: 独立草案未覆盖，且该问题自然，可吸收
  revise:
    meaning: 核心需求有价值，但问法需调整
  merge:
    meaning: 与一个或多个独立草案合并
  exclude:
    meaning: 不适合作为 Product Query
  reserve:
    meaning: 有价值，但不进入首版正式集合
```

模板必须保持空白。

---

# 九、Pass 1 独立出题 Guide

生成：

```text
PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md
independent_query_draft.template.jsonl
```

Guide 必须要求独立 WebGPT：

1. 只看 Product Scenario Brief 和 Neutral Library Content Map；
2. 暂时不看 Legacy Candidate；
3. 独立提出 24–30 条候选；
4. 不需要为每个 Topic Cluster 出题；
5. 不按 Query Family 硬凑配额；
6. 优先自然、独立、真实可能使用的问题；
7. 允许少量多视频综合和可能无答案的问题；
8. 不生成答案、Target Video 或 Gold；
9. 不预测系统是否能检索成功；
10. 标记自己不确定、需要和用户讨论的问题。

模板格式：

```json
{
  "independent_draft_id": "PQS_IND_...",
  "proposed_query": "",
  "topic_cluster_ids": [],
  "query_family": "",
  "complexity": "simple|moderate|natural_multi_aspect",
  "single_or_multi_item_intent": "single|multi|unknown",
  "authoring_rationale": "",
  "needs_user_discussion": false,
  "user_validated_as_plausible": null
}
```

`user_validated_as_plausible` 必须保持 `null`。

---

# 十、最终用户确认模板

生成：

```text
product_query_user_validation.template.jsonl
```

格式：

```json
{
  "draft_query_id": "",
  "final_user_query": "",
  "authoring_origin": [],
  "user_action": "",
  "user_validated_as_plausible": null,
  "decision_reason": ""
}
```

允许动作：

```yaml
user_action:
  approve_as_is:
  approve_with_revision:
  merge:
  exclude:
  reserve:
```

只有用户本人可以把：

```yaml
user_validated_as_plausible: true
```

写入正式决策。

Codex和独立 WebGPT 均不得代填。

---

# 十一、独立 WebGPT Handoff 文件

生成：

```text
PQS_V1_INDEPENDENT_WEBGPT_HANDOFF.md
```

该文件必须明确建议用户分两次提供材料。

## Pass 1 提供

```text
PQS_V1_PRODUCT_SCENARIO_BRIEF.md
PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md
PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md
independent_query_draft.template.jsonl
```

并要求独立 WebGPT先完成独立候选。

## Pass 2 提供

独立候选完成后，再提供：

```text
PQS_V1_LEGACY_CANDIDATE_PACKET.md
legacy_candidate_review.template.jsonl
```

要求其完成：

```text
Legacy Candidate Reconciliation
```

## 最终讨论

独立 WebGPT随后：

* 展示统一候选池；
* 和用户逐组讨论；
* 修订自然问法；
* 合并重复；
* 最终推荐 20–24 条；
* 等待用户逐条或分批确认。

不得替用户完成最终确认。

---

# 十二、内容地图的质量要求

## 12.1 Grounding

每个 Topic Cluster 必须有内部 Provenance。

不得仅凭模型常识生成收藏夹主题。

## 12.2 中立性

内容描述不得出现：

```text
这个问题系统能很好回答
这是一个困难 Case
这是 Builder 容易失败的主题
适合进入 Frozen Eval
```

## 12.3 不把 AI Summary 当证据

在 Scenario Brief 和 Content Map 中明确：

> AI Summary、标题和章节只用于 Query Authoring Navigation，不构成后续 Evidence Gold。

## 12.4 不制造可回答性承诺

不得使用：

```text
收藏夹可以回答……
该主题包含完整答案……
有充分证据说明……
```

改用：

```text
收藏内容涉及……
现有导航材料提到……
主题材料可能包含……
```

---

# 十三、调用与污染审计

生成：

```text
pqs_v1_authoring_packet_execution.audit.json
```

至少记录：

```yaml
retrieval_calls: 0
product_search_calls: 0
embedding_calls: 0
candidate_builder_calls: 0
selector_calls: 0
sufficiency_judge_calls: 0
final_answer_calls: 0

raw_transcript_read_for_authoring: false
gold_read_for_authoring: false
stress_results_read_for_topic_prioritization: false
system_performance_used: false
heldout_accessed: false

new_product_queries_generated_by_codex: 0
legacy_queries_rewritten_by_codex: 0
human_decisions_filled: 0
```

注意：

* 读取元数据、标题、描述、AI Summary、Topic Tags 不算 Retrieval Call；
* 但不得调用 Product Search 来生成主题；
* 不得读取原字幕正文来判断能否出题。

---

# 十四、测试要求

至少覆盖：

```text
test_authoring_packet_does_not_run_retrieval
test_authoring_packet_does_not_call_embedding
test_authoring_packet_does_not_call_builder
test_authoring_packet_does_not_call_selector
test_authoring_packet_does_not_access_heldout

test_authoring_packet_does_not_read_raw_transcript
test_authoring_packet_does_not_read_gold
test_authoring_packet_does_not_use_stress_results

test_neutral_content_map_is_grounded_in_navigation_assets
test_neutral_content_map_has_internal_provenance
test_neutral_content_map_excludes_video_ids
test_neutral_content_map_excludes_bv_ids
test_neutral_content_map_excludes_exact_timestamps
test_neutral_content_map_excludes_full_video_title_lists
test_neutral_content_map_does_not_claim_answerability

test_legacy_packet_preserves_all_revised_candidates
test_legacy_packet_preserves_raw_query
test_legacy_packet_contains_no_system_performance
test_legacy_review_template_is_blank

test_independent_authoring_template_is_blank
test_user_validation_template_is_blank
test_codex_generates_no_new_product_queries

test_handoff_requires_pass1_before_legacy_pass2
test_handoff_keeps_provenance_manifest_private
test_handoff_does_not_start_dev_eval_split
test_handoff_does_not_start_product_baseline
test_handoff_does_not_start_f1a_or_f1b
```

不得修改旧测试制造通过。

---

# 十五、输出目录

至少生成：

```text
research/v3_5/product_query_set_v1/authoring_packet/
  protocol/
  product_scenarios/
  library_content_map/
  provenance/
  independent_authoring/
  legacy_candidates/
  user_validation/
  isolation/
  tests/

  PQS_V1_PRODUCT_SCENARIO_BRIEF.md
  PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md
  pqs_v1_neutral_library_content_map.jsonl
  pqs_v1_content_map_provenance.jsonl

  PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md
  independent_query_draft.template.jsonl

  PQS_V1_LEGACY_CANDIDATE_PACKET.md
  pqs_v1_legacy_candidates.jsonl
  legacy_candidate_review.template.jsonl

  product_query_user_validation.template.jsonl
  PQS_V1_INDEPENDENT_WEBGPT_HANDOFF.md

  pqs_v1_authoring_packet_manifest.json
  pqs_v1_authoring_packet_file_hash_manifest.jsonl
  pqs_v1_authoring_packet_execution.audit.json

  V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md
```

---

# 十六、报告必须回答

`V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md` 必须回答：

## Positioning

1. Product Query Set 是否被定义为真实搜索日志；
2. 最终数据集实际定位；
3. Codex、独立 WebGPT、用户各自角色。

## Product Scenario Brief

4. 使用了哪些产品需求来源；
5. 是否包含真实产品信息任务；
6. 是否包含系统性能或 Stress 结果；
7. 是否生成了新的 Product Query。

## Content Map

8. Topic Cluster 数量；
9. 各 Cluster 的大致内容数量；
10. 使用了哪些导航性来源；
11. 是否读取原字幕正文；
12. 是否查看 Gold；
13. 是否向独立 WebGPT暴露 Video ID / BV / 时间戳；
14. 是否为每个 Cluster 保留内部 Provenance；
15. 是否对可回答性作出承诺。

## Legacy Pool

16. Legacy Candidate 数量；
17. 是否保留原始措辞；
18. 是否发生 Codex 自动改写；
19. 是否包含系统表现信息；
20. 是否与 Pass 1 Packet 分离。

## Handoff

21. 是否明确 Pass 1 独立出题；
22. 是否明确 Pass 2 Legacy Reconciliation；
23. 是否生成空白独立出题模板；
24. 是否生成空白 Legacy Review Template；
25. 是否生成空白 User Validation Template；
26. 是否可以交给独立 WebGPT；
27. Product Query 是否已冻结；
28. Dev / Eval 是否已划分；
29. Product Baseline 是否已启动；
30. F1A / F1B 是否已启动。

---

# 十七、完成状态

成功时输出：

```text
Stage 3R-PQS-B0 Complete

Product Query Set Reframed as Scenario-grounded and User-validated
Neutral Product Scenario Brief Exported
Neutral Library Content Map Exported
Internal Content-map Provenance Preserved
Legacy Candidate Pool Exported Separately
Two-pass Independent WebGPT Handoff Prepared
No Product Queries Generated or Selected by Codex
Ready for Independent WebGPT Pass 1 Authoring
```

阻塞时输出：

```text
Stage 3R-PQS-B0 Blocked

Neutral Library Content Map Could Not Be Exported
Without Raw Transcript, Gold, or Evaluation-result Leakage
```

---

# 十八、强制停止点

完成后立即停止。

不得：

* 生成新的 Product Query；
* 选择最终 20–24 条；
* 修改 Legacy Candidate；
* 代替用户确认自然性；
* 正式划分 Dev / Frozen Eval；
* 运行 Retrieval Baseline；
* 生成 Evidence Gold；
* 修 Candidate Builder；
* 修 Selector；
* 进入 Stage 4；
* 提交或 push，除非用户另行要求。

最终只返回：

1. 完成或阻塞状态；
2. Topic Cluster 数；
3. 使用的导航材料类型；
4. Legacy Candidate 数；
5. 是否读取原字幕或 Gold；
6. 是否生成新 Product Query；
7. Pass 1 Packet 路径；
8. Pass 2 Legacy Packet 路径；
9. Independent WebGPT Handoff 路径；
10. Report 路径；
11. 是否可以关闭当前 Codex Session。
