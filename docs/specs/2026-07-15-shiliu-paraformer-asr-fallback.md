# 拾流：Paraformer-v2 无字幕兜底

## Status

Approved

## Goal

当 B 站视频没有中文或英文字幕时，使用 Paraformer-v2 生成带时间戳的字幕，并接入现有原文整理与摘要流程。

## Context and Current State

- `src/shiliu/pipeline.py:PipelineService._record_missing_subtitle` 当前连续检查无字幕后将视频标记为 `skipped_no_subtitle`。
- `references/upstreams/bilibili-cli/bili_cli/client.py:get_audio_url` 和 `download_audio` 已提供音频地址获取与下载能力，不需要修改上游 submodule。
- `src/shiliu/pipeline.py:PipelineService` 当前通过 `processing_profile` 区分“立即点击快速路径”和“定时正式路径”。
- `src/shiliu/db.py:SCHEMA_VERSION` 当前为 3；批准时测试基线为 `36 passed`。
- Paraformer-v2 支持异步文件转写、最长 12 小时文件及句子／词级时间戳，见[Paraformer-v2 官方接口文档](https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-restful-api)。

首次真实测试样本：

```text
标题：AI Agent面试，简历上的项目做这几个方向面试官追着你聊
BV：BV1ToTy6tEyc
时长：183 秒
分P：1
字幕：无中文、无英文
预计费用：约 0.015 元
```

## Scope

- 设置页增加独立的 Paraformer-v2 配置和连接测试。
- 无字幕视频支持按时长规则自动或手动 ASR。
- 下载临时音频并上传至 DashScope 临时存储。
- 持久化异步 `task_id`，支持进程重启后恢复。
- 保存 Paraformer 原始结果和带时间戳字幕。
- 将 ASR 字幕接入现有 DeepSeek 原文整理和摘要流程。
- 页面显示真实 ASR 阶段、失败原因和冷却状态。
- 完成一次指定真实视频的端到端验证。

## Non-goals

本任务不实现：

- 音频播放、音频管理或长期音频保存。
- 多 P 音频处理。
- 实时语音识别或 WebSocket ASR。
- 说话人分离、热词管理或语气词自动删除。
- Fun-ASR、Qwen-ASR 或通用 Provider 插件系统。
- 自建 OSS、Redis、Celery、独立 Worker 或消息队列。
- 批量处理现有全部无字幕视频。
- 修改或分叉 `bilibili-cli` submodule。
- 对已有摘要执行音频重新识别。
- 超过 5 分钟视频的自动 ASR。

实现不得包含 Non-goals 明确排除的能力。

## Users and Key Flows

### 自动路径

```text
连续三次无中英文字幕
→ 视频时长 ≤ 300 秒
→ 自动提交 Paraformer
→ 使用定时正式 DeepSeek 路径
→ 正式字幕整理
→ 正式摘要
```

### 手动路径

```text
用户点击“立即生成字幕”
→ 不受 5 分钟限制
→ 提交 Paraformer
→ 持久化 trigger_mode=manual
→ 快速字幕整理 no thinking
→ 正式摘要 thinking=max
→ 标记为快速版
→ 后续定时精修
```

即使 ASR 结果稍后由定时任务取回，也必须依据持久化的 `trigger_mode=manual` 走快速路径，不得因轮询发生在定时进程中而改成正式路径。

## Behavioral Requirements

### 触发规则

- `duration_seconds <= 300`：三次字幕检查失败后允许自动 ASR。
- `duration_seconds > 300`：只能由用户点击“立即生成字幕”。
- 当前已有的 `skipped_no_subtitle` 不自动批量重排。
- 首次真实测试仅处理 `BV1ToTy6tEyc`。
- 未配置或未通过测试的 DashScope 凭据不得自动调用。
- 同一视频同时只能存在一个活动 ASR 任务。

### 音频生命周期

- 仅下载第一 P 的低码率音频。
- 音频只能写入拾流管理的临时目录。
- ASR 成功、最终失败或取消后均必须删除临时音频。
- 永久保存内容仅包括 `asr-raw.json`、带时间戳的 `subtitle-raw.json` 和 `subtitle-raw.txt`、整理原文与摘要。

### Paraformer 参数

第一版固定为：

```text
model = paraformer-v2
language_hints = ["zh", "en"]
timestamp_alignment_enabled = true
disfluency_removal_enabled = false
diarization_enabled = false
```

