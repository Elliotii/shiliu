# V3 Domain Taxonomy Completion ExecPlan

## Mission

基于冻结的 Run A、Run B、Run C1，将三份带明确协议来源的独立 Discovery Evidence 收敛为可进入产品实现阶段的 Domain Draft B，并完成 131 / 131 Trial Assignment、可复现 Eval、有限 Revision、完整 Decision Log 和独立只读复核。

本文件是 living document。每完成一个 Milestone，必须更新进度、结果、风险、恢复位置和下一动作；不得把 A/B/C1 描述成同协议下的等价随机运行，也不得使用简单 2/3 投票。

## Frozen facts

- Snapshot #2：131 cards；128 Discovery Eligible；3 Trial-only；Hash `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2`。
- Run A：旧单响应 Consolidation，已完成；作为独立证据源，不是母版。
- Run B：40 / 40 Candidate Decisions，Evidence Contract v2，`PASS_WITH_CHANGES`，3 个 unresolved。
- Run C1：44 / 44 Decisions，Evidence Contract v2，工程完整；Gate `FAIL`，10 个 unresolved，22.7273%，4 个 multi-evidence。
- Checkpoint 3.12D：Tag `checkpoint/v3.12d-run-c1-failed`，Commit `3d9594a`。
- C2 不可执行；历史 Run 原始输入、响应、Tree、Decision、DB 状态和 Hash 均不可修改。

## Final deliverables

Runtime 产物位于本地私有 Run 目录，不提交真实 Card/Profile/Prompt/Response。最终至少包含：

- `domain-semantic-contract-v2.json`
- `semantic-contract-diff-a-b-c1.json`
- `unresolved-adjudication-final.json`
- `cross-run-domain-clusters.json`
- `cross-run-alignment-decisions.json`
- `domain-draft-a.json` / `domain-draft-a-tree.md`
- `trial-assignment-initial.json`
- `domain-eval-metrics-initial.json`
- `domain-diagnosis-initial.json`
- `domain-revision-01.json`；仅满足门禁时允许 `domain-revision-02.json`
- `domain-draft-b.json` / `domain-draft-b-tree.md`
- `trial-assignment-final.json`
- `domain-eval-metrics-final.json`
- `domain-decision-log.json`
- `reports/V3_DOMAIN_COMPLETION_FINAL.md`

## Non-goals and forbidden inputs

- 不运行 C2，不重跑 A/B/C1，不修改历史产物。
- 不读取 Silver Reference，不修改其他三个受控分面，不完成剩余受控分面 Assignment。
- 不实现 Entity Typing、前端、Evolution、Embedding、BERTopic、向量数据库、Agent Harness 或通用 Eval 平台。
- 不将 C1 Tree、A Tree 或 B Tree 直接作为 Draft A。
- 不把 unresolved 自动升级为新 Domain。

## Milestones

### M0 — Mission bootstrap

- 输入：Checkpoint 3.12D Git/DB/Runtime 状态。
- 输出：本 ExecPlan、Status、Decision Log、Mission 分支与冻结 Tag；统一本地 Runtime 路径及可恢复状态入口。
- Provider：0。
- 验收：历史 Hash 不变；工作区测试通过；提交并推送。
- 恢复：从最后一个已提交文档状态继续。

### M1 — Canonical Domain Semantic Contract v2

- 输入：A/B Consolidation Prompt/Schema/结果，C1 Node/Router Prompt/Schema/结果，产品 Domain 定义，Evidence Contract v2。
- 输出：`domain-semantic-contract-v2.json`、`semantic-contract-diff-a-b-c1.json`。
- Provider：1 次 high-thinking Contract 审定；必要时最多 1 次局部 JSON Repair；随后独立只读 Reviewer，不复用生产上下文。
- 验收：Domain/Topic/Entity、支持度、层级、unresolved 边界可执行；没有把 C1 偏差静默写成规则；Reviewer 无 Blocking。
- 恢复：原始响应先落盘；Stage 完成后不重放。

### M2 — Unresolved adjudication

- 输入：Run B 3 项、C1 10 项；每项限 Candidate、少量 Profiles、邻近节点和 provenance。
- 输出：`unresolved-adjudication-final.json`。
- Provider：分批 high-thinking adjudication；每批 1 次主调用 + 最多 1 次局部 Repair；独立只读反例 Reviewer。
- 验收：每项有唯一 adjudication/operation、反例、confidence、reviewer verdict；只有 `true_tree_gap` 形成 Domain Proposal。
- 恢复：按 adjudication batch 恢复，不重放完成批次。

### M3 — Candidate-centric cross-run alignment

- 输入：Final Nodes、Normalized Candidates、Decisions、Evidence Pools、Profiles、M2 裁决和 protocol provenance。
- 输出：`cross-run-domain-clusters.json`、`cross-run-alignment-decisions.json`。
- Provider：本地生成 candidate pairs；分批 high-thinking 语义对齐；必要时 batch-local Repair。
- 验收：不使用多数票或固定 Run 权重；每个 Cluster 有来源、关系、scope proposal 和 confidence。
- 恢复：Pair/Cluster Batch 可独立恢复。

