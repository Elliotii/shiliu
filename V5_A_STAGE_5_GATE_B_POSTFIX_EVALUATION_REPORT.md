# 拾流 V5-A Gate B Post-fix Integration Validation Report

```yaml
run_id: GB-20260803T130621Z-da72aa1-postfix
disposition: evaluation_infrastructure_failure_preprovider
entry_gate: pass
credential_access: denied_keychain_-128
provider_calls: 0
http_attempts: 0
cost_usd: 0.000000000
opportunistic_rerun: false
gate_B_self_accepted: false
gate_C_started: false
```

## 1. 有效机械证据

全新 sibling root 从不可变 schema-9 snapshot 形成；隔离工作副本迁移至 schema 10 后
integrity `ok`、FK 0、157 videos / 140 completed、1633 retrieval units / 154 indexed。
schema-9 snapshot 副本保持 `0444`，只有工作 `eval.db` 为 owner-writable `0644`；artifact
tree 只读。五个冻结 Prompt/Tool/Schema blob、原 root manifest/report/snapshot SHA、目标
subtitle SHA 与材料性 corpus/index identity 全部通过。

Stage 1–5 联合定向为 174 passed；run-wide meter 的 logical 17、HTTP 34、input 140000、
output 31984、34 分钟和 US$0.50 总硬门已机械通过。2026-08-03 运行时官方价格仍为
V4-Pro cache-hit 0.003625、cache-miss 0.435、output 0.87 USD / 1M tokens；含峰值与
两次 HTTP reservation 的总最坏费用为 US$0.35490432。

## 2. 正式运行停止事实

Entry Gate 通过后，runner 按授权仅尝试读取一次 existing LLM Keychain reference。macOS
Keychain 返回 `Keychain Access Denied (-128)`，上层分类为 `KeyringLocked`。失败发生在
API key 返回、Task 创建和 Provider factory/transport 之前；secret 未输出、未写 manifest，
Provider Action、SideEffect 和 Research Task 均为 0。

这是 `evaluation_infrastructure_failure`，不是 implementation failure、provider failure 或
product-quality failure。没有重试 credential，没有启动第二个 runner，也没有修改 endpoint、
model、Prompt、Tool/Schema、case、evaluator 或预算。

## 3. Case rubric

| Case | Durable product path | Answer/evidence/audit/HITL rubric | Disposition |
| --- | --- | --- | --- |
| GB-G-01 | not exercised | not exercised | pre-provider credential failure |
| GB-I-01 | not exercised | not exercised | pre-provider credential failure |
| GB-H-01 | not exercised | fixed answer not consumed | pre-provider credential failure |

因此本次 run 不提供新的真实 Provider + durable product orchestration 产品质量证据，不覆盖
原 run `GB-20260803T081500Z-be96740` 的诊断地位，也不构成完整 Gate B 接受证据。

## 4. 边界与请求

- 原 formal root、首次失败 root与本次 root 均未覆盖、未复用、未删除；
- live DB 未读取为 runtime state，未迁移；
- Gate C、Merge、Push、Tag 均未执行；
- 请求 V5 主 Session 对本次 pre-provider infrastructure failure 选择后续治理决定；V5-A
  不自行重试或接受 Gate B。
