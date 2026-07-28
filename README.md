# 拾流 Shiliu — V0–V3.5 Final Baseline

拾流是一个本地运行的 Bilibili 收藏阅读、检索和证据充分性系统。截至
V3.5，项目已经完成从收藏同步与内容处理，到可搜索视频证据库，再到细粒度
Evidence 与 Sufficiency 判断的完整基础链；它尚不生成最终答案，也不是
Agentic Search 系统。

当前仓库状态以以下文件为准：

- `SHILIU_V0_TO_V3_5_FINAL_CLOSEOUT.md`
- `SHILIU_V0_TO_V3_5_FINAL_REPOSITORY_MANIFEST.md`
- `SHILIU_V0_TO_V3_5_FINAL_REPOSITORY_MANIFEST.json`
- `V3_CLOSEOUT.md`
- `V3_5_FINAL_CLOSEOUT.md`

`V3_CURRENT_STATE.md` 与 `V3_5_CURRENT_STATE.md` 仅保留为历史状态记录，已经
标记为 superseded。

## 已完成能力

### V0–V2：产品与数据管线

- 多收藏夹同步、增量导入和后台处理；
- 字幕优先、受限 ASR fallback、原始 Artifact 保存；
- AI 整理与结构化摘要；
- 阅读状态、Mark、归档和人工 Markdown 笔记；
- FastAPI、Jinja、SQLite 和本地文件资产组成的产品界面。

### V3：检索

- 可重建、可增量维护的 Video/Transcript Retrieval Unit；
- FTS5 Lexical、Qwen Dense、RRF Hybrid 和确定性 Auto Router；
- 产品过滤、同视频聚合、证据窗口和粗粒度时间跳转；
- `POST /api/search`、Web Search、Raw/Presentation Trace 与类型化错误；
- 冻结 Snapshot、人工 pooled/judged Gold 和正式 Retrieval Eval。

V3 的正式决定和收口见 `SHILIU_V3_VERSION_DECISION.md` 与
`V3_CLOSEOUT.md`。

### V3.5：Evidence 与 Sufficiency

- Evidence Identity、Source Version、Timeline、Segment 和时间范围；
- `SearchCandidateSet` 到 `EvidenceCandidateSet` / `EvidenceBundle`；
- 固定 Candidate Builder、Fine Selector、Mechanical Gate；
- Semantic Sufficiency 四状态判断；
- `POST /api/evidence-sufficiency`、Trace 查询和 Search UI 集成；
- Product Query Set、Development/Frozen 分离、预测先冻结后开 Gold 的正式评测。

V3.5 的成熟度是：

```yaml
implementation: implemented
integration: minimally_product_integrated
operation: limited_pilot
evaluation: formally_evaluated_below_target
maturity: partial
```

## 明确限制

- V3.5 Frozen Evaluation 的 Retrieval Hit@10 为 1.0，但 Candidate Builder
  complete-group availability 为 0.0，EvidenceBundle complete-group hit 为
  0.0，Semantic four-state accuracy 为 0.2。
- Semantic Judge 仍有明显延迟，生产代理超时配置不在仓库内。
- Fine Builder/Selector 是冻结历史实现，不应成为后续版本不可替换的硬依赖。
- Final Answer generation、Agentic Search、Memory、Harness 和自动补证闭环均未实现。
- 当前能力不是已经证明稳定日常使用的 `production-used`。

README 只记录聚合结果。具体 Eval Query、Gold、视频标识、字幕证据和逐 Case
结果只存在于受访问边界约束的正式 Artifact 中，不在总览文档展开。

## 开发运行

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest
.venv/bin/shiliu serve
```

默认服务监听 `127.0.0.1:18520`。本地状态和内容目录可通过
`SHILIU_STATE_DIR` 与 `SHILIU_CONTENT_DIR` 覆盖。

默认 `pytest` 是确定性核心套件。需要外部历史 workspace 或本机产品数据库的
测试使用 `external_artifact` 标记；需要实时 Provider 的测试使用
`live_provider` 标记，必须通过单独命令显式执行。

## 本地数据政策

仓库不提交个人数据库、完整收藏数据、Provider 原始日志、模型缓存、批量中间
Trace、临时导出和可再生运行目录。正式仓库只保留最终 Closeout、Manifest、
必要 Seal/结果、最小测试 Fixture；未脱敏 Case-level Trace 不进入最终包。
