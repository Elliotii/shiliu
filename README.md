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
- Durable Research、prior-Evidence continuation 与 Personalization 在明确权限、
  版本和 Receipt 边界内复用已经落地的证据。Knowledge Draft 支持不可变版本、
  Citation/Evidence lineage 和显式确认门，但高质量 Candidate 内容物化及
  durable-Knowledge-native reuse 尚未被 V5.6 验收。

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

## 安装与本地运行

当前公开版本面向 macOS 和 Python 3.10+。仓库使用公开的 `bilibili-cli` 子模块；
克隆时请一并初始化：

```bash
git clone --recurse-submodules <your-fork-or-repository-url>
cd Shiliu
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/shiliu serve
```

如果已经普通克隆，可补执行 `git submodule update --init --recursive`。首次启动会在
用户目录创建本地配置、数据库和内容目录；仓库本身不附带任何个人收藏语料。
需要远程模型的 Ingestion、Ask、Taxonomy 或 Research 功能时，通过环境变量或系统
Keychain 提供 Provider API key。只查看界面、运行本地测试和词法检索不需要凭据。

Qwen Dense/Hybrid 检索是可选能力：

```bash
.venv/bin/pip install -e '.[qwen]'
export SHILIU_QWEN_MODEL_PATH=/absolute/path/to/Qwen3-Embedding-0.6B
```

模型文件不会随仓库分发；默认查找
`~/.cache/shiliu/models/Qwen3-Embedding-0.6B`，不可用时应明确视为本地模型尚未就绪。

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

演示路径见 `DEMO_GUIDE.md`，实现与测试证据映射见
`PORTFOLIO_EVIDENCE_INDEX.md`。公开仓库不分发真实语料运行报告；相关能力以代码、
合成测试和用户在自有数据上的本地验证为准。

## 明确边界

拾流是个人本地产品，不宣称大规模分布式、高并发生产系统、通用多模态理解、
GraphRAG、自动自我进化或普适 Research Agent。仓库不提交个人数据库、Cookie、
API Key、私人收藏夹 URL、个人 transcript、Provider 原始 payload 或模型缓存。

本快照以 `accepted_with_limitations` 发布：Provider 联机路径、真实收藏夹全量同步、
本地 Qwen 模型和 LaunchAgent 需要使用者自己的凭据、数据与 macOS 环境验证；公开
测试不等价于完整内部 Eval 的复现。Knowledge Draft 的持久化和 lineage 已保留，
但 Candidate prose 的语义来源仍有已知缺陷，因此本版本不宣称高质量长期 Knowledge
内容物化或 durable Knowledge 原生复用。
