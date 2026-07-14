# 拾流 Shiliu

拾流是一个只在本机运行的 B 站收藏内容整理工具。V1 可以用一个只读 B 站登录读取多个公开收藏夹，并使用 OpenAI-compatible 模型生成整理原文和结构化摘要。

正式需求和验收边界见 [`docs/specs/2026-07-15-shiliu-v1.md`](docs/specs/2026-07-15-shiliu-v1.md)。

## V1 行为

- 首页“立即同步”中新发现的视频先使用快速字幕模型，再使用正式摘要模型生成快速版。
- 定时同步使用正式模型和 `reasoning_effort=max`；快速版会在后续定时周期中精修。
- 设置页可通过公开收藏夹 URL 添加来源，并选择只处理新增、导入最新 N 条或导入全部历史。
- 历史积压 24 小时可处理，每轮最多 8 条；05:00–11:59 仅暂停自动发现和精修。
- 页面关闭不会停止已经启动的后台同步；重新打开页面可继续查看持久化进度。

## 开发运行

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest
.venv/bin/shiliu serve
```

默认页面只监听 `127.0.0.1:18520`。测试可通过 `SHILIU_STATE_DIR` 和 `SHILIU_CONTENT_DIR` 覆盖本地目录。
