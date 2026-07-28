### A. Audit Status

```text
Completed with Unknown
```

两个授权目标均已核查。Unknown 来自：

- `SHILIU_V3_VERSION_DECISION.md` 本地缺失；
- 除 amended ledger 外，其余资产没有可比对的 Stage 6B 历史 hash；
- 仓库中没有名为 “Master Case Seed” 的独立资产或定义可确认 video 88 的该项身份。

## B. video 88 Finding

### Classification

```text
Confirmed Multiple Timeline Runs
```

更精确地说：这是同一视频、同一 P、同一 CID、同一字幕轨道中的两个单调时间运行段，以反向顺序拼接进同一个 JSON array。该 Artifact 整体不满足单调时间序列，但现有证据不支持“多个 P/cid/字幕轨道被混合”。

### Confirmed Fact — DB 与 Artifact 身份

| 字段 | Live / Snapshot 事实 |
|---|---|
| video_id | `88` |
| BVID | `BV1TxwQz5E4B` |
| part / P | `1` |
| CID | `36755996991`，仅存在于 `metadata.json`，DB 无 `cid` 列 |
| page_count | `1` |
| title / part_title | `龙虾退散潮，我做了一期OpenClaw理性入门教程｜下` |
| subtitle source | `human` |
| upstream type | `0` |
| language | `zh` |
| processing status | `completed`，无 error_code |
| duration | `2768s` |
| Live raw path | `/Users/elliot/Documents/Shiliu/videos/BV1TxwQz5E4B/subtitle-raw.txt`；JSON 位于同目录 |
| Snapshot raw path | `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV1TxwQz5E4B/subtitle-raw.json` |

Snapshot Manifest 对应 Raw Subtitle：

```text
sha256:
cc6afce905dc90ee1c89d1906c2617ba80c4992196c256e5fa8a66db9c0e2f0c

size:
166855 bytes

status:
ok
```

本轮重新计算的 Snapshot Artifact hash 与 Manifest 完全一致。

Metadata Manifest：

```text
sha256:
2581e74dae387a53990c6f05f47f8bde52e3bbb8951d14e9385d069cf491dca4
```

### Confirmed Fact — JSON 结构

Artifact：

- 顶层是 JSON array；
- 共 `1748` 个 Segment；
- 每个 Segment 都是 object；
- 所有 Segment 具有完全一致的 `content/from/to` 字段；
- 没有嵌套的新标题、章节、P、CID 或 subtitle-track 标记；
- Metadata 只声明一个 human subtitle track。

因此没有 JSON schema 异常，但数组顺序不是全局时间单调。

### Confirmed Fact — 两个 Timeline Runs

| Run | Segment indices | 时间范围 | 数量 |
|---|---:|---:|---:|
| Run 1 | 0–1388 | `567.400–2767.800s` | 1389 |
| Run 2 | 1389–1747 | `0.133–567.333s` | 359 |

两个运行段各自单调，且边界近似连续：

```text
Run 2 end:   567.333s
Run 1 start: 567.400s
gap:         0.067s
```

这表明内容更像是一个完整时间轴被旋转/反向分块落盘，而不是第二条字幕从零重复覆盖全片。

### 重置点前后简化 Segment

重置前：

```json
{"index":1382,"from":2761.933,"to":2762.233,"content":"OK"}
{"index":1383,"from":2762.233,"to":2763.366,"content":"感谢大家的观看"}
{"index":1384,"from":2763.366,"to":2764.700,"content":"相关的文档可以在评论区"}
{"index":1385,"from":2764.700,"to":2765.733,"content":"或者是私信找我要"}
{"index":1386,"from":2765.733,"to":2766.700,"content":"那觉得不错可以三连"}
{"index":1387,"from":2766.700,"to":2767.133,"content":"谢谢大家"}
{"index":1388,"from":2767.133,"to":2767.800,"content":"下期再见！"}
```

重置后：

```json
{"index":1389,"from":0.133,"to":0.733,"content":"OK，接下来"}
{"index":1390,"from":0.733,"to":2.100,"content":"我们来从0到1的实操一下"}
{"index":1391,"from":2.100,"to":3.033,"content":"OpenClaw的安装、"}
{"index":1392,"from":3.033,"to":4.200,"content":"部署和使用"}
{"index":1393,"from":4.233,"to":5.833,"content":"那装之前一定要问自己一句"}
{"index":1394,"from":5.833,"to":7.400,"content":"你想让他帮你做什么"}
{"index":1395,"from":7.400,"to":8.500,"content":"不要盲目跟风"}
```

Run 2 末尾：

```json
{"index":1744,"from":558.866,"to":560.300,"content":"我们直接点击打开应用"}
{"index":1745,"from":560.600,"to":561.700,"content":"然后给他发个消息"}
{"index":1746,"from":564.300,"to":565.600,"content":"当我们收到了回复之后"}
{"index":1747,"from":565.600,"to":567.333,"content":"飞书的渠道配置就已经完成了"}
```

