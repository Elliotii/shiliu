# Shiliu V3.5-B Stage 5 工作记录

## 文档范围

本文记录本次 Stage 5 中完成的 Minimal API、Minimal UI、End-to-End
Trace 集成，以及 Stage 5 完成后围绕现有搜索页、实时收藏内容和封面展示所做的
产品修复。

明确不包含：

- `bilibili-cli` 的安装、登录、Cookie 获取、浏览器钥匙串访问或重新认证；
- 对冻结 Retrieval、Candidate Builder、Selector、Mechanical Gate 或
  Semantic Judge 算法的优化；
- Final Answer、Agentic Search、Memory、Harness 或大型异步任务系统。

正式 Stage 5 于 2026-07-27 完成并冻结。其后的搜索、同步保护和封面展示修改
属于产品运行修复，单独记录，不重新解释原冻结结果。

---

## Stage 5 Minimal API / UI / Trace Integration Result

以下正文内容按 `STAGE5_FINAL_CLOSEOUT.md` 的正式输出原样收录；为嵌入本文，
只将其中的二级标题降为三级：

### Final result

`stage5_minimal_integration_pass_with_documented_limitations`

`Stage5_status: formally_closed_pass_with_limitations`

`next_stage: Pre_Frozen_Checklist`

Stage 5 reused the existing FastAPI, application services, Product Search,
SearchCandidateSet projection, Search page, and logging directory. It added only
a thin synchronous facade, two API routes, an additive Root Trace, and an
existing-page UI panel.

The formal route is V3 Search/Auto Retrieval → `stage3b-acronym-w3.5-v1` →
`v3.5-deterministic-fine-selector-v1` → EvidenceBundle v1 →
`mechanical-gate-v1-r1` → frozen Semantic Judge. Mechanical terminal statuses
bypass the Judge and remain distinct from semantic four-state decisions.

The UI shows Query, current/final stage, status, latency, authoritative evidence
text and timestamps, Evidence/Segment IDs, Gate status/reasons, semantic
supported/missing/conflict fields, confidence, Evidence IDs used, Policy
version, Trace spans, typed errors, and the explicit no-Final-Answer limitation.

The provider timeout is 180 seconds, above the observed Stage 4B maximum of
89.173 seconds. Judge start/end, latency, retry count, parse status, model,
Prompt/Policy versions, and response hash are traced.

The focused contract/fixture/DOM and frozen regression suite passed 78/78.
One live frozen-Development-runtime Judge smoke passed with a valid structured
decision. Mechanical source-unverifiable and synthetic invalid live executions
both bypassed the Judge. Browser DOM smoke loaded the existing page and rendered
the Stage 5 failed/limitation state without console errors.

### Documented limitations

- Track A end-to-end performance remains constrained by Retrieval and Evidence
  Resolution.
- Track B remains an approved-span diagnostic projection, not a complete
  known-video Builder/Selector replay.
- Semantic Judge latency remains high; the 11.996-second smoke does not replace
  the prior 75–89-second observed latency evidence.
- No deployment proxy configuration exists in the repository; production proxy
  timeout must be checked by the deployer.
- Browser smoke used an empty temporary corpus for UI/error-state inspection;
  formal evidence rendering is covered by fixture/DOM tests.
- The repository-wide suite has 1371 passes and 9 unrelated historical
  hash/state failures, plus one pre-existing test collection dependency missing.
  Stage 5 focused tests and affected frozen regressions have no failures.

Frozen components were not changed. Frozen Evaluation was not accessed. No
Final Answer, Agentic Search, Memory, Harness, or asynchronous task system was
added.

Pre-Frozen Checklist has not started. Stage 5 can be closed and this Session can
be closed.

---

## 一、开始集成前完成的审计

先审计并确认了现有应用已经具备可复用的主体结构：

- FastAPI 应用工厂和现有路由结构；
- `Application` 服务组合方式；
- 产品搜索 API `/api/search`；
- 现有搜索页 `/search`；
- `SearchOrchestrator` 及其 Search Trace；
- `EvidenceSearchService.search_library(...)`；
- `SearchCandidateSet`、`EvidenceCandidateSet`、`EvidenceBundle`、
  `SufficiencyRequest`、`MechanicalGateDecision` 和
  `SufficiencyDecision` 等正式合同；
