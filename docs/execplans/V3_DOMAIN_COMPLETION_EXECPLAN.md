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
- [x] M1 Contract v2：Run #24，Revision 01，独立复核 `PASS_WITH_CONCERNS`，无 Blocking。
- [x] M2 unresolved adjudication：13 个来源项去重为 12 组，Revision 01 后独立复核 `PASS_WITH_CONCERNS`，0 Blocking。
- [~] M3 cross-run alignment：8 / 8 批次和 126 / 126 工程门禁完成；停在独立语义复核前，尚未冻结。
- [ ] M4 Draft A。
- [ ] M5 hierarchy validation。
- [ ] M6 131 Assignment。
- [ ] M7 Eval / Diagnosis。
- [ ] M8 Revision。
- [ ] M9 Draft B / Final Review。

当前停止点：Run #24 为 `waiting_for_review / cross_run_alignment_review`。不得直接进入 Draft A；下一次恢复应先完成 M3 独立反例复核，并处理已发现的跨 Component 近重复 Scope 与 Use Context 泄漏风险。

## M1 completion note

- Provider 主调用：1 次 `deepseek-v4-pro / high`；因结构校验失败执行 1 次独立 JSON Repair。
- 合计：13,610 input tokens；14,358 output tokens；5,525 reasoning tokens；181.126 秒。
- Repair 仍少一条结构规则，随后只对已有批准规则做本地确定性因式分解与枚举归一化；额外 Provider 调用为 0。
- 首轮独立复核发现证据数量与 Domain 语义类型混用、顶层误用 parent-subset 两项 Blocking。
- Revision 01 保留 Provider Draft，进行一次零调用最小修订；第二轮独立复核为 `PASS_WITH_CONCERNS`，无 Blocking。
- 冻结的 payload hash：Contract `21c17219474615b9e828431c2135fe039c81fb0cf823700a5078c07c618d0b6f`；Diff `0f9b7e4140e5ad2735ecfb6a4e02c6864979729a193434fc9f6fbbee66fc26a5`。
- 延后门槛：`stable` 的可计算 Assignment 产品门槛必须在 M6 Assignment Protocol 中冻结；此前不得自动晋升 stable。

## M2 completion note

- Run B 3 项、Run C1 10 项 unresolved 按来源保留，去重后为 12 个裁决组；只合并了一个共享同一 Evidence 且语义相近的跨 Run 组。
- 每组只读取 Candidate 边界、1–2 个代表 Profile、4 个邻近节点、4 个可能对应 Candidate 与 protocol provenance；未读取完整 128 卡片。
- 3 个 high-thinking 批次；2 次 JSON Repair 后出现越组节点引用，均只删除非法 ref 做零调用本地恢复，未修改裁决、操作、证据或理由。
- M2 合计：24,679 input、20,409 output、13,323 reasoning tokens，346.233 秒。
- 首轮独立反例 Reviewer 判定 FAIL，4 个 Blocking；Revision 01 将两个过度晋升的 Gap 撤回为 Topic、修正一个类型/操作冲突、修正一个违反 excludes 的 merge target。
- 第二轮复核：`PASS_WITH_CONCERNS`，0 Blocking。最终 6 个 `merge_into_existing`、6 个 `downgrade_to_topic`、0 个 `create_domain_proposal`。
- Final payload hash：`c472c4c3c73ef566a7a1afc9b43283b0d617ef4c664afa860eb1d963b7a936e5`。

## M3 execution note — stopped before semantic freeze

- 输入仍是 A/B/C1 三份带协议 provenance 的独立证据，不是等价随机运行；没有重跑 A/B/C1/C1，也没有读取 Silver。
- 本地先生成 105 个高召回候选 Pair、42 个 source component；pair score 明确不是语义结论。
- 126 个 Candidate（A 42 / B 40 / C1 44）分 8 个 high-thinking Batch 对齐，最终形成 65 个 provisional Cluster。
- 工程门禁：126 / 126 精确唯一覆盖；missing/extra/duplicate 均为 0；`stable=0`；M2 已降级 Candidate 被复晋升为 Domain 的数量为 0。
- 分布：47 `domain_candidate`、16 `non_domain_topic`、1 `non_domain_entity`、1 `uncertain`；40 probable、6 weak、2 uncertain、17 not_applicable。
- M3 全审计 usage（含失败 attempt 与 JSON Repair）：102,876 input、105,375 output、71,652 reasoning tokens、1,535.258 秒。
- 失败与恢复：Batch 002 首次 high-thinking 在 8,191 reasoning token 后 length 截断；Batch 005 首次 TLS 失败且无 usage；7 个 Batch 使用 JSON Repair；5 个 Batch 使用零 Provider 的受限本地恢复。所有 attempt history 均保留。
- Gate 仅为 `READY_FOR_INDEPENDENT_REVIEW`，不是语义 PASS。Clusters payload hash `71b240220dc51a0ca4d2c3241b967090acf2d4441963d0e9f103755586032693`；Decisions payload hash `c43b319e421ab86770292d14c208f2790def9e8960cf96b6befc0dd469c718c0`。
- 本地反例扫描发现跨 Component 漏对齐：Agent 架构、RAG、AI 辅助开发存在近重复 Scope；求职/面试 Cluster 可能违反 Use Context 排除规则。因此 M3 尚未满足“可冻结进入 Draft A”的验收条件。
- 第一个独立 Reviewer 因子任务额度耗尽未产生 verdict；第二个 Reviewer 在用户要求本轮停止后被中止。不得把两者记录为 PASS/FAIL。
- 完整本轮报告：`reports/V3_DOMAIN_COMPLETION_RUN_REPORT_2026-07-19.md`。
