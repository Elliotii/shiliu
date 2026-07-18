# V3 Checkpoint 3.9：Content Type Semantic Purification

## 最终结论

```text
FAIL
```

Checkpoint 3.9 的工程链路已经实现并完成两轮受限执行，但语义验收未通过。

第一次 Reduce-only Run #13 修复了明显的 Domain 泄漏；独立 Reviewer 随后发现
`自动化工作流设计` 与 `学习路线与职业规划` 仍把任务目标或使用情境当作内容形式，
因此按协议触发了唯一一次 Local Content Type Prompt 第二层修复。

第二层 Run #14 成功收缩 Local 候选并通过自动 Gate，但第二次独立 Reviewer 发现：

- `开源项目解析` 仍按对象类别拆分；
- `面试经验` 仍按求职使用情境拆分；
- `项目复盘与经验分享`、`面试经验`、`经验分享与建议` 兄弟边界重叠；
- 31 个 Normalize 候选全部被判为 Content Type，Reduce 没有真实拒绝；
- Judge 仍把“可在同类对象或情境中复用”误当成“表达形式”，产生假阴性。

附件约束规定：唯一一次第二层修复结束后，无论 PASS 或 FAIL 都必须停止。因此本轮
不会继续修改 Judge / Consolidation Prompt，不会再次调用模型，也不会进入 Run B、
Run C、Cross-run Merge 或 Trial Assignment。

## 1. 冻结范围

| 项目 | 值 |
|---|---|
| 正式来源 | Run #12 |
| Snapshot | #2 |
| Snapshot Hash | `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2` |
| Discovery Cards | 128 |
| 第一次 Purity Run | #13 |
| 第二层 Local Prompt Run | #14 |
| Model | `deepseek-v4-pro` |
| Thinking | off |
| 第一次实现 Commit | `09cd8ea8fca515e78cab82116b5d5dbe9e9f4707` |
| 第二层实现 Commit | `10e9dae` |

Run #10、#11 和 #12 的历史产物及 Manifest 没有修改。本轮没有读取 Silver
Reference、完整字幕或完整总结。

## 2. 实现内容

### Candidate Typing

每个候选必须输出：

```text
candidate_kind
reason
supporting_evidence
topic_substitution_result
recommended_action
target_node_id
salvaged_content_type
confidence
```

Schema 支持 `content_type / domain / topic / entity / mixed / unsupported`，并对
四种 `remove_as_*`、mixed salvage 和 needs-review 路由做严格校验。覆盖全部候选
只表示每个候选都有决定，不再强制所有候选进入最终节点。

### Reduce Prompt

第一次 Reduce 加入 Topic Substitution Test、通用正反例和“无固定 Top-K”约束；
没有写入 Run A 的期望分类名称。

第二层只修改 Local Content Type Prompt：

- 通常 3～6 个候选，8 个只是技术上限；
- 跨主题成立只是必要条件，不是充分条件；
- 必须回答内容如何表达、组织或呈现；
- 必须与讲什么、解决什么、使用情境分离；
- 禁止删去领域词后把主题重新包装为 Content Type。

Domain Prompt、Domain Draft 和 Snapshot 均未修改。

### 独立 Purity Judge 与 Gate

Judge 只读取最终节点、来源候选和 decisions、每节点最多 3 个 Compact Form View、
Domain 名称和定义。它不读取 Silver、人工分类、完整字幕或完整总结，也不能修改 Draft。

Gate 新增并实际记录：candidate typing coverage、五类泄漏、mixed/unsupported、拒绝
分布、Judge 分歧和静默归一化事件。

### 严格校验与预算预检

已移除 Pydantic `mode="before"` 的静默截断。越界字段现在产生 Validation Error，
进入独立 JSON Repair 或显式可审计归一化。

调用前预算记录估计、要求、分配上限和安全余量；未来 Domain 仅做预算验证，没有重新
调用。

## 3. 第一次执行：Run #13

### 复用与调用边界

Run #13 从 Run #12 零调用复用 15 个 Stage：

- 6 个 Domain Local Discovery；
- 6 个 Content Type Local Discovery；
- 两条 Normalize；
- Domain Consolidation。

