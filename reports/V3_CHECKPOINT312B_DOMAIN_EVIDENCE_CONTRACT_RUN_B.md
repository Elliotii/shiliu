# V3 Checkpoint 3.12B：Domain Evidence Contract v2 and Run B Completion

状态：`FAIL_BEFORE_ADAPTER_IMPLEMENTATION`。

本报告记录 Run #22 原始 Consolidation 响应审计发现的阻塞事实。为避免伪造来源血缘，本轮没有实现 Adapter、没有生成 Run A/B v2 派生视图，也没有改变旧 Run。

## 1. Git 冻结

- 停止现场 Commit：`acce8e25564400115b63201d6c205b82eae7535d`
- Tag：`checkpoint/v3.12-stopped-at-run-b`
- 分支：`feat/v3-domain-evidence-contract`
- Run #22 冻结文件清单 Hash：`361e2e3ff8657865570d51db04da5ca81d9a56bc2197ced5bb991ba1104ff17b`
- Run #22 数据库状态仍为 `retry_wait / domain_consolidation / invalid_model_output`。

## 2. 新增 Provider 成本

```text
新增 Provider 调用：0
新增 Provider Token：0
```

本轮没有重跑 Local Discovery、Consolidation 或 JSON Repair。

## 3. 原始响应事实

Run #22 Consolidation 主调用审计显示：

```text
finish_reason：length
completion_tokens：18,432
reasoning_tokens：13,261
raw_response_chars：16,605
```

主响应文件已完整落盘，但模型输出在 `candidate_decisions` 的 `nc_037` 对象中途结束，因此文件不是完整 JSON。

### 已完整落盘的 Domain 部分

主响应中的 `domains` 数组可以独立完整解析，共 9 个一级 Domain。其逐字段规范化 Hash 为：

```text
5db1a1c709f513f63fb51bb8a7434fe2de355ca72b1bd37e0949f2cefa200555
```

两次 Repair 的 Domain 数组与主响应逐字段完全相等，Hash 也完全相等。Canonical includes、35 条父节点证据及 C106/C128/C117 因而有一致、可验证的模型来源。

### 未完成的 Candidate Decision 部分

- Candidate Table：40 条，`nc_001–nc_040`。
- 主响应：只有 `nc_001–nc_036` 是完整 JSON 对象；`nc_037` 在 `"action` 中途截断。
- Repair 1：只有 `nc_001–nc_036`。
- Repair 2：与 Repair 1 逐字节相同，也只有 `nc_001–nc_036`。
- 主响应已完成的前 36 条 Decision 与 Repair 的 36 条逐字段完全一致。

缺失完整 Consolidation 决策的候选：

| Candidate | 名称 | Evidence | 与现有节点证据关系 |
|---|---|---|---|
| `nc_037` | 算法与数据结构 | `C131` | 无重合 |
| `nc_038` | 自动化演示文稿生成 | `C084` | 无重合 |
| `nc_039` | 语音交互系统 | `C016` | 仅与 `d_08` 重合 1 条，Jaccard 0.0286 |
| `nc_040` | 间隔重复系统 | `C126` | 无重合 |

没有其他落盘文件包含这四个候选的完整 `action / target_id / reason` 决策。

## 4. 为什么不能实现 v2 Adapter

Domain Evidence Contract v2 要求：

- `source_candidate_ids` 完整覆盖 Consolidation 对节点的候选归并决定；
- 来源候选不得为减少证据池而删除；
- Adapter 不得伪造正式 Assignment 或模型未做出的语义决定；
- 无法追溯来源必须 Blocking。

当前可以无损适配 9 个 Domain 节点的语义字段与证据字段，也可以保留全部 canonical includes、35 条父节点模型证据和 C106/C128/C117。但无法证明 `nc_037–nc_040` 是：

- 合并到哪个现有节点；
- 降级为 Topic / Entity；
- 删除为 unsupported；
- 还是形成被截断的新节点。

按名字或证据重合进行本地映射会创建模型未完成的 Consolidation 决策；把它们直接忽略则会静默删除四个来源候选。两种做法都违反 v2 防伪造和完整血缘要求。

## 5. 未实施内容

- 未编写正式 Evidence Contract ADR；
- 未实现 v2 Schema / Adapter；
- 未生成 Run A/B v2 派生视图；
- 未执行 Parent/Child v2 Gate；
- 未把 Run #22 改成 completed；
- 未创建 Run C、Merge、Validator 或 Draft A；
- 未读取 Silver Reference；
- 未修改 Prompt、Profile、Candidate Table、Domain 节点或父子结构。

## 6. 解除阻塞所需的新授权

以下方案至少批准一个，才能继续：

1. 允许一次只针对 `nc_037–nc_040` 的窄范围 Candidate Decision 补全调用；不提供原始卡片，只提供冻结 Candidate Table、现有 9 个节点及原始响应尾部。
2. 明确允许把四个候选标记为 `unresolved_candidate_ids`，使 Run B 以 Blocking 或 `PASS_WITH_CHANGES` 保留，禁止进入 Run C，直到后续人工或模型补决策。
3. 明确授权一个本地确定性推断规则，并接受它不是原 Consolidation 模型决策。当前证据不足，不推荐。

在本轮“零 Provider 调用、不得伪造来源、Run B 必须完整验收”的组合约束下，没有安全恢复路径。

## 7. 结论

### 独立只读 Reviewer

结论：`FAIL`，必须停止。

Reviewer 独立确认：

- 主响应因 `finish_reason=length` 截断；
- 9 个 Domain 与 Repair 逐字段相同；
- Candidate Table 为 40 条，但主响应和 Repair 都只有 36 条完整 Decision；
- `nc_037–nc_040` 没有落盘的完整 `action / target_id / reason`；
- reasoning 日志不是最终结构化决策，且不能作为 Adapter 血缘；
- Run #22 文件树 Hash、数据库状态和 Stage 数量在复核前后均未改变；
- 在零模型调用与禁止伪造来源的组合约束下，不能完成 Run B Gate。

Blocking Finding 与主 Agent 一致，没有尚未解决的判断分歧。

```text
FAIL
Evidence Contract v2 的字段设计本身可成立，
但 Run #22 缺少 nc_037–nc_040 的完整 Consolidation 决策。
在不调用模型、不删除候选且不伪造来源血缘的条件下，无法完成 Run B 验收。
```
