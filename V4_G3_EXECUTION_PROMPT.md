# Shiliu V4 Goal 3 Execution Prompt

```yaml
session_type: bounded_goal_execution
goal: Goal 3 — Product Integration, Lightweight Eval, and Demo
status: ready_to_execute
date: 2026-07-29
repository: Shiliu
expected_branch: codex/v4-main
upstream_goals:
  - Goal 1 — Complete Grounded RAG
  - Goal 2 — Independent Agentic Search
baseline_commit: 18b1956
```

你正在启动一个新的：

```text
Shiliu V4 Goal 3 Execution Session
拾流 V4 Goal 3 执行 Session
```

本 Session 只负责实现和验证：

```text
Goal 3 — Product Integration、Lightweight Eval 与 Demo
```

不得扩展到 V5、第二项目、V0–V3.5 历史治理任务，或新建 Answer、
Citation、Navigation、Tool、Policy、Trace、Eval、Provider、Agent
Infrastructure 平台。

---

# 1. 角色与职责

你在本 Session 中担任：

```text
Goal 3 Implementation Owner
Ask Product Integration Engineer
Grounded Answer UX Engineer
Lightweight Eval and Demo Owner
```

主 V4 Session 仍然负责：

- 跨 Goal 架构和产品范围；
- `V4_MASTER_STATE.md`；
- `V4_DECISION_LEDGER.md`；
- Goal 3 结果的 Integration Review；
- 是否接受 Deferred 能力；
- 是否宣布 V4 完成。

本 Goal Session 不得自行改变：

- V4 三个纵向 Goal；
- `/ask` 与 `/search` 的产品分工；
- Fast 默认、Deep 显式选择的产品行为；
- Fast/Deep 共享 Ask、Answer、Citation 和 Evidence 合同；
- 原字幕/ASR 的事实权威；
- Navigation 与事实 Context 隔离；
- Goal 1/2 已接受的 Provider、LangGraph、预算和停止边界；
- 用户已经批准的 Goal 3 Trace、Eval 和 Demo 范围。

---

# 2. 必读文件与渐进式阅读

开始工作前，按以下顺序完整阅读：

```text
1. V4_G3_EXECUTION_PROMPT.md
2. V4_MASTER_STATE.md
3. V4_DESIGN_PROPOSAL.md
4. V4_DECISION_LEDGER.md
5. V4_G1_IMPLEMENTATION_REPORT.md
6. V4_G2_IMPLEMENTATION_REPORT.md
7. README.md
```

然后只检查 Goal 3 直接相关的当前源码：

```text
src/shiliu/app.py
src/shiliu/web.py

src/shiliu/templates/base.html
src/shiliu/templates/search.html

src/shiliu/static/app.css
src/shiliu/static/search.css
src/shiliu/static/search.js

src/shiliu/ask/contracts.py
src/shiliu/ask/service.py
src/shiliu/ask/finalize.py
src/shiliu/ask/deep/contracts.py
src/shiliu/ask/deep/service.py
src/shiliu/ask/deep/decision.py
src/shiliu/ask/deep/graph.py

src/shiliu/retrieval/product_search.py
src/shiliu/evidence/source.py
```

直接相关测试：

```text
tests/test_v4_ask_contracts.py
tests/test_v4_fast_ask_api.py
tests/test_v4_deep_search.py
tests/test_product_search_api.py
tests/test_boundaries_and_web.py
tests/test_v1.py
```

只有遇到具体实现阻塞时，才继续读取其他文件。

不得重新进行：

- 全仓库架构审计；
- V0–V3.5 历史材料全文审计；
- Agent 框架或 Provider 重新选型；
- Candidate Builder、Selector、Stage4、Stage5 或历史 Eval 全面审计；
- 开放式 Web Research；
- 通用前端框架迁移；
- 通用 Trace、Eval、Policy 或 Demo 平台设计。

---

# 3. 开始前仓库检查

修改代码前：

1. 确认当前分支和工作区状态；
2. 不覆盖用户已有修改；
3. 确认三份 V4 正式文件和本 Prompt 存在；
4. 确认 Goal 1、Goal 2 实现报告存在；
5. 运行 Fast/Deep Ask 与 Web 定向测试，建立当前 Session 基线；
6. 记录已有失败和 Warning，但不要因无关历史问题扩大范围；
7. 检查当前 `/api/ask`、Ask Trace API 和 `/search` 页面真实行为。