只新增 Content Type Reduce 和 Purity Judge 两个模型阶段。

### 分型结果

```text
Normalize candidates  45
decisions             45 / 45

content_type          33
domain                11
unsupported            1

merge_into            31
keep                   2
remove_as_domain      11
remove_as_unsupported  1
```

最终 11 个节点：

```text
实操教程
工具评测与对比
技术原理解析
经验分享
观点评论
方法论与框架
项目复盘
工具介绍与推荐
自动化工作流设计
学习路线与职业规划
概念解释
```

自动 Gate 为 PASS，11 个节点均被 Judge 判为 pure。但第一次独立 Reviewer 给出
FAIL：`自动化工作流设计` 是任务/方法主题，`学习路线与职业规划` 混合使用情境；
Judge 把跨主题可成立误当作充分条件。

## 4. 唯一一次第二层：Run #14

### 复用与失效范围

Run #14 从 Run #12 零调用复用 8 个 Domain Stage：

- 6 个 Domain Local Discovery；
- Domain Candidate Normalize；
- Domain Consolidation。

真实重跑：

```text
6 Content Type Local Batch
→ Content Type Normalize
→ Content Type Reduce
→ Purity Judge
→ Quality Gate
```

第一次 Purity Run #13、Snapshot、Classification Profile、Compact Form View 和
Domain 路径均保留完整 Hash 血缘。

### Local 收缩

| 指标 | Run #13 来源 | Run #14 第二层 |
|---|---:|---:|
| 每批候选 | 8/8/8/8/8/6 | 5/6/6/6/5/5 |
| 原始候选 | 46 | 33 |
| Normalize 候选 | 45 | 31 |
| 饱和 Batch | 5 / 6 | 0 / 6 |
| C 级 ambiguous | 20 / 35 | 17 / 35 |

第二层 Prompt 对 Local 噪声和饱和确实有效。

### Reduce 与最终节点

```text
candidate_kind: content_type 31
recommended_action: merge_into 26, keep 5
removed / mixed / needs_review: 0
final nodes: 12
```

```text
操作教程
工具评测与对比
技术原理深度解读
项目复盘与经验分享
观点评论
开源项目解析
知识体系梳理
面试经验
论文精读
课程大纲
行业事件快讯
经验分享与建议
```

自动 Gate 仍为 PASS：12 个节点均被 Judge 判为 pure，0 blocking，3 warnings。
Warnings 为：最终节点偏多、`课程大纲` 只有一条支持、既有 Domain 新名称需审计。

### 第二次独立 Reviewer

Reviewer 结论：

```text
FAIL
```

Blocking Findings：

1. `开源项目解析` 以对象类别定义分类，且把项目介绍和源码解析混合；
2. `面试经验` 是求职情境，应并入通用经验/复盘形式；
3. 三个经验类节点存在严重兄弟重叠；
4. 31 个候选零拒绝，Candidate Typing 没有落实必要非充分条件；
5. Judge 使用被审 Candidate Decision 的 `passes` 作为自身证据，并继续使用同类对象/
   情境内复用的循环论证。

Reviewer 认为 `知识体系梳理`、`论文精读`、`课程大纲`、`行业事件快讯` 本身可解释为
形式，但低支持节点的长期浏览价值仍未证明。

主 Agent 接受 Reviewer 的 Blocking Findings，不接受自动 Gate 的假阴性 PASS。

## 5. Repair、恢复故障与审计

### Run #13

- Reduce 原响应把最终支持 ID 写成 `nct_*`；第一次 Repair 未修正，第二次窄 Repair
  使用冻结映射展开为 `C*`；
- Judge findings 合法，但 summary 超长；第二次窄 Repair 只压缩 summary；
- Reduce 的非支持字段和全部 decisions 保持不变；Judge findings 保持不变。

### Run #14

- Reduce 原响应有 8 条 notes 且支持 ID 使用 `nct_*`；
- 两次窄 Repair 分别修正一个问题，但没有同时满足两项约束；
- 恢复器错误地创建 `attempt-02`，意外重放一次完整 Reduce；该结果被明确标记为
  discarded，不参与最终 Draft，但 usage 和耗时仍计入审计；
