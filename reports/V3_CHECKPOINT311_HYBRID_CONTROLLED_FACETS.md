# V3 Checkpoint 3.11 — Hybrid Controlled Facets

## 结论

```text
FAIL
```

本轮没有形成完整的 48 条受控分面赋值，因此不能宣称混合受控分面已经通过验证，也不能进入 128 条、Run B/C 或正式 UI。失败发生在结构化赋值的最后一批：同一内容重复输出同一个 Object Type，主响应与 JSON Repair 均未去重。附件允许的两轮窄修复已经用完，主 Agent 按停止条件终止继续修改和重跑。

这个 FAIL 是 Checkpoint 执行失败，不等价于已经证明受控 Form/Object 缺乏独立检索价值；后者因 48 条结果不完整而尚未得到公平评估。

## 1. Git 冻结与分支

| 项目 | 值 |
|---|---|
| Checkpoint 3.10 冻结 Commit | `6e0673e85474251f0c5362198076b52754ec36a0` |
| 冻结 Tag | `checkpoint/v3.10-failed` |
| 当前分支 | `feat/v3-hybrid-controlled-facets` |
| 基础实现 Commit | `adc5039` |
| 窄修复 1 | `8562679` |
| 窄修复 2 | `bef9e97` |

Run #15、#16、#17 的 Manifest Hash 在新 Run 创建时冻结，并由运行时 Gate 复核。旧开放词表仅作为禁止输入列入 Manifest，不作为正确性证据。历史 Run 没有被恢复或改写。

## 2. ADR 与架构边界

ADR：`docs/adr/ADR_V3_HYBRID_CONTROLLED_FACETS.md`

当前模型明确拆分为：

- Domain：继续读取冻结 Run #12，保持开放、最多两级；本轮不发现、不修改 Domain。
- Presentation Form：版本化受控词表，稳定 ID `PF01`–`PF11`。
- Focus Object Type：版本化受控词表，稳定 ID `OT01`–`OT09`。
- Suggested Use Context：版本化受控词表，稳定 ID `UC01`–`UC08`，允许为空且仅为建议属性。
- Novelty：只生成 Proposal，不得在运行时发布 active 词条。

Checkpoint 3.10 的开放 Form/Object/Context Builder 已禁止创建新 Run；未完成的旧 Run 只读，已完成 Run 仍可查询状态。

## 3. 受控词表

| 词表 | Active 数 | 文件 Hash |
|---|---:|---|
| Presentation Form v1 | 11 | `c4fdcfe01322e3795a25e25cd5f219d2c68404261157768137e823521668d57a` |
| Focus Object Type v1 | 9 | `8fbcb4593a3f0979812476aafcc94098baa2a5a8b05c5943a9cef2fa45dc4ab0` |
| Suggested Use Context v1 | 8 | `2bd8e3b691bc86436071971b2f1d9ad5b3709ca8772a03cf453f6b6c8d1edf82` |

词表在运行时只读，Run Manifest 冻结 Hash；Hash 变化会阻止执行。未发现运行时创建 active 词条、自由标签或隐性 Top-K。

## 4. Entity → Object Type

规则版本为 `entity-object-type-mapping-v1`：

- 有可靠类型时优先确定性映射；
- 当前 Profile 中多数 Entity 只有字符串而无类型，保存为 `untyped`；
- 模型只能在既有 OT ID 内辅助选择，也可留空；
- `source_entities` 必须逐字来自该卡片冻结 Entity；没有 Entity 时 Object Type 必须为空；
- 具体实体名保留在 `source_entities`，不得写成新的 Object Type。

Run #19 暴露出 Repair 不知道每卡允许 Entity 的缺陷；Prompt v3 和 Repair Hint 随后冻结了每卡 Entity 白名单。Run #20 未再触发未知 Entity 门禁。

## 5. 相同 48 条输入

三个 Run 均使用同一冻结范围：

```text
Snapshot: #2
Domain Draft: Run #12
Profile Spike: profile-spike-s2-20260717T143038355542Z
Cards: 48
Evidence: A/B/C = 22/9/17
Batch size: 12
```

Run Manifest Hash：

- Run #18：`141032ed00a0d446a172f2f89f3215cc8750c615cf20269f4adff67ac58d079d`
- Run #19：`fffc89fd0c7b0ff3183e126cdffe11eff32d7bda3471fb9a9be21d36df7a120a`
- Run #20：`80a2b9d930b1cf66fcd50404ea7e5944d6dfff1f1a5360ce776a5b101449ac29`

## 6. 两轮窄修复与停止原因

### Run #18

- Batch 1 完成；Batch 2 失败。
- 模型将 `secondary_paths` 写为 `["child_id"]`，Schema 要求完整路径数组。
- 窄修复 1：接受无歧义 shorthand，并用冻结 Domain 父子关系规范化；Prompt v2 明确完整路径格式。

### Run #19

- Batch 1–2 完成；Batch 3 失败。
- 主响应出现空 `source_entities` 和超长 evidence；Repair 随后填入不属于该卡片的 Entity，被证据 Gate 拒绝。
- 窄修复 2：Prompt 与 Repair Hint 都携带每卡 Entity 白名单；无 Entity 时 Object 必须为空；evidence 最多 3 条。

### Run #20