### 冷却与幂等

- 活动任务期间重复点击不得重复下载、上传或计费，只返回现有任务状态。
- 第一次可重试失败后冷却 10 分钟，第二次后冷却 30 分钟，第三次失败进入 `needs_review` 并停止自动重试。
- 按钮在任务运行或冷却期间禁用，并显示剩余冷却时间。
- HTTP 429、网络超时、上传失败和结果临时不可用属于可重试错误。
- API Key 无效、模型不存在和不支持的文件格式直接进入 `needs_review`。
- 用户点击不能绕过活动任务或冷却时间。

## Proposed Approach

- 在单一新模块 `src/shiliu/asr.py` 中定义最小 `ASRProvider` Protocol、Paraformer HTTP 实现和结果规范化；不为一个 Provider 创建 package、registry 或插件系统。
- 新增 `asr_jobs` 作为外部异步任务的持久化边界，记录 `video_id`、`provider`、`model`、`trigger_mode`、`status`、`task_id`、重试与时间字段。
- ASR 句子结果转换为现有 `SubtitleSegment` 后，继续调用现有 `PipelineService`，不复制原文整理或摘要流程。
- `videos.status` 只保留用户可感知的粗粒度管道状态；下载、上传、已提交、轮询等细阶段仅存在 `asr_jobs.status` 中，页面通过关联数据显示，不扩张 `VideoStatus` 枚举。
- 复用现有 manual background thread、scheduled runner、SQLite 和进程锁，不新增常驻任务系统。

## Alternatives Considered

- 直接把 B 站 CDN URL 交给 Paraformer：不采用，存在签名过期和防盗链下载失败。
- 长期保存音频：不采用，不符合当前产品边界。
- 引入 DashScope SDK：不采用，现有 `httpx` 足以完成接口调用。
- 所有无字幕视频立即自动识别：不采用，缺少费用和长视频控制。

## Data / API / Tool / Interface Changes

- 配置增加独立 `[asr]` 区域。
- DashScope API Key 使用独立 macOS Keychain 项，不以明文写入普通配置。
- 数据库版本升级并增加 `asr_jobs`。
- `SubtitleSource` 增加可观察的 ASR 来源，并记录 provider 与 model。
- 页面增加 ASR 开关、连接测试、“立即生成字幕”、ASR 来源标识、当前阶段和冷却时间。

## Technical Constraints

- 继续使用本地 FastAPI、SQLite、launchd 和串行同步。
- 不修改 submodule，不新增 DashScope、OSS 或音视频处理 SDK。
- 自动 ASR 每轮最多提交 1 个视频。
- Paraformer 结果链接有效期有限，必须尽快下载到本地；结果过期时按可重试失败处理。
- API Key 不得出现在日志、数据库、配置明文或页面响应中。
- 临时音频不得暴露为网页下载接口。

## Change Boundary

允许修改：

- `src/shiliu/config.py`：ASR 配置与 Keychain 引用。
- `src/shiliu/domain.py`：粗粒度状态和 ASR 字幕来源。
- `src/shiliu/db.py`：迁移和 ASR 任务记录。
- `src/shiliu/bilibili_bridge.py` 和 `src/shiliu/bilibili.py`：调用现有上游音频能力。
- `src/shiliu/pipeline.py` 和 `src/shiliu/sync.py`：触发、恢复和下游 profile 路由。
- `src/shiliu/web.py`、模板和静态文件：设置、按钮和状态。
- `tests/`：单元、接口和恢复测试。
- 新增 `src/shiliu/asr.py`，仅包含最小接口、Paraformer 调用与结果规范化。

默认不允许修改：

- `references/upstreams/bilibili-cli`
- 收藏夹排序、同步优先级和现有摘要结构
- launchd 安装结构
- 现有 OpenAI-compatible Provider 行为

跨出上述边界必须停止并请求批准。

## Complexity Budget

允许：

- 一个同文件内的最小 ASR Protocol。
- 一个 Paraformer 实现。
- 一次数据库迁移和一个 ASR 任务表。
- 复用现有 `httpx`、SQLite、后台线程和进程锁。

不允许新增：

- 通用插件注册系统或 ASR package 层级。
- 新任务队列或常驻 Worker。
- DashScope SDK、OSS SDK、ffmpeg 等新依赖。
- 并行 ASR 批处理。
- 第二种 ASR Provider。

