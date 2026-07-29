# Shiliu V4 Goal 3 Implementation Report

```yaml
goal: Goal 3 — Product Integration, Lightweight Eval, and Demo
implementation_status: complete
integration_review: ready
date: 2026-07-29
branch: codex/v4-main
starting_commit: 18b1956
```

## A. Outcome

Goal 3 的产品、真实 Eval、人工审阅与 Demo 已完成：

- `GET /ask` 是可用的 Fast/Deep 统一入口；
- Fast 默认，Deep 由用户显式选择；
- Fast `partial / insufficient` 可保留 Query 和 Filters 切换到 Deep，
  不会自动发起请求；
- 两种模式共用 `AskResponse`、Answer Block、Citation 和 Evidence Renderer；
- Citation 标记可以展开、定位并高亮权威字幕 Evidence Card；
- 用户 Trace 默认可见，开发者 Trace 按需读取；
- `/search` 保持直接证据搜索，并共用薄 Evidence UI；
- 六例 Manifest、真实 Eval Runner、四段 Demo 记录和 Scripted UI Fixture
  已建立。
- 用户明确授权后，已使用当前本地数据库的临时 SQLite 快照和当前 DeepSeek
  配置完成 6 Fast + 4 Deep；
- 10 次运行全部完成确定性检查，逐 Case 四维人工审阅均已填写；
- 真实 Search、Fast、Deep、诚实失败四段 Demo 均有后端运行记录，并与
  桌面/移动浏览器交互验证组合留证。

当前结论：

```yaml
goal_3_product_implementation: complete
goal_3_deterministic_verification: complete
goal_3_real_eval: complete_6_fast_4_deep
goal_3_manual_review: complete_10_of_10
goal_3_demo: complete
goal_3_overall: complete
blocking_findings_remaining: 0
recommend_v4_complete: true
```

## B. Product and Code Changes

### `/ask` Route、Template 与 Static

- `src/shiliu/web.py`
  - 新增 `GET /ask`；
  - 复用当前 active source 列表。
- `src/shiliu/templates/ask.html`
  - 问题输入；
  - Fast/Deep 可访问 Radio；
  - 折叠限定范围；
  - Idle、Loading、Error、Complete、Partial、Insufficient；
  - Answer、Evidence、User Trace、Developer Trace；
  - 显式 Fast-to-Deep。
- `src/shiliu/static/ask.js`
  - Query/Mode/Filter URL 状态与 `popstate`；
  - 一次性 `/api/ask` 请求；
  - 真实本地等待时间、防重复提交、Abort/Sequence 旧响应隔离；
  - Fast/Deep 统一结果渲染；
  - Citation 展示编号、分组、展开、定位与高亮；
  - Developer Trace 懒加载及 404 降级；
  - 全部用户、Answer、Quote 与 Trace 字符串使用 `textContent`。
- `src/shiliu/static/ask.css`
  - 桌面与 390px 手机布局；
  - 长 Answer、长 Quote、状态、Trace 和证据卡样式。

### Shared Evidence Renderer

- `src/shiliu/static/evidence-ui.js`
- `src/shiliu/static/evidence-ui.css`

共享：

- 时间与时长格式；
- 字幕来源文案；
- 权威 Quote Card；
- `t=` 时间跳转；
- 折叠 Evidence Identity；
- Citation Target 高亮。

`search.js` 已改为调用该 Renderer，不再自己维护 Window 时间、字幕来源、跳转
和证据卡 DOM；Search 页面原有视频分组、更多窗口和 Search 状态机保持独立。

### Fast/Deep Interaction

- Fast 默认；
- Deep 必须显式选择；
- Fast-to-Deep 只切换 Mode、保留 Query/Filters 并更新 URL；
- 不后台升级、不增加 Router；
- `insufficient` 不渲染 Answer Block；
- 未被 Block 引用的 Citation 不会被附到段落；
- 同一个 Citation 在多个 Block 中复用同一 Evidence Card。

### User/Developer Trace

- 用户 Trace 对零值降噪，展示模式、Latency、Evidence、停止原因及 Deep
  Decision/Tool/Visited/Navigation/Dropped 指标；
- 终止原因已映射为产品文案；
- 开发者 Trace 只在展开后请求；
- UI 只投影受控 Action Kind、Observation Summary、Usage、Policy 和计数；
- 不展示完整 Prompt、Secrets、隐藏推理或完整字幕 Corpus；
- Trace 404 不破坏已经返回的 Answer/Citation。

