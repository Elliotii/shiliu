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

### D009 — Treat local alignment pairs as recall candidates, never semantic votes

- `stage`: cross_run_alignment
- `affected_nodes`: all 126 normalized candidates
- `before`: A/B/C1 的最终 Tree 与 Candidate 尚未形成统一对应关系。
- `after`: 本地字符、边界、Evidence 与 parent hint 只生成 105 个候选 Pair 和 42 个 source component；最终关系由 high-thinking 逐 Cluster 裁决。
- `evidence`: `m3-cross-run-alignment-bundle.json` 的 `local_scores_are_semantic_decisions=false`；8 个批次均携带 protocol provenance。
- `reason`: 防止把协议差异、名称相似或相同 Evidence 自动解释为语义等价。
- `alternatives_considered`: 2/3 多数票、固定 Run 权重、直接对齐三棵 Tree；全部拒绝。
- `risk`: 高召回图仍可能漏连跨 Component 的近重复 Scope，必须由 M3 独立复核补查。
- `provider_source`: local candidate generation + 8 high-thinking alignment batches
- `review_status`: engineering_pass_semantic_review_pending

### D010 — Prohibit stable before product Assignment and preserve M2 downgrades

- `stage`: cross_run_alignment
- `affected_nodes`: all 65 provisional clusters
- `before`: Provider 在部分 Alignment 响应中按历史节点或发现支持度直接给出 `stable`。
- `after`: M3 在没有产品 Assignment 证据时一律不得 stable；受影响项只降为 probable。M2 已冻结的 Topic/Entity/unsupported 降级不得被静默复晋升。
- `evidence`: 最终 `stable=0`；M2 downgrade repromotion=0；Validator 覆盖两项硬门禁。
- `reason`: 执行 Contract v2 的“语义类型与证据成熟度分离”，把 stable 数值门槛留到 M6。
- `alternatives_considered`: 接受历史 Run 的 stable；拒绝。删除这些 Candidate；拒绝，仍需保留 provenance 与后续 Assignment 验证。
- `risk`: probable 数量仍偏高，必须在 Draft A 与 Assignment 后重新评估。
- `provider_source`: Provider semantics + deterministic policy normalization
- `review_status`: accepted_engineering_rule

### D011 — Limit local recovery to audited structural transformations

- `stage`: cross_run_alignment_resume
- `affected_nodes`: Batch 001、002、004、007、008
- `before`: JSON Repair 或 Schema 条件导致结构尾差，包括旧字段形状、列表上限、非 Domain 空边界、占位名称/定义和 pre-Assignment stable。
- `after`: 只允许四类有来源变换：从冻结 Candidate 选择名称/定义；按 Schema 有序截限；补写 Provider grouping provenance；stable 降 probable。成员分组、定义语义、Evidence 与 disposition 不由本地代码改写。
- `evidence`: 每个 `local-recovery-audit.json` 保存 source hash、before/after、result hash 与 `provider_call_count=0`。
- `reason`: 避免为格式问题重放完整语料，同时不让本地代码冒充语义裁判。
- `alternatives_considered`: 重放整批；拒绝。直接忽略 Schema；拒绝。人工发明缺失边界；拒绝。
- `risk`: Batch 001 的 decision reason 是 provenance 描述，不是新的模型语义理由；独立 Reviewer 必须看到该来源差异。
- `provider_source`: none for recovery; original Provider response retained
- `review_status`: accepted_engineering_rule

### D012 — Stop M3 before semantic freeze

- `stage`: cross_run_alignment_review
- `affected_nodes`: provisional clusters `xc_001` … `xc_065`
- `before`: 8 / 8 Batch、126 / 126 覆盖与工程 Gate 已通过。
- `after`: Run #24 保持 `waiting_for_review / cross_run_alignment_review`；不进入 Draft A。
- `evidence`: 本地反例扫描发现 Agent 架构、RAG、AI 辅助开发跨 Component 近重复 Scope；`xc_007`、`xc_018`、`xc_049` 等求职/面试 Scope 可能违反 Use Context 排除规则。
- `reason`: 工程完整性不能替代语义可用性；M3 验收要求独立反例复核和明确边界。
- `alternatives_considered`: 把 `READY_FOR_INDEPENDENT_REVIEW` 当 PASS；拒绝。直接在 Draft A Synthesis 再处理；拒绝，会丢失 M3 对齐责任和审计边界。
- `risk`: M3 尚未冻结；后续必须做最小跨 Component Alignment Revision，不能重跑 A/B/C1 或无界重跑全部 M3。
- `provider_source`: local audit; independent reviewer verdict not_evaluated
- `review_status`: stopped_for_review

