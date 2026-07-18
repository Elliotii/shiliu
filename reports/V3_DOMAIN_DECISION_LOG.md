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

### D002 — Separate Domain semantic type from evidence maturity

- `stage`: semantic_contract_v2
- `affected_nodes`: all future Domain candidates
- `before`: Provider Draft 将“能被多条内容共同支持”写入 Domain 定义，证据数量可能决定语义类型。
- `after`: Domain 类型由稳定知识领域或实践问题空间的语义边界决定；证据数量只影响 stable/probable/weak/uncertain 状态。
- `evidence`: 首轮独立 Reviewer Blocking 1；Revision 01 `support_policy.evidence_affects_status_not_semantic_type=true`。
- `reason`: 避免把语义本体和当前语料成熟度混为一谈。
- `alternatives_considered`: 保留 foundational 单证据自动例外；拒绝，任何例外必须显式 adjudication。
- `risk`: weak/uncertain 候选会增多，但不会制造错误确定性。
- `provider_source`: Provider Draft + local revision 01
- `review_status`: accepted_PASS_WITH_CONCERNS

### D003 — Count distinct content evidence, not repeated run provenance

- `stage`: semantic_contract_v2
- `affected_nodes`: all future support calculations
- `before`: 跨 Run 重复出现可能被误读为新增 Evidence。
- `after`: multi-evidence 至少需要 2 个不同 `content_id`；同一内容跨 A/B/C1 重复只增加 provenance，不增加独立内容数。
- `evidence`: Contract v2 Support Policy 与 Diff `sr_03`。
- `reason`: 三个 Run 不是三份新的用户内容。
- `alternatives_considered`: 按 Run 出现次数投票；拒绝。
- `risk`: 某些跨 Run 稳定但单内容节点保持 weak/uncertain。
- `provider_source`: local revision 01
- `review_status`: accepted

### D004 — Apply parent entailment only to child nodes

- `stage`: semantic_contract_v2
- `affected_nodes`: future hierarchy
- `before`: Provider Draft 对所有 stable/probable 节点要求语义子集，顶层节点没有可用父级。
- `after`: 顶层节点执行语义边界和 evidence/status 条件；二级节点额外执行 parent entailment 与 semantic-subset。
- `evidence`: 首轮独立 Reviewer Blocking 2。
- `reason`: 使最多两级层级规则可执行。
- `alternatives_considered`: 为顶层引入虚拟根节点；拒绝，产品不需要第三层或机械根节点。
- `risk`: 顶层粒度仍需 M5 Hierarchy Reviewer 检查。
- `provider_source`: local revision 01
- `review_status`: accepted

### D005 — Preserve non-Domain axes and honest unresolved routing

- `stage`: semantic_contract_v2
- `affected_nodes`: all unresolved and future assignments
- `before`: A/B/C1 对实践、对象和使用情境的处理不完全一致。
- `after`: 稳定知识领域与稳定实践问题空间允许成为 Domain；Form/Object/Use Context/Topic/Entity 不进入 Domain Tree；unresolved 仅表示冻结树无法安全路由，必须裁决且不自动建域。
- `evidence`: Contract v2 Axis Policy、Non-domain Routing Policy、Unresolved Policy；第二轮独立复核通过。
- `reason`: 固化产品轴，避免把面试用途、学习路径或具体对象当领域。
- `alternatives_considered`: 沿用任一历史 Run 的隐含口径；拒绝。
- `risk`: 稳定实践问题空间与 Use Context 的边界仍需 M2/M3 逐项验证。
- `provider_source`: semantic adjudication + approved product definition
- `review_status`: accepted_PASS_WITH_CONCERNS

### D006 — Defer numeric stable threshold to Assignment Protocol

- `stage`: semantic_contract_v2
- `affected_nodes`: future stable nodes
- `before`: `stable` 只有语义定义，没有可计算的产品赋值门槛。
- `after`: M1 冻结语义定义；在 M6 Assignment Protocol 冻结最少独立 Assignment、冲突和未决条件；此前不得自动晋升 stable。
- `evidence`: 第二轮独立 Reviewer non-blocking concern。
- `reason`: M1 尚无 131 条产品 Assignment，不应虚构数值门槛。
- `alternatives_considered`: M1 直接规定固定数量；拒绝，缺少全量分布证据。
- `risk`: Draft A 中 stable 状态只能保守使用，需 M6 后复核。
- `provider_source`: independent read-only reviewer
- `review_status`: accepted_with_follow_up

### D007 — Adjudicate all historical unresolved without auto-creating Domains

- `stage`: unresolved_adjudication
- `affected_nodes`: `ua_001` … `ua_012`
- `before`: Run B 3 项、Run C1 10 项均使用 `unresolved_requires_new_domain`，其中一个跨 Run 语义重复。
- `after`: 13 个来源项去重为 12 组；6 组 `merge_into_existing`，6 组 `downgrade_to_topic`，0 组 `create_domain_proposal`。
- `evidence`: 每组受限 Candidate 边界、1–2 个代表 Profile、邻近节点、跨 Run 候选和 provenance；第二次独立复核无 Blocking。
- `reason`: unresolved 只表示历史冻结树无法安全路由，不是新建 Domain 的充分证据。
- `alternatives_considered`: 将历史 unresolved 全部变为 weak Domain；拒绝。把同名或同 ID 候选直接合并；拒绝，仅合并共享 Evidence 且语义相近的跨 Run 组。
- `risk`: 当前没有新 Gap Proposal；若 Trial Assignment 出现 multi-evidence systematic gap，必须作为后续 Diagnosis 新证据处理。
- `provider_source`: 3 high-thinking adjudication batches + independent counterexample review
- `review_status`: accepted_PASS_WITH_CONCERNS

### D008 — Reject four M2 overreach or boundary-conflict decisions

- `stage`: unresolved_adjudication_revision_01
- `affected_nodes`: `ua_003`, `ua_007`, `ua_008`, `ua_012`
- `before`: 2 个单样本/使用情境候选被创建 Gap Proposal；1 个类型与操作冲突；1 个 merge target 违反自身 excludes。
- `after`: 前两项降为 Topic；类型/操作统一为 Topic + downgrade；merge 改到可容纳全部 Evidence 的更宽父节点。
- `evidence`: 首轮独立 Reviewer 4 个 Blocking；逐项 Revision 后第二轮 Reviewer 确认全部消除。
- `reason`: 防止单一方法、个人工作流、具体工具或不完整子节点被错误提升为 Domain。
- `alternatives_considered`: 保留 weak true-tree-gap；拒绝，语义边界本身未被证据支持，而不只是成熟度不足。
- `risk`: 未来更多异质内容可能支持重新提出轴纯 Domain；必须用新 Evidence 审议，不能静默恢复旧结论。
- `provider_source`: local revision 01, provider_call_count=0
- `review_status`: accepted_PASS_WITH_CONCERNS