### Policy Version

- 新增 `src/shiliu/ask/deep/policy.py`；
- 将现有 Deep Policy 文本赋予静态版本：

```text
v4-deep-policy-v1
```

- `AgentDecisionService` 使用该静态 Policy；
- Deep Trace 记录 `policy_version`；
- 未增加 Registry、Loader、Marketplace 或动态 Skill Runtime。

### Eval Runner 与 Artifacts

- `eval/v4_goal3_cases.json`
  - 六条普通 Query；
  - 2 Direct/Single-topic、1 Contextual、1 Cross-video、1 Partial、
    1 No-evidence；
  - Fast 6 条，Deep 规定 4 条；
  - 无 Target Answer、Gold Span 或 Runtime Judge。
- `scripts/run_v4_goal3_eval.py`
  - 使用本机数据库临时 SQLite 快照；
  - 逐 Case 保留合同、Citation、Identity/Version、Segment、Navigation 隔离、
    Budget、Latency、Usage、Repair、Truncation 和 Dropped 指标；
  - Review Material 只保留有限 Answer/Quote 摘录；
  - 支持分 Case/Mode 运行和有界结果合并。
- `eval/v4_goal3_results.json`
  - 保留 6 Fast + 4 Deep 真实 Provider 结果；
  - 保留确定性检查、有限 Answer/Quote、运行指标与 10 条人工审阅；
  - 不包含 Secrets、完整 Prompt 或无界字幕。
- `scripts/run_v4_goal3_search_demo.py`
  - 对当前数据库临时快照执行真实 `MCP` 关键词搜索；
  - 验证结果窗口和 Bilibili `?t=` 跳转结构；
  - 不调用 Provider，也不修改真实数据库。
- `scripts/run_v4_goal3_ui_fixture.py`
  - 完全虚构数据的 UI QA Fixture；
  - 覆盖 Fast/Deep、Complete/Partial/Insufficient、Provider Error、
    Loading、Citation、Trace/404 和 Search；
  - 不作为真实质量 Eval。
- `eval/v4_goal3_demo_results.json`
  - 保留四段真实后端 + Scripted 浏览器视觉验证结果及验证等级。

### README

README 已更新为 V4 产品说明，解释：

- Fast 与 Deep；
- Navigation/Fact 隔离；
- 原字幕/ASR 权威；
- Citation 定位与跳转；
- `partial / insufficient`；
- 非流式、内存 Trace、Provider 延迟和浏览器取消边界；
- 本地运行、定向/全套测试、UI Fixture 和真实 Eval 命令；
- 真实 Eval 的数据传输授权要求。

## C. Tests

### 修改前真实基线

```text
branch: codex/v4-main
commit: 18b1956
working_tree:
  user_modified:
    - V4_MASTER_STATE.md
    - V4_DESIGN_PROPOSAL.md
    - V4_DECISION_LEDGER.md
  untracked:
    - V4_G3_EXECUTION_PROMPT.md
directed: 76 passed
warnings: 1 existing Starlette/httpx deprecation warning
```

三份正式 V4 文件与 Prompt 均被保留，Goal 3 没有修改它们。

### Goal 3 定向与 Goal 1/2/Search 回归

```text
80 passed
1 existing Starlette/httpx deprecation warning
```

覆盖：

- `/ask` Route、导航、Static；
- Fast/Deep 控件与默认值；
- 共享 Evidence Renderer；
- Loading、防重复、旧响应隔离源契约；
- Complete、Partial、Insufficient、Provider/Network Error；
- Fast-to-Deep、URL/Popstate；
- Answer Block 顺序与 Citation 复用；
- 折叠 Citation 自动展开后定位；
- Bilibili `t=`；
- Developer Trace 懒加载与 404；
- Deep Policy Version；
- 六 Fast / 四 Deep Manifest；
- Fast Ask、Deep Search、Product Search 和历史 Web 回归。

JavaScript 语法检查：

```text
node --check evidence-ui.js: passed
node --check search.js: passed
node --check ask.js: passed
```

最终完整性检查：

