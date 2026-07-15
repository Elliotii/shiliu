# 拾流 V3.0 阶段 0/1 验收报告

日期：2026-07-16

## 实现边界

本阶段只实现：

- Anti-Contamination Contract；
- Reference Taxonomy、Gold Set 和候选清单 Schema/模板；
- 人工 Reference 的版本化、Hash 和禁止覆盖冻结工具；
- 四张 Taxonomy 表；
- 不可变 Corpus Snapshot；
- Stored Classification Card；
- 默认排除收藏夹上下文的 Discovery View；
- A/B/C/D 证据等级和 Discovery Eligible 规则；
- 独立 Snapshot 预览页面与候选清单导出。

本阶段没有实现或调用 LLM、Search、Discovery、Assignment、Revision 或 Publish。

## 数据库迁移

- 原 Schema：5
- 当前 Schema：6
- 迁移前备份：`shiliu.pre-v6.backup.db`
- 新表严格为四张：
  - `taxonomy_corpus_snapshots`
  - `taxonomy_classification_cards`
  - `taxonomy_runs`
  - `taxonomy_stage_runs`

## 真实快照结果

来源：`零分姐姐 · 2026找工作学习`

- 来源状态：`paused`，冻结后仍为 `paused`；
- 原始活跃 membership：131；
- 去重 Card：131；
- 合并的重复 membership：0；
- Discovery Eligible：65；
- Trial Assignment only：66；
- A/B/C/D：49 / 10 / 6 / 66；
- Snapshot ID：1；
- Snapshot Hash：`9dd91c9d682f3ff0debf655bd0b938605351308a03d000abd9527e4225ca37e6`。

重复冻结相同内容时复用 Snapshot #1，没有新增重复快照。

## 真实样例 Card

| content_key | 证据 | 是否已物化 | 标题 |
|---|---:|---:|---|
| `bilibili:BV1qhE26VEbS:p1` | D | 是 | 我做Agent平台这一年，评测这关卡了我整整一个月 |
| `bilibili:BV1EZ7p6CE8h:p1` | D | 是 | agent 项目不会写面试一面就不过怎么优化 |
| `bilibili:BV1fRSfBWE5X:p1` | A | 是 | vlog｜白天上班 晚上vibe coding，准备一个月上架我的第一款App！ |
| `bilibili:BV1HhJs6oEap:p1` | B | 是 | 别再问Agent学习路线了，你的学习顺序从头就是反的 |
| `bilibili:BV1ySLc6QEcB:p1` | D | 否 | Git+Github核心概念大串讲，从零到一全攻略，详细实战教程 |

页面会同时展示这些样例的完整 Stored Card 和 Discovery View JSON。

## Stored Card 与 Discovery View

Stored Card 独有字段：

```text
content_key
video_id
source_ids
folder_names
memberships
```

Discovery View 固定字段：

```text
content_id
title
uploader
description
one_line_summary
key_points
projects_tools_models
evidence_level
```

Discovery View 不含收藏夹名称、来源 ID、membership metadata、阅读状态、Mark、归档、忽略或人工笔记。

## 自动验证

```text
58 passed
1 个既有 Starlette/httpx 弃用警告
```

覆盖：

- Schema 迁移和四表边界；
- A/B/C/D；
- `-` 不计为有效简介；
- D 级排除于 Discovery；
- 未物化 Card；
- 多收藏夹去重；
- 已移除内容排除；
- 暂停来源只读冻结且不恢复同步；
- Stored/Discovery 字段隔离；
- 用户状态与笔记防泄漏；
- Snapshot 不可变；
- 相同 Hash 复用；
- 空 Snapshot 拒绝；
- 页面预览、冻结和候选清单；
- Snapshot 路径不调用模型；
- Runtime 不依赖 Eval；
- Reference 冻结 Hash 和禁止覆盖。