主 Session 最近一次确认的基线：

```text
branch: codex/v4-main
commit: 18b1956 feat: complete V4 agentic search goal

24 passed（Goal 2 与 Integration Repair 定向）
12 passed（Fast Ask API）
75 passed（Retrieval / Evidence 定向）
1446 passed，4 deselected（默认全套）
1 existing Starlette/httpx deprecation warning
```

这些只是参考。Goal Session 必须记录开始时的真实 Git 状态和真实测试结果。

---

# 4. Goal 3 用户结果

Goal 3 完成后，用户必须能够：

```text
打开 /ask
→ 输入一个关于收藏内容的问题
→ 明确选择“快速回答”或“深入搜索”
→ 等待一次性结构化回答
→ 阅读自然语言 Answer Blocks
→ 点击 [1][2] 定位对应字幕证据卡
→ 从证据卡跳转到 B 站时间点
→ 理解 complete / partial / insufficient
→ 查看简洁的用户 Trace
→ 在需要时展开开发者 Trace
```

必须证明：

- `/ask` 是真实可用的产品入口，不只是 API Demo；
- Fast 与 Deep 使用同一个页面、Ask Contract 和结果渲染器；
- Fast 默认，Deep 由用户显式选择；
- Fast `partial`/`insufficient` 可以显式保留原问题进入 Deep；
- `/search` 仍然能独立进行证据搜索和手动查证；
- Citation 只展示权威字幕，Navigation 内容不进入事实证据卡；
- Trace 能解释模式、成本和停止，但不暴露隐藏推理；
- 轻量 Eval 能为是否优化提供证据；
- Demo 同时展示成功、模式差异和诚实失败。

---

# 5. 本 Goal 的范围分类

## 5.1 `must_build`

- `GET /ask` 产品页面；
- 顶部导航中的“问答”和“搜索证据”分工；
- Fast 默认、Deep 显式模式选择；
- Fast-to-Deep 显式继续操作；
- Fast/Deep 共用 Answer Block、Citation 和 Evidence 展示；
- Loading、Error、`complete`、`partial`、`insufficient` 状态；
- Citation 标记到 Evidence Card 的可访问定位；
- Evidence Card、分组展开和 B 站时间点跳转；
- 默认可见的用户 Trace 摘要；
- 默认折叠、按需读取的开发者 Trace；
- 六条普通真实 Query 的轻量 Eval；
- 由重复材料性失败驱动的有界修正；
- 四段端到端 Demo；
- README、测试和 `V4_G3_IMPLEMENTATION_REPORT.md`。

## 5.2 `in_goal_support`

- 从现有 Search UI 提取薄 Evidence Renderer 和必要共享样式；
- Ask URL Query/Mode/Filter 状态；
- Ask 与 Search 之间的 Query 传递；
- 用户友好的 `termination_reason` 文案映射；
- Deep 静态 Policy Version 和 Trace 字段；
- 小型 Eval Runner、Case Manifest 和有界结果记录；
- 必要的 Web Route、Template、Static 和测试适配；
- 现有 State Progress Event 可无阻塞复用时的薄增强。

## 5.3 `deferred`

- Fast/Deep 自动路由；
- Answer Token Streaming；
- 为进度新建 SSE/WebSocket 基础设施；
- 服务器端取消、后台任务和任务队列；
- Trace 持久化、Checkpoint 或 Durable Resume；
- 通用 Observability Dashboard；
- Runtime Semantic Judge；
- 大型 Frozen Eval、多 Reviewer、密封运行或总分平台；
- Independent Navigation Index；
- Reranker；
- Native Tool Calling；
- Automatic Context Compaction；
- Skill Registry、动态 Policy Loader 或 Policy Platform；
- 通用 Provider/LLM SDK；
- LangGraph Memory、HITL、Interrupt、Subgraph 或 Multi-Agent；
- LangGraph Cloud 或 LangSmith Runtime；
- 生产部署和生产 SLA 声明。

不得把任何 `in_goal_support` 项目拆成新 Goal 或平台。

---

# 6. `/ask` 产品入口

新增：

```text
GET /ask
```

顶部导航建议表达：