```text
python -m compileall -q src scripts: passed
python -m pip check: no broken requirements
git diff --check: passed
Goal 3 JSON parse: passed
result secret-pattern scan: no matches
matrix audit: 10 runs / 6 Fast / 4 Deep / 10 reviews / all deterministic checks
```

### 默认全套

```text
1450 passed, 4 deselected
1 existing Starlette/httpx deprecation warning
```

### 浏览器与视觉验证

真实浏览器执行了：

- Desktop 1280px；
- Mobile 390px；
- Fast 默认；
- Query/Mode URL restore/back；
- 真实等待秒数与 Submit Disabled；
- Complete、Partial、Insufficient；
- Provider Error 与断网 Error；
- Fast-to-Deep 保留 Query 且不自动请求；
- 两个 Answer Block 复用 `[1]`；
- 点击折叠的 `[2]` 自动展开、滚动、聚焦、高亮；
- 长 Answer、长 Quote、多 Citation；
- Bilibili `t=12 / t=42`；
- 用户 Trace；
- Deep Policy/Action/Observation/Usage Developer Trace；
- Developer Trace 404；
- `/search` 两个共享 Evidence Card 和“更多相关片段”；
- 手机 `scrollWidth == clientWidth == 390`。

浏览器技能的真实 DOM/视觉检查直接促成了一个 Citation 定位 Bug 修复和一个
桌面标题孤字换行修正。

## D. Lightweight Eval

六个 Case：

| Case | Category | Fast | Deep |
|---|---|---:|---:|
| `direct_fact_mcp` | direct fact | required | required |
| `single_topic_context_compression` | single topic | required | — |
| `contextual_tool_failure` | contextual | required | required |
| `cross_video_context_management` | cross-video | required | required |
| `partial_universal_claim` | partial support | required | — |
| `no_evidence_quantum_protocol` | no reliable evidence | required | required |

真实矩阵：

```yaml
fast_completed: 6/6
deep_completed: 4/4
manual_reviews_completed: 10/10
real_results_preserved: 10
runtime_errors: 0
all_deterministic_checks_passed: true
database_mode: temporary_snapshot
provider: current_configured_deepseek
```

运行结果：

| Case | Mode | Status | Termination | 人工结论摘要 |
|---|---|---|---|---|
| contextual tool failure | Fast | partial | answer_ready | 多策略有用；两项为间接扩展 |
| contextual tool failure | Deep | complete | answer_ready | 两项直接支持；覆盖较窄 |
| cross-video context | Fast | insufficient | provider_error | Provider 长度上限；诚实失败 |
| cross-video context | Deep | partial | answer_ready | 有材料，但比较包含推断 |
| direct MCP | Fast | partial | answer_ready | 定义和连接均受支持 |
| direct MCP | Deep | partial | answer_ready | 定义/架构/注入均受支持 |
| no-evidence protocol | Fast | insufficient | answer_ready | 拒绝虚构，无 Answer/Citation |
| no-evidence protocol | Deep | partial | provider_error | 结论合理，抽样不足以证明全库缺失 |
| universal compaction claim | Fast | partial | answer_ready | 正确否定全称；一条弱相关引用 |
| context compression | Fast | partial | answer_ready | 主干充分；一条引用不相关 |

人工四维分布：

```yaml
supportedness: {pass: 4, partial: 5, fail: 1}
usefulness: {pass: 8, partial: 1, fail: 1}
coverage: {pass: 5, partial: 4, fail: 1}
status_honesty: {pass: 9, partial: 1}
```

未使用 Mock 填充真实结果，未计算生产 SLA 或误导性总分。Fast 跨视频的单次
Provider 长度失败和 Deep 无证据边界均按真实输出保留。

## E. Eval-driven Decisions

已经实施的有界修正：

1. Browser QA 发现点击 `[2]` 时目标 Evidence Card 仍在折叠组中。修正为先展开
   对应组，再滚动、聚焦和高亮；未改变 Citation Identity。
2. Desktop QA 发现首屏标题出现孤字换行。收紧 Hero 字号和宽度；不改变产品结构。

Eval 后没有实施质量调参：

- 仅一条 Fast 因 Provider 长度上限没有结构化输出；
- 两条 Fast 出现弱相关 Citation，但核心结论仍由其他引用支持；
- 一条 Deep 比较含明确披露的推断，一条 Deep 无证据回答以抽样材料作全库断言；
- 这些结果不足以证明某个有界 Runtime 修正能稳定改善矩阵，且用户授权的是
  既定 6 + 4 次真实运行，因此未事后重跑或为通过评测调 Prompt；
