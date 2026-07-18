# V3 Domain Completion — M1 Semantic Contract

## Outcome

M1 已冻结为 `Domain Semantic Contract v2 / Revision 01`。第二轮独立只读技术复核为 `PASS_WITH_CONCERNS`，没有 Blocking，可以进入 unresolved adjudication。

## What was frozen

- Domain 是相对稳定、可长期复用的知识领域或实践问题空间。
- 当前证据数量不决定语义类型，只决定节点成熟状态。
- `stable / probable / weak / uncertain` 有明确、互不冲突的语义。
- 至少两个不同 `content_id` 才构成 multi-evidence；同一内容跨 Run 重复不重复计数。
- 顶层与二级节点使用不同层级条件；只有二级节点要求 parent entailment 与语义子集。
- Form、Object、Use Context、Topic、Entity 不进入 Domain Tree。
- unresolved 不自动创建 Domain，必须进入正式 adjudication。
- 最大层级为两级，父子关系不使用 Evidence Set 包含替代语义包含。

## Execution and recovery

- Mission Run：`24`。
- 1 次 high-thinking 主调用，1 次 JSON Repair；合计 13,610 input、14,358 output、5,525 reasoning tokens，181.126 秒。
- Repair 后的结构尾差由本地确定性恢复处理，额外 Provider 调用为 0，并保存 transformation audit。
- Provider Draft、Repair 原文、最终 Revision 与独立复核均保存在 `<local-run-artifact>/run-000024/`，不提交私人 Runtime 数据。

## Review history

首轮 Reviewer 判定 FAIL，Blocking 为：

1. Domain 本体与 multi-evidence 成熟度冲突；
2. 顶层节点被错误要求满足 parent semantic subset。

Revision 01 只修改对应 Contract 字段及 Diff `sr_01 / sr_03 / sr_06`，并保留 Provider Draft。第二轮 Reviewer 确认两项 Blocking 已消除。

## Hashes

- Contract payload：`21c17219474615b9e828431c2135fe039c81fb0cf823700a5078c07c618d0b6f`
- Semantic Diff payload：`0f9b7e4140e5ad2735ecfb6a4e02c6864979729a193434fc9f6fbbee66fc26a5`

## Deferred concern

`stable` 的可计算 Assignment 产品门槛将在 M6 Assignment Protocol 中冻结。在该门槛完成前，Pipeline 不得自动把任何节点晋升为 stable。

## Validation

```text
250 tests passed
git diff --check passed
independent review: PASS_WITH_CONCERNS, blocking=0
```