Artifact index 0 随后从 `567.400s` 继续讲 OpenClaw 目录结构，时间上与 Run 2 结尾连续。

### 重复与轨道判断

**Confirmed Fact**

- 重置后前 10 个 Segment 在重置前没有完全相同的 content。
- 第二个运行段只覆盖 `0.133–567.333s`，没有再次从零覆盖整段 `2768s`。
- 无新标题、章节、P、CID 或 track 结构。
- Metadata 显示 `page_count=1`、单 CID、单 human track。

**Inference**

最符合本地证据的解释是：同一字幕 body 的两个时间分块以 `[后半段, 前半段]` 顺序拼接/保存，而不是多个独立视频或字幕轨道混合。

### Confirmed Fact — Chunk 影响

Snapshot 中 video 88 有 27 个 Transcript Chunks。

当前 Chunker：

- 没有在时间下降处自然断开；
- 跨越了 timeline reset；
- 生成了 1 个 `start_time > end_time` Chunk；
- 该 Chunk 同时覆盖 Run 1 末尾和 Run 2 开头。

非法 Chunk：

```text
unit_id:
transcript_chunk:bilibili:BV1TxwQz5E4B:p1:chunk_cc3222c5f91a7fa074ec5802f8a21799

start_time:
2712.466

end_time:
35.733

characters:
807
```

后续 Chunk 又从 overlap Segment 开始：

```text
34.500–141.333s
139.733–249.533s
247.700–356.600s
355.400–475.266s
475.000–567.333s
```

因此，Chunker 没有把两个运行段作为独立边界处理。产生非法 Chunk 的原因是 reset 后 `candidate.end - first_start` 为负，未触发 maximum-duration 条件。

### Gold / Eval 影响

**Confirmed Fact**

video 88 已进入 Locked V3 Gold：

- Q01：`evidence_retrieval_relevant_ids` 和 `video_discovery_relevant_ids`
- Q19：`evidence_retrieval_relevant_ids` 和 `video_discovery_relevant_ids`
- Q03、Q05、Q07、Q09、Q11、Q15、Q18：judged N

其他资产：

- 出现在 `eval_pool_candidates.jsonl` 的 9 个 query pool 中；
- 出现在 Formal per-query results；
- 不在 `eval_gold_candidates.jsonl`；
- 没有任何 Approved Interval；
- 不在当前 10 个 Approved Interval Evidence Seed 中。

**Unknown**

仓库中没有独立的 “Master Case Seed” 定义或资产，因此不能确认外部 Version Session 所称候选 Master Case 身份；只能确认它不属于现有 10 个 Approved Interval Seed。

### Recommendation — 最保守 Stage 1 行为

1. 不排序、不修复、不重建该 Artifact。
2. Stage 1 读取时先验证 Segment 时间单调性。
3. 一旦检测到时间下降，将其标记为多个 timeline runs；不得让 Chunk 跨 run。
4. 对已经存在的 `start > end` Chunk，Evidence Candidate Builder 应拒绝使用并返回可审计的 unverifiable/invalid-timeline 状态。
5. 在没有 source-version 绑定和显式 run-aware mapping 前，video 88 不应作为 V3.5 Evidence Master Case 或引用型 Seed。
6. 不改变其冻结 V3 Gold 标签和 V3 Formal Eval 结果；该问题作为 V3.5 intake data condition 处理。

## C. Eval Asset Fingerprint Table

除 amended ledger 外，所有存在文件均为：

```text
Newly fingerprinted at V3.5 intake
```

当前 hash 不能证明这些文件自 Stage 6B 后从未变化。