- 没有增加 Index、Reranker、Native Tool Calling、Compaction 或新平台。

提交主 Session 的信号：Goal 3 完成条件已满足；上述弱相关 Citation、跨视频
推断和无证据全库断言可作为后续质量工作输入，但不构成 V4 Blocking Finding。

## F. Demo

四段 Demo 记录位于 `eval/v4_goal3_demo_results.json`。

### Search Evidence

- `/search`；
- Query `MCP`；
- 真实数据库快照返回 10 个视频、16 个字幕窗口，71.649 ms；
- 全部返回窗口的 Bilibili `?t=` 跳转结构通过；
- 浏览器 Fixture 另验证首窗、展开第二窗和 `t=12 / t=42` 交互。

### Fast Grounded RAG

- `/ask` Fast 默认；
- 真实 MCP Query，54,395.041 ms；
- `partial / answer_ready`，两个 Answer Blocks、5 个现行 Citation；
- `[1][2]` 稳定编号；
- 分组 Evidence Card；
- User Trace。

### Deep Agentic Search

- `/ask` Deep 显式选择；
- 真实工具失败 Query，45,852.801 ms；
- `complete / answer_ready`，3 Decision Rounds、2 Tool Calls、2 Citations；
- 共享 Answer/Citation；
- Deep 指标；
- 懒加载 Developer Trace；
- Navigation → Transcript Search → Window → Finish；
- `v4-deep-policy-v1`。

### Honest Failure

- 真实虚构协议 Query，Fast `insufficient / answer_ready`；
- 51,133.003 ms，经一次结构修复仍拒绝虚构；
- 无 Answer Blocks/Citations；
- Limitations 与停止原因可见；
- 显式 Deep 继续。

真实质量与运行字段来自 Goal 3 本次矩阵；浏览器 Fixture 用于覆盖真实矩阵不易
稳定触发的 Loading、Network Error、Trace 404、折叠 Citation 和移动宽度交互。
两者在结果文件中明确区分，没有把 Fixture 当作真实 Provider 质量结果。

## G. Scope Audit

```yaml
fast_deep_shared_ask_contract: true
fast_deep_shared_response_renderer: true
search_ask_shared_evidence_renderer: true
navigation_in_fact_context: false
non_transcript_citation_source: false
automatic_router_added: false
automatic_fast_to_deep: false
second_answer_or_citation_backend: false
native_tool_calling: false
independent_navigation_index: false
reranker: false
runtime_semantic_judge: false
automatic_context_compaction: false
token_streaming_or_sse_websocket: false
checkpoint_persistence_memory_resume: false
hitl_interrupt_subgraph_multi_agent: false
new_provider_trace_eval_policy_platform: false
historical_eval_gold_accessed: false
v0_to_v3_5_frozen_material_modified: false
master_state_or_decision_ledger_modified_by_goal3: false
```

## H. Risks and Open Issues

### Blocking

无。

### Non-blocking

1. Trace 是内存态，进程重启后 Developer Trace 可能 404；UI 已诚实降级。
2. 浏览器 Abort 只防止旧 Response 覆盖，不取消服务器端 Provider 运行。
3. Fast 跨视频 Case 的 Provider 输出达到长度上限；这是一次真实运行失败，
   已由 `insufficient/provider_error` 诚实呈现。
4. 两个 Fast Case 含弱相关 Citation；Deep 跨视频比较含推断；Deep 无证据
   Case 用有限样本支撑全库缺失，人工审阅已降为 partial。

### Deferred / V5 Input

当前没有新证据触发 Independent Navigation Index、Reranker、Native Tool
Calling、Context Compaction、Adaptive Router、Streaming、Persistence 或 V5
个性化。

## I. Suggested Master State Update

当前建议：

```yaml
goal_3:
  product_implementation: complete
  deterministic_tests: passed
  browser_visual_qa: passed_with_bounded_repairs
  lightweight_eval_manifest: complete
  real_eval_matrix: complete_6_fast_4_deep
  manual_review: complete_10_of_10
  integrated_real_demo: complete_backend_plus_browser_validation
  status: complete

v4:
  status: ready_for_integration_review
  declare_complete: recommended_after_master_session_review
```