### D013 — Apply one reviewer-bounded M3 Alignment Revision

- `stage`: cross_run_alignment_revision_01
- `affected_nodes`: 30 个首轮 Reviewer 明确点名的 Cluster。
- `before`: 65 个 provisional Cluster；首轮独立 Reviewer 为 `FAIL`，7 组 Blocking，包含跨 Component 重复、粒度冲突、维度泄漏和 M2 Topic 的语义旁路复晋升。
- `after`: 55 个 Cluster；26 Domain Candidate、17 Topic、1 Entity、2 Object、4 Use Context、5 Uncertain；126 / 126 Candidate 唯一覆盖。
- `evidence`: `m3-independent-semantic-review.json`、`m3-alignment-revision-01.json`、`m3-revision-gate.json`。
- `reason`: M3 工程完整性不能消除跨 Component 语义重复；用户允许最多一次只针对 Reviewer Blocking 的局部修订。
- `alternatives_considered`: 重跑八个 Alignment Batch、在 Draft A 中顺便吸收、无界继续修订；均拒绝。
- `risk`: Agent 核心架构、记忆专项和生产工程仍共享部分术语；Draft A 必须保持语义边界。
- `provider_source`: deterministic reviewer-directed revision, provider_call_count=0
- `review_status`: second_reviewer_PASS_WITH_CONCERNS

### D014 — Freeze M3 after the conditional second review

- `stage`: m3_freeze
- `affected_nodes`: 全部 55 个 Final Cluster 与 126 个 Candidate provenance。
- `before`: Revision Gate 已通过，但尚未确认首轮 7 个 Blocking 是否逐项消除。
- `after`: 第二次独立 Reviewer 逐项确认 BF-01…BF-07 已解决，0 Blocking；M3 Frozen。
- `evidence`: `m3-second-semantic-review.json`、`m3-final-gate.json`、`m3-final-manifest.json`。
- `reason`: 满足独立复核、126/126 Coverage、M2 repromotion=0、stable=0 和 Engineering Gate=PASS 的全部冻结条件。
- `alternatives_considered`: 继续清理所有 Concern；拒绝，Concern 应留给 Draft A 与 Trial Assignment 验证。
- `risk`: 仍保留 weak/uncertain 与非阻断边界问题，不得在 Draft A 提前标记 stable。
- `provider_source`: independent read-only review, provider_call_count=0
- `review_status`: accepted_PASS_WITH_CONCERNS

### D015 — Synthesize Draft A from frozen M3 evidence only

- `stage`: domain_draft_a_synthesis
- `affected_nodes`: `draft_001` … `draft_025`
- `before`: M3 冻结 55 个 Cluster，其中 31 个为 `domain_candidate / uncertain`，尚无产品 Domain Tree。
- `after`: 形成 25 节点的两级 Draft A；20 顶层、5 二级；19 probable、1 weak、5 uncertain、0 stable；26 个 Cluster 进入节点，5 个 uncertain Cluster 显式排除待补证据。
- `evidence`: Frozen Contract、M2 约束、M3 Final Clusters/Decisions、紧凑 Decision Log、每 Cluster 最多 3 条代表 Profile；Draft Hash `be4c86e2038088af5ed966d2ab5cd60a2088df8387950bf8c21c167e171be855`。
- `reason`: 只综合冻结语义证据，不复制任一历史 Run，也不在没有 Trial Assignment 的情况下晋升 stable。
- `alternatives_considered`: 一 Cluster 一节点、强制 Top-K、读取完整 131 Cards、重跑 A/B/C1；全部拒绝。
- `risk`: 树偏平，且部署/生产化/基础设施等相邻边界仍需 Assignment 分布验证。
- `provider_source`: deepseek-v4-pro high-thinking synthesis + JSON Repair；并发恢复审计见正式报告。
- `review_status`: deterministic_gate_pass_independent_review_pending

### D016 — Freeze Draft A without hierarchy revision

