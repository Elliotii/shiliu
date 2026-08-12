# Shiliu V5.5 Goal 3 Closeout — Personalized Product Experience & Journey Consolidation

> Date: 2026-08-13
> Branch: `codex/v5-5-productization`
> Goal 3 baseline: `09e50bd0f3b4c4a7d86ad90306d766369b4b2572`
> Status: COMPLETE

## 1. 最终用户 Journey

普通用户现在可以沿着同一套已有能力连续前进：

```text
内容流 → 围绕当前内容搜索 / 提问
       → 基于搜索结果提问 / 显式进入长程研究
       → 阅读结果与当前字幕证据
       → 保存并发布知识
       → 从全局“知识”重新发现主题
       → 查看 currentness / 原始字幕
       → 提出后续相关问题
       → 由既有 ArtifactRoute 判断直接使用、补充或重新研究
```

没有自动提交 Research，也没有新增 Router、Agent、Provider、Worker、Memory、schema 或第二套 Knowledge authority。

## 2. Research hierarchy

`/research/{task_id}` 的普通主视图调整为：问题与当前状态 → 研究结果 → 当前字幕证据 → 保存知识 → 下一步 → 个性化帮助。Policy、routing、delta、assistance 内部投影、Personal Workspace generic authoring、durable trace、raw IDs、hash、reason codes 和维护控制保留在关闭的 `Advanced / Diagnostics / 维护信息` 中。

知识 Fact 的修正、停用、替代操作仍完整保留，但折叠在“维护这条结论”中。Research 新建表单的服务器验证细节也折叠为“高级验证设置”。这只是 UI hierarchy 和文案投影，没有复制或改变 Research 状态系统。

## 3. V5-C 产品化与 cold start

- 产品化：显式 Current Focus 薄 UI、已确认回答展示偏好、存在真实卡片时的 Knowledge Assistance。
- Current Focus 完全复用既有 `focus_state`、`user_authored`、`user_state_authority` 和 `correct` 合同；不推断、不调用 LLM、不后台修改。
- 保持隐藏 / Advanced：Knowledge Progress、Staleness / Collection Delta、Corpus / routing 解释、Project Radar、Integrated Journey 的内部投影；只有产生真实用户价值时才露出简短帮助。
- cold start 只显示一个小型可操作说明；空 assistance / delta / radar 面板不占据主视图。

真实 UI 中只执行一次自然操作，将 Current Focus 设置为 `Agent Skill`；服务返回 `201 Created`，刷新后主视图显示该关注。没有 fixture 或直接 DB insert。

## 4. Knowledge 全局入口与真实 G2 asset

新增 `/knowledge`，它是现有 published Topic Page、Fact、currentness 与 citation lineage 的薄 read projection；没有新 index、aggregate、lifecycle 或持久化模型。

从普通导航重新发现了 G2 已发布 Topic Page：

```text
根据收藏中的相关字幕，用两到三点说明 Skill 为什么不只是更长的 Prompt，并标出来源。
```

页面展示 3 条核心结论、来源仍有效、最后更新时间、已发布版本、原视频时间点与 `/videos/168/transcript`。用户无需 Task ID。点击“基于这个主题提出新问题”会进入既有 Research Knowledge 区并预填问题；已存在的相关不同问题仍显示“已有知识足够，可以直接使用”，可下钻 `/media/168/raw-subtitle`，证明 ArtifactRoute / Direct Reuse 没有回归。

## 5. Contextual handoff

- Library → Search / Ask：每个真实内容卡片携带标题与收藏夹上下文。
- Search → Ask：保留 query 与现有产品筛选上下文；每条结果也可直接提问。
- Search / Ask → Research：传递当前问题，只有用户点击“继续做长程研究”后才进入 Research，新建表单仍等待用户显式提交。
- Knowledge → later query / reuse：从全局 Knowledge 入口进入既有 ArtifactRoute，不重建 query、scope 或知识资产。

## 6. 完成的 SHOULD

- Mark 统一命名为“稍后回看”，并与“我的笔记”明确区分。
- Home 的 `completed_with_errors`、`skipped_no_subtitle`、`cooldown`、`running` 等状态转换为用户语言。
- Search 主结果用“为什么匹配 / 证据是否足够 / 下一步”语言；pipeline、gate、trace、reason code 留在 Advanced。
- `/taxonomy` 保留能力，但从主导航降级到“更多 → 语料实验”。

## 7. 真实 Journey 结果

