# Product Query Set v1 — Product Scenario Brief

## 产品背景

拾流管理和检索用户保存的 Bilibili 视频资料。用户希望在不重新逐个观看视频的情况下，找到相关视频、定位原字幕证据，并判断收藏夹是否足以回答问题。

## 自然信息任务

独立出题时可参考这些自然信息任务维度：概念或术语解释、技术或工具的作用、实施流程或操作步骤、两个方法或工具的比较、方案选择时机、限制/风险/前置条件、视频是否报告实际效果、评测/测试/质量保障方法、多个视频的互补信息，以及收藏夹可能缺少足够信息的情况。这些是 Authoring Dimensions，不是配额。

## 当前产品边界

- 原字幕与 ASR 是后续证据权威；标题、描述、AI Summary 和章节仅用于 Query Authoring Navigation，不构成后续 Evidence Gold。
- V3.5 关注 Evidence Resolution 与 Sufficiency；本阶段不要求生成答案、Target Video 或 Evidence Gold。
- Product Query 应像普通用户搜索，而不是专门为某个标签或某条视频标题编写。

## 自然性标准

```yaml
standalone_understandable: true
plausible_for_shiliu: true
natural_user_wording: true
not_written_to_match_exact_video_title: true
not_written_to_force_a_known_label: true
```

允许简单单意图、自然双方面/少量多方面、单视频或多视频综合，以及少量可能无答案的问题。避免让集合被证据审计式、项目规划式、过长复合式或面试大纲式问题主导。
