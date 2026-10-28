# 拾流 Shiliu

本地运行的个人 Bilibili 收藏知识助手。将收藏夹同步为可追溯的字幕语料，提供检索、带时间戳引用的 Fast/Deep 问答，以及有版本与确认边界的 Assistant、Wiki、Memory。

当前阶段版本 **0.4.0**：PostgreSQL + pgvector + pg_textsearch BM25；Schema HEAD 为 **`0014_assistant_source_patch`**。这是个人本地部署的阶段交付，不是已经验证的公网多用户服务。

## 当前能力

- **Collection**：多个收藏夹、稳定历史回填边界、持续增量同步；仅完整权威扫描判定移除，同一视频可属于多个来源。暂停或缩小回填范围不会删除已导入资料。
- **检索**：PostgreSQL 持久化；字幕 BM25、本地 Qwen Dense、RRF 融合；检索本身不调用远程 LLM。标题、作者、简介的综合发现保留独立 Profile。
- **Fast**：BM25 + Dense + RRF 后使用 Wide-30，按排序交付合法 Top30 原文 Segment，保留精确去重、版本与 Citation 回放。不能把整理稿当成原文。
- **Deep**：Search/Read、Evidence Store、Reduce 和最终证据装填；保持自身 Context 策略，没有随 Fast 切换 Wide-30。
- **Assistant**：持久 Thread/Run、工具循环、SSE 流式交付、检查点与上下文整理。显式 `transcript_chunk` Scope 使用字幕 BM25；默认 `all` 和 Bootstrap 仍是综合检索，不能声称所有字幕问题默认都走 BM25。Search→Read 支持同版本 JSON/TXT 精确锚点和分页。
- **Wiki / Memory**：显式保存、版本与来源依赖、Memory 自动提炼/更正/遗忘；无人值守视频维护的正文增补/修订先确认，安全关联仍可自动处理；显式授权保存不重复确认。
- **消息**：展示真实变更、待确认和重要异常，提供已读/历史筛选、受控 Diff 和来源跳转；只提供业务层证明安全的合法操作，不支持通用撤销。
- 同步保留 PG 租约、Fencing、单机文件锁和有界重试；已修复已确认的 FK 锁竞争/快照事务自阻塞及 Wiki 旧来源 JSON 等价比较问题。

## 证据与模型边界

```text
收藏 Membership → 原字幕 / 有界 ASR → 原始时间轴 Segment
  → 整理稿、摘要及索引投影 → Search / Fast / Deep / Assistant
```

Raw Subtitle / Raw ASR 是引用权威；摘要、章节、标签与笔记用于辅助导航。正式模型角色由 `AppConfig.model_for` 决定：Fast 最终回答固定 `deepseek-v4-flash`，Assistant 默认同型号；Ingestion、Interactive、Taxonomy 分别使用配置的角色映射。Deep 使用 Interactive 配置，不能仅凭模型别名推断 Provider 未来版本不变。API Key 使用本地凭据存储，不提交到 Git。

Embedding 使用离线 `Qwen/Qwen3-Embedding-0.6B`，固定 revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，512 维；不上传到远程 Embedding 服务。

## 安装与运行

已验证环境：macOS arm64、Python 3.12、PostgreSQL **18.6**、pgvector **0.8.7**、pg_textsearch **1.5.1**。Python 包要求 >=3.10；数据库版本/扩展身份会被校验。BM25 需在目标 PG 预装并配置该版本扩展；不是仅 `pip install` 就能准备数据库。

```bash
uv sync --locked --extra test --extra qwen --no-editable
# 使用实际已经初始化的受限数据库连接及独立绝对目录，以下是占位符。
export SHILIU_DATABASE_URL='host=/absolute/socket port=5432 dbname=shiliu user=shiliu_runtime'
export SHILIU_ARTIFACT_ROOT='/absolute/artifacts'
export SHILIU_ENV=development
export SHILIU_STATE_DIR='/absolute/state'
export SHILIU_CONTENT_DIR='/absolute/scratch'
export SHILIU_QWEN_MODEL_PATH='/absolute/Qwen3-Embedding-0.6B'
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
.venv/bin/shiliu serve --no-background
```

运行前由管理员安装扩展、使用专用连接调用 `shiliu.migration.schema.upgrade` 到 HEAD，并调用 `grant_roles` 授权 runtime/etl；运行时角色不能执行 DDL。角色、个人 Workspace 和 Artifact 根必须匹配。详见 [数据库合同](migrations/README.md)、[隔离 PG 验证说明](tests/postgres/README.md)。Qwen 目录需是指定 revision 的完整本地快照，含 `.candidate-revision`；服务不自动下载模型。

`shiliu setup` 配置 B 站 CLI、模型与本地凭据；CLI 上游见 `.gitmodules`，首次使用需完成其本地安装与登录。默认 Web 为 `http://127.0.0.1:18520/`，包括 `/search`、`/ask`、`/assistant`、`/setup`。首次核对使用 `--no-background`，不会自动运行后台处理；自动同步默认关闭，启用前确认 ASR/模型费用。后台运行和小时调度由操作者明确启用，不由安装过程启动。

**已有正式实例的运维入口具有精确资源绑定，不是任意 DSN 的安装器。** 此发布不附正式数据、绑定文件或一键生产部署模板；不要复制他人的私有绑定来绕过校验。Schema 升级前停写并保留 PG + Artifact 配对备份；0014 运维入口见 [备份与恢复](docs/operations/POSTGRES_PAIRED_BACKUP.md)。本次版本整理没有重新部署正在运行的实例。

## 验证与公开成果

- [0.4.0 Release Notes](docs/releases/v0.4.0.md)
- [公开评测摘要与比较边界](docs/releases/POSTGRES_EVALUATION_SUMMARY.md)
- [公开/私有数据边界](docs/PRIVACY_BOUNDARIES.md)

PG 测试使用独立、带 marker 的本地实例；`tests/postgres` 使用随机测试库与 Stub Provider，真实模型/外部历史资产测试默认排除。不要把旧 SQLite 测试直接视为当前全量回归入口，也不要把纯工程测试通过率包装成答案准确率。

```bash
# 先按 tests/postgres/README.md 准备并启动隔离 PG，设置其显式测试连接。
PYTHONPATH=src .venv/bin/python -m pytest tests/postgres/test_runtime_backup.py
node --test tests/js/test_assistant_messages_p1.mjs tests/js/test_assistant_source_patch_p2.mjs
```

## 已知限制

- 自动提炼 Memory 新建的一键撤回暂缓；更正、遗忘、恢复 Wiki 历史版本与撤销某次修改不是同一操作。后续已修改的目标不能强行消息级撤销。
- Test50 已多次用于诊断，不能称为从未接触的盲测集；答案覆盖和引用支持仍有缺口，不宣称零幻觉。
- Research 与历史评测代码保留作既有能力/研究参考，不是本阶段新增正式质量承诺；未新做 Deep/Assistant 大规模真实模型质量评测。
- 数据有用户/Workspace 隔离与版本保护，不等于已经提供完整多用户认证、公网安全或高并发 SLA。仅在可信本地环境运行。
- W14冻结Schema26 ETL直接导入当前0014目标仍受旧合同和空库要求限制，不提供任意旧库一键直迁；本次验证的是0014运行库备份/恢复。
- SQLite 只保留只读迁移/历史资产工具边界，不是正式存储后端。旧源码、Prompt 和历史结果各有版本，不将其与当前 PG 指标混作单变量实验。