- 现有 Jinja、原生 JavaScript 和 CSS 前端；
- 现有应用日志目录和测试框架。

因此没有新建 Web Framework、独立前端、数据库、任务队列、Agent
Orchestrator 或可观察性平台。

同时检查了正式冻结资产的完整性，包括：

- Candidate Builder；
- Deterministic Fine Selector；
- Evidence Identity Contract V1；
- Mechanical Gate v1-r1；
- `SufficiencyRequest` / `SufficiencyDecision` 合同；
- Semantic Judge 实现、Prompt、Policy 和最终 Freeze Seal。

Stage 5 没有访问 Frozen Evaluation，也没有为接线而改变冻结组件的行为。

## 二、Minimal API 与服务接线

### 1. 新增薄编排服务

新增 `src/shiliu/stage5.py`，主要包含：

- `Stage5PipelineRequest`：在现有 Product Search Request 基础上只增加
  `query_language`；
- `Stage5PipelineService`：按冻结顺序调用现有组件；
- `FrozenSemanticJudgeAdapter`：只负责调用已经冻结的 Semantic Judge
  transport；
- `Stage5IntegrationError`：承载有类型的集成错误。

该服务没有增加 Query Rewrite、新排序、新过滤、证据补选、Prompt 改写、
Final Answer 或 Agent Loop。

### 2. 正式运行链路

集成后的正式顺序为：

```text
V3 Search / Auto Retrieval
→ SearchCandidateSet
→ stage3b-acronym-w3.5-v1
→ v3.5-deterministic-fine-selector-v1
→ EvidenceBundle v1
→ mechanical-gate-v1-r1
→ frozen Semantic Sufficiency Judge
→ SufficiencyDecision v1
```

明确没有把以下实验版本接入正式链路：

- `stage3b-adaptive-swap-w3.5-v1`
- `v3.5-deterministic-fine-selector-v2`

### 3. 应用服务装配

在现有 `Application` 中惰性创建 `Stage5PipelineService`，并复用：

- 当前数据库；
- 当前 Artifact Store；
- 当前 `EvidenceSearchService`；
- 当前应用日志目录。

正式接线使用：

```text
authority_mode = live_current_exact_replay
runtime_corpus_identity = shiliu-live-current
```

这意味着现在网页搜索读取的是拾流当前已同步、已建立索引的收藏内容，不是
之前测试用的 snapshot/fixture。它也不是每次搜索时临时请求一次哔哩哔哩：
远端收藏先由同步任务更新到本地，搜索再查询本地当前库。

### 4. 新增 API

在现有 FastAPI 应用中增加：

- `POST /api/evidence-sufficiency`
- `GET /api/evidence-sufficiency/traces/{trace_id}`

执行耗时链路时，路由使用现有框架的线程卸载能力，未建立新的大型异步任务系统。

## 三、Mechanical Gate 与 Semantic Judge 路由

路由保持冻结语义：

| Mechanical Gate 状态 | 是否调用 Semantic Judge | 返回行为 |
|---|---:|---|
| `judge_eligible` | 是 | 返回冻结 Judge 的四态语义判断 |
| `source_unverifiable` | 否 | 保留机械终态，并写明 bypass reason |
| `invalid` | 否 | 保留机械终态，并写明 bypass reason |

机械状态与语义状态没有混在一起。尤其是：

- `source_unverifiable` 不会伪装成 Semantic Judge 的 `unverifiable`；
- `invalid` 不会伪装成 `insufficient`；
- Provider、超时或结构化输出失败不会伪装成任何语义判断结果。

Semantic Judge 保持冻结配置：

```text
provider: openai-codex-cli
model: gpt-5.6-terra
temperature: 0
policy: v3.5-semantic-sufficiency-policy-v1
```

只有 `judge_eligible` 才会调用 Judge。合法结果仍是：

- `sufficient`
- `partial`
- `insufficient`
- `unverifiable`

## 四、API 聚合响应

Stage 5 API 聚合但不改写正式输出，返回：