主 Session Integration Review 只需复核最终全套测试、Diff、Scope、10 条真实
结果和人工审阅，并由主 Session 更新 `V4_MASTER_STATE.md` /
`V4_DECISION_LEDGER.md`。

Goal 3 Session 不自行宣布 V4 完成。

## J. Main Session Integration Repair

### J.1 Findings Received

主 Session 要求本轮只修复两个 Blocking Findings：

1. 有限检索证据被表述为整个收藏库不存在，且三个目标 Case 出现全库否定或
   弱相关 Citation；
2. Eval Runner 的 `status_termination_valid` 为硬编码，原
   `navigation_not_cited` 依赖 Navigation Event 上通常为空的字段。

另包含一个非阻塞展示修复：共享顶栏将 `/search` 显示为“搜索证据”。本轮
没有扩大到新的产品能力、Runtime Semantic Judge 或 Eval 平台。

### J.2 Code Changes

- `GroundedAnswerService` 的 Initial 与 Same-context Repair Prompt 共用同一组
  Grounding Boundary 指令：
  - Retrieval/Context 是有限样本；
  - 未出现不能证明整个收藏库不存在；
  - 全称或否定范围结论必须有直接支持；
  - 无直接支持时返回 `insufficient`、空 Answer Blocks，并采用范围诚实文案；
  - Limitations 不能承载无 Citation 的材料性事实；
  - 每个 Citation 必须直接支持所在 Block 的完整材料性表述，不能因 Allowlist
    命中而机械附加，也不能拼接无关样本证明全库缺失。
- 共享 `AnswerFinalizer` 对模型声明的 `insufficient` 增加薄确定性保护：
  - 强制空 Answer Blocks/Citations；
  - 丢弃模型生成的材料性 Limitation；
  - 使用“本次检索未找到足以回答该问题的可靠字幕证据”；
  - 只追加 Runtime 已知的 Context Truncation 与确定性停止边界。
- Eval Runner 新增纯 `_deterministic_checks()`：
  - 真实重验 `AskResponse` Schema；
  - 真实比较 Response 与 Trace Summary 的 Termination；
  - 真实检查 `insufficient`/answering Shape、Block Citation 与 Response
    Citation Resolution；
  - 以 `_validate_citation()` 的当前原字幕重建结果生成
    `citations_reconstruct_from_current_transcript`；
  - 删除硬编码 `status_termination_valid: True` 和基于 Navigation 空字段的
    `navigation_not_cited`。
- 新增六类负向 Checker 测试：Termination 不一致、Insufficient 带正文/引用、
  answering 无 Block、缺失 Response Citation、Citation 无法重建，以及
  Navigation Event 无 `citation_ids` 不能证明 Provenance。
- 共享顶栏文案改为“搜索证据”，并验证 `/ask`、`/search` 与首页。

### J.3 Deterministic Verification

```yaml
before_repair_directed:
  result: 43 passed
  warning: 1 existing Starlette/httpx deprecation warning

after_repair_core_directed:
  result: 50 passed
  warning: 1 existing Starlette/httpx deprecation warning

after_repair_extended_directed:
  result: 97 passed
  warning: 1 existing Starlette/httpx deprecation warning

default_full_suite:
  result: 1457 passed, 4 deselected
  warning: 1 existing Starlette/httpx deprecation warning

static:
  compileall: passed
  pip_check: no_broken_requirements
  pip_cache_warning: existing_user_cache_not_writable
  node_evidence_ui: passed
  node_search: passed
  node_ask: passed
  git_diff_check: passed
```

浏览器 Fixture 复验确认：

- `/ask` 与 `/search` 顶栏均显示“搜索证据”；
- Fast 默认、Deep 可显式选择；
- Fast/Deep 控件与共享 Evidence UI 未回归；
- 点击折叠的 `[2]` 会展开证据并将焦点移动到第二条权威字幕卡；
- Developer Trace 可按需展开并读取；
- `/search` 继续加载共享 Evidence Renderer。

### J.4 Targeted Real Reruns

