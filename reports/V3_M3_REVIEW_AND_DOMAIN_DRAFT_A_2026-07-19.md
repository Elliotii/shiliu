# V3 Run #24：M3 语义复核与 Domain Draft A 运行报告

日期：2026-07-19

分支：`codex/v3-domain-completion`

停止位置：`waiting_for_review / domain_draft_a_frozen_before_trial_assignment`

## 结论

本轮按恢复任务完成 M3 独立语义复核、一次 Reviewer-bounded Alignment Revision、M3 Freeze、Domain Draft A Synthesis、Complexity Gate、独立 Hierarchy Review 和 Draft A Freeze。

语义判定为 `PASS_WITH_CONCERNS`：M3 与 Draft A 均无语义 Blocking。工程判定为 `BLOCKED_BEFORE_TRIAL_ASSIGNMENT`：并发事故已正式记录，single-flight / attempt lease 尚未实现，因此当前不允许进入 Trial Assignment。本轮没有启动 Trial Assignment、Eval、Draft B、C2，也没有重跑 A/B/C1 或 M3 八个批次。

## Run #24 恢复与输入边界

- Snapshot #2 保持冻结：131 Cards、128 Discovery Eligible、3 Trial-only。
- 只读取 A/B/C1 的冻结产物及其 protocol provenance；没有把三者当成等价随机投票。
- 没有读取 Silver Reference、完整 131 Cards、用户笔记、收藏夹名称或其他受控分面结果。
- M3 Revision 只处理独立 Reviewer 明确点名的 Blocking；Draft A 只读取 M3 Frozen 产物与受限代表证据。

## M3 独立语义复核

独立复核 Bundle：`<local-run-artifact>/run-000024/m3-independent-review-bundle.json`。

首轮输入包含 65 个 provisional Cluster、41 个高召回风险 Pair、23 个风险 Component。Reviewer 判定 `FAIL`，指出 7 组 Blocking：

1. Agent 相关 Cluster 存在三组重复或边界重叠；
2. RAG 领域重复；
3. AI 辅助开发存在重复与粒度冲突；
4. Use Context、Object、Topic 泄漏进 Domain 候选；
5. M2 已降级 Topic 出现语义旁路复晋升；
6. 部分 Cluster 混合多个 Scope；
7. 同一语义在不同 Run 间出现 disposition 分裂。

### Alignment Revision 01

只修改 Reviewer 点名的 30 个 Cluster，Provider 调用为 0；没有重跑八个 Alignment Batch。

| 指标 | Revision 前 | Revision 后 |
|---|---:|---:|
| Cluster 总数 | 65 | 55 |
| Domain Candidate | 47 | 26 |
| Topic | 16 | 17 |
| Entity | 1 | 1 |
| Object | 0 | 2 |
| Use Context | 0 | 4 |
| Uncertain | 1 | 5 |
| Candidate 唯一覆盖 | 126 / 126 | 126 / 126 |
| stable | 0 | 0 |
| M2 exact repromotion | 0 | 0 |
| M2 semantic parallel repromotion | 存在风险 | 0 |

第二次独立 Reviewer 仅复核首轮 Blocking 和 Revision 影响，判定 `PASS_WITH_CONCERNS`、0 Blocking。保留的 Concern 为 Agent 子域相邻边界、Object 重叠以及未受影响项的 Hash 审计粒度。

### M3 Freeze

M3 Engineering Gate、Revision Gate 与第二次独立复核全部满足冻结条件。Frozen SHA256：

- Clusters：`de67704a5d6f68c807ee2fd93d8f42e25a08d7cc1c81e60e1019daf8a6b5edd3`
- Decisions：`aa21cac07730a335503d99d7f672e89a7d3f420ef09b5a5c8198e45efe3a13ee`
- Semantic Review：`ce6a2834ee36d00c6b2fa256b0a9c7483d3022502ed43cd95b47d252c27af30d`
- Gate：`69b31d88c0edf36ac4720bb1c7ab164932b53a48cac849ee73301704028b1993`
- Manifest：`7cf8f7cd0add7068c80334baabad43b6d8486cdbb2ce520483eb7c6547c4ac1e`

## Domain Draft A Synthesis

### 预算与实际输入

- Eligible Frozen Cluster：31。
- Prompt：52,593 字符；估算 17,531 input tokens。
- 估算 output 上界：14,370 tokens；配置 max tokens：24,576。
- 模型：`deepseek-v4-pro`，`high thinking`。
- 输入仅含 Frozen Contract、M2 约束、M3 Final Clusters/Decisions、紧凑 Decision Log 和每 Cluster 最多 3 条代表 Profile。

