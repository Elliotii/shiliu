# Shiliu V3.5 — Six-case Human Label Calibration Guide

Status: calibration guide only; not Gold and not a Development/Held-out split.

Active batch: `stage2a-followup-calibration-01`  
Decision template: `research/v3_5/review_decisions.calibration.template.jsonl`

## Core Principle

完整 Raw Transcript 必须可访问，但不要求逐行线性阅读整份字幕。

应先使用 Navigation Aids 定位，再检查其他关键词位置、相关时间段和上下文，并在需要时跳出已有候选检查完整 Transcript。Full Transcript Accessible ≠ Full Transcript Linearly Read From Start to End.

系统/Codex 已负责 Source Version、Segment ID、时间、Timeline Run、Existing Interval、V3 Chunk、关键词位置、完整 Transcript 展示和格式校验。人工只负责最终语义批准：问题需要哪些主要 Aspect；哪些 Raw Segment 真正支持 Query；是否存在等价或互补 Evidence Group；证据支持全部、部分还是没有主要答案；Source 是否可验证；Reason Code；以及是否需要第二次复核。

## Review Order and Guidance

### 1. CASE_015 — Quick authority confirmation

检查是否确实没有 Raw Transcript Authority。不得根据标题推断正文。不需要阅读不存在的正文。

### 2. CASE_017 — Quick authority confirmation

检查它是否是合理的策划型库外 Negative Control、V3 Top Results 是否只是明显噪声，以及是否存在明显应升级为 `query_video` 的 Target。

这不是对全部 144 个视频做穷举式“无答案证明”。批准语义仅是：在冻结资料库主题和 V3 检索结果下，没有发现应批准为目标证据来源的明显视频。

### 3. CASE_013 — Focused semantic review

从导航位置开始，检查完整正文是否只是 MemoryOS 邻近主题，或是否存在能形成有用主要答案的真实支持。重点校准 `partial` 与 `insufficient` 的边界。

### 4. CASE_001 — Seed-assisted evidence verification

从 Existing Interval 和其他关键词命中开始，检查已有 Span 是否真实支持 Query、是否存在其他等价 Evidence Group，以及是否需要更完整上下文。Existing Interval 只是导航，不是 Gold。

### 5. CASE_003 — Deep multi-aspect review

先拆分 Query Aspect：MCP、Function Calling、二者区别。再检查每个必要 Aspect 的真实支持，重点校准 `sufficient` 与 `partial` 的边界。

### 6. CASE_012 — Robustness review

只允许 Run-local Evidence Group，不得创建跨 Timeline Run Span。检查多 Run Source 是否仍可读取，以及 frozen cross-run Parent Chunk 是否不影响 Run-local Evidence。

## Evidence Group Instructions

Gold Evidence Groups are **OR**. Required spans inside one group are **AND**.

- 一个位置可以独立支持完整问题：单独建立一个 Group。
- 必须组合两个分散位置：放入同一个 Group 的两个 `required_spans`。
- 每个 Group 必须留在一个 Timeline Run，并引用精确 Stage 1 Segment IDs。

## Four-state Calibration Reminder

- `sufficient`: 支持所有必要 Aspect。
- `partial`: 支持有意义的一部分，但缺少另一必要部分。
- `insufficient`: Raw 可验证，但没有形成有用主要答案。
- `unverifiable`: 缺少可靠 Raw Source authority，无法验证正文。

这些定义用于人工校准；本 Guide 和 Manifest 均未预填任何 Case 的 Label。

## When `needs_second_review` Must Be `true`

- required_aspects 难以稳定拆分；
- sufficient/partial 或 partial/insufficient 边界不清；
- 多个 Span 是否等价不清；
- Evidence 存在冲突；
- Source language 无法可靠判断；
- video 88 Run-local 边界有疑问。

## Workload Boundary

本轮只填写校准模板中的 6 条记录。其余 Primary 不要求在 Round 1 完成。所有 Reserve 默认 inactive；除非 Version Session 记录 activation reason、替代/补充对象、时间和授权者，否则不要审阅或填写 Reserve。
