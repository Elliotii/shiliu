# V3 Checkpoint 3.12：Domain Stability and Draft A

状态：`STOPPED_AT_RUN_B`。本报告记录硬停止现场；Domain Draft A 尚未形成。

## 1. Checkpoint 3.11B 冻结

- 基础 Commit：`033b92a783c71344320499c5947e6d1cb9619000`
- Tag：`checkpoint/v3.11b-pass-with-changes`
- 工作分支：`feat/v3-domain-stability`
- Run #21 未修改；版本化动态分面与跨分面指标保存在新的本地派生目录，不写回 Run #21。

## 2. 无模型工程加固

- 新增 `repair-semantic-diff.json`，区分 syntax、schema、normalization 与 semantic selection/addition/removal。
- Object Type 超过两个时不按输出顺序截断；未选择项进入 `overflow_object_type_candidates`。
- Gate 支持 Repair、语义 Repair、未类型化 Entity、模型辅助 Object 与 Overflow Warning。
- 新增 `dynamic-facet-metrics-v1.json` 和 `cross-facet-redundancy-v1.json` 离线冻结工具。
- Entity Typing 延后到剩余 80 条受控分面赋值之前，见 `ADR_V3_DOMAIN_STABILITY.md`。

## 3. Run A 可比性审计

结论：`COMPARABLE`。

- Snapshot Hash：`1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2`
- Classification Profile Hash：`07a814d37dacf397790c6928f9e4f84768d2eb138a3112152cac383edd7f39ba`
- Run A Manifest Hash：`fe896db14a3afc7d8a4a285c5ed39bf43ccf33f2d9af7cb05841548c6dc0ce97`
- 当前 Semantic Contract Hash：`305adfbc146b4aea2c824110e590fafb628649e478012630b438d8b457a4f83a`
- 6 个 Local Discovery Prompt 均与 Run A 冻结 Prompt 逐字节 Hash 相同。
- Consolidation Prompt 与 Run A 冻结 Prompt 逐字节 Hash 相同。
- Prompt、输入 View、Normalize、Consolidation 任务、模型与 Thinking 配置没有语义漂移。
- 后续差异仅为严格 Schema、原始响应先落盘、独立 Repair、Resume 与审计字段。

本地审计产物：`<local-content-dir>/taxonomy/runtime/checkpoint312-foundation/run-a-comparability-audit.json`。

## 4. Run B

### Manifest

- Run ID：`22`
- Label / Seed：`B / 202`
- Eligible Card：128；D 级未进入。
- Batch Size：24，共 6 批；全局顺序和批次成员已冻结。
- 创建代码 Commit：`64ef7f7`

### 已完成阶段

- Domain Local Discovery：6/6，一次成功。
- Candidate Normalize：完成。
- Domain Consolidation 主调用：原始响应已落盘，但未通过严格 Schema。

### 成本

| 部分 | Token | 耗时 |
|---|---:|---:|
| 6 个 Local Discovery | 19,181 | 118.396 s |
| Consolidation 主调用 | 24,104 | 235.163 s |
| Repair 1 | 10,575 | 43.644 s |
| Repair 2 | 10,628 | 46.774 s |
| 合计 | 64,488 | 443.977 s |

Consolidation 主调用包含 13,261 reasoning tokens。没有重放主语料调用；两次 Repair 都只读取 raw response、validation error 和精简 Schema。

## 5. 停止原因

主响应存在三个列表预算问题：两个 `includes` 为 6/5，一个父节点 `supporting_ids` 为 35/32。Repair 1 与 Repair 2 的响应 Hash 完全一致，仍保留相同超限。

第二轮窄修复使用冻结 Candidate Table 对超限字段进行确定性、有审计的语义选择，随后原语义校验发现父子支持范围不合法：

| Parent | Child | Child 中不属于 Parent 的 ID |
|---|---|---|
| `d_08 AI辅助软件开发` | `d_08_02 AI编程工具与终端` | `C106` |
| `d_08 AI辅助软件开发` | `d_08_04 AI编程学习路径` | `C128` |
| `d_08 AI辅助软件开发` | `d_08_05 AI应用开发策略` | `C117` |

父节点已经达到 32 个 supporting IDs。继续处理必须在以下语义动作中选择：

1. 将三个子节点证据优先纳入父节点，同时移除父节点其他三个证据；
2. 从子节点移除这三个证据；
3. 修改父子结构；
4. 修改 Schema 容量或 Domain Prompt。

这些都不是纯格式 Repair。Run B 已使用两轮窄修复额度，因此依照 Checkpoint 3.12 硬停止条件停止。

## 6. 未执行

- Run C 未创建；
- Cross-run Merge 未执行；
- Hierarchy Validator 未执行；
- Domain Draft A 未形成；
- Draft A Gate 与独立 Reviewer 未执行；
- 未进行 Trial Assignment、Diagnosis、Revision、剩余分面赋值或 UI 工作。

## 7. 当前结论

```text
FAIL
Checkpoint 3.12 在 Run B Consolidation 停止。
A/B/C 尚未形成，因此不能声称已得到稳定、可解释或可追溯的 Domain Draft A。
```

建议下一轮显式批准一种父子支持预算协议后，仅从 Run #22 已保存的 Consolidation 原始响应继续；不要重跑 6 个 Local Batch，也不要重放 Consolidation 主调用。