- `request_id`、`trace_id` 和原始 Query；
- 完整 `SearchCandidateSet` 及数量摘要；
- `EvidenceCandidateSet` 摘要；
- 正式 `EvidenceBundle`；
- 独立的 Mechanical Gate 结果；
- 独立的 Semantic Sufficiency 结果或 bypass 信息；
- 所有组件版本；
- 各阶段延迟；
- warnings 和 typed errors；
- `final_answer_generated: false`。

Evidence 展示投影保留：

- Evidence ID；
- Video ID 和可用标题；
- Segment IDs；
- 开始、结束时间；
- 权威字幕原文；
- Source Language / Source Type；
- Source Identity / Version；
- Selector Method。

Sufficiency 展示保留：

- Status；
- Supported Aspects；
- Missing Aspects；
- Conflicts；
- Reason Codes；
- Confidence；
- Evidence IDs Used；
- Policy Version；
- Trace ID。

没有为了 UI 生成不存在的字幕、时间戳、证据文本或 Reason Code。

## 五、Minimal UI

Stage 5 没有新建前端应用，而是在现有 `/search` 页面中加入一个可选入口：

```text
判断证据充分性（约 1–3 分钟）
```

未勾选时仍请求普通搜索 `/api/search`；勾选后请求
`/api/evidence-sufficiency`。

UI 新增或补齐了：

- Query；
- Processing / Completed / Failed；
- Current Stage；
- Total Latency；
- Trace ID；
- EvidenceBundle 的证据原文和时间范围；
- Evidence ID、Segment IDs、来源与 Selector；
- Mechanical Gate 状态和 Reason Codes；
- Semantic Judge 四态结果；
- Supported / Missing / Conflicts；
- Confidence、Evidence IDs Used、Policy Version；
- End-to-End Trace 阶段列表；
- 有类型的集成错误；
- “只判断现有证据是否充分，不生成最终答案”的明确限制说明。

等待阶段明确显示：

```text
retrieval
→ candidate builder
→ fine selector
→ gate
→ semantic judge
```

前端 DOM 全部使用安全节点和 `textContent` 构造，没有用不受控
`innerHTML` 注入证据内容。

## 六、End-to-End Trace

新增 Root Trace 合同：

```text
v3.5-stage5-root-trace-v1
```

每个请求都有：

- Trace ID；
- Request ID；
- Query Hash；
- 开始与结束时间；
- Total Latency；
- Final Pipeline Status。

固定阶段为：

1. `retrieval`
2. `candidate_builder`
3. `fine_selector`
4. `mechanical_gate`
5. `semantic_judge_or_bypass`

每个阶段记录：

- Stage Name；
- Component Version；
- Input / Output Hash；
- Status；
- Start / Complete Time；
- Latency；
- Retry Count；
- Error Type；
- Parent Trace ID。

Judge Span 额外记录：

- Provider 和 Model；
- Temperature；
- Prompt / Policy Version；
- Parse Status；
- Evidence IDs Used；
- Raw Response Hash。

不会持久化 Raw Response、系统密钥、Cookie、凭据或模型私有推理过程。

Trace 以 JSON 原子写入现有日志树：

```text
<logs_dir>/stage5_traces/<trace_id>.json
```

并可通过 Trace API 回读。

## 七、长延迟和错误处理

Stage 4B 已观察到的 Judge 最大延迟是 89.173 秒。Stage 5 使用 180 秒
Provider Timeout，高于该最大值，并保留一次冻结重试策略。

前端没有设置会过早中断 Judge 的固定短超时，而是展示明确 processing 状态。
仓库中没有生产部署代理配置，所以生产环境的反向代理超时仍需由部署者确认。

错误类型明确区分为：

- `input_validation_error`
- `retrieval_or_resolution_error`
- `mechanical_invalid`
- `source_unverifiable`
- `judge_timeout_or_provider_error`
- `structured_output_error`
- `internal_integration_error`

Provider、Timeout 和 Parse 错误不会被错误映射成
`insufficient` 或 `unverifiable`。

## 八、测试、Live Smoke 与冻结

### 正式 Stage 5 验证

