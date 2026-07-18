# 拾流 V3 Domain Completion 本轮运行报告

## 1. 结论与停止位置

本轮在一个安全、可恢复的阶段边界停止：

```text
Run #24
status: waiting_for_review
current_stage: cross_run_alignment_review
```

M1 Domain Semantic Contract v2 与 M2 unresolved adjudication 已冻结；M3 的 8 个 Provider Batch 和全部工程门禁已完成，但独立语义 Reviewer 尚未给出 verdict，因此 M3 **未冻结**，也没有进入 Domain Draft A。

这不是 Mission 完成点。当前最准确的阶段判断是：

```text
M3 engineering execution: PASS
M3 semantic review: not_evaluated
M4–M9: not_started
```

## 2. 冻结输入与边界

- Snapshot #2：131 Cards；128 Discovery Eligible；3 Trial-only。
- Snapshot Hash：`1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2`。
- Run A：旧单响应协议，42 Candidates；只作为独立证据源。
- Run B：Evidence Contract v2，40 Candidates；只作为独立证据源。
- Run C1：Evidence Contract v2，44 Candidates；Quality Gate FAIL，但工程产物冻结；只作为独立证据源。
- A/B/C1 没有被描述为同协议随机重复，没有使用 2/3 投票或固定 Run 权重。
- 本轮未运行 C2，未重跑 A/B/C1，未修改历史 Run，未读取 Silver Reference，未读取其他受控分面，也未进入前端、Embedding、BERTopic、向量数据库或 Agent Harness。

## 3. 已完成 Milestone

### M0 — Mission bootstrap

- 建立 living ExecPlan、Status、Decision Log。
- 建立 `codex/v3-domain-completion` 分支和 Checkpoint 3.12D 恢复边界。

### M1 — Domain Semantic Contract v2

- 产物：`domain-semantic-contract-v2.json`、`semantic-contract-diff-a-b-c1.json`。
- 独立复核：`PASS_WITH_CONCERNS`，0 Blocking。
- Revision 01 将 Domain 语义类型与 Evidence maturity 分离，并把 parent entailment 限定到子节点。
- Contract payload hash：`21c17219474615b9e828431c2135fe039c81fb0cf823700a5078c07c618d0b6f`。
- Diff payload hash：`0f9b7e4140e5ad2735ecfb6a4e02c6864979729a193434fc9f6fbbee66fc26a5`。

### M2 — Unresolved adjudication

- Run B 3 项 + C1 10 项，保留来源后去重为 12 组。
- 最终：6 `merge_into_existing`、6 `downgrade_to_topic`、0 `create_domain_proposal`。
- 首轮 Reviewer 发现 4 个 Blocking；Revision 01 后第二轮为 `PASS_WITH_CONCERNS`，0 Blocking。
- Final payload hash：`c472c4c3c73ef566a7a1afc9b43283b0d617ef4c664afa860eb1d963b7a936e5`。

### M3 — Candidate-centric cross-run alignment（工程执行完成，未冻结）

- 本地 Pair：105；source component：42；pair score 仅作高召回候选，不作语义决策。
- 126 Candidates：A 42 / B 40 / C1 44。
- 8 个 high-thinking Batch，形成 65 个 provisional Cluster。
- 关系分布：24 equivalent、24 unrelated、5 overlapping-but-distinct、5 granularity-variant、4 protocol-specific、3 uncertain。
- disposition：47 domain-candidate、16 non-domain-topic、1 non-domain-entity、1 uncertain。
- status：40 probable、6 weak、2 uncertain、17 not-applicable、0 stable。
- exact coverage：126 / 126；missing=0、extra=0、duplicate=0。
- M2 downgrade 被复晋升为 Domain：0。

M3 payload hashes：

- Clusters：`71b240220dc51a0ca4d2c3241b967090acf2d4441963d0e9f103755586032693`。
- Decisions：`c43b319e421ab86770292d14c208f2790def9e8960cf96b6befc0dd469c718c0`。
- Gate：`READY_FOR_INDEPENDENT_REVIEW`；该状态不等于 PASS。

## 4. Provider 调用与成本

### M3 批次审计汇总

| Batch | Stage attempts | Input | Output | Reasoning | Elapsed | Repair | Local recovery |
|---|---:|---:|---:|---:|---:|---|---|
| 001 | 1 | 12,656 | 9,280 | 5,171 | 137.963s | yes | yes |
| 002 | 2 | 20,336 | 23,879 | 21,135 | 362.897s | yes | yes |
| 003 | 1 | 9,935 | 11,274 | 8,078 | 175.093s | yes | no |
| 004 | 1 | 13,266 | 13,322 | 7,905 | 244.235s | yes | yes |
| 005 | 2 | 15,701 | 14,697 | 8,426 | 158.346s | yes | no |
| 006 | 1 | 11,861 | 13,206 | 10,184 | 178.707s | no | no |
| 007 | 1 | 11,891 | 11,824 | 6,849 | 166.442s | yes | yes |
| 008 | 1 | 7,230 | 7,893 | 3,904 | 111.575s | yes | yes |
| **M3 total** | 10 | **102,876** | **105,375** | **71,652** | **1,535.258s** | 7 batches | 5 batches |