```text
内容流 | 问答 | 搜索证据 | ...
```

要求：

- `/ask` 是主要回答入口；
- `/search` 的 Route 和直接 Retrieval 功能保持可用；
- 页面首屏突出问题输入与模式选择；
- Fast 默认选中；
- 模式选择使用明确的可访问控件，不依赖颜色区分；
- 常用筛选放入折叠的“限定范围”区域；
- 不把 Search 的 Retrieval Mode、Scope、Sufficiency 等开发者选项原样搬入
  Ask 首屏；
- Ask 只提交当前 `AskRequest` 已支持的 Query、Mode 和 Filters；
- Query 和 Mode 进入 URL 状态，刷新、返回和分享时行为可预测；
- 页面兼容桌面与当前项目已有的移动端宽度；
- 不引入新的前端框架。

模式说明：

```text
快速回答
适合明确事实、概念和单主题问题

深入搜索
适合跨视频比较、复杂问题或需要逐步寻找证据的问题
```

Fast 返回 `partial` 或 `insufficient` 时：

```text
显示“使用深入搜索继续”
→ 保留原 Query
→ 保留当前 Filters
→ 明确切换到 Deep
→ 由用户再次发起请求
```

不得在后台自动升级，也不得增加 Adaptive Router。

---

# 7. Loading、Error 与结果状态

Ask API 首版一次性返回。等待界面必须诚实：

Fast：

```text
正在检索字幕并生成有依据的回答……
```

Deep：

```text
正在导航视频并逐步查找字幕证据，可能需要几分钟……
```

要求：

- 显示本地已等待时间；
- 不把静态动画伪装成真实服务器阶段；
- 没有真实 Progress Event 时，不显示虚假的 Round 或 Tool 进度；
- 防止重复提交；
- 新请求可以在浏览器侧废弃旧 Response，避免旧结果覆盖新结果；
- 不承诺浏览器 Abort 等于服务器端运行取消；
- 请求失败时显示可理解错误和可重试操作；
- `provider_error`、`evidence_unavailable` 与普通网络错误使用不同文案；
- `limitations` 必须可见；
- `partial` 和 `insufficient` 不得伪装成完整成功。

Progress Event 只有在已有后端事件可以用小改动、无新基础设施接入时才允许；
不接入不影响 Goal 3 验收。

---

# 8. 共享 Answer、Citation 与 Evidence 展示

页面必须直接消费现有：

```yaml
run_id:
mode:
status:
answer_blocks:
citations:
limitations:
termination_reason:
trace_summary:
```

不得增加：

- 自由 `answer`；
- 独立 `claims`；
- `DeepAskResponse`；
- 第二套 Citation；
- Fast/Deep 分支渲染器。

渲染要求：

- 按 `answer_blocks` 顺序生成正文；
- 每个 Block 末尾按 `citation_ids` 生成 `[1][2]`；
- Citation 编号是本次 Response 内的展示编号，不替代 Stable Citation ID；
- 点击 Citation 标记滚动到并高亮对应 Evidence Card；
- 同一个 Citation 被多个 Block 引用时复用同一 Evidence Card；
- 未被 Answer Block 引用的 Citation 不应被误标为支持某个段落；
- `insufficient` 不渲染虚构答案；
- Status、Limitations 和 Termination 分开显示。

Evidence Card 至少展示：

```yaml
video title:
source type:
time range:
authoritative quote:
Bilibili timestamp jump:
```

可以将同一视频的多个 Citation 分组，默认显示首条并展开其他证据，以复用
现有 Search 的“更多相关片段”交互。Identity、Source Version 和 Segment 等
开发者元数据进入折叠区，不占据用户主阅读路径。

`/search` 当前 Evidence/Window Renderer 是私有页面实现。Goal 3 应提取最小
共享函数和样式，或采用等价薄组件边界；不得复制整份 `search.js` 或维护两套
时间格式、字幕来源、跳转和展开逻辑。

UI-only 展开行为不得改变 Citation Identity。NavigationDocument、标题描述、
AI 总结、User Notes 和整理稿不能显示成事实 Citation。

---

# 9. Trace 两层投影

## 9.1 用户 Trace

默认可见，使用产品语言展示：

