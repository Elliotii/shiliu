# V3 Run A Independent Read-only Review

## Independent Reviewer Result

```text
PASS_WITH_CONCERNS
```

复核过程只读取代码、SQLite、Run #10/#11/#12 产物和主报告；没有修改代码、
数据库或运行产物，没有调用 DeepSeek，没有读取 Silver Reference，也没有重新执行
Run A。

## Evidence

- Content Type 可复现为 46 个局部候选、45 个 Normalize 候选、8 个最终节点；
  45 条 Candidate Decision 完整覆盖全部 `nct_*`，其中 `merged_into=44`、
  `kept=1`。
- Domain 可复现为 43 个局部候选、42 个 Normalize Domain、20 个 Topic hints、
  7 个一级和 9 个二级 Domain；42 条 Decision 完整覆盖全部 `nc_*`。
- Content Type / Domain supporting ID 并集分别为 90 / 128 和 84 / 128。
- 最终引用的 Token / 时间可复现为 83,228 / 538.655 秒；加入 Run #11 失败调用
  后为 97,257 / 670.939 秒。
- Run #12 十二个 Discovery Stage 和 Content Type Consolidation 均为
  `attempt_count=0`；复制文件与源文件 Hash 一致，两个 lineage 文件字段完整。
- Run #10 冻结证据保持一致：54 个文件，Tree / Manifest / DB Run / DB Stages
  Hash 分别为：

```text
e43a1bfee9d3c9e5bd28f219b99d20df2e1237d5ea1ca423e1bc4333ed67cc67
8af50461d2f1468c1cc51f582c52a27a0bd8d03b8eb2cbba7a1a7c965ab864e9
47e14e4422bd615b73a9d01fef98db8f7ae45c3f4ea1e5afc4d74c8ecb023a01
2b88212126b117a231733ae7371643df38f8941acf85291ae3e6fcc2cbc6c5ae
```

- 中间容量来自 `source_batch_count × per_batch_schema_limit`；Domain Reduce 预算
  来自 Run Manifest 冻结的候选数公式，不是候选 Top-K。
- Run #11 正确记录为 `retry_wait/consolidation`；Audit 记录
  `finish_reason=length`、8,191 reasoning Tokens 和空正文；Run #12 为 completed。
- 自动 Gate 的 PASS 可从 `quality-result.json` 复现：0 blocking、3 warnings。
- Reviewer 独立执行两个最相关测试文件，共 25 tests passed；主 Agent 另行执行
  全量 137 tests passed。

## Concerns

1. 自动 Gate 的跨维度泄漏检测只是规范化名称等值匹配，不是语义判断；
   `Agent 架构与原理` 明显偏向 Domain，`AI 学习路径与职业规划` 混合内容目标和
   领域。自动 PASS 不能当作语义验收通过。
2. 存在字段级静默截断：原始 Domain 响应中 `软件工程基础.includes` 有 6 条，
   `TopLevelDomainNode` 的 `mode="before"` validator 静默保留前 5 条，删除了
   `互联网架构演变`。候选节点本身没有丢失，但“无静默删除”不能扩展到所有字段。
3. `_cap_fields` 还用于其他文本和列表边界；现有测试没有覆盖所有 raw-to-parsed
   不变性。
4. Run #10 仍保留历史 `running/content_type_normalization`，这是不可变要求的结果，
   不代表新状态机仍有同样缺陷。
5. Run #12 Domain Consolidation 在 19,456 上限内使用了 19,295 completion
   Tokens，24,576 最大保险尚未经过更坏输入验证。

## Required Fixes

- 进入 Run B / C 前增加 Content Type 语义纯度检查，识别重新命名后的
  Domain / Entity / Topic 泄漏。
- 明确处理 `Agent 架构与原理` 等错误 Content Type；必要时只重跑 Content Type
  Consolidation。
- 取消模型输出的静默 `mode="before"` 截断，或把每一次截断显式记录为校验错误/
  审计事件；补 raw-response 与 parsed-output 差异测试。

## Non-blocking Suggestions

- Consolidation completion 使用率超过 90% 时产生预算警告。
- 增加语义近似泄漏、raw/parsed 一致性及 removed/downgraded Decision 分支测试。

## 与主报告的分歧

Reviewer 与主 Agent 的 `PASS_WITH_CHANGES` 方向一致，没有结论性分歧。主 Agent
接受全部 Required Fixes。唯一文字修正是把“没有静默丢弃”严格限定为“全部候选
节点都有决策记录”；字段级静默截断作为新发现单独列出。
