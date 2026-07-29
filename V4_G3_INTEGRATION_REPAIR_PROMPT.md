# Shiliu V4 Goal 3 Integration Repair Prompt

你正在继续：

```text
Shiliu V4 Goal 3 Session
Goal 3 Integration Repair
```

这不是新 Goal，也不是 Goal 3 重做。主 V4 Session 已完成 Goal 3 Integration
Review，并接受：

- `/ask` 产品入口；
- Fast / Deep 双模式交互；
- 共享 Answer / Citation / Evidence UI；
- User Trace 与按需 Developer Trace；
- 六 Case 轻量 Eval 结构；
- 四段 Demo；
- 浏览器与完整回归结果。

当前只处理主 Session 确认的两个 Blocking Findings 和一个非阻塞展示小修。
完成后追加原实现报告，返回主 Session 复验。

---

# 1. 权威输入

先完整阅读：

```text
V4_G3_IMPLEMENTATION_REPORT.md
V4_G3_EXECUTION_PROMPT.md
V4_DESIGN_PROPOSAL.md
V4_MASTER_STATE.md
V4_DECISION_LEDGER.md
```

然后只检查本修复直接相关的代码、测试和结果：

```text
src/shiliu/ask/answer.py
src/shiliu/ask/finalize.py
src/shiliu/ask/validation.py
src/shiliu/ask/contracts.py
src/shiliu/templates/base.html
scripts/run_v4_goal3_eval.py
eval/v4_goal3_cases.json
eval/v4_goal3_results.json
tests/test_v4_ask_contracts.py
tests/test_v4_context_and_citations.py
tests/test_v4_fast_ask_api.py
tests/test_v4_deep_search.py
tests/test_v4_ask_page.py
```

必要时可沿真实调用链读取相邻模块，但不得重新扩大为全面审计。

---

# 2. 工作区与 Git 边界

当前基线：

```yaml
branch: codex/v4-main
baseline_commit: 18b1956
working_tree: contains_uncommitted_main_session_and_goal3_work
```

必须：

- 保留当前工作区全部已有修改；
- 不执行 Reset、Checkout、Clean、Stash 或 Rebase；
- 不覆盖三份正式 V4 文件；
- 不把已有未提交修改误判为本轮异常；
- 开始修改前记录 `git status --short`；
- 完成后使用 `git diff --check`；
- 本 Session 不 Stage、Commit、Push 或 Merge。

主 Session 会在修复复验通过后统一更新正式状态并处理 Git。

---

# 3. Integration Review 结论

Goal 3 当前状态：

```yaml
goal_3_product_implementation: accepted
goal_3_deterministic_regression: accepted
goal_3_browser_integration: accepted
goal_3_eval_execution: completed
goal_3_eval_quality_evidence: repair_required
goal_3_overall: changes_requested
v4_complete: not_yet
blocking_findings: 2
```

## Blocking Finding 1：有限证据被表述成全库否定

`no_evidence_quantum_protocol` 的真实结果暴露了共享回答边界问题：

- Fast 没有 Answer Block / Citation，但 `limitations` 声称“收藏内容中未提及”；
- Deep 使用少量不相关字幕样本，回答“所有提供的转录证据均未提及”，并附上不能
  直接支持材料性结论的 Citation；
- 当前 Fast Context 明确存在截断，Deep 也没有穷举整个收藏库；
- 因此“本次有限检索未找到”不能升级为“整个收藏库不存在”。

相邻的两个 Fast Case 还出现了重复或弱相关 Citation：

```text
partial_universal_claim
single_topic_context_compression
```

这不是 Citation Identity 故障，而是 Answer Block 与所选 Citation 的语义支持
边界不够严格。

## Blocking Finding 2：Eval 中存在硬编码 / 空洞通过项

`scripts/run_v4_goal3_eval.py` 当前包含：

```python
"status_termination_valid": True
```

因此报告中的“All deterministic checks passed”并不完全成立。

当前 `navigation_not_cited` 主要依赖 Navigation Event 上通常不存在的
`citation_ids`，容易空洞通过。真实 Citation 已经能够从当前 Source Version
的原字幕重建；Eval 应直接使用这一权威事实，而不是依赖空 Event 字段。

## Non-blocking Presentation Repair

正式决策中的 `/search` 导航语义是“搜索证据”。当前顶栏文案仍是“搜索”。
本轮将其薄改为：

```text
搜索证据
```

不得借此重做导航或页面。

---

# 4. 修复目标

本轮只完成：