```yaml
mode:
latency:
query_count:
retrieval_count:
valid_evidence_count:
stale_evidence_count:
context_truncated:
termination_reason:

deep_only:
  decision_rounds:
  tool_calls:
  visited_video_count:
  visited_segment_count:
  navigation_result_count:
  evidence_candidate_dropped_count:
```

数字为零时避免制造噪音。终止原因至少映射为：

| 内部值 | 用户文案方向 |
|---|---|
| `answer_ready` | 已找到足够证据并完成回答 |
| `no_new_evidence` | 继续搜索没有发现新的有效字幕 |
| `repeated_search` | 后续搜索开始重复已有结果 |
| `budget_exhausted` | 已达到本次搜索的安全上限 |
| `provider_error` | 回答服务暂时不可用 |
| `evidence_unavailable` | 相关线索的当前字幕证据不可用或已过期 |

Deep 可以显示有界行动时间线：

```text
导航视频
→ 搜索字幕
→ 读取字幕上下文
→ 根据观察继续或停止
→ 生成并校验回答
```

只展示 Action Kind、受控参数和 Observation Summary，不展示 Chain-of-thought。

## 9.2 开发者 Trace

默认折叠。只在用户展开时请求：

```text
GET /api/ask/traces/{run_id}
```

展示内容可以包括：

- Query rewrites；
- Agent Action 和有界参数；
- Tool Observation 摘要；
- Round、Tool、Visited 和 Evidence 计数；
- Stale、Dropped 和 Context Truncation；
- Provider Role、Latency、Usage、Retry、Repair 和 Error；
- Guard Decision；
- Status 和 Termination；
- Citation Validation；
- Policy Version。

要求：

- 不复制完整字幕 Corpus；
- 不展示 Secrets；
- 不依赖 Trace 永久存在；
- 404 时说明该内存 Trace 已不可用，不影响已返回 Answer/Citation；
- 不增加数据库 Trace Schema 或持久化服务。

## 9.3 Deep Policy Version

将 Goal 2 当前隐式 Deep Search Policy 赋予一个静态版本，例如：

```text
v4-deep-policy-v1
```

并记录到 Deep Trace/Eval Result。只允许最小常量或薄模块提取；不得建设：

- `SKILL.md` Runtime；
- Skill Registry；
- 动态 Policy 加载；
- Policy Marketplace；
- 新的 Agent Infrastructure Goal。

---

# 10. 轻量 Eval

Eval 的目标是支持工程判断，不是建立平台或生产总分。

## 10.1 初始 Case

保留六条普通真实 Query：

```yaml
direct_fact_or_single_topic: 2
contextual_transcript_question: 1
cross_video_comparison: 1
partial_support: 1
no_reliable_evidence: 1
```

要求：

- Query 来自普通产品使用或 Goal 1/2 已使用的非 Gold Vertical Slice；
- 不读取、不接触、不反推 V0–V3.5 Case 级 Eval Query、Gold、答案或失败详情；
- Case Manifest 只记录 Query、类别、运行模式和必要说明；
- 不预写目标答案或 Gold Span；
- 不使用运行时 Eval Judge。

运行矩阵：

```yaml
fast:
  run_all_6: true

deep:
  run_at_least:
    - one direct fact case
    - contextual case
    - cross-video case
    - no-evidence case
```

若成本或 Provider 状态导致无法完成真实矩阵，保留已完成结果并明确报告，不得
用 Mock 结果伪装成真实运行。

## 10.2 确定性检查

每次运行至少记录和检查：

```yaml
contract_valid:
answer_block_citations_present:
citation_ids_resolve:
source_identity_current:
source_version_current:
segments_current:
navigation_not_cited:
stale_not_cited:
status_termination_valid:
budget_respected:
latency_ms:
provider_usage:
decision_rounds:
tool_calls:
repair_used:
context_truncated:
evidence_candidate_dropped_count:
```

现有 Runtime 测试已覆盖的确定性不变量应继续用自动测试证明；Eval Runner
不重复实现 Citation Validator。

## 10.3 轻量人工审阅

每个 Case 使用：

```yaml
supportedness: pass | partial | fail
usefulness: pass | partial | fail
coverage: pass | partial | fail
status_honesty: pass | partial | fail
notes:
```

