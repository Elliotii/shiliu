# Shiliu Demo Guide

目标：用 6–8 分钟展示“个人收藏 → 权威字幕证据 → 可验证回答 → 持久研究”的完整
产品闭环。演示使用本机已授权语料，不在录屏、截图或公开材料中展示私人收藏夹
URL、Cookie、Keychain、API Key 或本地绝对数据路径。

## 1. Source 与持续同步（约 1 分钟）

打开 `/setup`：

1. 展示 Source status、Continuous sync、Remote detected、Imported、Completed、
   Pending、Failed 和 Not backfilled。
2. 展示稳定 History coverage 与 oldest covered favorite_time。
3. 说明 Latest N 是向历史扩展的稳定边界，不是 corpus 容量上限；未来新增收藏
   始终进入 Forward Sync。
4. 说明缩小范围不删除已导入数据；真正 Purge 不是这个控件的一部分。

## 2. Known-item Search（约 1 分钟）

打开 `/search`：

1. 用一个已知精确标题搜索，确认 exact-title 命中。
2. 用标题中的概念词再次搜索，展示 lexical + local Qwen hybrid 结果。
3. 切换单来源/多来源 scope，确认共享视频不会因一个来源变化而消失。

Search 本身不调用远程 LLM；Summary/Chapter 只用于导航增强。

## 3. Evidence 与时间戳（约 1 分钟）

展开一个搜索结果的 Evidence：

1. 展示字幕类型、Quote、起止时间和 Source Version。
2. 点击时间戳打开 Bilibili 对应位置。
3. 强调原字幕/ASR Segment 是事实权威，Summary 和整理稿不能成为 Citation。

## 4. Ask Fast（约 1–2 分钟）

打开 `/ask`，选择 Fast：

1. 提一个可以由单个或少量视频回答的自然问题。
2. 展示 `complete` / `partial` / `insufficient` 状态与 termination reason。
3. 点击回答 Citation，定位到对应 Evidence Card 与视频时间戳。

## 5. Ask Deep（约 1–2 分钟）

对一个跨视频比较问题显式选择 Deep：

1. 展示有界 Round、Tool、Context 与停止原因。
2. 展示导航材料与最终事实 Evidence 的区别。
3. 若证据不足，保留诚实限制，不把检索噪声包装成答案。

## 6. Durable Research / Knowledge Draft（约 1 分钟）

打开 `/research`：

1. 展示 Research Task、Attempt、Receipt 和 EvidenceUse 的持久 lineage。
2. 展示 Knowledge Draft 的不可变版本、Answer Snapshot、Citation/Evidence mapping
   与显式确认门。
3. 明确说明 Candidate 内容物化仍有语义来源缺陷；不要把 Fact/Artifact/Topic Page
   的结构存在演示成已验收的高质量长期 Knowledge 或原生复用能力。
4. 展示 Personal Workspace/Personalization 只消费明确用户状态，不自动创造偏好。

## 7. Developer closeout（可选）

在不显示 Secret 的前提下说明：

- ingestion 使用 Flash；interactive 与 taxonomy 使用独立的 Pro role mapping；
- 新 ingestion artifact 有轻量 provenance sidecar；旧 artifact 保留并标记 unknown；
- 不完整远端 scan 不执行 removal reconciliation；
- hourly LaunchAgent 复用同一 SyncService 与全局进程锁。

最终以公开测试结果和本机脱敏后的运行状态收尾。不要展示或复制内部运行报告、
Provider 请求/响应、真实 transcript 或绝对数据路径。
