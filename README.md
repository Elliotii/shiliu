# 拾流 Shiliu V2

拾流是一个只在本机运行的 B 站收藏阅读与内容管理工具。它使用一个只读 B 站登录读取多个公开收藏夹，通过 OpenAI-compatible 模型生成整理原文和结构化摘要，并提供阅读状态、Mark、归档与人工笔记。

当前 V2 需求和验收边界见 [`docs/specs/2026-07-15-shiliu-reading-mark-notes.md`](docs/specs/2026-07-15-shiliu-reading-mark-notes.md)。多来源与双处理路径见 [`docs/specs/2026-07-15-shiliu-v1.md`](docs/specs/2026-07-15-shiliu-v1.md)，无字幕兜底见 [`docs/specs/2026-07-15-shiliu-paraformer-asr-fallback.md`](docs/specs/2026-07-15-shiliu-paraformer-asr-fallback.md)。

## V2 能力

### 收藏与同步

- 通过公开收藏夹 URL 添加多个来源，按账号、收藏夹或全部来源浏览。
- 支持只处理新增、导入最新 N 条或导入全部历史；历史积压每轮最多处理 8 条。
- “立即同步”先生成快速版，定时同步生成正式版并精修已有快速结果。
- 定时任务每小时运行；当前临时取消 05:00–11:59 静默时段，自动发现、精修和失败重试全天可运行。
- 同步在后台运行，关闭页面不会中断；重复点击会连接已有任务进度。

### 字幕与 AI 内容

- 只处理 P1，优先选择中文字幕，其次英文字幕。
- 无中英文字幕时，5 分钟以内的视频可自动使用 Paraformer-v2；更长视频可手动触发。
- 生成轻度整理的完整原文、结构化 AI 总结、重要章节、实体、可执行事项和相关链接。
- 保存封面、原始带时间戳字幕、整理原文、摘要 JSON 和 Markdown 本地资产。

### 阅读管理

- 三档手动阅读状态：未阅、正在阅读、已阅；已阅卡片自动弱化。
- 独立 Mark 标记、渐变强调外框和 Mark 内容筛选。
- 独立归档视图及恢复，保留阅读状态、Mark、忽略状态和笔记。
- 一条视频支持多条人工 Markdown 笔记，点击编辑、失焦保存和轻量删除。
- 同一视频位于多个收藏夹时显示多张来源卡片，但共享字幕、摘要和用户状态。
- 视频重新流入时复用已有内容，不重复调用 ASR 或 LLM。

## 开发运行

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest
.venv/bin/shiliu serve
```

默认页面只监听 `127.0.0.1:18520`。测试可通过 `SHILIU_STATE_DIR` 和 `SHILIU_CONTENT_DIR` 覆盖本地目录。