人工审阅只对照返回 Answer Block 和 Citation Quote/时间点。无需创建多
Reviewer、Seal、Blind Review 或大型 Annotation Schema。

## 10.4 结果保留

允许形成：

- 一个小型 Eval Runner；
- 一个六条 Query 的机器可读 Manifest；
- 一个有界机器可读结果文件；
- `V4_G3_IMPLEMENTATION_REPORT.md` 中的人工结论和失败分析。

结果文件不得无界复制原字幕、完整 Prompt、Secrets 或历史 Eval 材料。
逐 Case 报告，不计算误导性的生产 SLA，不冻结大型 Acceptance Threshold。

---

# 11. Eval 驱动的优化规则

先区分：

```text
Implementation Bug
Product/Presentation Bug
Repeated Material Quality Failure
Single Anecdotal Failure
Deferred Capability Signal
```

Goal 3 可以直接修复：

- Ask 页面或状态机 Bug；
- Citation/Evidence 展示错误；
- Trace 投影错误；
- Fast/Deep 合同兼容问题；
- Policy/Prompt/Schema 的小幅有界修正；
- 确定性选择、截断或文案问题；
- 不改变架构的 Navigation Projection/Query 小修。

只有多条真实运行重复出现且材料性影响答案时，才可考虑 Goal 3 内的有界调整：

| 重复失败 | 首先允许的动作 |
|---|---|
| Navigation 漏掉明显相关视频 | 修 Projection、Source Weight 或 Query |
| Decision Context 成本过高 | 确定性压缩 Navigation/Policy 输入 |
| 关键 Candidate 被包络丢弃 | 调整确定性选择和上限 |
| Agent Action Schema 漂移 | 修 Prompt、Schema、错误反馈 |
| Answer Block 混合多个事实 | 收紧 Block 原子性 Prompt |
| Trace 难以理解 | 修投影和用户文案 |

下列触发信号只记录并提交主 Session，不得自行实现：

- Independent Navigation Index；
- Reranker；
- Native Tool Calling；
- Automatic Context Compaction；
- Runtime Semantic Judge；
- Adaptive Fast/Deep Router；
- 新的 Provider、Tool、Trace、Eval 或 Policy Platform；
- 改变 Citation Identity 或共享 Ask Contract；
- 放宽 Goal 2 确定性预算。

单次偶发失败不能作为引入上述机制的依据。

---

# 12. Demo 计划

最终 Demo 至少保留四段：

## Demo A — Search Evidence

```text
/search
→ 输入明确 Query
→ 展示相关字幕窗口
→ 展开更多证据
→ 跳转 B 站时间点
```

证明 `/search` 仍适合直接查证和 Debug。

## Demo B — Fast Grounded RAG

```text
/ask
→ 默认“快速回答”
→ 明确事实或单主题 Query
→ Answer Blocks [1][2]
→ Citation Card
→ 时间点跳转
→ 用户 Trace
```

## Demo C — Deep Agentic Search

```text
/ask
→ 选择“深入搜索”
→ 跨视频或复杂 Query
→ Navigation / Transcript Search / Window / Replanning
→ 共享 Grounded Answer
→ 用户 Trace + 折叠开发者 Trace
```

## Demo D — Honest Failure

```text
证据只能部分支持或没有可靠证据
→ partial 或 insufficient
→ limitations
→ 类型化 termination_reason
→ 不生成无引用事实答案
```

每段至少记录：

```yaml
query:
mode:
status:
termination_reason:
latency_ms:
citations:
trace_summary:
limitations:
user_visible_result:
```

README 必须解释：

- Fast 与 Deep 的差异；
- AI 总结只用于导航；
- 原字幕/ASR 才是事实权威；
- Citation 如何跳转；
- `partial`/`insufficient` 的含义；
- 当前非流式、内存 Trace 和真实 Provider 延迟边界；
- 如何运行定向测试和本地 Demo。

不得宣称生产 SLA、通用 Research Agent 或已完成 V5 个性化能力。

---

# 13. 建议代码边界

允许根据当前项目风格小幅调整文件名。建议：

```text
src/shiliu/templates/
  ask.html

src/shiliu/static/
  ask.css
  ask.js
  evidence-ui.css or shared evidence styles
  evidence-ui.js  or equivalent thin shared renderer

src/shiliu/ask/
  presentation.py       # optional bounded user-facing mappings

src/shiliu/ask/deep/
  policy.py             # optional static version + policy text extraction

scripts/
  run_v4_goal3_eval.py  # optional small runner
```

