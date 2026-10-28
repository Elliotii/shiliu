# Schema 0014 的 PG + Artifact 配对备份

入口：`python -m shiliu.migration.backup_cli create|verify|restore`。复用原 W14 writer/restore、typed row hash 和 Artifact Hash；只接受精确 marker 绑定的隔离实例或已有正式实例，不是通用备份平台。

## 前置条件

1. 人工停写 Web、Assistant/投影 Worker、收藏同步及其他写入者，禁止并发启服/定时任务。工具不会停服务；`--writers-stopped` 是操作者确认，另检查同库无其他连接，并在 dump 前后比较完整报告。这不是可以热备份的承诺。
2. 明确 `SHILIU_DATABASE_URL`、`SHILIU_ARTIFACT_ROOT`、`SHILIU_ENV`。使用绑定 ETL 角色；禁止猜测 DSN、默认目录或邻近环境。原 exact binding、实例版本/目录校验、私有权限和路径保护仍生效。
3. 备份目录必须是该资源根下 `backups/w14_<唯一名字>` 的新目录。PG18.6 + vector0.8.7 + pg_textsearch1.5.1；Schema 必须为 `0014_assistant_source_patch`。
4. `migrations/contracts/runtime_0014_catalog.json` 是干净隔离升级产生并独立核对的结构合同，覆盖132张表（含 alembic）、新增消息表和 Proposal 字段/约束。它不包含业务数据。未知版本/结构漂移拒绝，不自动接受当前库作为自己的合同。

## 备份与离线检查

```bash
# 环境已经显式设置为所需 ETL 目标；路径必须属于匹配资源根。
python -m shiliu.migration.backup_cli create /absolute/bound-root/backups/w14_release_backup --writers-stopped
python -m shiliu.migration.backup_cli verify /absolute/bound-root/backups/w14_release_backup
```

输出包含 dump hash、Schema 与对象数；`pair.json` 保存完整 typed row hash、catalog、identity sequence高水位和现存迁移 rebuild audit（不存在则明确为 null）。备份含完整 `pg_dump --format=custom`、全部已登记 Artifact 对象及 manifest。SQL NULL/JSON null 不混同；文件 hash/size 被验证。失败留下现场，不将无 `pair.json` 或验证失败的目录当作可用备份；不要覆盖或复用失败目录。

## 恢复

**只恢复到独立空数据库及空 Artifact 根。** 不覆盖源库，不在原目录做“试恢复”。先预装精确的 vector/BM25 扩展及空 schema；目标同样必须满足已有资源绑定。`--admin-url` 仅传精确绑定的管理员连接（不得放密码）；普通 ETL 环境指向该恢复目标。

```bash
python -m shiliu.migration.backup_cli restore /absolute/bound-root/backups/w14_release_backup --writers-stopped --admin-url 'host=/absolute/bound-socket port=55483 dbname=bound_restore_database user=bound_admin'
```

上面连接是说明形状的占位符，实际必须符合 marker、库名、端口、角色和 Artifact 对应关系。恢复仅略过已验证的扩展 bootstrap DDL，保留全量表/数据/约束/Trigger；重新授予原 runtime/etl 权限。恢复后重算完整 runtime report 与配对 manifest 相等才报告成功。失败不自动清库或重试，保持停写并调查；启动或切换入口仍由独立运维授权决定。

回退到备份会失去备份之后的新写入；PG 与 Artifact 必须成对选择。确认旧 Wheel 与恢复后的 Schema 兼容，不能只降包而忽略0013/0014结构。备份及 manifest 含私有数据，永不提交 Git。