```text
Shared Grounded Answer Boundary Repair
→ Real Deterministic Eval Checks
→ Search Navigation Label
→ Four Targeted Real Reruns
→ Full Regression
→ Report Appendix
```

不增加新平台、独立 Goal 或新产品能力。

---

# 5. Repair A：共享 Grounded Answer 边界

## 5.1 Initial 与 Repair Prompt 必须同时收紧

更新共享：

```text
_answer_messages()
_repair_messages()
```

Fast 与 Deep 必须继续走同一个 `GroundedAnswerService` /
`AnswerFinalizer`。不得分别写两套修复。

Prompt 至少明确：

1. Retrieval / Context 是有限样本；未出现某事实不等于整个收藏库不存在；
2. 对“不存在 / 从未 / 所有视频都没有”等全称或否定问题，只有字幕证据直接支持
   该范围时才能作范围化结论；
3. 没有直接支持时，应返回 `insufficient` 和空 `answer_blocks`，采用范围诚实的
   表述，例如：

   ```text
   本次检索未找到足以回答该问题的可靠字幕证据
   ```

4. `limitations` 只能说明检索范围、证据缺口、截断、Provider 或停止边界；
   不得承载无 Citation 支持的材料性事实断言；
5. 每个 `citation_id` 必须直接支持所在 Answer Block 的完整材料性表述；
6. 不得因为 Citation ID 在 Allowlist 中就机械附加；
7. 不得用多个不相关样本拼成“全库缺失”；
8. 不得添加自由 `answer`、`claims` 或第二事实源。

## 5.2 允许的薄确定性保护

可在共享 `AnswerFinalizer` 增加不涉及语义判断的薄保护：

- `insufficient` 必须保持空 Answer Blocks / Citations；
- 对 `insufficient`，可丢弃模型生成的材料性 limitation，改用固定、范围诚实的
  无证据说明，再追加 Runtime 已知的 Context Truncation / Provider / Stop 信息；
- 保持 `status` 与 `termination_reason` 分离；
- 保持 Citation 的 Identity / Version / Segment Revalidation。

不得写关键词黑名单、否定句分类器或 Runtime Semantic Judge。若某项需要理解
自然语言语义才能执行，只能放进共享 Prompt 和离线人工审阅，不能伪装成确定性
Runtime Validation。

## 5.3 必须保持不变

- Answer Block 是唯一正文事实源；
- Fast / Deep 共享 Answer、Citation、Evidence 展示合同；
- Citation 只来自当前版本 `TranscriptEvidenceSpan`；
- Navigation、标题、简介、AI 总结、Notes、整理稿不得进入事实 Citation；
- 一次 Same-context Repair 上限不变；
- Deep 的预算、StateGraph、Tool、停止条件不变；
- 不引入 Runtime Semantic Judge。

---

# 6. Repair B：真实确定性 Eval 检查

重构 `scripts/run_v4_goal3_eval.py` 中的检查，使每个布尔字段都由真实数据计算。
可以提取少量纯函数，方便单元测试；不得建设 Eval Framework。

## 6.1 `status_termination_valid`

至少真实检查：

- `response.termination_reason == response.trace_summary.termination_reason`；
- `insufficient` 时没有 Answer Blocks 和 Citations；
- `complete` / `partial` 时至少有一个 Answer Block；
- 每个 Answer Block 至少有一个 Citation ID；
- Answer Block 引用的 ID 全部存在于 Response Citations；
- Contract 中的枚举值通过真实 Schema 保证，不再硬编码 `True`。

如果现有冻结合同允许某个明确例外，必须在代码和测试中显式表达，不能用常量
绕过。

## 6.2 Citation 权威检查

保留并复用现有 `_validate_citation()` 对每条 Citation 的检查：

- 当前 Source Identity；
- 当前 Source Version；
- Segment 边界；
- 原字幕内容；
- Stable Citation ID；
- Bilibili 时间跳转结构。

将 `navigation_not_cited` 替换成或重定义为一个可证明的检查。推荐在新结果中使用
清楚的字段：

```text
citations_reconstruct_from_current_transcript
```

判断依据必须是每条 Citation 能否从当前版本权威字幕重建，而不是 Navigation
Event 是否碰巧带有空 `citation_ids`。

若为兼容现有结果保留旧字段，也必须让它从真实 Provenance / Transcript
Reconstruction 得出，并在报告中解释；不得继续空洞通过。

## 6.3 必须增加的负向测试

至少添加能证明检查会失败的测试：