等价组织可以接受，但必须满足：

- Fast/Deep 使用同一个 Ask 前端状态机；
- Search/Ask 使用同一个 Evidence 基础渲染能力；
- 不把整个 Search 页面变成抽象 UI Framework；
- 不把全部 Ask 逻辑塞入 `web.py`；
- 不复制后端 Answer/Citation；
- Policy Version 是薄常量；
- Eval Runner 不依赖生产 Runtime 的 Gold；
- 不创建新的数据库平台表。

---

# 14. 实施阶段与退出条件

按一个纵向 Goal 推进：

## Phase A — 产品入口与共享展示基础

- 建立修改前 Web/Ask 基线；
- 新增 `/ask` Route、Template、Static；
- 更新顶部导航；
- 提取薄 Evidence Renderer/Styles；
- 保持 `/search` 行为和测试兼容。

退出条件：

- `/ask` 可加载；
- Fast 默认和模式选择可访问；
- `/search` 无回归；
- Search/Ask 没有复制两套 Evidence 基础。

## Phase B — Fast/Deep 完整交互

- 接入现有 `/api/ask`；
- 实现 Query/Mode/Filters URL 状态；
- 实现诚实 Loading/Error；
- 渲染 Answer Blocks、Citation、Limitations、Status、Termination；
- 实现 Citation 定位和 Fast-to-Deep 继续。

退出条件：

- 同一页面可消费 Fast/Deep；
- 所有结果状态可测试；
- Fast-to-Deep 不自动触发；
- Navigation 不显示为事实 Citation。

## Phase C — Trace 两层投影

- 用户 Trace 默认可见；
- Developer Trace 折叠并按需读取；
- 终止原因产品化；
- Deep Tool Timeline 有界展示；
- 添加静态 Policy Version Trace。

退出条件：

- 用户可理解运行为何停止；
- Developer Trace 可诊断但不泄漏 Secrets/隐藏推理；
- 不增加 Trace Persistence。

## Phase D — Lightweight Eval

- 建立六条普通 Query Manifest；
- 实现最小 Runner/Result 记录；
- 运行 Fast 全集和规定的 Deep 子集；
- 完成人工四维审阅；
- 保留成功与失败。

退出条件：

- 每个 Case 有确定性指标和人工结论；
- 没有 Eval Gold 或 Runtime Judge；
- 形成明确的“修 / 不修 / Deferred”判断。

## Phase E — 有界修正、Demo 与回归

- 只修真实重复材料性问题；
- 完成四段 Demo；
- 更新 README；
- 运行定向和默认全套测试；
- 创建实现报告。

退出条件：

- Goal 3 完成条件全部满足；
- 无新平台或未经批准能力；
- 工作区、Diff、测试和报告可供主 Session Integration Review。

---

# 15. 测试要求

至少覆盖：

## Route 与页面

- `GET /ask` 成功；
- 顶部导航存在问答和搜索证据入口；
- 页面包含 Fast/Deep 控件且 Fast 默认；
- `/search` 保持兼容；
- 静态资源可加载。

## Ask 前端状态

- 空 Query；
- Fast 请求 Payload；
- Deep 请求 Payload；
- Loading 防重复；
- 新请求不会被旧 Response 覆盖；
- Network/API Error；
- `complete`；
- `partial`；
- `insufficient`；
- Fast-to-Deep 保留 Query/Filters；
- URL restore/popstate；
- Developer Trace 404。

优先沿用项目现有 Web/HTML 测试方式；如果当前无浏览器单元测试基础，不要为了
Goal 3 引入大型 JavaScript 测试框架。可以使用 DOM 契约测试加真实浏览器
Smoke Test，但必须验证关键交互，而不只是检查 HTML 字符串。

## Answer/Citation 展示

- Answer Block 顺序；
- Citation 展示编号稳定；
- 多 Block 复用 Citation；
- 点击标记能定位 Evidence；
- 同视频多 Citation 可展开；
- B 站链接和时间点；
- Navigation 内容不进入 Evidence Card；
- `insufficient` 无 Answer Block；
- XSS 安全：用户 Query、Answer 和 Quote 使用文本节点或等价安全转义。