### M4 — Domain Draft A synthesis

- 输入：M3 Clusters 和 M2 true gaps。
- 输出：`domain-draft-a.json`、`domain-draft-a-tree.md`。
- Provider：1 次 high-thinking Synthesis + 最多 1 次局部 Repair。
- 验收：不是复制任一 Run；最多两级；节点有完整边界、状态、来源、证据和风险。

### M5 — Hierarchy validation

- 输入：Draft A。
- 输出：确定性结构报告、局部 high-thinking risk review、最多一次预 Assignment 修正。
- Provider：仅风险节点；不允许重新生成整树。
- 验收：ID/父子/深度/循环/重复/泄漏/来源硬条件通过；未解决风险显式保留。

### M6 — 131-card Trial Assignment

- 输入：冻结 Draft A、128 Eligible Profile/Compact Views、3 D Cards。
- 输出：`trial-assignment-initial.json`。
- Provider：适中批次，off/medium thinking；每批 1 次主调用 + 最多 1 次局部 Repair/Tail；高风险内容才进入 high-thinking adjudication batch。
- 验收：131 / 131，ID 合法、无重复/缺失、标签预算合规、无运行时建 Domain；已完成批次不重放。

### M7 — Eval and diagnosis

- 输入：Draft A + Initial Assignment。
- 输出：`domain-eval-metrics-initial.json`、`domain-diagnosis-initial.json`。
- Provider：Metrics 全本地；仅最大失败模式可使用 high-thinking diagnosis/review。
- 验收：Metrics 可复算；Gap/Ambiguity 诚实保留；只选择一个最大失败模式。

### M8 — Bounded revision

- 输入：Diagnosis + Draft A + 受影响 Assignment。
- 输出：Revision 01；只有门禁满足才允许 Revision 02。
- Provider：high-thinking Revision Decision；只重跑受影响 Assignment。
- 验收：结构与质量有实质改善、复杂度不失控、没有强行分类；失败 Revision 回滚并留痕。

### M9 — Domain Draft B and final review

- 输入：被接受的 Revision 与 Final Assignment。
- 输出：Draft B、Final Metrics、Decision Log、最终报告、独立只读 Reviewer。
- Provider：最终 high-thinking Reviewer，只读且不能修改 Taxonomy。
- 验收：最终判定只能是 PASS / PASS_WITH_CONCERNS / FAIL；满足 Mission 的停止位置。

## Provider and cost discipline

- Semantic Contract、Adjudication、Alignment、Synthesis、Hierarchy Risk、Revision、Final Review 使用 high thinking。
- Assignment、Repair、Tail、结构化报告使用 off/medium。
- 每次调用前落盘 Audit 状态，原始响应收到后立即落盘，再做解析；记录模型、Prompt/Schema Hash、thinking、tokens、reasoning、耗时、repair、response hash。
- 每阶段设置明确输出预算；不得携带完整 128 Cards 重试格式错误。

## Complexity and quality gates

- Eligible taxonomy gap ≤ 5%；Eligible ambiguous ≤ 15%。
- 不存在未处理的 multi-evidence systematic gap、zero-assignment stable node 或明显维度泄漏。
- 单 Evidence 默认不能成为 stable；新增 stable/probable 必须解决多个内容或一个高证据 Gap Cluster。
- 持续统计 top/second/total nodes、状态分布、single/low/unused support、sibling/parent confusion、revision 新增节点与解决 Gap 比。

## Hard stops

只有以下情况停止 Mission：无法形成可执行 Contract v2；必须改变产品定义或读取 Silver；Snapshot/历史 Run 改变；需要用户选择明确产品偏好；两轮 Revision 无实质改善；Draft B 仍有 multi-evidence systematic gap；只能靠大量低支持节点降低 Gap；覆盖/边界/复杂度无法同时满足。

## Validation commands

```bash
PYTHONPATH=src:. .venv/bin/pytest -q
git diff --check
git status --short
shiliu taxonomy domain-completion status <run_id>
shiliu taxonomy domain-completion resume <run_id>
```

CLI 名称在 M1 Runtime 实现后固定；如果现有 CLI 语法要求平铺子命令，将记录语义等价命令。

## Current progress

- [x] Checkpoint 3.12D 已冻结并推送。
- [x] Mission Goal 与分阶段计划已建立。
- [x] M0 文档和恢复纪律提交。
- [ ] M1 Contract v2。
- [ ] M2 unresolved adjudication。
- [ ] M3 cross-run alignment。
- [ ] M4 Draft A。
- [ ] M5 hierarchy validation。
- [ ] M6 131 Assignment。
- [ ] M7 Eval / Diagnosis。
- [ ] M8 Revision。
- [ ] M9 Draft B / Final Review。

当前下一动作：审计 A/B/C1 的真实 Prompt、Schema 和结果，构建 M1 可恢复输入 Bundle。
