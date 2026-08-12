# Post-V5 Current Work Environment Report

检查时间：2026-08-11（Asia/Shanghai）

检查方式：Git、remote ref、LaunchAgent submitted process 和 onboarding state 的只读检查。除按用户要求新增本报告外，未修改代码、配置、数据库或 LaunchAgent，未中断当前 ingestion。

## 1. Current Git branch

```text
codex/post-v5-product-closeout
```

## 2. Current HEAD

```text
ad1d93562f89318f25282a801466299ccc2c7867
```

Commit subject：

```text
fix(sync): accept complete visible favorite snapshots
```

## 3. Remote push status

已 push。

本地 HEAD、本地 remote-tracking ref 和远端 `refs/heads/codex/post-v5-product-closeout` 均为：

```text
ad1d93562f89318f25282a801466299ccc2c7867
```

## 4. Working tree status

不 clean。

在新增本报告之前，working tree 包含 1 个 modified 文件和 5 个 untracked 文件；均为 Markdown 文档，没有源码、配置、数据库或 LaunchAgent 变更。

新增本报告后，本报告本身也是一个 untracked Markdown 文件。

## 5. Modified / untracked files

### Modified

| 文件 | 分类 | 说明 |
|---|---|---|
| `README.md` | 产品/Portfolio 文档 | 非源码、非配置、非运行时状态 |

### Untracked（检查前已存在）

| 文件 | 分类 | 说明 |
|---|---|---|
| `DEMO_GUIDE.md` | 产品/演示报告 | 非源码、非配置、非运行时状态 |
| `PORTFOLIO_EVIDENCE_INDEX.md` | Portfolio 报告 | 非源码、非配置、非运行时状态 |
| `POST_V5_PRODUCT_CLOSEOUT.md` | Closeout 报告 | 非源码、非配置、非运行时状态 |
| `POST_V5_QUERY_PERSISTENCE_AUDIT.md` | Persistence 审计报告 | 非源码、非配置、非运行时状态 |
| `SHILIU_CURRENT_LLM_CALL_INVENTORY.md` | LLM 调用清单报告 | 非源码、非配置、非运行时状态 |

### Untracked（本次按要求新增）

| 文件 | 分类 | 说明 |
|---|---|---|
| `POST_V5_CURRENT_WORK_ENVIRONMENT_REPORT.md` | 环境事实报告 | 本报告；非源码、非配置、非运行时状态 |

当前 Git working tree 内没有本地运行时文件。真实数据库、onboarding state 和日志位于仓库外的 Shiliu Application Support 目录，不属于 Git working tree。

## 6. Running ingestion code basis

当前 600+ ingestion 进程仍在运行：

```text
process label: app.shiliu.onboarding
PID: 5531
started: 2026-08-11 15:48:57 +0800
phase: all_history
```

它基于以下 branch / HEAD 启动：

```text
branch: codex/post-v5-product-closeout
HEAD: ad1d93562f89318f25282a801466299ccc2c7867
```

事实依据：

- `ad1d935` 的 commit time 为 2026-08-11 15:48:11 +0800；
- onboarding 进程于 2026-08-11 15:48:57 +0800 启动；
- 启动前该 commit 已创建并 push；
- 当前 branch 和 HEAD 仍为该 commit；
- 当前 tracked source/config 相对该 HEAD 没有任何修改；
- 当前未提交差异全部为 Markdown 文档。

因此当前运行进程使用的实现与 `ad1d935` tracked source 一致。

## 7. Stable checkpoint status

### Model Routing / Provenance

已完成、已 commit、已 push。

```text
7e784245370c7e6895427b05242715d6b743b65b
feat: isolate model roles and record artifact provenance
```

该 commit 是远端 `origin/codex/post-v5-product-closeout` 的祖先。

### Backfill / Continuous Sync / Source UI

已完成、已 commit、已 push。

主要 checkpoint：

```text
0f3f613395587996c25daa8d413b4e77b2c6c268
feat: add safe historical favorites backfill
```

该 commit 是远端 `origin/codex/post-v5-product-closeout` 的祖先。

后续与真实 rollout 有关的 bounded fixes 也已经全部 commit/push，直至当前远端 HEAD `ad1d935`。

## 8. Uncommitted source changes required by a later Persistence Session

不存在。

当前没有任何尚未 commit 的源码、schema、配置、测试或 LaunchAgent 修改需要 Persistence Session 继承。

后续 Session 如需继承当前工程实现，应从：

```text
codex/post-v5-product-closeout
ad1d93562f89318f25282a801466299ccc2c7867
```

开始。当前未提交内容仅为文档/报告。