### Draft A 结果

- 25 节点：20 顶层、5 二级；最大深度 2。
- 19 probable、1 weak、5 uncertain、0 stable。
- 26 个 Cluster 进入节点；5 个 uncertain Cluster 以 `excluded pending evidence` 保留。
- Provider Draft v2 Hash：`be4c86e2038088af5ed966d2ab5cd60a2088df8387950bf8c21c167e171be855`。
- Canonical Frozen Draft v3 Hash：`42f6a9f0e08cd756951da4a1854c2ada6a362a8b6d4646b945379e6019c3c937`。
- Frozen Tree Hash：`c54054e04f1ebbd9eec1307d369525f3f34427c6e82a2205a2ffc730b687a281`。
- Frozen v3 将来源拆为 26 个全局唯一的 `direct_source_cluster_ids` 与确定性派生的 `scope_source_cluster_ids`；`draft_001` 和 `draft_006` 的父级来源聚合只存在于 Scope，不再重复直接消费。

### Draft A Tree

- AI Agent系统
  - AI Agent 记忆与上下文工程
  - AI Agent 测试与评估
  - AI Agent 系统工程化
  - 多代理协作系统
- AI辅助软件开发
  - AI辅助开发工作流与工程方法
- 检索增强生成（RAG）
- 大模型微调与适配
- 提示词工程
- 上下文优化与成本管理
- 大模型部署与推理优化
- AI 生成式视觉内容与设计自动化
- AI在游戏开发中的应用
- AI时代职业发展与技能转型
- 软件/互联网架构演进
- 版本控制与协作
- 命令行界面与自动化
- AI 系统集成与接口设计
- AI安全与对齐评估
- 人机交互接口设计
- Markdown 编辑与内容处理
- AI工程化与生产部署
- AI大模型原理与能力基础
- AI 基础设施

排除待补证据 Cluster：`xc_031`、`xc_033`、`xc_050`、`xc_061`、`xc_065`。

## Complexity Gate 与独立 Hierarchy Review

确定性 Gate 为 PASS，Blocking 为 0。复杂度信号：

- node / eligible-cluster ratio：`0.806452`；
- root share：`0.8`；
- low-support nodes：7；
- single-evidence nodes：1；
- sibling evidence overlap：`draft_019` 与 `draft_021`；
- parent-child scope conflict：0。

独立 Reviewer 判定 `PASS_WITH_CONCERNS`，Blocking 0、Dimension Leakage 0。主要 Concern：

1. 树偏平且接近一 Cluster 一节点；强制压缩可能创建无来源父域，应由 Trial Assignment 验证实际浏览复杂度；
2. `draft_012`、`draft_023`、`draft_025` 的部署、产品化和基础设施边界相邻；
3. `draft_019` 与 `draft_021` 共享部分证据，但当前定义仍区分集成与交互；
4. Agent 评估节点证据面较宽；
5. AI 产品化支持度较低；
6. 职业发展仍有退化为 Use Context 的风险。

Reviewer 没有要求 Revision。任务规则只允许为 Blocking 做一次层级修订，因此本轮明确记录 `hierarchy_revision=not_required`，没有再次调用模型。

## Provider usage 与并发恢复异常

Draft A 原计划为 1 次 Primary + 最多 1 次 JSON Repair。长请求恢复期间，两个恢复进程在较早请求尚未落盘时进入同一 attempt，最终收到 2 个 Primary 与 2 个 Repair Response。这不是一次正常调用，而是正式的 Blocking Engineering Finding。后续审计确认四份 Raw 均仍存在；此前“第一份 Repair 被覆盖”的说法不准确，第一份 Repair 实际保存为 `repair-raw-response-02.txt`。

| Response | 类型 | Prompt | Completion | Reasoning | Cached Prompt | 耗时 |
|---|---|---:|---:|---:|---:|---:|
| `565fc77e…` | Primary | 18,722 | 15,865 | 7,818 | unknown | 190.156s |
| `16cfca4b…` | Primary | 18,722 | 18,184 | 6,663 | 18,688 | 204.567s |
| `77dca950…` | JSON Repair | 9,356 | 8,079 | 0 | unknown | 69.407s |
| `b928a44f…` | JSON Repair | unknown | unknown | unknown | unknown | 95.819s |

可确认的最小合计：46,800 prompt、42,128 completion、14,481 reasoning tokens、560.049 秒；另有一个 Repair Response 的 usage 无法恢复，因此这不是完整上限。数据库 Stage Row 只覆盖其中部分调用，正式报告以 concurrency audit 的“已知最小值 + 1 个 unknown response”为准。

