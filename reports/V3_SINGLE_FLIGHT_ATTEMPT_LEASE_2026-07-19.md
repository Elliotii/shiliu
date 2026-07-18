# V3 ENG-DRAFT-A-002 Single-Flight / Attempt Lease Report

## Outcome

```text
Engineering Gate: PASS
Run #24: waiting_for_review / trial_assignment_ready
trial_assignment_eligible: true
Trial Assignment: not_started
Real Provider calls in this checkpoint: 0
```

本检查点只修复 Provider 调用并发控制与恢复审计，没有修改 M1、M2、M3、Domain Draft A、Hierarchy Review 或 Draft A Tree，也没有读取 Silver Reference。

## Incident recap

Draft A 恢复时，foreground 与后台恢复进程读取到同一 `audit.json`，都把“尚无可用 Raw”解释成可以发送请求。因为 `audit.json.status` 不是原子锁，最终同一逻辑 Attempt 产生 2 个 Primary 和 2 个 JSON Repair Response；其中 1 个 Repair 的 usage 无法恢复。该事故继续保留在既有 Draft A Response Ledger，未被改写成正常单调用。

## Final concurrency contract

Single-flight key：

```text
run_id / stage_name / unit_key / attempt_id / request_kind
```

`request_kind` 明确区分 `primary` 和 `json_repair`。同一 Key 同时只允许一个合法 Owner；不同 Batch Unit 仍可并行。原子性通过 macOS 本地文件系统 `O_CREAT | O_EXCL` 实现，JSON 更新使用临时文件、`fsync` 和原子 replace；无需 Redis、Celery 或外部锁服务。

Lease 保存 Owner UUID、PID、hostname、acquired/heartbeat/expires 时间、Prompt/Schema Hash、稳定 idempotency key、Provider 请求/响应时间、Raw 引用、response ID 和 release reason。同步阻塞请求期间由轻量 heartbeat thread 续租，默认 900 秒 Lease、15 秒 heartbeat，均可配置。

状态路径：

```text
prepared → requesting → response_received → persisted → completed
requesting → failed
response_received/persisted → validation_failed
prepared → repair_requesting → response_received → persisted → completed
expired + owner dead + no response evidence → abandoned → new Attempt
```

Lease 只证明调用所有权，不参与 Schema、Semantic、Reviewer 或 Freeze Gate 判断。

## Recovery behavior

- 有效 Lease：第二个进程返回 `provider_already_in_progress`，不调用 Provider、不创建 Attempt、不覆盖审计。
- Ledger 已有 Raw：直接解析、校验，必要时进入独立 Repair Lease；Primary 不重发。
- Lease 过期但 Owner 仍存活或无法确认：保守拒绝重发。
- Lease 过期、同机 Owner 已确认死亡、且无 Raw/Ledger/response marker：原子写 takeover marker，将旧 Attempt 标记 abandoned；恢复入口创建新的 Attempt。
- Provider 或 Repair 已失败：同一 Attempt 不重发；工作流创建新 Attempt。
- 已完成 Stage 被并发 Runner 再次观察到时，Repository 原子返回 completed 结果，不增 Attempt、不重放 Provider。

## Immutable response ledger

新响应保存为：

```text
attempt-XX/responses/primary/response-<response-id-or-hash>.txt
attempt-XX/responses/json_repair/response-<response-id-or-hash>.txt
```

Raw 使用排他创建，内容冲突立即失败；append-only `provider-response-ledger.jsonl` 保存 response ID、request kind、Attempt、Owner、Raw SHA256、usage、耗时和 finish reason。`accepted-response.json` 只保存唯一采用响应的引用。历史 `raw-response*.txt` 与 `repair-raw-response*.txt` 不迁移、不重写，恢复适配器仍可只读。

## Test matrix

| Scenario | Expected Provider count | Result |
|---|---:|---|
| 同 Attempt 双进程 Primary | 1 | PASS |
| 不同 Unit 并行 | 2 | PASS |
| Primary Raw 后崩溃并 Resume | 1 | PASS |
| 同 Attempt 双进程 Repair | Primary 1 / Repair 1 | PASS |
| 过期 Lease 且 Owner 死亡 | old abandoned / new Attempt 1 | PASS |
| Owner 信息缺失 | 0，保守拒绝 | PASS |
| Raw 已落盘但 Audit 未更新 | 仍为 1 | PASS |
| foreground + recovery runner | 每种 request kind 最多 1 | PASS |
| 多 Raw 与唯一 accepted pointer | 无覆盖 / accepted 1 | PASS |
| 历史 Raw 兼容 | 读取且不重写 | PASS |

定向并发/恢复测试 10 / 10 与 Attempt 计数事务测试通过；全量测试 288 / 288 通过；`git diff --check` 通过。测试 Provider 为可计数、可阻塞 Fake，本轮没有真实 Provider 请求。

## Frozen hash verification

| Artifact | Before SHA256 | After SHA256 | Result |
|---|---|---|---|
| M1 Domain Semantic Contract v2 | `d10bbe8027e0858baff9897be34b51a91958afb8375ac9e5b8b27e469dec258a` | same | PASS |
| M2 Unresolved Final | `2b7ce02aead4d33e263e5357b5e555586e2bc17a7db57ce9e4523cbb9eb7550a` | same | PASS |
| M3 Final Clusters | `de67704a5d6f68c807ee2fd93d8f42e25a08d7cc1c81e60e1019daf8a6b5edd3` | same | PASS |
| M3 Final Decisions | `aa21cac07730a335503d99d7f672e89a7d3f420ef09b5a5c8198e45efe3a13ee` | same | PASS |
| M3 Final Review | `ce6a2834ee36d00c6b2fa256b0a9c7483d3022502ed43cd95b47d252c27af30d` | same | PASS |
| M3 Final Gate | `69b31d88c0edf36ac4720bb1c7ab164932b53a48cac849ee73301704028b1993` | same | PASS |
| M3 Final Manifest | `7cf8f7cd0add7068c80334baabad43b6d8486cdbb2ce520483eb7c6547c4ac1e` | same | PASS |
| Canonical Domain Draft A | `9374212a8d29b289cbfcca4c031cf7702c3c92b897f0c6082fd8557dd1623787` | same | PASS |
| Draft A Tree | `30332f6ef33397f1de08b3cf7d4b569927c2cc847075443374a390a1f105e091` | same | PASS |

以上为文件字节 SHA256。独立私有 Gate 保存完整 before/after 对照；既有 Draft A Manifest 未被修改。

## Eligibility and remaining risk

`trial-assignment-engineering-gate.json` 已独立重算并通过，blocking findings 为空。Run #24 已清除旧错误字段并更新为 `waiting_for_review / trial_assignment_ready`，数据库中不存在 Trial Assignment Stage，Gate 明确记录 `trial_assignment_started=false`。

剩余风险只有保守恢复策略：跨主机或 Owner 信息不足时，系统不会自动判断 Lease 可接管；需要人工核验。这会优先造成暂停，不会造成重复扣费。M6 仍需用户另行授权后才可启动。