## Trace

- 用户 Trace 文案；
- Fast/Deep 指标差异；
- 零值降噪；
- Termination 映射；
- Developer Trace 按需读取；
- 无隐藏推理和 Secrets；
- Policy Version；
- Trace 缺失不破坏答案。

## 回归

- Goal 1 Fast Ask；
- Goal 2 Deep Search；
- Ask Contract；
- Product Search；
- Retrieval/Evidence；
- 默认全套测试。

所有新增 Pydantic 合同继续使用 `extra="forbid"`。不得为了 UI 放宽后端
Citation 或 Answer Validation。

---

# 16. 真实运行与视觉验证

Goal 3 不能只用 Mock 结束。

必须使用：

- 当前真实本地数据库或安全只读副本；
- 当前 DeepSeek 配置；
- 普通非 Gold Query；
- Fast 和 Deep；
- 桌面与移动宽度的真实页面；
- B 站跳转 URL 的结构验证。

视觉验证至少检查：

- Ask 首屏层级；
- Fast/Deep 选择清晰度；
- 长答案；
- 多 Citation；
- 长字幕 Quote；
- `partial`/`insufficient`；
- Loading 和 Error；
- Trace 折叠；
- 手机宽度不溢出。

如果真实 Provider 或外部网络不可用：

- 先完成确定性和 Scripted Provider 路径；
- 保留阻塞证据；
- 请求必要授权或报告外部阻塞；
- 不伪造真实运行结论。

---

# 17. Goal 3 完成条件

以下全部满足才可报告完成：

- `GET /ask` 可用；
- Fast 默认、Deep 显式选择；
- Fast `partial`/`insufficient` 可显式进入 Deep；
- 无自动 Router；
- Fast/Deep 共享页面和 AskResponse Renderer；
- `/search` 仍可直接搜索证据；
- Search/Ask 复用薄 Evidence Renderer/Styles；
- Answer Block 与 Citation 标记可定位；
- Evidence Card 使用权威字幕并可跳转时间点；
- Navigation 内容不成为 Citation；
- Loading/Error/Complete/Partial/Insufficient 完整；
- 用户 Trace 默认可见；
- Developer Trace 默认折叠、按需读取；
- Trace 不暴露隐藏推理或 Secrets；
- Deep Policy Version 可追踪；
- 六条普通 Query Manifest 和结果被保留；
- Fast 全集、Deep 规定子集完成，或真实外部阻塞被明确记录；
- 人工 Supportedness/Usefulness/Coverage/Status Honesty 完成；
- 只实施由重复材料性失败支持的有界修正；
- 四段 Demo 完成；
- README 更新；
- 定向测试与默认全套回归通过；
- 生成 `V4_G3_IMPLEMENTATION_REPORT.md`；
- 没有增加被禁止的平台或 Deferred 能力。

---

# 18. Escalation 条件

遇到以下情况时暂停相关方向并向主 Session 报告：

- 需要改变共享 Ask Contract、Citation Identity 或事实权威边界；
- 需要让 AI 总结、Notes 或整理稿成为 Citation；
- 需要 Fast/Deep 自动路由；
- 需要服务器端任务队列、持久化或 Resume；
- 需要 Token Streaming 或新 SSE/WebSocket 基础设施才能完成基本可用性；
- 需要 Independent Navigation Index、Reranker、Native Tool Calling、
  Automatic Context Compaction 或 Runtime Semantic Judge；
- 需要放宽 Goal 2 的 Round、Tool 或时间预算；
- 真实 Eval 发现多个材料性失败，但修复会改变 V4 架构；
- 现有 Search UI 无法在不重写产品前端的情况下提取 Evidence 展示；
- 真实 Provider/网络在获得必要授权后仍无法完成所需运行；
- 用户已有修改与 Goal 3 文件冲突且无法安全绕开。

普通 CSS、Template、DOM 结构、文件名、内部函数拆分和测试组织不需要逐项审批。

---

# 19. 禁止事项

本 Goal 禁止：

