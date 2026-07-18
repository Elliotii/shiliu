# V3 Run #24：M3 语义复核与 Domain Draft A 运行报告

日期：2026-07-19

分支：`codex/v3-domain-completion`

停止位置：`waiting_for_review / domain_draft_a_frozen_before_trial_assignment`

## 结论

本轮按恢复任务完成 M3 独立语义复核、一次 Reviewer-bounded Alignment Revision、M3 Freeze、Domain Draft A Synthesis、Complexity Gate、独立 Hierarchy Review 和 Draft A Freeze。

最终判定为 `PASS_WITH_CONCERNS`：M3 与 Draft A 均无 Blocking，允许下一阶段进入 Trial Assignment；本轮没有启动 Trial Assignment、Eval、Draft B、C2，也没有重跑 A/B/C1 或 M3 八个批次。

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
- Draft Hash：`be4c86e2038088af5ed966d2ab5cd60a2088df8387950bf8c21c167e171be855`。
- Tree Hash：`a19ffd72ebf4c9f83a7e203130b0c192058523085bf29d12e090eaf4549cfbff`。

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

Draft A 原计划为 1 次 Primary + 最多 1 次 JSON Repair。长请求恢复期间，两个恢复进程在较早请求尚未落盘时进入同一 attempt，最终收到 2 个 Primary 与 2 个 Repair Response。原始响应均有审计记录，但通用单文件 Repair 路径使较晚 Repair 覆盖了第一份 Repair raw。

| Response | 类型 | Prompt | Completion | Reasoning | Cached Prompt | 耗时 |
|---|---|---:|---:|---:|---:|---:|
| `565fc77e…` | Primary | 18,722 | 15,865 | 7,818 | unknown | 190.156s |
| `16cfca4b…` | Primary | 18,722 | 18,184 | 6,663 | 18,688 | 204.567s |
| `77dca950…` | JSON Repair | 9,356 | 8,079 | 0 | unknown | 69.407s |
| `b928a44f…` | JSON Repair | unknown | unknown | unknown | unknown | 95.819s |

可确认的最小合计：46,800 prompt、42,128 completion、14,481 reasoning tokens、560.049 秒；另有一个 Repair Response 的 usage 无法恢复，因此这不是完整上限。数据库 Stage Row 只覆盖其中部分调用，正式报告以 concurrency audit 的“已知最小值 + 1 个 unknown response”为准。

最终接受的是第二个 Repair Response。它在修正本地 Validator 的一条过严规则后直接通过：父子节点可以共享来源 Cluster 作为聚合 provenance，但无关分支不能重复消费同一 Cluster。该恢复没有新增 Provider 调用，也没有修改 Draft 语义。

## 验证与提交

- Draft A 定向测试：6 passed。
- 全量测试：273 passed；仅保留既有 Starlette/httpx deprecation warning。
- `git diff --check`：通过。
- M3 Freeze commit：`287554a feat: review and freeze M3 domain alignment`，已推送。
- Draft A commit：测试通过后在本轮创建并推送（Commit ID 以 Git 历史为准）。

## 停止边界与下一阶段

Run #24 已冻结为：

```text
waiting_for_review / domain_draft_a_frozen_before_trial_assignment
```

下一阶段允许执行 M6 Trial Assignment，但本轮没有启动。需要重点验证：树偏平是否真的妨碍浏览、相邻领域是否产生持续混淆、低支持节点是否获得有效赋值，以及 5 个 excluded Cluster 是否继续保持信息不足。
