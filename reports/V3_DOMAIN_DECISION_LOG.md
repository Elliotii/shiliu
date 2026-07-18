# V3 Domain Decision Log

本日志记录 V3 Domain Completion Mission 的产品 Taxonomy 决策。历史 Run 的模型输出不是人工正确答案；所有新增、删除、合并、拆分、改名、移动、降级、Gap 裁决、Revision 与 Reviewer 分歧都必须保留 Before / After 和来源。

## Decision schema

```text
decision_id
stage
affected_nodes
before
after
evidence
reason
alternatives_considered
risk
provider_source
review_status
```

## Decisions

### D000 — Treat A/B/C1 as independent evidence sources

- `stage`: mission_bootstrap
- `affected_nodes`: none
- `before`: A/B/C1 曾被部分自动审计描述成可直接比较的运行。
- `after`: 三者仅作为带协议 provenance 的独立 Discovery Evidence Source；不使用简单多数票或固定 Run 权重。
- `evidence`: Checkpoint 3.12D 独立复核确认 C1 global Semantic Comparability 未被证明。
- `reason`: 防止把协议差异误当作随机稳定性。
- `alternatives_considered`: 将 C1 视为 A/B 的等价 C Run；拒绝。
- `risk`: 后续 Alignment 成本增加，但语义结论更可信。
- `provider_source`: none
- `review_status`: accepted

### D001 — Freeze C1 failure and prohibit C2

- `stage`: mission_bootstrap
- `affected_nodes`: none
- `before`: C2 仅存在 replication plan。
- `after`: 冻结 `checkpoint/v3.12d-run-c1-failed`；Mission 内不得运行 C2。
- `evidence`: C1 unresolved 10 / 44，4 个 multi-evidence；replication eligibility false。
- `reason`: 先统一产品 Semantic Contract 并综合现有证据，不继续扩建 Discovery Harness。
- `alternatives_considered`: 先补 Prompt Hash 后运行 C2；拒绝。
- `risk`: 失去同协议复制样本，但符合产品收敛目标。
- `provider_source`: none
- `review_status`: accepted