| file | current_sha256 | historical_hash_status | historical_hash | parse_status | record_count_or_role | risk |
|---|---|---|---|---|---|---|
| `research/v3_eval/eval_queries.locked.jsonl` | `21382e8ba058cc6e51ea41c776ad216824363090888ee3a5569e36dc971c36ba` | Historical Hash Unavailable | — | Valid JSONL | 24 locked queries | Newly fingerprinted at V3.5 intake |
| `research/v3_eval/eval_gold.locked.jsonl` | `873b5fbf78ba2e8fc90dfb2fca96776e0e703a1c4fedd56dd20a49e43995b300` | Historical Hash Unavailable | — | Valid JSONL | 24 Gold queries; 452 judgments; 10 intervals | Newly fingerprinted at V3.5 intake |
| `research/v3_eval/eval_gold_review.decisions.amended.jsonl` | `e93fd09bd06151d8665f50a17cc24bc2673105d21886e77b8a4cfa12f7ba0257` | Historical Hash Verified | `e93fd09bd06151d8665f50a17cc24bc2673105d21886e77b8a4cfa12f7ba0257` | Valid JSONL | 24 ledger records; 452 judgments | None |
| `research/v3_eval/gold_lock_audit.json` | `46d81526341a9e7c1e311aed3a03a964563e9e91f87c17be0fc796b7f0975db0` | Historical Hash Unavailable | — | Valid JSON | Gold lock audit; validation passed | Newly fingerprinted at V3.5 intake |
| `research/v3_eval/human_ledger_amendment_audit.json` | `d3a488a57fcc7a8e41c6c06ce46cde61498336cb3a201dc505b038011baa4ee1` | Historical Hash Unavailable | — | Valid JSON | 5 allowed pairs; 4 changes; validation passed | Newly fingerprinted at V3.5 intake |
| `research/v3_eval/eval_results.json` | `9bf49fe37565bbd8694e4bcd61a2c1126950b3387604797b8936407cd1c3bfbc` | Historical Hash Unavailable | — | Valid JSON | Formal aggregate result bundle | Newly fingerprinted at V3.5 intake |
| `research/v3_eval/eval_results.csv` | `3412f7e5e3be2732b68042d8066612f828b9599b3c324d14b24f3554c34ebaa9` | Historical Hash Unavailable | — | Valid CSV | 264 metric rows | Newly fingerprinted at V3.5 intake |
| `research/v3_eval/eval_per_query_results.jsonl` | `2b540e4c2ab7c7580ee4b4df212fe8aeb854845d6d4c55e743ef2e82b637d647` | Historical Hash Unavailable | — | Valid JSONL | 24 per-query records | Newly fingerprinted at V3.5 intake |
| `research/v3_eval/failure_cases.md` | `3f08db8086089a6545cd244775ced1894ec071c5b14995c1197f2cf6dad82d3e` | Historical Hash Unavailable | — | Valid UTF-8 Markdown | 8 documented factual cases | Newly fingerprinted at V3.5 intake |
| `research/v3_eval/V3_EVAL_PROTOCOL.md` | `225d39836fcee67adfe9fc567bdc2b759dd3daf94f9940ecb7b4100063d00bbe` | Historical Hash Unavailable | — | Valid UTF-8 Markdown | V3 Formal Eval protocol | Newly fingerprinted at V3.5 intake |
| `V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md` | `80e4abfd1d6b87f50a1c3e905a99af6fcc89d0ed2ce55d85c934f25809be9a75` | Historical Hash Unavailable | — | Valid UTF-8 Markdown | Stage 6B evidence report | Newly fingerprinted at V3.5 intake |
| `SHILIU_V3_VERSION_DECISION.md` | — | File Missing | — | File Missing | Expected V3 authority decision | Intake bundle incomplete if required |

### Eval cardinalities

```text
Locked queries:
24

Gold queries:
24

Judgments:
452
  R_evidence: 104
  R_title: 6
  N: 337
  U_title: 5
  OOS: 0

Approved intervals:
10
```

### Amended ledger historical verification

Stage 6B Report 和 `human_ledger_amendment_audit.json` 均记录：

```text
e93fd09bd06151d8665f50a17cc24bc2673105d21886e77b8a4cfa12f7ba0257
```

当前 amended ledger SHA-256 与该历史值完全一致。

## D. Authority Assessment

### 是否存在实际 Hash Conflict？

```text
No.
```

没有发现任何当前 hash 与已记录历史 hash 冲突。

唯一可以直接历史验证的目标文件是 amended ledger，结果匹配。

### 是否只是缺少历史 Hash？

```text
Yes, for the other existing assets.
```

其余 10 个现存目标文件缺少可比较的 Stage 6B 历史 hash。Snapshot DB hash 虽然有历史记录，但不能替代这些文件各自的 hash。

另有一个独立问题：

```text
SHILIU_V3_VERSION_DECISION.md is missing.
```

这是 File Missing，不是 Hash Conflict。

### 当前资产是否可在 V3.5 intake 时被重新 fingerprint 并冻结？

```text
Yes, for the 11 files currently present.
```

这 11 个文件均可解析，可采用本报告中的 current SHA-256 作为：

```text
Newly fingerprinted at V3.5 intake
```

但完整的 12 文件 intake bundle 目前不能宣称完整冻结，因为 `SHILIU_V3_VERSION_DECISION.md` 缺失。需要 Version Session：

- 提供该权威文件；或
- 明确将其从 canonical fingerprint set 中移除。

## E. Worktree Check

核查前后 `git status --short` 完全一致。

既有状态仍为：

- 5 个 tracked modified；
- 既有 V3/Stage 5/Stage 6/Eval/Web/Test untracked 资产；
- 上一轮按用户授权创建的 `V3_5_PHASE0_READ_ONLY_LOCAL_DELTA_AUDIT_REPORT.md` 仍为 untracked；
- 本轮没有新增或修改任何文件。

## F. Stop Statement

```text
Phase 0 supplementary read-only audit is complete.

No code, database, artifact, index, Gold, Snapshot, Prompt, Policy, Git state, or product behavior was intentionally modified.

No V3.5 implementation was started.
No V3 Retrieval tuning was performed.
No V4 work was started.
```