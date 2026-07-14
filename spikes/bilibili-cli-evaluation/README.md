# bilibili-cli Technical Spike

本目录只验证拾流 V0 当前需要的只读能力：登录、单个收藏夹、分页、视频元数据、字幕和结构化错误契约。

明确排除：

- 音频下载、音频切片和 ASR；
- B 站 AI summary；
- 点赞、投币、关注、取消收藏、动态等账号写操作；
- 高并发和压力测试。

## 固定规则

- 首次扫描只建立收藏夹基线，不处理历史项目；
- 一个 BV 是一个内容项；V0 只获取并总结 P1；
- 预留 `process_all_parts: false` 开关，但 V0 不实现多 P 字幕和多 P 摘要；
- 字幕选择顺序为中文、英文、跳过；
- 每份保存的字幕必须记录来源：`human`、`ai` 或无法识别时的 `unknown`，并保留上游原始 `type` 值；
- 无合格字幕时记录 `SKIPPED_NO_TRANSCRIPT`；
- 目标只绑定一个收藏夹；
- 取消收藏不删除本地资产；
- 原始响应只保存脱敏证据，凭证不进入工作区。

## 上游快照

- Repository: `https://github.com/public-clis/bilibili-cli.git`
- Commit: `dbe28551930df43b633baa52e9639832aeada967`
- Source version: `0.6.2`
- PyPI latest during evaluation: `0.6.2` (2026-03-11)
- License declared by bilibili-cli: Apache-2.0
- Direct runtime dependency: `bilibili-api-python 17.4.2`, declared GPL-3.0-or-later

## 隐私

真实凭证保存在上游默认位置 `~/.bilibili-cli/credential.json`，实测权限为 `0600`。本目录不保存 Cookie、账号 ID、用户名、收藏夹名称或私人视频标题。