- Contract / Fixture / DOM / Frozen Regression：78/78 通过；
- Python compile：通过；
- JavaScript syntax check：通过；
- `git diff --check`：通过；
- Live `judge_eligible`：通过并得到合法结构化结果；
- Live `source_unverifiable`：通过，Judge 调用数为 0；
- Synthetic `invalid`：通过，Judge 调用数为 0；
- Browser DOM smoke：页面和控制项正常加载，错误/限制状态正常展示，
  console error 为 0。

正式 live judge smoke：

```text
case: PQS_V1_Q003
status: insufficient
model: gpt-5.6-terra
latency: 11,996 ms
retry_count: 0
parse_status: valid
```

仓库级回归当时为 1371 passes、9 个与 Stage 5 无关的历史
hash/state failures，以及一个既有的测试收集依赖缺失。Stage 5 focused
tests 和受影响的冻结回归没有失败。

### Freeze Seal

生成了 `STAGE5_INTEGRATION_FREEZE_SEAL.json`，记录：

- API、Service Adapter、UI、Trace 和 Test Hash；
- 正式冻结组件 Hash；
- Semantic Judge Final Freeze Seal Hash；
- Timeout 数值和依据；
- Fixture Hash；
- Live Smoke Trace IDs；
- Gate 路由断言；
- `Frozen_Evaluation_accessed: false`；
- `Final_Answer_generated: false`；
- `Agentic_Search_added: false`。

该 Seal 描述的是 2026-07-27 正式关闭时的文件快照。下面记录的产品修复发生在
Seal 之后，因此不能把当前 UI 文件 Hash 与原 Seal 混为同一个冻结快照。

---

## 九、Stage 5 完成后的产品运行修复

这些修改没有改变冻结的 Candidate Builder、Selector、Mechanical Gate 或
Semantic Judge 行为。

### 1. 恢复当前收藏内容的实时搜索

针对网页封面消失、搜索任何内容都没有结果的问题，完成了：

- 将服务运行所需内容迁移到 LaunchAgent 可以稳定访问的应用数据目录；
- 更新数据库中的绝对内容路径和运行配置；
- 保留原内容，并建立迁移前备份；
- 重新同步当前收藏；
- 重建 lexical 和 dense 搜索索引；
- 恢复 Web 服务和每小时同步任务；
- 验证 `/search` 使用当前本地收藏库，不再依赖 Stage 5 测试 snapshot。

当次恢复结果为：

```text
current items: 151
discovered / processed: 6 / 6
failed: 0
lexical / dense indexed units: 1602 / 1602
```

### 2. 防止临时网络故障破坏现有同步状态

修正了同步生命周期：

- 可重试的来源网络错误进入可恢复的 `cooldown`，而不是直接变成永久
  `unavailable`；
- 当数据库已经存在来源但它们当前暂停、需要认证或暂时不可用时，不再错误回退到
  legacy sync；
- 该保护避免一次临时失败把现有索引错误地同步成空库；
- 新增了“现有不可用来源不触发 legacy sync”和“可重试失败进入 cooldown”
  的回归测试。

这保留了后续自动同步能力：来源恢复后，定时同步仍会继续使用当前收藏来源。

### 3. UP 主名称由精确匹配改成包含匹配

后端过滤由：

```sql
lower(u.uploader) = lower(?)
```

改为：

```sql
instr(lower(u.uploader), lower(?)) > 0
```

效果：

- 输入完整名称仍能匹配；
- 输入名称的一部分也能匹配；
- 英文 ASCII 大小写可模糊；
- UI 标签更新为“UP 主（名称包含）”；
- 增加普通搜索和 Stage 5 证据充分性入口的对应回归覆盖。

### 4. 搜索结果封面居中

修正搜索结果卡片封面：

- 封面不再固定贴在左上角 `(0, 0)`；
- 水平和垂直中心都对齐到卡片左侧封面区域中点；
- 根据图片 `naturalWidth` / `naturalHeight` 通用识别竖屏封面；
- 竖屏封面仍放在固定大小的左侧区域，不改变搜索结果卡片尺寸；
- 图片加载失败时继续显示 `NO COVER` fallback；
- 更新静态资源版本，避免浏览器继续使用旧 CSS/JS 缓存。

### 5. 内容流竖屏和黑边封面处理

内容流保持固定长方形封面区域，不因竖屏图改变卡片尺寸。

处理策略：