如实际音频格式必须依赖 ffmpeg 或 PyAV 转换，实施必须停止并重新确认。

## Architectural Integrity Review

- ASR 是“字幕来源获取”的新分支，不是第二套原文／摘要 Pipeline。
- `asr_jobs` 的新表仅因 Paraformer 具有外部异步 `task_id`、过期和跨进程恢复需求而存在，不延伸为通用任务引擎。
- `trigger_mode` 属于 ASR 任务本身，避免调度进程类型污染 DeepSeek profile 选择。
- ASR 细阶段不进入 `VideoStatus`，避免全局视频状态机被单一 Provider 污染。
- 单一 `asr.py` 和 Protocol 已是当前所需的最大抽象程度；未出现第二个 Provider 前不得拆 package 或建 registry。
- 现有 SyncService、PipelineService、后台线程和进程锁仍是唯一编排边界；不增加新 daemon、queue 或 worker。

## Error Handling and Recovery

- 进程退出后根据 `task_id` 恢复轮询。
- 临时 URL 失效但任务未完成时，按冷却策略重新上传并提交。
- 结果已完成但下载失败时，优先重试下载，不重新计费。
- 数据库迁移前生成备份。
- ASR 失败不得破坏现有视频、收藏夹成员关系或字幕状态。
- 最终失败后页面提供明确原因和人工重试入口。

## Acceptance Criteria

- 5 分钟以内的视频在三次无字幕后可自动进入 ASR。
- 超过 5 分钟的视频不会自动调用 ASR。
- 手动 ASR 下游始终使用“立即点击”DeepSeek 路径；自动 ASR 使用定时正式路径。
- 重复点击不会产生第二个任务，冷却时间和剩余时间可观察。
- 进程重启后可恢复任务，ASR 完成后本地临时音频已删除。
- Paraformer 结果包含递增时间戳并进入现有整理与摘要流程。
- `BV1ToTy6tEyc` 完成一次真实端到端处理。
- API Key 未进入普通文件、数据库、日志或响应。
- 批准时现有 36 项测试继续通过。
- 实现不包含 Non-goals 排除的能力。

## Verification Plan

自动验证：

```bash
.venv/bin/python -m pytest -q
```

新增测试至少覆盖：

- 300 秒边界和 301 秒仅允许手动。
- 手动与自动 DeepSeek profile 路由。
- 重复点击幂等。
- 10／30 分钟冷却和第三次失败。
- 任务恢复。
- Paraformer JSON 到 `SubtitleSegment` 的转换。
- 临时音频清理。
- API Key 不落盘。
- ASR 细阶段不扩张 `VideoStatus`。

真实验证：

- 仅使用 `BV1ToTy6tEyc`。
- 记录 Paraformer `task_id`、耗时和计费时长。
- 检查 `AI Agent` 等术语。
- 检查时间戳递增并覆盖主要语音。
- 验证原文和摘要生成。
- 验证临时音频删除。

## Risks

- 中英文技术词识别错误。
- B 站音频地址或格式发生变化。
- DashScope 临时上传或结果链接过期。
- 电脑长时间睡眠导致结果获取延迟。
- 手动长视频产生较高费用。

## Assumptions

- 用户会提供有效的 DashScope API Key。
- DashScope 临时存储适用于当前个人、低并发场景。
- 自动 ASR 每轮最多处理 1 个可以接受。
- 当前上游下载的低码率音频格式可被 Paraformer 直接接受。
- `BV1ToTy6tEyc` 仅作为一次明确授权的真实测试。

## Open Questions

没有阻塞本 Spec 的开放问题。

## Stop and Escalation Conditions

实施遇到以下情况必须停止：

- 音频必须依赖 ffmpeg、PyAV 或其他新依赖转换。
- 必须修改 `bilibili-cli` submodule。
- DashScope 临时上传不支持实际音频格式。
- 需要自建 OSS、任务队列或常驻 Worker。
- 无法保证音频删除或 API Key 不落盘。
- 手动／自动 DeepSeek 路径无法可靠持久化区分。
- 真实测试将调用选定视频之外的 ASR。
- 需要扩大为通用多 Provider 框架。
- 任一 Acceptance Criterion 无法满足。

## Approval

- Approver：用户
- Approval statement：“批准，落盘后自检架构，防止简单新增功能污染架构”
- Approval date：2026-07-15
