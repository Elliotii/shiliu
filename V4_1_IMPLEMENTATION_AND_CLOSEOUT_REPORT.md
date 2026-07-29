# Shiliu V4.1 Implementation and Closeout Report

```yaml
document_role: v4_1_implementation_and_closeout
date: 2026-07-30
branch: codex/v4.1-hardening
baseline_commit: cbf264be2571c3d62775c064445de8a1ba17880a
v4_1_status: complete
provider_configuration: baseline_only_unchanged
legacy_h0_dual_configuration_e2e_executed: false
formal_provider_or_runtime_configuration_changed: false
```

## 1. Outcome

V4.1 按 `V4_1_CONTINUATION_EXECUTION_PROMPT.md` 的 Phase 0–7 顺序完成：

1. 更正 H0 报告口径并实现 crash-safe 分阶段 E2E harness；
2. 完成 Fast Before、H1 和 Fast After；
3. 完成 Deep Before、H2 和 Deep After；
4. 完成 H3 全套验证、状态/决策同步和本 Closeout。

没有调用 Thinking Off、Reduced Reasoning、新 Provider 或旧 H0 双配置 E2E；
没有修改 `max_tokens`、Retrieval、Context Selection、Ask Contract、Citation
Identity、Source Authority、Tool、Budget、Graph 拓扑或产品入口。

## 2. Phase 0 — Crash-safe E2E Harness

新增 continuation 专用薄 runner：

- 每个 Run 前原子持久化 `in_flight` WAL；
- 每个 Run 使用 Phase、Case、Mode、Code-state、Manifest、Query Hash、
  Corpus、Source Code 和 Provider Configuration Identity；
- Provider 返回后立即保存有界指标；Review 前和 Review 中使用显式状态；
- 任意未知 `in_flight`、Provider 后私有对象丢失或 Review 中断均阻断恢复，
  不自动重放；
- 完成并审阅的 Run 不重复调用；
- 开始前按 Phase 与全 Campaign 最坏情况预留 Logical/HTTP 上限；
- 每个 Response Citation 按当前 Source Version、Timeline、Segment、
  Stable Citation ID、Quote 和 Jump URL 完整重建验证；
- 完整 Answer 与 Evidence 只在进程内真实 TTY 显示并审阅；
- Checkpoint 只保留指标、Citation ID、四维评分、有界理由和 Hash。

四个 Checkpoint 均位于 Git Ignore 的 `.h0/`、权限 `0600`，最终所有 Run
状态均为 `review_complete`，没有未知 `in_flight`。

故障注入覆盖：

- Provider 返回后、结果 Checkpoint 前崩溃；
- Provider 结果 Checkpoint 后、Review 前崩溃；
- Review 中崩溃；
- 完成 Run 去重；
- Campaign Identity 冲突；
- 私人 Query、Answer、Evidence 和 Review Reason 扫描；
- Phase/总调用上限预留；
- 连续两次 Provider Failure Fail-fast。

Checkpoint 未持久化私人 Prompt、Answer 正文、Transcript/Navigation 正文、
API Key 或 Raw Provider Response。隐私 Key 扫描和正文字符串扫描均通过。

## 3. H1 — Fast Answer Hardening

### 3.1 Accepted implementation

共享 Grounded Answer Boundary 现在明确：

- 有限样本不能证明全库/全称命题；
- 一个权威当前字幕直接反例可以否定 “always” 主张，形成带 Citation 的有限
  `partial` 结论；
- Limitation 必须说明这不是完整全库审计；
- Cross-video 只比较当前 Transcript Evidence 支持的材料；
- 缺少全库覆盖不单独否定有用的有限综合；
- Answer Block 应材料性、简洁、不重复；规范化后完全重复 Block 触发现有一次
  Repair。

没有新增 Runtime Judge、Sufficiency Pipeline、Reranker、Compaction、Router
或依赖。

### 3.2 Fast paired evidence

| Case | Before | After | Quality result |
| --- | --- | --- | --- |
| `no_evidence_quantum_protocol` | `insufficient/answer_ready`, 21.826s | `insufficient/answer_ready`, 15.803s | 四维均 pass；No-evidence 未回归 |
| `single_topic_context_compression` | `partial`, 58.109s；usefulness/coverage partial | `partial`, 67.259s；四维均 pass | 从重复、覆盖有限改善为两块有界说明 |
| `partial_universal_claim` | `partial`, 42.999s | `partial`, 59.584s | 直接反例、Citation、有限范围和非全库 Limitation 均 pass |
| `cross_video_context_management` | `partial`, 64.522s；supported/useful | `insufficient/provider_error`, 94.336s | 一次 Provider Failure；诚实 fail-closed，未 Repair、未重跑 |

Fast Before/After 均为 4 Run、8 Logical、8 HTTP、0 Repair。Before 总延迟
187.455s，After 总延迟 236.981s；After 的增量主要受单次 94.336s Provider
Failure 影响。Checkpoint 没有保留逐 Provider 调用延迟分布，因此不能把
Provider/非 Provider 延迟进一步拆分，也不作因果声称。

Cross-video After 是一次明确 Provider Failure，不是 Schema/Citation/
Supportedness 输出退化；前一相同 Corpus/Query 的 Before 已生成当前 Evidence
支持的有限综合，后续不同 Query 成功恢复，故未触发“连续两次 Provider
Failure”停止条件。该 Query 没有额外 Run、重采样或本地伪造结果。

## 4. H2 — Deterministic Deep DecisionView

### 4.1 Accepted implementation

正式路径为：

```text
DeepRuntimeState
→ DecisionViewProjector
→ existing AgentAction Provider
```