- 竖屏封面以中心为锚点使用 `object-fit: cover`；
- 允许裁掉上下边缘，不把完整竖屏图缩成很小的一条；
- 封面区域未被图片覆盖时，背景颜色与卡片一致；
- 对“素材本身已经带左右黑边”的图片使用通用像素算法检测；
- 在浏览器中把图片缩采样为 48×27，计算各列亮度，寻找暗色侧栏与中间有效内容
  的边界；
- 识别成功后按有效内容宽度计算有限缩放，居中裁掉素材自带黑边；
- 算法对所有内容流封面统一运行，不是对单张图片人工设置规则；
- Canvas 无法读取时安全回退到普通居中裁切，不影响卡片展示。

### 6. 后续针对性验证

在不同修改阶段分别运行了针对性回归：

- 搜索和同步恢复相关：18/18；
- UP 主包含匹配相关：31/31；
- 搜索结果与内容流封面相关：27/27。

同时对当前 Web 页面和搜索请求进行了实际运行检查。按用户要求，最后一轮封面
调整没有再做截图验收。

---

## 十、最终产物

正式 Stage 5 产物：

- `STAGE5_EXISTING_INTEGRATION_AUDIT.md`
- `STAGE5_API_INTEGRATION_CONTRACT.md`
- `STAGE5_TRACE_CONTRACT.md`
- `STAGE5_INTEGRATION_TEST_RESULTS.json`
- `STAGE5_LIVE_SMOKE_RESULTS.json`
- `STAGE5_INTEGRATION_FREEZE_SEAL.json`
- `STAGE5_FINAL_CLOSEOUT.md`
- `STAGE5_FINAL_CLOSEOUT.json`

核心实现与测试：

- `src/shiliu/stage5.py`
- `src/shiliu/app.py`
- `src/shiliu/web.py`
- `src/shiliu/templates/search.html`
- `src/shiliu/static/search.js`
- `src/shiliu/static/search.css`
- `tests/test_stage5_integration.py`
- `tests/test_search_page.py`

后续产品修复涉及：

- `src/shiliu/retrieval/service.py`
- `src/shiliu/sync.py`
- `src/shiliu/static/app.js`
- `src/shiliu/static/library.css`
- `src/shiliu/templates/base.html`
- `tests/test_database_and_sync.py`

正式 Closeout 记录的输出 Hash：

```text
STAGE5_EXISTING_INTEGRATION_AUDIT.md
13c138ef087f82e01dffd55cf534a17218c5e5c9bb4aad1c0fb58587fa2b9186

STAGE5_API_INTEGRATION_CONTRACT.md
b9093379015fd88af1e3016fb72e5f873ebae6f5d5bde7cd0a341d3b6073ed2e

STAGE5_TRACE_CONTRACT.md
4ccd0716bda3ea40f5d3ea90829d766969e8e0f0fb53ff72137e2e09a78bde8c

STAGE5_INTEGRATION_TEST_RESULTS.json
8c3bf69e1e3bc60030ff81297c79ce91df2ab60fb49975111f663364f50b84db

STAGE5_LIVE_SMOKE_RESULTS.json
55b36c8d6b4969ed43a8433ece38b7b31d4ebfc56fa5cab41932c968c7f1c83e

STAGE5_INTEGRATION_FREEZE_SEAL.json
c65b77dfb8fbce546e8054ec9d57af682db9b8be1c725f1d2b138326ee9d9461

STAGE5_FINAL_CLOSEOUT.md
062fd7c8d000a65014af60274663e86693313b39aa5b90cae599a470f5eaa62a
```

## 十一、当前边界

- Stage 5 只判断现有 Evidence 是否充分，不生成最终答案；
- 搜索数据来自当前已同步到本地的收藏库，不是每次搜索都实时访问远端；
- Track A 仍受 Retrieval / Evidence Resolution 限制；
- Track B 仍是 approved-span diagnostic projection，不是完整 known-video
  Builder / Selector replay；
- Semantic Judge 本身仍可能需要约 1–3 分钟；
- 原 Stage 5 状态是
  `formally_closed_pass_with_limitations`；
- 原定下一阶段是 `Pre_Frozen_Checklist`，Stage 5 closeout 本身没有直接启动它。
