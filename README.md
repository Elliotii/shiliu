# 拾流 Shiliu

拾流是一个本地运行的个人 Bilibili 收藏证据驱动检索与研究助手。它把一个或
多个收藏夹持续同步成本地语料库，保留原字幕或 ASR 时间轴作为事实权威，并在
此基础上提供混合检索、带时间戳引用的问答、深入搜索和可持久化的研究工作区。

## 产品能力

- 收藏夹来源支持稳定时间边界的历史回填：From now、Latest 100/300/500 和
  All。缩小范围只停止继续向旧历史扩展，不删除已经导入的视频、Membership、
  Artifact、索引或用户状态。
- Discovery、History Backfill 与 Continuous Forward Sync 分离。只有完整、
  权威的远端快照才执行 removal reconciliation；不完整分页和临时失败不会把
  “本轮没看到”解释成远端删除。
- 同一视频可以属于多个收藏夹。来源暂停或 Membership 移除只影响该来源，最后
  一个活跃 Membership 消失后才会退出可检索范围。
- Search 使用 FTS5 词法检索与本地 Qwen Dense/Hybrid 检索，不调用远程 LLM。
- Ask Fast 和 Ask Deep 只用当前原字幕/ASR Segment 形成事实 Evidence；回答中的
  Citation 可跳转到 Bilibili 对应时间点。
- Durable Research、Persistent Knowledge 与 Personalization 在明确权限、版本、
  Receipt 和人工确认边界内复用已经落地的证据，不自动把推断写成用户事实。

## Evidence 与模型边界

```text
Bilibili membership
  → subtitle / bounded ASR
  → raw timestamped evidence
  → derived transcript / summary
  → lexical + local dense index
  → Search / Fast Ask / Deep Ask / Research
```

Raw Subtitle / Raw ASR 始终是 Citation Authority。整理稿、结构化 Summary、
章节、Taxonomy 和 User Notes 可以帮助导航，但不能替代原始时间轴证据。

新生成内容使用静态 role mapping：

```text
Transcript cleanup / refinement  → deepseek-v4-flash
Structured summary / refinement  → deepseek-v4-flash
Taxonomy                          → deepseek-v4-pro
Query analysis / agent action     → deepseek-v4-pro
Grounded answer                   → deepseek-v4-pro
Search embedding                  → local Qwen, offline
```

Ingestion、Interactive 与 Taxonomy 配置互相独立。新 transcript/summary artifact
会记录 provider、model、prompt/schema version、generated_at 和 source hash 的
轻量 provenance sidecar；旧 artifact 不重生成，缺失信息明确标为
`legacy_unknown`。历史 Frozen Eval 的模型身份不受这些产品设置影响。

## 本地运行

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/shiliu serve
```

默认页面：

```text
http://127.0.0.1:18520/
http://127.0.0.1:18520/search
http://127.0.0.1:18520/ask
http://127.0.0.1:18520/research
http://127.0.0.1:18520/setup
```

立即同步会先验证完整远端快照并处理 forward changes；“继续历史导入”只消费已经
由权威 baseline 选中的历史队列，复用同一进程锁、pipeline stage、retry 与
retrieval coordinator，不重复扫描远端收藏夹。现有 LaunchAgent 每小时触发
scheduled sync，不需要第二套 scheduler。

## 验证

```bash
.venv/bin/python -m pytest
```

Backfill、Sync、Multi-folder 与模型路由定向回归：

```bash
.venv/bin/python -m pytest \
  tests/test_backfill_sync.py \
  tests/test_database_and_sync.py \
  tests/test_v1.py \
  tests/test_pipeline.py
```

演示路径见 `DEMO_GUIDE.md`，能力证据映射见 `PORTFOLIO_EVIDENCE_INDEX.md`，真实
语料上线状态见 `POST_V5_REAL_CORPUS_ONBOARDING_REPORT.md`。

## 明确边界

拾流是个人本地产品，不宣称大规模分布式、高并发生产系统、通用多模态理解、
GraphRAG、自动自我进化或普适 Research Agent。仓库不提交个人数据库、Cookie、
API Key、私人收藏夹 URL、个人 transcript、Provider 原始 payload 或模型缓存。
