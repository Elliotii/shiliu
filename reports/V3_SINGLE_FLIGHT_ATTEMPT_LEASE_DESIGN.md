# V3 Provider Single-Flight / Attempt Lease Design

## 竞态路径

当前 `TaxonomyWorkflow._model_stage()` 会先把 Stage 标记为 `processing`，随后按既有 Attempt 目录调用 `AuditedJsonCaller`。恢复时，两个进程都可能读取到同一份 `audit.json`，同时判断“尚无 Raw”，再各自调用 Primary；Schema 失败后，Repair 路径也会重复进入。`audit.json.status=requesting` 只是业务审计字段，不具备原子互斥能力。

## 锁粒度

Single-flight key 为：

```text
run_id / stage_name / unit_key / attempt_id / request_kind
```

`request_kind` 至少区分 `primary` 与 `json_repair`。不同 Unit 使用不同 Attempt 目录和 Lease，因此仍可并行；同一 Unit、同一 Attempt、同一请求类型只允许一个 Owner 调用 Provider。

## 原子实现

采用 macOS 本地文件系统的 `O_CREAT | O_EXCL` 创建 Lease 文件，并以 `fsync` 保证“Owner 与 requesting 状态先持久化，Provider 后发送”。它提供跨进程原子性、崩溃后可审计状态和零外部依赖，符合拾流 local-first 单体架构；不需要 Redis、Celery 或外部锁服务。

## Lease 字段

Lease v1 保存：run/stage/unit/attempt/request kind、state、owner UUID、PID、hostname、acquired/heartbeat/expires 时间、稳定 idempotency key、prompt/schema hash、Provider 请求/响应时间、Raw 路径、response ID、release reason。

稳定 idempotency key 由以下字段做 SHA256：

```text
run_id + stage_name + unit_key + attempt_id + request_kind
+ prompt_hash + schema_hash
```

当前 OpenAI-compatible Provider 未暴露幂等 Header 接口，因此 key 先进入本地 Lease 与 Ledger；未来 Provider 支持时可以透传，不改变本地协议。

## 状态机

```text
prepared
  → requesting
  → response_received
  → persisted
  → completed

requesting → failed
requesting → abandoned（仅过期、Owner 已死、且无 Raw/Ledger/response marker）

response_received / persisted → validation_failed
validation_failed → repair_requesting（独立 json_repair Lease）
repair_requesting → response_received → persisted → completed
```

Lease 只控制并发，不决定 Schema、Semantic、Reviewer 或 Freeze Gate。

## 第二进程与恢复

- 有效 Lease：返回 `provider_already_in_progress`；不新建 Attempt、不写 Audit、不调用 Provider。
- 已有不可变 Raw/Ledger：直接从 Raw 解析，不重发。
- Lease 过期但 Owner 信息缺失或 Owner 仍存活：保守拒绝重发。
- Lease 过期、Owner 确认死亡、无 Raw/Ledger/response marker：原子创建 takeover marker，将旧 Attempt 标记 `abandoned`；唯一接管者创建新的 Attempt 目录。
- 同步阻塞 Provider 调用期间由轻量 heartbeat thread 刷新 Lease；timeout 与 heartbeat interval 可由配置/环境覆盖，测试可缩短。

## Immutable Response Ledger

新响应写入：

```text
attempt-XX/responses/<request_kind>/response-<response-id-or-hash>.txt
```

Raw 文件用排他创建且永不覆盖。`provider-response-ledger.jsonl` 只追加 response/accepted 事件；`accepted-response.json` 仅保存唯一被采用 Raw 的引用。旧 `raw-response*.txt` 与 `repair-raw-response*.txt` 只读兼容，不迁移、不重写。

## 失败恢复与审计

每次请求审计必须能关联 Lease owner、idempotency key、不可变 Raw hash、Ledger event、usage、耗时与 finish reason。若 Provider 已返回但业务 Audit 未更新，只要 Ledger/Raw 存在，Resume 就从 Raw 开始。Primary 与 Repair 使用独立 Lease 和 Ledger 事件。

## Trial Assignment 前门禁

只有 10 类 Mock 并发/恢复测试、全量测试和 Run #24 冻结 Hash 对比全部通过，才生成 `trial-assignment-engineering-gate.json` 并把 Run 更新为 `trial_assignment_ready`。本检查点不会启动 Trial Assignment。