1. Response 与 Trace Summary 的 `termination_reason` 不一致；
2. `insufficient` 却含 Answer Block 或 Citation；
3. 非 `insufficient` 却没有 Answer Block；
4. Answer Block 引用了 Response 中不存在的 Citation ID；
5. Citation 无法从当前版本原字幕重建；
6. Navigation Event 没有 `citation_ids` 时，不能据此自动证明 Citation 来源正确。

测试可直接覆盖提取后的纯检查函数和现有 Citation Validator，不得调用真实
Provider。

结果文件中不得再出现没有执行逻辑支撑的“通过”字段。

---

# 7. Repair C：导航展示

只修改共享顶栏：

```html
<a href="/search">搜索证据</a>
```

补充或更新最小页面测试，确认 `/ask` 和 `/search` 都使用该共享导航。

不得改路由、页面层级或创建新导航组件。

---

# 8. 修改前与修改后验证

修改前先运行不依赖真实 Provider 的相关定向测试，记录真实结果。修改后至少运行：

```bash
.venv/bin/python -m pytest -q \
  tests/test_v4_ask_contracts.py \
  tests/test_v4_context_and_citations.py \
  tests/test_v4_fast_ask_api.py \
  tests/test_v4_deep_search.py \
  tests/test_v4_ask_page.py

.venv/bin/python -m pytest -q

.venv/bin/python -m compileall -q src scripts
.venv/bin/python -m pip check
node --check src/shiliu/static/evidence-ui.js
node --check src/shiliu/static/search.js
node --check src/shiliu/static/ask.js
git diff --check
```

若仓库已有更完整的 Goal 3 定向命令，应继续运行并记录。既有 Starlette/httpx
Deprecation Warning 可以如实保留；不得隐藏新 Warning 或失败。

不需要重做完整视觉设计 QA。至少验证：

- 顶栏显示“搜索证据”；
- `/ask` Fast / Deep 控件与共享 Evidence UI 未回归；
- Citation 点击、折叠展开和 Developer Trace 基本交互未回归。

可使用既有 UI Fixture；Fixture 不能替代真实质量复跑。

---

# 9. 真实 Provider 复跑授权边界

代码、单测、Fixture 和静态检查可直接完成。

以下四个真实复跑会向当前配置的 DeepSeek Provider 发送普通测试 Query 和有界
字幕 Evidence：

```yaml
fast:
  - no_evidence_quantum_protocol
  - partial_universal_claim
  - single_topic_context_compression
deep:
  - no_evidence_quantum_protocol
```

如果用户尚未在本次 Repair Session 中明确授权这四次新调用，必须在调用前暂停并
一次性请求授权。不得把原 Goal 3 的 6 + 4 次授权自动解释为无限后续调用授权。

不得复跑其他 Case，不得为追求通过而重复采样。网络或 Provider 失败时保留真实
结果；如需再次调用，重新说明原因和新增次数。

---

# 10. 目标复跑与结果保留

原始结果：

```text
eval/v4_goal3_results.json
```

必须保持不变，作为修复前证据。新的四次结果写入：

```text
eval/v4_goal3_repair_results.json
```

不要覆盖原 10 次矩阵。可使用现有 Runner：

```bash
.venv/bin/python scripts/run_v4_goal3_eval.py \
  --mode fast \
  --case no_evidence_quantum_protocol \
  --case partial_universal_claim \
  --case single_topic_context_compression \
  --output eval/v4_goal3_repair_results.json

.venv/bin/python scripts/run_v4_goal3_eval.py \
  --mode deep \
  --case no_evidence_quantum_protocol \
  --output eval/v4_goal3_repair_results.json
```

两条命令合计只应产生四个 `(case_id, mode)` 结果。完成后：

- 对 4/4 做 Supportedness / Usefulness / Coverage / Status Honesty 人工审阅；
- 将人工审阅写入 Repair 结果文件；
- 记录真实 Status、Termination、Citation、Latency、Usage 和 Checker；
- 保留失败，不 Mock，不伪造，不用总分掩盖单 Case；
- 扫描结果，确认不包含 Secrets、完整 Prompt 或无界字幕 Corpus。

---

# 11. Repair Acceptance

必须同时满足：

## Answer Boundary