DecisionView 保留 Original Query、优先/有界 Open Questions、有界 Resolved
Questions、Latest Action/Observation、Evidence Inventory、合法 Window
Anchors、Previous Query/Visited 摘要、精确剩余预算和现有静态
Policy/Schema。

模型投影移除：

- 每个 Evidence 的完整 `segment_ids`；
- Navigation `description` 与重复长 `summary_sections`；
- 最近 60 个逐项 `visited_segment_ids`。

完整 Runtime State、Evidence Spans、Visited Sets、Events 和 Guard 输入未删除。
Window Anchor 由完整 Runtime Evidence 的中间合法 Segment 确定性投影，Graph
Guard 仍对完整 Segment Set 验证。

脚本化高成本 State 测试证明新动态 Payload 不超过旧形态 60%；实际 E2E 的累计
Prompt Tokens 降幅更大。

### 4.2 Deep paired evidence

| Case | Before | After | Prompt Token change | Flow and quality |
| --- | --- | --- | --- | --- |
| `contextual_tool_failure` | 29,605 tokens；3 rounds；2 tools；63.400s | 13,128 tokens；4 rounds；3 tools；42.436s | -55.7% | Replanning/coverage 保留；四维从 coverage partial 提升为全 pass |
| `cross_video_context_management` | 36,149 tokens；3 rounds；2 tools；78.891s | 15,237 tokens；4 rounds；4 tools；71.205s | -57.9% | Before 误把同源片段描述为两视频；After 使用不同来源并四维全 pass |

两条累计 Prompt Tokens 从 65,754 降至 28,365（-56.9%），总延迟从
142.290s 降至 113.641s（-20.1%）。Logical/HTTP 从 8/8 增至 10/10，是因为
两条 After 各多一次材料性的 Replanning/Tool Round，而不是 Retry；Repair
仍为 0。

由于 Checkpoint 只保留每 Run 累计 Prompt Tokens 与 Usage Row Count，报告用
“累计值”和“每 Logical Invocation 平均值”而非伪造逐 Round 分布：

- Before 平均约 7,401 / 9,037 Prompt Tokens per logical invocation；
- After 平均约 2,626 / 3,047 Prompt Tokens per logical invocation。

Navigation→Transcript→Window/Replan→Finish、Observation 后 Action 变化、
Repeated Query/Segment、No-new Evidence、Round/Tool/Deadline Guard、
Stable Citation 和 Source Version Revalidation 均由定向测试保持。

## 5. Provider Envelope and Recovery

```yaml
authorized:
  product_e2e_runs_max: 12
  logical_provider_invocations_max: 56
  transport_http_attempts_max: 112
actual:
  product_e2e_runs: 12
  logical_provider_invocations: 34
  transport_http_attempts: 34
  thinking_off_calls: 0
  new_fixed_replay_calls: 0
  automatic_resampling: false
  answer_repairs: 0
checkpoint_terminal_state:
  fast_before: complete
  fast_after: complete
  deep_before: complete
  deep_after: complete
  unknown_in_flight: 0
```

本次唯一 Provider 事件是 Fast After Cross-video 的一次非连续失败。没有
Checkpoint 恢复、重复调用、Identity 冲突、上限不足或私人正文落盘事故。

数值上未使用 22 Logical / 78 HTTP，但本授权是一次性固定 12-Run 矩阵；矩阵
完成后这些不是可继续调用的余额。任何新 Provider 调用仍需 Main Session 新授权。

H0 首次事故的未知历史消耗继续只在
`V4_1_H0_INVESTIGATION_REPORT.md` 单独披露，没有改写为零，也没有计入本矩阵。

## 6. Verification

```yaml
directed_h0_h1_h2:
  result: 68_passed
product_regression:
  result: 61_passed
  coverage:
    - /ask
    - /search
    - Fast
    - Deep
    - Evidence Card
    - Bilibili timestamp jump
default_full_suite:
  result: 1498_passed_4_deselected
  warning: existing_Starlette_httpx_deprecation
compileall: passed
pip_check: no_broken_requirements
pip_warning: existing_user_cache_not_writable
node_ask_js: passed
node_search_js: passed
git_diff_check: passed
```

首次直接执行默认 Pytest 时缺少仓库 `PYTHONPATH`，只在 collection 阶段产生
16 个路径导入错误，没有执行测试。使用项目既有的仓库导入环境重跑后完整通过；
该环境错误不计为产品测试失败，但在此披露。

## 7. Formal Files

Runtime：

- `src/shiliu/ask/answer.py`
- `src/shiliu/ask/validation.py`
- `src/shiliu/ask/deep/decision.py`

Harness/Test：

- `scripts/run_v4_1_continuation.py`
- `tests/test_v4_1_continuation.py`
- `scripts/run_v4_1_h0_investigation.py`
- `tests/test_v4_1_h0_investigation.py`
- `tests/test_v4_fast_ask_api.py`
- `tests/test_v4_deep_search.py`
- `.gitignore`

Authority/Closeout：

- `V4_1_H0_INVESTIGATION_REPORT.md`
- `V4_MASTER_STATE.md`
- `V4_DECISION_LEDGER.md`
- `V4_1_IMPLEMENTATION_AND_CLOSEOUT_REPORT.md`

没有创建独立 H1/H2 Prompt、Gate、Readiness、Eval Platform 或多 Reviewer
文件。

## 8. Acceptance Recommendation

```yaml
recommend_main_session_accept: true
recommend_main_session_push_after_review: true
remaining_blocking_finding: none
```

建议 Main Session 接受 V4.1 H1/H2 正式改动和 crash-safe E2E 证据，并在复核
本地 Commit 后 Push。新的 Provider Replay、E2E、配置调整、V5 或 Deferred
能力不包含在本 Closeout 授权中。