M1–M3 全 Run 累计：

```text
input_tokens:     141,165
completion_tokens: 140,142
reasoning_tokens:  90,500
elapsed_seconds: 2,062.617
cost_value: unknown
```

Provider 未返回可用货币成本，因此成本保持 `unknown`，没有伪造金额。

### 失败与额外消耗

1. Batch 002 首次调用在 8,191 reasoning tokens 后 `finish_reason=length`，正文为空；该失败额外消耗 10,168 input + 8,191 completion/reasoning，146.285 秒。随后只重试 Batch 002。
2. Batch 005 首次 TLS 连接失败，无响应、无 token usage，耗时 5.011 秒；随后只重试 Batch 005。
3. JSON Repair 共发生于 7 个 Batch；Repair 合计约 16,906 input + 14,085 output，201.678 秒，不含额外 reasoning。
4. 5 个 Batch 使用零 Provider 的本地恢复；所有恢复都有 source hash、before/after、result hash，且 `provider_call_count=0`。

## 5. 恢复和 Schema 决策

本轮只允许以下恢复：

- 从冻结 Candidate 原名/定义选择 canonical name/definition，不发明新语义；
- 对 exceeds-Schema 的 includes/excludes/representatives 有序截限；
- 对已有 Provider grouping 补 provenance reason，不改变分组；
- M3 pre-Assignment `stable` 降为 `probable`；
- 非 Domain Topic/Entity 可保留空 includes/excludes；
- `domain_disposition=uncertain` 保留 `status=uncertain`，不强制伪装成非 Domain。

本地代码没有修改 Cluster 成员、Provider canonical definition 的语义、Evidence Pool 或 disposition。M2 已冻结 downgrade 的复晋升由 Validator 硬拒绝。

## 6. 验证结果

- M3 expected / actual Candidate：126 / 126。
- missing / extra / duplicate：0 / 0 / 0。
- A / B / C1 provenance：42 / 40 / 44。
- stable before Assignment：0。
- M2 downgrade repromotion：0。
- 定向测试：18 passed。
- 全量测试：261 passed。
- `git diff --check`：通过。
- 唯一测试 warning：现有 Starlette `TestClient` 对 httpx 的 deprecation warning，与本轮功能无关。

## 7. 尚未通过的语义门禁

本地反例扫描发现下列问题必须先由独立 Reviewer 裁决：

1. Agent 架构/系统工程/开发方法论被分散在多个 local component，存在近重复 Scope。
2. RAG 形成两个高度相近的 Cluster。
3. AI 辅助开发形成多个相近 Cluster。
4. 求职/面试 Cluster 可能把 `Suggested Use Context` 错当 Domain，违反 Contract v2。
5. 工具/配置、学习方法论等 Scope 需要检查是否属于稳定实践问题空间，还是 Object/Use Context/Topic 泄漏。

第一个独立 Reviewer 子任务因额度耗尽而失败，没有形成 verdict；第二个 Reviewer 在用户要求本轮停止后被中止。因此独立复核状态必须记录为：

```text
not_evaluated
```

不能记录为 PASS、PASS_WITH_CONCERNS 或 FAIL。

## 8. 尚未完成的 Mission 交付物

- M3 独立复核、必要的最小跨 Component Alignment Revision 和 M3 冻结。
- `domain-draft-a.json` / `domain-draft-a-tree.md`。
- Hierarchy Validator 与风险复核。
- 131 / 131 Trial Assignment。
- Initial Eval / Diagnosis。
- 有界 Revision 01；门禁满足时才可能 Revision 02。
- Domain Draft B、Final Assignment、Final Metrics、Decision Log JSON 和最终独立 Reviewer。
- `reports/V3_DOMAIN_COMPLETION_FINAL.md`。

## 9. 下次恢复入口

先检查，不直接继续：

```bash
PYTHONPATH=src:. .venv/bin/shiliu taxonomy status 24
```

下一动作顺序：

```text
独立只读 M3 Reviewer
→ 最小跨 Component Alignment Revision
→ 重新执行 126 / 126 工程门禁
→ 第二次独立复核（如首轮有 Blocking）
→ 冻结 M3
→ 进入 Draft A
```

在 M3 Reviewer 与 Revision 记录完成前，不应把普通 `resume 24` 当作自动进入 Draft A 的授权。