- Batch 1–3 完成；Batch 4 失败。
- `C071` 对两个不同 Entity 分别输出 `OT07`，违反单卡 Object Type ID 唯一约束。
- JSON Repair 保留了重复项，Schema 再次拒绝。
- 由于两轮修复额度已用完，没有静默去重、没有修改 Schema、没有创建 Run #21。

最终状态：Run #18 `retry_wait`、Run #19 `failed`、Run #20 `retry_wait`。这些状态和原始请求/响应保留在本地私有运行目录，不提交 Git。

## 7. Token、耗时、Repair、Retry

| Run | 主调用 | Repair | Prompt Tokens | Completion Tokens | Total Tokens | Provider 秒 | 结果 |
|---|---:|---:|---:|---:|---:|---:|---|
| #18 | 2 | 1 | 20,325 | 9,345 | 29,670 | 65.611 | Batch 2 失败 |
| #19 | 3 | 2 | 34,579 | 18,182 | 52,761 | 123.553 | Batch 3 失败 |
| #20 | 4 | 4 | 56,103 | 31,312 | 87,415 | 218.811 | Batch 4 失败 |
| 合计 | 9 | 7 | 111,007 | 58,839 | 169,846 | 407.975 | 未形成 48 条结果 |

Provider 没有返回 reasoning token，故该字段为 unknown。Run #20 的 4 个批次均进入 Repair，说明当前 Schema 遵循仍不稳定；即便第四批去重，Repair 率本身也应作为扩容前关注项。

## 8. Novelty、动态筛选、冗余与派生筛选

以下产物没有生成：

- 完整 48 条 `controlled-facet-assignments.json`；
- `facet-novelty-proposals.json`；
- `dynamic-faceting.json`；
- `derived-filter-proposals.json`；
- `checkpoint311-quality-gate/quality-result.json`；
- 完整 Reviewer Bundle。

原因是这些都是完整赋值后的确定性阶段。系统没有用 36 条部分结果伪造 48 条指标。

## 9. 与 Checkpoint 3.10 的公平对比

| 指标 | 3.10 开放分面 | 3.11 受控分面 |
|---|---:|---:|
| Form 词表容量 | 28 | 固定 11 |
| Object 词表容量 | 28 | 固定 9 |
| Context 词表容量 | 29 | 固定 8 |
| 完整赋值内容 | 48 | 未完成 |
| 模型调用 | 已完成旧 Pipeline | 9 主调用 + 7 Repair |
| Total Tokens | 166,357 | 169,846（含三次诊断 Run） |

不能公平比较 Form unknown、Object/Context 空值、平均标签、Novelty、同义词碎片、跨分面共现和动态筛选，因为 3.11 没有完整 48 条结果。受控词表的节点容量显著收敛是架构事实，但不是质量 PASS 证据。

## 10. 自动 Gate

```text
NOT_EXECUTED
```

自动 Gate 位于完整 Assignment 之后。由于 Run #20 在 Batch 4 被 Schema Gate 阻断，后续 Gate 不存在。前置边界检查已确认：Domain、受控词表与历史 Manifest Hash 未变化；运行输入未包含 Silver Reference 或 Run #17 开放词表。

## 11. 独立 Reviewer

```text
FAIL
```

Reviewer 只读取了代码、ADR、受控词表、本报告、Run Manifest 和非 Silver 运行审计；没有修改代码/数据库、发起 Provider 调用或使用 Run #17 Candidate Decisions 证明正确性。

Reviewer 已确认：

- Checkpoint 3.10 Tag、Run #12/#15/#16/#17 Manifest Hash 和新 Run 血缘一致；
- ADR 正确区分开放 Domain 与受控 Form/Object/Context；
- 三套词表版本化、运行时只读且只接受 active ID；
- 旧开放 Builder 被 Service 硬阻断；没有自由正式标签、隐性 Top-K 或静默截断；
- C071 的两个 Entity 均可追溯，但重复 OT07 被正确拒绝；
- 两轮修复和停止位置符合协议；成本数字可复现。

Reviewer 的 Blocking Findings：

1. 完整 48 条未形成，不能用 36 条推断覆盖率、Novelty、空值率、筛选价值或分面独立性；
2. Run #20 四批全部进入 Repair，且主响应反复产生 Schema 外字段，结构遵循存在系统性不稳定；
3. 受控容量从 `28/28/29` 收敛到 `11/9/8`，但实际检索价值尚未验证；
4. 当前 122 个真实 Entity 全部为 `untyped`，确定性映射优先路径只在代码和合成测试中成立，尚无真实样本证据。

Reviewer 要求在新的显式授权下才允许继续：对重复 OT 做字段级可审计合并，明确禁止 Schema 外 Domain 字段，只重跑受影响批次；完整结果形成后重新执行动态分析、自动 Gate、公平对比和独立复核。

## 12. 测试

```text
193 passed, 1 third-party deprecation warning
```

覆盖受控稳定 ID、运行时只读、active/deprecated、Form 受控 ID、unknown/novelty、Entity 映射、Object 无证据为空、Context 可空、Novelty Proposal、旧路径禁用、Domain/历史不变、无静默截断、动态非零选项、OR/AND、跨分面冗余、派生表达式、Reviewer 输入边界及两项窄修复。

## 13. 是否值得扩到 128 条

```text
NO
```

当前连相同 48 条的结构化赋值都没有稳定完成，且 Run #20 Repair 率为 100%。在新的显式授权前，不应进入 128 条、Run B/C、Domain Trial Assignment 或 UI。