- Fast no-evidence 不再在 Answer 或 Limitations 中声称整个收藏库未提及；
- Deep no-evidence 不再用少量不相关字幕证明全库缺失；
- 无直接证据时采用“本次检索未找到可靠字幕证据”一类范围诚实表述；
- `insufficient` 没有 Answer Blocks / Citations；
- 两个 Fast 质量 Case 不再附加与对应 Block 无直接支持关系的弱 Citation；
- 每个材料性 Answer Block 的每个 Citation 都直接支持该 Block；
- Fast / Deep 仍共享同一 Answer Service 与 Finalizer。

## Eval Integrity

- `status_termination_valid` 不再硬编码；
- Response / Trace 不一致会真实失败；
- Answer Shape / Citation Resolution 异常会真实失败；
- Citation 来源由当前版本原字幕重建证明；
- Navigation 空字段不能让检查自动通过；
- 负向测试证明 Checker 具备检出能力。

## Product / Regression

- 顶栏为“搜索证据”；
- Goal 3 定向、Goal 1/2 回归和默认全套通过；
- JS、Compileall、Pip Check、Diff Check 通过；
- 没有第二套 Answer / Citation / Eval 后端；
- 没有新增架构级能力或 Deferred 平台。

如果某一次真实 Provider 输出仍不理想，但代码边界、Checker 和真实失败表达均正确，
必须如实记录并交由主 Session 判断；不得无界调 Prompt 或反复调用。

---

# 12. 严格禁止事项

本修复禁止：

- 新增 Goal 4 或任何独立 Infrastructure Goal；
- 重写 Fast / Deep Orchestrator；
- 修改共享 Ask Contract；
- 创建第二套 Answer、Citation 或 Evidence UI；
- 添加 Runtime Semantic Judge；
- 添加 Reranker、Independent Navigation Index 或 Context Compaction；
- 添加 Native Tool Calling；
- 添加 Streaming、SSE、WebSocket、Queue 或持久化；
- 添加 LangGraph Checkpointer、Memory、HITL、Subgraph 或 Multi-Agent；
- 扩大 Deep Round、Tool、Context 或 Runtime Budget；
- 增加新的真实 Eval Case；
- 重跑完整 6 + 4 矩阵；
- 将标题、简介、AI 总结、Notes 或整理稿变成事实 Citation；
- 修改 V0–V3.5 冻结材料；
- 修改 `V4_DESIGN_PROPOSAL.md`、`V4_MASTER_STATE.md` 或
  `V4_DECISION_LEDGER.md`；
- 自行宣布 Goal 3 或 V4 正式验收；
- Commit、Push、Merge。

---

# 13. 报告要求

不要创建第二份 Implementation Report。直接在：

```text
V4_G3_IMPLEMENTATION_REPORT.md
```

末尾追加：

```text
## J. Main Session Integration Repair
```

J 节只包含：

### J.1 Findings Received

- 两个 Blocking Findings；
- 一个 Navigation 文案小修；
- 修复范围没有扩大。

### J.2 Code Changes

- 共享 Answer / Repair Prompt；
- 薄确定性 Insufficient 保护（如实施）；
- Eval Checker 真实计算；
- 负向测试；
- Navigation Label。

### J.3 Deterministic Verification

- 修改前基线；
- 定向测试；
- 默认全套；
- JS / Compileall / Pip / Diff；
- Warning 和失败。

### J.4 Targeted Real Reruns

- 授权情况；
- 恰好四次运行；
- 修复前 / 修复后对照；
- 4/4 人工审阅；
- 保留失败与边界。

### J.5 Scope Audit

- 无新平台；
- 无架构扩张；
- Fast / Deep 共享层未分叉；
- 原结果文件未覆盖；
- 三份正式状态文件未修改；
- 未 Commit / Push。

### J.6 Repair Outcome

使用：

```yaml
answer_boundary_repair:
eval_integrity_repair:
navigation_label_repair:
directed_tests:
full_suite:
targeted_real_reruns:
remaining_blocking_finding:
goal_3_recommendation:
v4_recommendation:
```

只有主 Session 才能给出正式 Goal 3 Acceptance 和 V4 Complete。

---

# 14. 返回主 Session

最终只返回：

1. 修改了什么；
2. 测试与四次真实复跑的真实结果；
3. 是否仍有 Blocking Finding；
4. Scope 是否保持；
5. 已追加的 `V4_G3_IMPLEMENTATION_REPORT.md` 路径；
6. `eval/v4_goal3_repair_results.json` 路径；
7. 是否建议主 Session 进行第二次 Integration Review。

现在开始本次有界 Integration Repair。先记录工作区和确定性基线；完成所有不依赖
Provider 的修复与测试后，在四次真实调用前遵守授权边界。