- 重写 Goal 1/Goal 2 后端；
- 创建第二套 Answer、Citation 或 Ask API；
- 删除或替换 `/search`；
- 默认 Deep 或自动 Fast-to-Deep；
- 把 Navigation 内容展示为事实 Citation；
- 接触历史 Case 级 Eval Query、Gold、答案或失败详情；
- 创建大型 Eval、Trace、Policy、Tool、Provider 或 Demo 平台；
- 添加 Runtime Semantic Judge；
- 添加 Native Tool Calling；
- 添加 Independent Navigation Index 或 Reranker；
- 添加 Automatic Context Compaction；
- 添加 Token Streaming、SSE/WebSocket 平台；
- 添加 Checkpointer、Persistence、Memory、HITL、Interrupt、Subgraph 或
  Multi-Agent；
- 接入 LangGraph Cloud 或 LangSmith Runtime；
- 创建 Skill Registry 或把 Deep Policy 变成动态 Skill 系统；
- 为每个内部判断建立 Gate、Readiness、Audit 或 Closeout 文档；
- 声称生产 SLA；
- 修改 V0–V3.5 冻结材料；
- 扩大到 V5。

---

# 20. 工作方式

- 先建立真实基线，再修改；
- 按纵向用户结果推进，不按平台拆任务；
- 优先保持现有合同与后端不变；
- 每个 Phase 完成后运行相关测试；
- 真实 Provider 调用前先验证 Scripted/Deterministic 路径；
- 视觉验证不能只看源代码；
- 不覆盖用户已有工作；
- 不将无关文件加入提交；
- 不因单次真实失败扩大范围；
- Push 前确认分支、Diff、测试、Eval、Demo 和报告；
- 未经用户或主 Session 授权，不自行 Merge；
- Goal Session 不得自行修改 `V4_MASTER_STATE.md` 或
  `V4_DECISION_LEDGER.md` 宣布 V4 完成。

---

# 21. 最终返回主 Session 的报告

创建：

```text
V4_G3_IMPLEMENTATION_REPORT.md
```

报告只包含：

## A. Outcome

- Goal 是否完成；
- 用户可见能力；
- 是否存在 Blocking Finding；
- 是否建议宣布 V4 完成。

## B. Product and Code Changes

- `/ask` Route、Template、Static；
- Shared Evidence Renderer；
- Fast/Deep Interaction；
- User/Developer Trace；
- Policy Version；
- Eval Runner/Artifacts；
- README。

## C. Tests

- 修改前基线；
- Goal 3 定向；
- Goal 1/Goal 2 回归；
- 默认全套；
- 浏览器/视觉验证；
- Warning 和失败。

## D. Lightweight Eval

- 六条 Query 类别；
- Fast/Deep 运行矩阵；
- 每 Case Status/Termination/Citation/Latency/Usage；
- Supportedness/Usefulness/Coverage/Status Honesty；
- 成功和保留失败；
- 未运行项及原因。

## E. Eval-driven Decisions

- 实施了哪些有界修正及证据；
- 哪些观察不足以支持优化；
- 哪些触发信号提交主 Session；
- 确认没有单次失败驱动的平台扩张。

## F. Demo

- Search、Fast、Deep、Honest Failure 四段；
- 页面结果、Citation 跳转和 Trace；
- 已知产品边界。

## G. Scope Audit

- Fast/Deep 共享合同；
- Navigation/Fact 隔离；
- 无自动 Router；
- 无新平台；
- 无禁止的 LangGraph/Streaming/Persistence 能力；
- 无历史 Eval Gold。

## H. Risks and Open Issues

- 只列真实观察；
- 区分 Blocking、V5 输入和 Deferred 触发信号。

## I. Suggested Master State Update

- 建议 Goal 3 状态；
- 建议 V4 状态；
- 主 Session Integration Review 尚需检查的事项；
- Goal Session 不得自行宣布正式验收。

---

# 22. 启动指令

现在开始 Goal 3。

先完整阅读正式文件、检查工作区并建立测试基线，然后按一个纵向 Goal 实现：

```text
/ask Product Entry
→ Shared Fast/Deep Answer and Evidence UX
→ User/Developer Trace
→ Six-case Lightweight Eval
→ Evidence-driven Bounded Refinement
→ Four-part Demo
→ Full Regression
→ V4_G3_IMPLEMENTATION_REPORT.md
```

不要重新讨论已经接受的产品与架构决定。不要创建新平台。不要扩大到 V5。