最终接受的是第二个 Repair Response。该恢复没有新增 Provider 调用，也没有修改 Draft 语义。此前临时 Validator 通过“允许父子共享 `source_cluster_ids`”解决聚合来源问题；最终冻结不保留这一放宽，而是迁移为唯一 Direct 来源与确定性 Scope 聚合。

### Response Ledger

| Response ID | 类型 | Raw path | Raw SHA256 | 采用 |
|---|---|---|---|---|
| `565fc77e…` | Primary | `raw-response.txt` | `5765791e522f0e994ed17147488484cbb8956b2ba7cea0d37fa9edb13c524a47` | 否 |
| `16cfca4b…` | Primary | `raw-response-02.txt` | `7c50ce518b4085fe03fb3dcedfb4e2f917c2539c77059ce69ef67cad715b928c` | 否 |
| `77dca950…` | Repair | `repair-raw-response-02.txt` | `1d6ea3bfe50d76c11ef293c366c9db78d35bbab34e90412815ac811a55f30e9d` | 否 |
| `b928a44f…` | Repair | `repair-raw-response.txt` | `bf640e64804486cef55911a02dde08b3701058f10801c0ede51d5f7122d8ba4c` | 是 |

最终选择理由：`b928a44f…` 属于 25 节点 Primary 链，修复后保持原语义并通过 Schema；另一条 33 节点链在 Repair 后仍校验失败。

### Primary → Final Repair Semantic Diff

机器 Diff SHA256：`d4b0f47f7654707b1b209986d1422774b71e6902e3f5aa524b868db09d08a9f1`。

- 25 个 `draft_node_id` 规范化；
- 5 个 `parent_id` 引用同步；
- 2 个有序超限截断：一处 representative IDs 9→8，一处 includes 10→8；
- 节点数、名称、definition、status、Cluster 成员、Candidate、Evidence、excluded Cluster 均未变化；
- `semantic_change_count=0`。

同一位独立 Hierarchy Reviewer 对照两份 Raw 与 Diff 后给出 `CONFIRMED_NO_SEMANTIC_CHANGE`；Review SHA256 `c76ed62fb1d8dcf55853ed9062c8a3f902a3da566693fae1aafc5d4c9cb9301f`，Provider 调用 0，usage unknown。

## Reviewer 原始证据与 Freeze 重算

- Reviewer 原始输入：`domain-draft-a-hierarchy-review-bundle.json`，SHA256 `7569a69c44d3c8d733ab1705f02a5159800c2f655a2167e85d5113d09e454f94`。
- Reviewer 原始输出：`domain-draft-a-hierarchy-review-raw-output.json`，SHA256 `38e6b626977e4e19190f330c1cf54a6d4a765107bb5be1b3990ed584e4649bd5`。
- Reviewer 类型：独立只读 Codex subagent；项目 Provider 调用 0；usage 未暴露，记录为 unknown。
- Freeze 不信任手写 `freeze_eligible`，而是重新读取并校验原始输入/输出 Hash、原始 verdict、Blocking、Dimension Leakage、Direct 唯一性、Scope 派生、Schema 与结构 Gate。

## Blocking Engineering Debt

`ENG-DRAFT-A-002` 必须在 Trial Assignment 前完成：为同一 `run/stage/unit` 增加原子 single-flight / attempt lease。第二个进程看到状态为 `requesting` 且 lease 未过期时不得重发；过期接管必须保留 attempt history 并使用新的 attempt 目录；并发测试必须证明每个 lease attempt 只有一次 Provider 调用。

## 验证与提交

- Draft A 定向测试：9 passed。
- 全量测试：276 passed；仅保留既有 Starlette/httpx deprecation warning。
- `git diff --check`：通过。
- M3 Freeze commit：`287554a feat: review and freeze M3 domain alignment`，已推送。
- Draft A 初始冻结 commit：`1149ba6 feat: synthesize and freeze Domain Draft A`，已推送。
- 本轮工程审计与 Canonical v3 Freeze：测试通过后创建后续 commit 并推送（Commit ID 以 Git 历史为准）。

## 停止边界与下一阶段

Run #24 已完成语义冻结并进入工程 Hold：

```text
waiting_for_review / domain_draft_a_frozen_engineering_hold_before_trial_assignment
```

下一动作只能是实现并测试 single-flight / attempt lease。完成工程 Gate 前 `trial_assignment_eligible=false`，不得启动 M6。工程 Gate 解除后，Trial Assignment 仍需重点验证：树偏平是否真的妨碍浏览、相邻领域是否产生持续混淆、低支持节点是否获得有效赋值，以及 5 个 excluded Cluster 是否继续保持信息不足。