```yaml
authorization: explicitly_received
new_provider_calls_completed: 4
call_budget:
  fast: 3/3
  deep: 1/1
extra_provider_calls: 0
reruns_or_resampling: 0
repair_result_file: eval/v4_goal3_repair_results.json
original_result_file_overwritten: false
deterministic_checks_all_true: 4/4
manual_reviews_completed: 4/4
results:
  - case: no_evidence_quantum_protocol
    mode: fast
    status: insufficient
    termination: answer_ready
    answer_blocks: 0
    citations: 0
    latency_ms: 19838.116
    provider_total_tokens: 8665
    checker: 10/10_true
    review: pass
  - case: partial_universal_claim
    mode: fast
    status: insufficient
    termination: answer_ready
    answer_blocks: 0
    citations: 0
    latency_ms: 36746.720
    provider_total_tokens: 9021
    checker: 10/10_true
    review: supportedness_pass_usefulness_partial_coverage_partial_honesty_pass
  - case: single_topic_context_compression
    mode: fast
    status: partial
    termination: answer_ready
    answer_blocks: 2
    citations: 3
    latency_ms: 90485.581
    provider_total_tokens: 11315
    checker: 10/10_true
    review: pass
  - case: no_evidence_quantum_protocol
    mode: deep
    status: insufficient
    termination: provider_error
    answer_blocks: 0
    citations: 0
    latency_ms: 28980.798
    provider_total_tokens: 11900
    checker: 10/10_true
    review: pass
```

与原结果相比，Fast/Deep 的无证据 Case 都不再使用无关 Citation 外推“整个收藏
库不存在”；Deep 从带五条无关 Citation 的 `partial/provider_error` 收敛为
`insufficient/provider_error` 空回答。`partial_universal_claim` 不再携带弱相关
Citation，但退化为安全而偏保守的 `insufficient`。上下文压缩 Case 去除了原来的
权限类无关 Citation，形成两个有用 Answer Blocks。Goal Session 初审只读取结果
文件前 500 字 `quote_excerpt`，曾将 `0e3e` 误判为不能支持“自动压缩造成性能
损失”。主 Session 使用当前 Source Version 和相同 Stable Citation ID 重建完整
232.71–467.59 秒字幕，确认其中明确包含“一旦触发自动压缩，性能就直接下降”；
Supportedness 因此更正为 `pass`。没有追加 Provider 调用。

### J.5 Scope Audit

```yaml
new_platform: false
architecture_expansion: false
runtime_semantic_judge: false
fast_deep_shared_answer_service: true
fast_deep_shared_finalizer: true
second_answer_or_citation_backend: false
original_goal3_results_sha256:
  65cc177742492459a5f3f3032f24b5d0495921dc7cc57b9a2fc4745c9e0d5b2e
original_goal3_results_overwritten: false
formal_v4_files_modified_by_repair: false
git_stage_commit_push_merge: false
```

三份正式状态文件在本轮前已经属于工作区已有修改；Repair 开始与当前哈希一致，
本轮没有编辑它们。

### J.6 Repair Outcome

```yaml
answer_boundary_repair: code_complete_and_no_evidence_cases_pass
eval_integrity_repair: deterministic_complete
navigation_label_repair: complete
directed_tests: passed
full_suite: passed
targeted_real_reruns: completed_3_fast_1_deep_without_resampling
remaining_blocking_finding: none
goal_3_recommendation: accepted_by_main_session_second_integration_review
v4_recommendation: ready_for_formal_completion_update
```

### J.7 Main Session Second Integration Review

主 Session 独立完成：

- 57 项 Goal 3 Repair、Ask、Deep 和 Search 定向测试；
- 默认完整测试集；
- Compileall、Pip Check、三个 JavaScript 语法检查和 `git diff --check`；
- 四条 Repair 结果、10 项确定性 Checker 和原结果 SHA-256 核验；
- `0e3e` 当前 Source Version、Stable Citation ID、Segment 范围和完整字幕重建。

第二次 Integration Review 结论：

```yaml
goal_3_product_implementation: accepted
goal_3_deterministic_regression: accepted
goal_3_browser_integration: accepted
goal_3_eval_integrity: accepted
goal_3_targeted_real_reruns: accepted
remaining_blocking_finding: none
goal_3_overall: accepted
v4_completion_readiness: ready
```

本次复核还确认：轻量 Eval 的 `quote_excerpt` 是有界审阅材料，不是完整 Citation。
当材料性支持可能位于截断范围之外时，人工审阅必须按 Stable Citation 重建当前
权威字幕后再作 Supportedness 判断，不能把 excerpt 截断误判为证据缺失。