所有 Journey 使用 Goal 3 worktree 的临时 `127.0.0.1:18521` 服务；未修改常驻 `18520` LaunchAgent 或 scheduled sync。

1. **A — Library → Query：PASS。** 从真实视频进入 Search，query 与 `folder_id=51947699` 自动保留；得到真实字幕结果，可继续 Ask；普通结果没有内部 routing language。
2. **B — Knowledge rediscovery：PASS。** 从全局导航找到 G2 Topic Page，查看 3 条结论、current source 与原始字幕，再进入 later related query，并观察到既有 direct reuse 结果。
3. **C — V5-C cold start：PASS。** 设置 Focus 前仅有简短 empty state，无大面积 Stage / Record / hash / reason-code console；无价值面板隐藏。
4. **D — real Focus：PASS。** 通过薄 UI 一次性显式设置 `Agent Skill`，刷新后保持；没有 synthetic data。
5. **E — escalation：PASS。** Search 的“继续做长程研究”把真实 query 预填进 Research；页面停在“开始研究”前，没有自动提交或 Provider 调用。

## 8. Focused / nearby regressions

最终运行 148 个 Python 测试，全部通过：

- Goal 3 focused、Web/Search/Ask、Goal 2 product：36 passed。
- V5-C Personal Workspace / personalization / corpus-aware / routing / assistance / integrated journey：26 passed。
- V5-B Knowledge workspace / lifecycle / reuse / closeout：26 passed。
- G1 operational control / Provider product / completion / persistence：60 passed。

另通过 4 个 V5-C JavaScript 测试、`node --check`（Research/Search/Ask）、`python -m compileall -q src` 与 implementation `git diff --check`。用户提供且保持原样的 Audit 自带 EOF 空行提示，因此仅从 whitespace check 中排除该历史事实文件。未运行 full deterministic suite，留给 V5.5 Final Gate。

## 9. Bounded correction

使用了唯一一次 bounded correction。真实 Journey 暴露出主页复合状态仍为 raw value、Research 摘要仍含 `Outer Audit`、Fact 维护按钮与主任务竞争、Library 问答标题引号重复，以及新建表单 / 回答偏好仍残留内部语言。修正只调整用户文案和折叠层级；没有改变 frozen behavior。

## 10. Remaining limitations

- `/knowledge` 目前是最近 50 个已发布 Topic Page 的只读入口，不含新 Knowledge search/index；这是刻意的 bounded projection。
- later query 继续要求用户填写必须回答的要点；没有新增自动 required-aspect inference。
- Current Focus 写入仍从某个 Research task 发出，因为既有 command/receipt 合同是 task-bound；全局展示不会后台创建 Focus。
- Search → Research 只传 query，不传内部 evidence IDs 或自造 routing context。
- Progress / Delta / Radar 在没有真实用户价值时继续隐藏；内部诊断仍可在 Advanced 查看。
- 本 Goal 没有运行 Provider，也没有切换正式服务。

## 11. Checkpoint / final HEAD

- Goal 3 baseline：`09e50bd0f3b4c4a7d86ad90306d766369b4b2572`
- Baseline ancestry：confirmed。
- Goal 3 final HEAD：包含本 closeout 的 branch tip；精确 immutable SHA 在提交后的交付信息中记录。
- 前置 Audit 保持原始 160 行事实记录，SHA-256：`d18d36fdee05114df70627b527c4d2bc31fb0226d13ab81d9617fecd4adec4ff`。

## 12. Completion Conditions

- [x] Research 普通主视图明确区分用户任务与 Advanced / Diagnostics。
- [x] V5-C 主视图不再以 Stage / Record / hash / reason-code console 为主。
- [x] Cold Start 对普通用户可理解且不占据大面积无价值主视图。
- [x] 已发布 Knowledge 可从普通全局产品入口重新发现。
- [x] Knowledge 可查看 currentness / 来源并下钻原始证据。
- [x] Knowledge 可进入 later related query / reuse flow。
- [x] Library → Search / Ask 有自然 contextual handoff。
- [x] Search / Ask → Research 有 bounded user-triggered handoff。
- [x] 未新增自动 Router / 自动 Research。
- [x] 5 条真实 Journey 完成。
- [x] SHOULD 项均为 bounded UI / 文案 / 导航调整。
- [x] focused / nearby regressions 通过。
- [x] G1 / G2 frozen behavior 未回归。
- [x] 未引入禁止的新架构。

Goal 3 completion conditions 已满足。建议用户验收后直接进入 V5.5 Final Gate；本 Goal 不自动执行 Final Gate。