- `stage`: domain_draft_a_hierarchy_review_and_freeze
- `affected_nodes`: 全部 25 个 Draft A 节点和 5 个 excluded Cluster。
- `before`: Complexity Gate 无 Blocking，但 `root_share=0.8`、`node/eligible-cluster ratio=0.806452`，存在一组兄弟 Evidence 重叠。
- `after`: 独立 Reviewer 判定 `PASS_WITH_CONCERNS`、0 Blocking、0 Dimension Leakage；Hierarchy Revision 标记为 `not_required`，Draft A 冻结。
- `evidence`: `domain-draft-a-hierarchy-review.json`、`domain-draft-a-manifest.json`、Tree Hash `a19ffd72ebf4c9f83a7e203130b0c192058523085bf29d12e090eaf4549cfbff`。
- `reason`: 任务只允许修复 Blocking；强行降低节点数会引入无来源父域，复杂度应交由 Trial Assignment 验证。
- `alternatives_considered`: 为追求更低节点数执行无 Blocking 的全树改写；拒绝。把 Concern 隐去；拒绝，全部保留在 Manifest。
- `risk`: 当前树可能对浏览偏细；若 Assignment 显示持续混淆或空节点，再在后续 Diagnosis 中提出受限 Revision。
- `provider_source`: independent read-only hierarchy review, provider_call_count=0
- `review_status`: accepted_PASS_WITH_CONCERNS

### D017 — Record the Draft A concurrent calls as a Blocking Engineering Finding

- `stage`: domain_draft_a_engineering_audit
- `affected_nodes`: Draft A Synthesis attempt lifecycle，不改变任何 Taxonomy 节点。
- `before`: 并发恢复曾被概括为一次主调用和 Repair，且第一份 Repair 被误记为覆盖丢失。
- `after`: 正式 Response Ledger 记录 2 个 Primary、2 个 Repair、1 个 unknown usage；四份 Raw 均保存 response ID、真实路径、usage、SHA256 与是否最终采用。
- `evidence`: `domain-draft-a-response-ledger.json`；最终选择 `b928a44f…`，对应 25 节点 Primary 链；33 节点链仍为 validation failed。
- `reason`: 不能把重复请求造成的成本和恢复风险包装成正常单次调用。
- `alternatives_considered`: 只采用数据库 Stage Row；拒绝，该 Row 低估真实调用。继续把第一份 Repair 写成 overwritten；拒绝，`repair-raw-response-02.txt` 实际仍在。
- `risk`: 没有原子 single-flight / attempt lease 时，后续批量 Assignment 可再次重复扣费和覆盖审计路径。
- `provider_source`: audit only, provider_call_count=0
- `review_status`: blocking_engineering_finding_recorded

### D018 — Split direct provenance from derived scope provenance

- `stage`: domain_draft_a_freeze_v3
- `affected_nodes`: 全部 25 个 Draft A 节点。
- `before`: `source_cluster_ids` 同时表示节点直接消费和父节点聚合范围；父子共享曾通过放宽唯一性表达。
- `after`: Canonical v3 使用 `direct_source_cluster_ids` 与 `scope_source_cluster_ids`；26 个 Direct Cluster 全局唯一，父级 Scope 只能由自身 Direct 与子孙 Scope 确定性并集得到。
- `evidence`: Direct count 26、unique count 26；只有 `draft_001` 与 `draft_006` 存在父级 scope 聚合；结构 Gate 重算为 PASS。
- `reason`: 唯一消费约束应落在直接语义来源，父级浏览范围不能伪装成重复直接消费。
- `alternatives_considered`: 继续允许父子重复 `source_cluster_ids`；拒绝。延后到 Assignment 前；可行但本轮可确定性迁移，无需留下该债务。
- `risk`: 未来任何层级修改都必须重新派生 Scope，禁止手写 Scope 绕过 Direct 唯一性。
- `provider_source`: deterministic local migration, provider_call_count=0
- `review_status`: accepted_gate_recomputed

### D019 — Freeze semantics while blocking Trial Assignment on single-flight debt

- `stage`: domain_draft_a_final_freeze
- `affected_nodes`: Run #24 状态机与下一阶段入口。
- `before`: Draft A 语义与 Hierarchy Gate 已通过，但并发事故根因尚无代码级防护。
- `after`: `semantic_freeze_status=FROZEN`；`engineering_gate=BLOCKED_BEFORE_TRIAL_ASSIGNMENT`；`trial_assignment_eligible=false`；下一阶段改为 `single_flight_attempt_lease_remediation`。
- `evidence`: Reviewer 原始输入 SHA256 `7569a69c…`、原始输出 SHA256 `38e6b626…`、usage unknown/provider call 0 均落盘；Freeze 独立重算 Gate，不读取手写布尔值。
- `reason`: 语义产物可冻结，但不得在已知重复调用风险未修复时启动 131 条批量 Assignment。
- `alternatives_considered`: 直接进入 M6；拒绝。撤销全部语义结果；拒绝，工程事故不否定已独立复核的语义树。
- `risk`: single-flight / lease 未完成前 Run 只能停在工程 Hold。
- `provider_source`: local freeze audit + independent reviewer evidence, provider_call_count=0
- `review_status`: semantic_PASS_engineering_BLOCKED