- 最终使用附件允许的可审计归一化：以第一次 Repair 的语义结果为源，只展开 12 个
  节点的 supporting/representative IDs，共保存 24 条逐字段 original/normalized
  事件；
- Judge findings 合法但 summary 超长，第二次窄 Repair 只压缩 summary。

代码收尾已修复：

- 多次 Repair 始终复用最新已有 `attempt-*` 目录，不再重放完整请求；
- `audited-normalization.json` 的逐字段事件进入统一 normalization audit；
- completed Stage 清除旧 error 字段；
- 恢复成功后的 `run-failure.json` 改为带 `historical=true` 的
  `run-failure-history.json`。

Run #13/#14 的历史失败文件已归档，并保存 post-run recovery audit。

## 6. Token 与耗时

### Run #13

| 模型阶段 | API 请求 | Tokens | Provider 耗时 |
|---|---:|---:|---:|
| Reduce + Repairs | 3 | 50,088 | 171.805 s |
| Judge + Repairs | 3 | 25,574 | 52.008 s |
| 合计 | 6 | 75,662 | 223.813 s |

### Run #14

| 模型阶段 | API 请求 | Tokens | Provider 耗时 |
|---|---:|---:|---:|
| 6 个 Local CT Batch | 6 | 28,246 | 59.906 s |
| Reduce、Repairs、discarded replay | 5 | 67,010 | 228.171 s |
| Judge + Repairs | 3 | 24,780 | 43.457 s |
| 合计 | 14 | 120,036 | 331.534 s |

Checkpoint 3.9 两轮新增总计：

```text
20 API requests
195,698 tokens
555.347 provider seconds
reasoning tokens: 0
```

Run #14 中意外完整重放及其 Repair 共消耗 25,344 Tokens，属于明确的故障成本，
没有从报告中剔除。

## 7. 预算预检

| 阶段 | 估计 Completion | 安全要求 | 分配上限 | 安全余量 |
|---|---:|---:|---:|---:|
| Run #13 Reduce | 9,856 | 12,320 | 13,312 | 3,456 |
| Run #13 Judge | 5,760 | 7,200 | 8,192 | 2,432 |
| Run #14 Reduce | 10,233 | 12,792 | 13,312 | 3,079 |
| Run #14 Judge | 6,144 | 7,680 | 8,192 | 2,048 |
| Future Domain | 19,295 | 23,154 | 23,552 | 4,257 |

Run #14 根据 31 个新候选和历史主响应重新执行同一预检；Domain 只复用和验证，没有
模型调用。所有主响应 `finish_reason=stop`，没有再发生 length exhaustion。

## 8. 测试与工程证据

实现和测试覆盖：

- Candidate Typing 六类、四种移除和 mixed salvage；
- Topic Substitution 通用例子与无答案名称硬编码；
- 第二层“必要非充分”Local Prompt；
- Judge 输入边界与节点完整覆盖；
- 严格 Schema 拒绝静默截断；
- 预算预检及调用前失败；
- 第一次派生 Run 的 15 Stage 复用；
- 第二层的 8 Domain Stage 复用和 6 CT Batch 重跑；
- raw / parsed Hash 与持久化 Stage Hash；
- Repair resume 不创建新完整调用目录；
- 逐字段可审计归一化；
- completed Stage 清除旧错误；
- 恢复后的 failure 文件历史化。

最终全量测试：

```text
154 passed
1 existing Starlette/httpx deprecation warning
```

## 9. 停止位置与后续权限边界

```text
Checkpoint 3.9: FAIL
Run A 尚不具备进入 Run B/C 的条件。
```

如果未来继续，需要用户显式批准一个新的窄范围 Checkpoint，建议只调整
Consolidation / Purity Judge，而不再重跑 Local Discovery：

1. Judge 增加跨节点兄弟重叠检查；
2. “跨主题”必须跨对象类别和使用情境，而不是只在同类对象内替换；
3. Judge 不得把 Candidate Decision 自身结论当作独立证据；
4. `开源项目解析` 拆回项目介绍、技术原理或教程形式；
5. `面试经验` 合并到通用经验/复盘形式；
6. 对低支持节点保留 Draft/Warning，不直接视为稳定 Content Type。

本轮不自动执行这些修改。
