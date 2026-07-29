# Shiliu V4.1 H0 Investigation Report

```yaml
document:
  name: V4_1_H0_INVESTIGATION_REPORT
  date: 2026-07-30
  branch: codex/v4.1-hardening
  baseline_commit: cbf264be2571c3d62775c064445de8a1ba17880a
  status: h0_closed_continuation_execution_authorized

prior_provider_replay_attempt:
  authorized: true
  campaign_started: true
  campaign_reached_quality_review: true
  bounded_trial_rows_persisted: 0
  quality_reviews_completed: 0
  exact_logical_trials_completed: unverified_after_process_loss
  exact_logical_provider_invocations_completed: unverified_after_process_loss
  exact_transport_http_attempts_completed: unverified_after_process_loss
  result_status: unusable_incomplete_instrumentation_failure

crash_safe_checkpoint_hardening:
  authorized: true
  completed: true
  provider_calls_during_hardening: 0
  end_to_end_calls_during_hardening: 0
  formal_runtime_changes: 0
  status: validated_by_complete_fixed_replay

new_fixed_provider_replay:
  authorized: true
  model: deepseek-v4-pro
  status: complete
  matrix_complete: true
  logical_trials_completed: 24
  logical_provider_invocations_completed: 26
  transport_http_attempts_completed: 26
  quality_reviews_completed: 17
  formal_runtime_changes: 0

end_to_end:
  authorized: true_under_v4_1_continuation_prompt
  legacy_h0_dual_configuration_runs_completed: 0
  continuation_baseline_only_runs_completed: 12
  continuation_status: complete
```

## A. Outcome

H0 的全部非 Provider 工作已经完成：

- 冻结 Baseline 与权威文档复核；
- Provider 配置组合 Request Body Dry-run；
- 四个 Fixed Request 的确定性生成、Hash 和三 Trial 稳定性检查；
- Trial 轮转、Usage、Repair、Retry、Error 和 Campaign Fail-fast
  Instrumentation；
- Final Structured Draft 与 Citation ID 的进程内保留能力；
- 中位延迟、最差质量/失败和输出分歧的轻量人工复核选择能力；
- Citation ID 到当前完整 Source Version Evidence 的复验/重建能力；
- Scripted Agent Action + 真实本地 Tool 的 Deep Payload Audit；
- 六 Case 的真实本地 Fast Context Diagnostics；
- 定向、默认全套、Compileall、Pip 和 Diff 检查。

第一次授权 Campaign 因质量复核 TTY 打开方式错误而丢失进程内结果；其
Logical Trial、Logical Provider Invocation 和 HTTP Attempt 消耗继续单独披露为
未知，未改写为零，也没有混入新矩阵。

Main Session 随后授权了 Crash-safe Bounded Checkpoint 修正，并在修正、定向
测试、`.h0/` Git 忽略验证和真实 TTY Preflight 完成后，明确授权一套新的
Fixed Provider Replay。新 Campaign 已完成：

```yaml
h0_status: h0_fixed_replay_complete_e2e_separately_authorized_under_continuation
matrix_complete: true
logical_trials: 24
logical_provider_invocations_including_repair: 26
transport_http_attempts: 26
quality_reviews: 17
provider_failures: 1
automatic_resampling: false
```

两个配置组合都暴露出质量问题。`thinking_off` 组合延迟显著更低，但在有充分
Evidence 的 Request 上多次错误返回 `insufficient`；Baseline 组合质量相对更好，
仍在 Universal/Partial-support Request 上全部错误拒答，并有一次
`output_budget_exhausted`。因此 H0 不支持采用 Thinking Off，也不支持修改正式
Provider 配置或 Runtime。

H0 本轮没有执行 End-to-End。其后 Main Session 已通过
`V4_1_CONTINUATION_EXECUTION_PROMPT.md` 对分阶段、Baseline-only 的 Paired E2E
提供独立有界授权；该授权不追溯改变 H0 调用事实。

H0-B 已提供足够证据建议 H2 实施 Deterministic DecisionView。H0-C 没有提供
足够证据触发 Reranker、Diversity-aware Selector 或 Context Compaction。

## B. Baseline and Scope

### Baseline

启动时核验：

```text
initial_branch: codex/v4-main
HEAD: cbf264be2571c3d62775c064445de8a1ba17880a
origin/codex/v4-main: cbf264be2571c3d62775c064445de8a1ba17880a
```

初始工作区只包含 Main Session 已披露的未跟踪文件：

```text
SHILIU_V4_WEBGPT_PROJECT_HANDOFF.md
V4_1_H0_INVESTIGATION_PROMPT.md
```

二者均保留且未修改。随后从冻结 Commit 创建：

```text
codex/v4.1-hardening
```

### Inputs read in full

- `V4_1_H0_INVESTIGATION_PROMPT.md`
- `SHILIU_V4_1_RUNTIME_AND_CONTEXT_HARDENING_PLAN.md`
- `V4_MASTER_STATE.md`
- `V4_DESIGN_PROPOSAL.md`
- `V4_DECISION_LEDGER.md`
- `V4_G1_IMPLEMENTATION_REPORT.md`
- `V4_G2_IMPLEMENTATION_REPORT.md`
- `V4_G3_IMPLEMENTATION_REPORT.md`

没有读取或恢复 V0–V3.5 Case 级 Eval Gold、Target Answer 或失败详情。

### Files changed

- `.gitignore`
- `scripts/run_v4_1_h0_investigation.py`
- `tests/test_v4_1_h0_investigation.py`
- `V4_1_H0_INVESTIGATION_REPORT.md`

正式 Fast、Deep、Provider、Prompt、Tool、Graph、Budget、Ask Contract 和 V4
状态文件均未修改。没有实施 H1 或 H2 行为。

## C. H0-A Provider Latency Attribution

### C.1 Fixed Request generation

四类 Request 使用临时 SQLite Snapshot、当前本地 Qwen Retrieval、三个确定性
Query（原 Query + 两个非 Gold Scripted Rewrite）、当前 Evidence
Materialization、`fuse_evidence()`、`TranscriptContextBuilder` 和当前
`_answer_messages()` 生成。

Capture 在网络调用前完成。完整 Messages、Evidence Context 和字幕只存在于
当前进程，没有写入仓库或结果文件。

| Request | Category | Request SHA-256 | Message chars | Context chars | Allowlist |
|---|---|---|---:|---:|---:|
| `no_evidence_quantum_protocol` | No-direct-support | `b28bf49e4ca29ff58eeeb39772beb1b50327bda95b3f2c29cda63a280d42c657` | 18,699 | 16,212 | 12 |
| `single_topic_context_compression` | Single-topic | `1787e28d26639ac73c1ec38816d84f8730e3b2ba2f0222cde8a8b5f07c639483` | 18,740 | 16,257 | 12 |
| `cross_video_context_management` | Cross-video | `1bb97a0ed2ccbe9d0df9f441b495ba2b865c80f3c8fa1924c6fdfc8576582a63` | 18,480 | 15,998 | 12 |
| `partial_universal_claim` | Universal/Partial-support | `60f7fd21031f7b2b5973498822a5c47e6f50e6ef4cd0da54dc508d1f1050b686` | 18,618 | 16,127 | 12 |

每个 Request 的三次 Trial Hash Dry-run 均逐字相同。

No-direct-support Case 不是零 Span Short Path；它包含有效 Retrieval 样本，但
没有直接支持虚构协议的字幕 Evidence，因此会真实进入 Grounded Answer。

### C.2 Configuration-combination comparison

本实验比较的是两个完整配置组合，不是单变量实验：

| Configuration | Thinking | Reasoning effort | Temperature |
|---|---:|---|---|
| `baseline` | enabled | high | Provider default / field omitted |
| `thinking_off` | disabled | null / field omitted | 0 |

四个 Request 的 Dry-run 均证明：

```yaml
non_configuration_request_body_identical: true
configuration_fields_only:
  - thinking
  - reasoning_effort
  - temperature
```

因此 Replay 可以比较两个配置组合，但结果不能声称只归因于 Thinking。Thinking、
Reasoning Effort 和 Temperature 同时变化；可能的服务端交互也无法被当前小样本
分离。

`reduced_reasoning` 状态：

```yaml
status: unavailable_in_current_provider_contract
```

当前 Adapter 只接受 `high|max`；`low|medium` 会以
`bad_provider_config` 确定性拒绝。H0 没有扩展正式 Adapter，也没有把
`high → max` 伪装成 Reduced Reasoning。

### C.3 Trial order

每个 Request 的执行顺序冻结为：

```text
Round 1: baseline → thinking_off
Round 2: thinking_off → baseline
Round 3: baseline → thinking_off
```

没有 Sleep、额外重采样或失败补跑。

### C.4 In-process Trial and quality-review contract

每个 Trial 在 Campaign 进程内保留：

```yaml
private_in_process_only:
  - final GroundedAnswerDraft
  - final Citation IDs
  - fixed ContextBuildResult
  - current full TranscriptEvidenceSpan objects

serializable:
  - bounded measurement row
  - final draft hash
  - Citation IDs
  - quality scores
  - bounded reason summary
  - reason summary hash
  - full review material hash
```

质量复核按 `Request × Configuration` 分组：

1. 必审中位延迟 Trial；
2. 必审确定性风险最高或失败 Trial；
3. 若三个 Final Draft/Error 行为 Hash 不同，则三次全部审阅；
4. 完成评分后，以四维评分选择真正的最差质量/失败 Trial；
5. 同一个 Trial 可以同时拥有多个选择理由。

每次复核都从 Fixed Context 的 Citation Allowlist 出发，对每个 Citation ID
执行当前 `TranscriptEvidenceMaterializer.validate_current()`。该方法从当前
Source Version 重新加载 Segment，重算 Citation ID、Quote、Time 和 Jump URL，
并与完整 `TranscriptEvidenceSpan` 比较。复核不使用 500 字 Excerpt。

对 `insufficient` 或 Provider Failure，也重建全部 12 个允许 Citation，而不是
因 Final Draft 没有 Citation 就跳过 Evidence，从而可以审查是否存在可用但未答
内容。

四维记录：

```yaml
supportedness: pass | partial | fail
usefulness: pass | partial | fail
coverage: pass | partial | fail
status_honesty: pass | partial | fail
```

完整答案和完整 Evidence 只通过当前 TTY 供人工审阅，不写入 stdout 最终结果、
仓库或本报告。若理由摘要完整复制了某个 Answer Block 或 Evidence Span，公开
结果会用隐私占位说明替换正文，同时保留原始理由 Hash。

### C.5 Campaign fail-fast

Campaign 采用：

```yaml
consecutive_provider_failure_limit: 3
```

每次成功形成 Final Structured Draft 会把连续失败计数归零。达到连续三次
Provider Failure 后：

- 不再开始新 Trial；
- 不重采样；
- 保留所有已完成 Trial；
- 对已完成分组继续执行质量复核；
- 输出 `matrix_complete: false`；
- 输出 `completed_trial_count`、`completed_trial_ids` 和明确 Stop Reason。

该阈值是实验安全边界，不是生产熔断器，也没有接入正式 Runtime。

### C.6 Deterministic measurement readiness

已覆盖：

- Usage 嵌套字段和缺失字段保留 `null`；
- Cache Hit/Miss fallback；
- Completion/Reasoning Tokens；
- First-pass Schema、Repair Required/Succeeded；
- Provider Logical Call 与 Transport Retry 分离；
- Provider Error 保留；
- Finish Reason、Status、Block/Citation Count；
- Final Draft Hash 与 Citation ID；
- Campaign 完整/不完整状态；
- 不输出 API Key、Authorization Header、Messages、完整 Context 或 Raw
  Response。

### C.7 Current attribution

新 Replay 支持以下有界归因：

```yaml
latency_attribution:
  request_shape_effect:
    status: observed
    finding: baseline latency increased materially on answer-bearing requests
  reasoning_effect:
    status: configuration_combination_association_only
    caution: cannot_isolate_thinking
  completion_effect:
    status: strong_observed_association
    finding: longer completion/reasoning output coincided with higher latency
  repair_effect:
    status: mechanically_adds_a_second_logical_call_when_triggered
    observed_repairs: 2
    observed_configuration: thinking_off
  cache_effect:
    status: high_cache_hit_observed_but_causal_effect_unresolved
  transport_or_service_variance:
    status: one_output_budget_exhausted_no_transport_retry
  unresolved:
    - Provider service state
    - cache interaction
    - configuration interaction
    - completion length
    - reasoning token variance
```

两个配置同时改变 Thinking、Reasoning Effort 和 Temperature，因此不能把延迟、
Token 或质量差异只归因于 Thinking。小样本也不能分离服务端状态、Cache 与输出
长度的交互。

### C.8 Executed Replay matrix

用户授权并实际执行的冻结矩阵：

```yaml
fixed_requests: 4
configurations:
  - baseline
  - thinking_off
trials_per_request_configuration: 3
logical_trials: 24
max_logical_provider_invocations_including_repair: 48
current_transport_retry_per_logical_invocation: max_1
max_transport_http_attempts_worst_case: 96
campaign_fail_fast:
  consecutive_provider_failures: 3
  preserves_completed_trials: true
  marks_matrix_incomplete: true
actual:
  logical_trials: 24
  logical_provider_invocations: 26
  transport_http_attempts: 26
  automatic_resampling: false
  matrix_complete: true
```

这里的 48 是 Prompt 冻结的逻辑 Provider Invocation 上限；96 是把当前每个
Structured Invocation 最多一次 Transport Retry 展开后的理论 HTTP Attempt
上界。Retry 不增加 Logical Trial，也不允许额外重采样。

数据发送：

- 四条普通 Query；
- 当前本机收藏中每个 Fixed Request 约 16k 字符的有界 Transcript Evidence
  Context；
- Grounded Answer System Prompt；
- `GroundedAnswerDraft` JSON Schema；
- Citation Allowlist；
- 当前配置的 model/max tokens。

结果只进入默认 Git 忽略检查点和本报告中的有界行、评分、短理由和 Hash；没有
创建包含正文的独立结果文件。

### C.9 Authorized execution incident

执行顺序：

1. 第一次启动在读取 macOS Keychain 时被 Sandbox 拒绝；API Key 尚未读取，
   Provider 调用为 0；
2. 在受控权限下重新启动同一 Fixed Replay；
3. Campaign Provider 阶段返回并调用 `conduct_quality_reviews()`；
4. 第一次调用 `terminal_quality_reviewer()` 时，双向 `/dev/tty` 流创建失败；
5. 进程退出，未生成 stdout JSON，也未写入报告行、完整答案或字幕。

可证明边界：

```yaml
fixed_replay_authorized: true
provider_campaign_entered: true
campaign_returned_to_quality_review: true
quality_review_scores_completed: 0
full_draft_or_evidence_displayed_before_failure: false
full_draft_or_evidence_persisted: false
end_to_end_runs: 0
formal_runtime_changes: 0
```

`run_campaign()` 在完整矩阵和 Campaign Fail-fast 两种情况下都会返回，所以仅凭
进入质量复核不能证明具体完成数。进程没有落盘 Usage 或 Trial Rows，故以下值
必须保留为未知，而不是从约六分钟墙钟时间推测：

```yaml
logical_trials_completed: unknown
logical_provider_invocations_completed: unknown
transport_http_attempts_completed: unknown
matrix_complete: unknown
```

修复只作用于 H0 Runner：质量复核现使用独立的 `/dev/tty` 只读与只写流，不再
创建要求 seek 的双向流。新增测试以不可 seek 的 Input/Output Stream 驱动完整
四维评分，并完成一次真实 PTY、零网络冒烟测试。没有修改正式 Runtime。

### C.10 Crash-safe bounded checkpoint and recovery

本节修正也只作用于 H0 Runner。

#### Provider 调用前真实 TTY Preflight

CLI 在加载 API Key 或开始 Provider Trial 前，必须完成：

1. 分别以只读和只写方式打开真实 `/dev/tty`；
2. 验证两个流均为 TTY；
3. 向 TTY 写入一次随机 Challenge；
4. 从同一 TTY 读回完全相同的 Challenge；
5. 生成仅绑定当前 PID、登记在当前进程内的 `TTYPreflightProof`；
6. `run_live_replay()` 一次性消费 Proof，不能重复使用或手工构造替代。

`run_live_replay()` 没有当前进程有效 Proof 时直接拒绝。CLI 还会先检查独立
Replay 授权短语，未授权时不会要求 TTY Challenge。真实 PTY 冒烟验证：

```yaml
network_calls: 0
provider_calls: 0
tty_read_write_roundtrip: passed
proof_bound_to_current_process: true
challenge_persisted: false
challenge_hash_present_in_memory: true
```

新授权 Replay 启动时再次执行同一真实 TTY Challenge/Response Preflight，并在
读取 Keychain Key、创建第一个 `in_flight` WAL 或调用 Provider 前通过。Challenge
正文没有写入检查点或报告。

#### Per-Trial bounded write-ahead checkpoint

默认检查点路径：

```text
.h0/v4_1_fixed_replay_checkpoint.json
```

新授权 Replay 只使用该默认路径。执行前后均由
`git check-ignore -v --no-index` 验证命中 `.gitignore` 的 `/.h0/` 规则；文件
权限为 `0600`，完成态 SHA-256 为
`e8532f9d0815be6067d5654ea5371822801ad155bcb5d06663891dd4796b61e0`。

每次 Trial 的状态顺序：

```text
atomic in_flight WAL
→ Provider invocation
→ bounded Trial row
→ atomic completed Trial checkpoint
→ clear in_flight
```

`in_flight` 在 Provider 前原子落盘，并为该 Trial 预留最多 2 个 Logical
Invocation / 4 个 HTTP Attempt。Provider 返回后只写：

- Trial/Request ID 和 Request Hash；
- 配置组合；
- Usage、Latency、Repair、Retry、Error、Status 和 Count；
- Final Draft Hash；
- Citation IDs；
- Started Time 和 Sequence Index。

不写 Final Draft、Messages、Query、Model Context、Evidence Quote 或 Raw
Response。

写入采用：

```yaml
temporary_file_mode: "0600"
checkpoint_file_mode: "0600"
write_flush_fsync: true
atomic_replace: true
parent_directory_fsync: true
```

每次写入前递归拒绝私有字段名，并检查当前完整 Query、Prompt Message、
Transcript Evidence Quote 和 Answer Block Text 没有出现在序列化内容中。

#### Per-Request immediate review

执行单位改为一个 Request 的六个 Trial：

```text
6 interleaved configuration Trials
→ atomic trials_complete_review_pending
→ immediate in-process Citation reconstruction/review
→ atomic checkpoint after each captured score
→ atomic review_complete group
→ only then start next Request
```

每个 Review Checkpoint 仍只包含四维评分、有界理由摘要及 Hash、Selection
Reason、Citation Count 和 Review Material Hash。完整 Draft/Evidence 继续只在
进程内和 TTY 出现。

#### Recovery and duplicate-call rules

| Recovered state | Action | Duplicate Provider call |
|---|---|---:|
| Completed `review_complete` group + next group `pending` | Skip completed six Trial IDs; continue next group | 0 |
| Entire Campaign `complete` | Return bounded checkpoint; do not load Key or call Provider | 0 |
| `in_flight` Trial | Conservatively assume Provider may have run; block Campaign | 0 |
| Partially collected active group | Private Drafts were not persisted; mark review unrecoverable and block | 0 |
| Six Trials complete, Review not started | Mark review unrecoverable and block | 0 |
| Review in progress | Preserve already checkpointed scores; mark remaining review unrecoverable and block | 0 |
| Campaign Fail-fast complete | Return completed Trials/Reviews and incomplete matrix | 0 |

禁止持久化 Answer 正文意味着 Hash 无法恢复正文。因此 active group 崩溃时不能
同时满足“恢复完整质量复核”和“不重调 Provider”。Runner 选择 at-most-once：
保留有界事实、拒绝重复调用、把该组/矩阵标记为不完整。只有已经
`review_complete` 的 Request Group 可以安全跨进程恢复并继续下一组。

Campaign Identity 由四个 Request Hash、配置组合、Trial Schedule、Fail-fast
阈值和调用上限共同计算。Checkpoint Identity 不匹配时拒绝执行，不能把旧行混入
新矩阵。

#### Executed Replay cap and result

本次新 Replay 的授权上限与实际消耗：

```yaml
fixed_requests: 4
trials_per_request: 6
logical_trials_max: 24
logical_provider_invocations_max_including_repair: 48
transport_http_attempts_max_including_one_retry_per_invocation: 96
consecutive_provider_failure_limit: 3
automatic_resampling: false
unknown_in_flight_trial_replayed: false
completed_review_group_replayed: false
actual_logical_trials: 24
actual_logical_provider_invocations: 26
actual_transport_http_attempts: 26
remaining_logical_invocation_cap: 22
matrix_complete: true
in_flight_trial_at_completion: null
```

检查点累计真实完成调用，并在 `in_flight` 时保守预留 2/4 上限；恢复不能把总
Campaign 上限扩展到 48/96 之外。这里的 26/26 是**新矩阵**的实际消耗，不包含
上一次因进程丢失而无法精确恢复的历史消耗；旧 Campaign 继续保留为未知。

### C.11 Replay measurements and quality review

#### Configuration-combination measurements

| Metric | Baseline combination | Thinking Off combination |
|---|---:|---:|
| Trials | 12 | 12 |
| Successful Provider Trials | 11 | 12 |
| Provider Failures | 1 | 0 |
| Logical Provider Invocations | 12 | 14 |
| HTTP Retries | 0 | 0 |
| Repairs required / succeeded | 0 / 0 | 2 / 2 |
| First-pass schema valid | 11 | 10 |
| Latency min / median / max | 5,212 / 21,794.5 / 62,202 ms | 2,172 / 2,841.5 / 10,844 ms |
| Prompt Tokens | 98,616 | 115,474 |
| Completion Tokens | 17,820 | 1,610 |
| Reasoning Tokens | 15,264 | 0 |
| Cache Hit / Miss Tokens | 97,536 / 1,080 | 106,112 / 9,362 |
| Status counts | complete 1; partial 3; insufficient 7; failure 1 | complete 1; insufficient 11 |

Thinking Off 组合的中位延迟约为 Baseline 组合的 13%，但这不是可接受的独立
优化结论：它同时改变三个配置字段，并伴随更高的错误拒答率和两次
Unknown Citation Repair。

唯一 Provider Failure 为 Baseline 的 Cross-video Trial：

```yaml
provider_error_code: output_budget_exhausted
logical_provider_invocations: 1
transport_retries: 0
latency_ms: 62202
```

两次 Repair 都出现在 Thinking Off 的 Single-topic Trial，First-pass Error 均为
`unknown_citation`；两次 Repair 在第二次 Logical Invocation 后通过 Schema，但
最终都错误返回 `insufficient`。

#### Quality-review aggregate

复核总数为 17；每次都按 Citation ID 从当前 Source Version 重建完整 Evidence。
完整 Draft 与 Evidence 没有持久化。

| Configuration | Reviews | Supportedness | Usefulness | Coverage | Status honesty |
|---|---:|---|---|---|---|
| Baseline | 8 | pass 4 / partial 1 / fail 3 | pass 4 / partial 1 / fail 3 | pass 4 / partial 1 / fail 3 | pass 5 / fail 3 |
| Thinking Off | 9 | pass 2 / partial 1 / fail 6 | pass 3 / fail 6 | pass 3 / fail 6 | pass 3 / fail 6 |

逐项只保留四维评分、理由摘要和 Hash：

| Trial | S/U/C/H | Reason summary | Reason Hash | Review Material Hash |
|---|---|---|---|---|
| `no_evidence_quantum_protocol:baseline:1` | pass/pass/pass/pass | 正确拒绝回答虚构协议；未使用不相关材料，状态与当前证据范围一致。 | `0f328b566ee61d8889b4be485a9eefb8e19aa84e2e9d43871c12854333fb8549` | `396a5aa92e39ed4a0bbf3ffdc30c487e0ed2d86e58a65faf5d3ba5dcfe0245c2` |
| `no_evidence_quantum_protocol:thinking_off:1` | pass/pass/pass/pass | 正确拒绝回答虚构协议；未使用不相关材料，状态与当前证据范围一致。 | `0f328b566ee61d8889b4be485a9eefb8e19aa84e2e9d43871c12854333fb8549` | `f7b318df022761047952d1dffaac9f12ea37044b21de2bc33b02b34c46c66bb7` |
| `no_evidence_quantum_protocol:thinking_off:2` | pass/pass/pass/pass | 正确拒绝回答虚构协议；未使用不相关材料，状态与当前证据范围一致。 | `0f328b566ee61d8889b4be485a9eefb8e19aa84e2e9d43871c12854333fb8549` | `cfa7d3a8d1d53ea1924841dc2f726e5fc36e62b610b24cde9e6985d57b56784e` |
| `single_topic_context_compression:baseline:1` | pass/pass/pass/pass | 回答覆盖定义、实现方式、窗口与注意力问题以及成本收益；各要点均由对应材料支持，保守标记 partial 合理。 | `2899d45d7a73933df150c1451046176a51ce82288f1d6c877ec69fc68e82d741` | `40d73cfb2136c370ed5a0e86cadf6cbd30b6d6ae8559a9bf62023a16d644b3a2` |
| `single_topic_context_compression:baseline:2` | partial/pass/pass/pass | 主体定义、机制和问题均有材料支撑；但“加速”属于从成本与上下文缩短推导出的轻微外延，未被当前片段直接陈述。 | `a7bd31b876f26b5bc28442211229ed6402607a8dadd34f99ac0f265c967fdd1f` | `f8852d35d42f98b40947ef17a18f27087ae2c54febec58a6eda849ec17fc8e3a` |
| `single_topic_context_compression:baseline:3` | pass/pass/pass/pass | 回答简洁覆盖定义、主要实现和核心问题，所有关键陈述均可由所引材料直接支持，partial 状态保守诚实。 | `cf862332ba904f28eb0e345ef1bc1311d740d8976ffa27b392305a705cbfbaf5` | `5ed3b5ca4b32823ff96e112fd41f7967a0df7bb0ebc1aea369a5a678ae5c192f` |
| `single_topic_context_compression:thinking_off:1` | partial/pass/pass/pass | 核心解释和问题分析充分；“避免遗忘”及“保持关键信息完整性”比所引片段的直接表述略强，属于轻微外延。 | `18a2a4241bcfdc66dc5efb5ebf0553e45d4d722dac76919e2225253dc57852e7` | `e894df180a5dcdff7f2543374caede119781ab70eea77c062f73a6e69445811f` |
| `single_topic_context_compression:thinking_off:2` | fail/fail/fail/fail | 当前材料包含直接定义、机制和问题说明，却错误返回 insufficient 且无答案，四维均失败。 | `75189ab7c46eec4088768bad8d4c152c5985e2943980220dad17959cde153544` | `f505eb068c6ce0ed1d0344d87506aec80d75bc8292b6f4dfc62adf8db86d8e2d` |
| `single_topic_context_compression:thinking_off:3` | fail/fail/fail/fail | 当前材料包含直接定义、机制和问题说明，却错误返回 insufficient 且无答案，四维均失败。 | `75189ab7c46eec4088768bad8d4c152c5985e2943980220dad17959cde153544` | `0fcae467e6c88f4905ccf6c44cc35aef380722a11c846593509e2a680295896e` |
| `cross_video_context_management:baseline:1` | pass/partial/partial/pass | 概念区分有直接材料支持，但仅总结单一视频视角，未完成不同视频之间的系统比较；partial 状态与限制说明诚实。 | `27ddbd973bba5698986212172058678f59fa6f01b2d361975eaa145fd15ab34b` | `b71837b2b3d28ff9f6f5edab62f0fce74cb0c74a9ebdc1a3cc4bcec33c0f101c` |
| `cross_video_context_management:baseline:2` | fail/fail/fail/fail | 该 Trial 为 Provider failure，未产生可核验的结构化答案，因此无法满足支持性、实用性、覆盖度或状态诚实性要求。 | `6a4541ea296ac6a038cd85e578ed080c44daaa650624516dd64fc725f96fc5b9` | `877fab952529551b69c6413742f5002ecd1c7f3448b4680048f99816d810ff51` |
| `cross_video_context_management:baseline:3` | fail/fail/fail/fail | 材料包含多个视频对上下文选择、压缩、隔离、检索与探索式管理的具体做法，足以进行有依据的横向综合；错误返回 insufficient，未完成核心比较。 | `f6e3d660094802f020496c199d6a5a85abf6f8b3eb5a344f051b8ad713118532` | `12f1cde2aa142b9fee5b40e3de2bf1cad8aeb376dda257d600d2899fc64f87ed` |
| `cross_video_context_management:thinking_off:1` | fail/fail/fail/fail | 材料提供了多个视频中的检索、筛选、压缩、隔离和探索式上下文管理实例；将证据判为不足并留空答案，既不实用也未覆盖问题。 | `2d3c58629743d1d389ad305ab5090095da404c24705467c8d122618dce6a9c61` | `9c8615cccd33e4582894c04b75e291fe1b35accf9a81897643b714bbc5371f68` |
| `cross_video_context_management:thinking_off:3` | fail/fail/fail/fail | 现有多段材料可支持跨视频比较不同的上下文检索、压缩、隔离及工程侧与模型侧权衡；错误返回 insufficient，未回答核心任务。 | `d1074ea1d4cd829f5ec30fbce19e9648ebf60e793f88f1a24313b2058bf9b2c` | `45cf1987e0124326186f7650b3381dc233b87ae88faf65f5ee3c8c7c06bb8117` |
| `partial_universal_claim:baseline:1` | fail/fail/fail/fail | 材料直接给出压缩会错误分组、丢失适用条件及摘要不如完整轨迹等反例，足以否定“所有任务都更好”；返回 insufficient 错失核心结论。 | `cd3ab072e445b516d4c06de334f5576b490aade2f28997343e8fc166bda7f3ab` | `4b21d465a3b3da1d242d5ce9d782f21352ca017f814b2c1a37d43ef9759b15d3` |
| `partial_universal_claim:thinking_off:1` | fail/fail/fail/fail | 证据明确呈现自动压缩的条件性收益与失败机制，包括错误合并、条件丢失和原始轨迹优于摘要；因此不足状态不诚实且未作应有否定回答。 | `72b0d1edc21b8e49aa86fc448397b17a89a177e071a5dcdff6e16d7e58926ef9` | `4d50e22d1fe46d31d49d00231eb7b0ea25e061642376dce7844e95fad9ad365a` |
| `partial_universal_claim:thinking_off:2` | fail/fail/fail/fail | 证据包含直接反例与适用条件，足以回答“不证明普遍更好”；该 Draft 未利用证据、未给结论，并错误声称证据不足。 | `ffba323c53965c4e48fb287356ab035d888f312077871cbd4a9fd6afd83a4c08` | `66772194fd7933f22bad2ff775df5b31c669b71f515f5edd391c943ff5bf44ea` |

`partial_universal_claim` 六个 Trial 在两个配置组合下都错误返回
`insufficient`。这说明问题不只存在于 Thinking Off 组合；当前 Grounded Answer
Prompt/Provider 行为对“由反例否定全称命题”的处理本身也需要后续独立调查。

#### Decision

```yaml
adopt_thinking_off: false
change_formal_provider_configuration: false
change_formal_runtime: false
enter_end_to_end_without_new_authorization: false
reason:
  - comparison_is_between_configuration_combinations
  - lower_latency_coincides_with_material_quality_regression
  - baseline_also_has_unresolved_quality_failures
```

## D. H0-B Deep Decision Payload Audit

### D.1 Current context diagram

```text
Complete DeepSearchState
  ├─ full Evidence Spans
  ├─ full visited IDs
  ├─ Navigation Documents
  ├─ Worklist / Budget / Events
  └─ Runtime guards
          │
          ▼
current _decision_messages()
  ├─ static Policy + full AgentDecision Schema
  ├─ last 8 Navigation Documents
  ├─ last 12 Evidence Spans
  │    ├─ quote[:500]
  │    └─ complete segment_ids
  ├─ last 24 video IDs
  ├─ last 60 segment IDs
  ├─ last 24 previous action/query keys
  └─ bounded latest Observation + dynamic Budget
          │
          ▼
agent_action Provider
```

源码反证了以下规划假设：

- 没有完整 Historical Observation List；
- 没有完整 Trace Payload；
- 没有直接发送全部 247–357 个 Visited Segment；
- Last Observation 已限 1,000 字；
- 当前 Payload 已是内嵌有界投影，不是完整 State Serialization。

### D.2 Scripted audit source

```yaml
payload_source: scripted_actions_with_real_local_tools
decision_sequence:
  - search_navigation
  - search_transcripts
  - read_transcript_window
  - search_navigation
  - finish
decision_rounds: 5
tool_calls: 4
termination_reason: answer_ready
final_evidence_spans: 7
runtime_visited_videos: 9
runtime_visited_segments: 261
provider_calls: 0
```

Capture Provider 只返回 Scripted `AgentDecision`；Navigation、Transcript
Search、Window Read、Reducer 和 LangGraph State 流均使用当前真实本地代码和
临时数据库 Snapshot。

### D.3 Per-round payload

字段 Token 仅使用 `ceil(character_count / 4)` 作相对估算。Provider
`prompt_tokens` 才是总量权威。动态剩余秒数字符会使总字符在重复 Dry-run 间
产生约 1–2 字差异。

| Round | Action | Message chars | Estimated tokens | Navigation | Evidence text | Evidence metadata | Visited segments |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | Navigation | 3,836–3,837 | 960 | 25 | 0 | 24 | 24 |
| 2 | Focused Transcript | 14,085–14,087 | 3,522 | 10,125 | 0 | 24 | 24 |
| 3 | Window | 42,720–42,721 | 10,681 | 10,125 | 3,281 | 20,731 | 4,523 |
| 4 | Replan Navigation | 43,235–43,237 | 10,809 | 10,125 | 3,326 | 21,116 | 4,523 |
| 5 | Finish | 42,177 | 10,545 | 9,111 | 3,326 | 21,116 | 4,523 |

其他区块：

| Block | R1 | R2 | R3 | R4 | R5 |
|---|---:|---:|---:|---:|---:|
| Static Policy | 606 | 606 | 606 | 606 | 606 |
| AgentDecision Schema | 2,795 | 2,795 | 2,795 | 2,795 | 2,795 |
| Tool Contracts | 0 | 0 | 0 | 0 | 0 |
| Original Query | 37 | 37 | 37 | 37 | 37 |
| Current Goal | 0 | 0 | 0 | 0 | 0 |
| Open Questions | 45 | 45 | 45 | 45 | 45 |
| Resolved Questions | 23 | 23 | 23 | 23 | 23 |
| Latest Observation + Action | 47 | 134 | 227 | 228 | 137 |
| Historical Observations | 0 | 0 | 0 | 0 | 0 |
| Visited Video IDs | 22 | 48 | 48 | 48 | 52 |
| Previous Query Keys | 31 | 68 | 122 | 208 | 249 |
| Budget | 143–146 | 143–146 | 143–146 | 143–146 | 143–146 |
| JSON structural overhead | 12 | 12 | 12 | 12 | 12 |

每轮字符可以回算到当前 System + User Message 总字符。System Message Hash 在
五轮完全一致：

```text
860ac16926636db2418ffee7fa108a90ec57156fb1da99b448d88c4c739270c4
```

固定 System Prefix 为 3,401 字；第一个动态字段位于第二条 Message 的
`question`。

### D.4 Required field checks

- Navigation `description` 实测最大 320 字，`matched_excerpt` 最大 280 字；
- `summary_sections[:4]` 每轮最多 16 项，实测单项最大 1,162 字、合计最大
  5,734 字；`_decision_messages()` 本身没有单 Section 字符上限；
- Evidence Quote 最大 500 字，七 Span 合计约 3,326 字；
- 单 Evidence 的完整 `segment_ids` 最多 54 项；
- Round 4/5 七 Span 的 `segment_ids` 合计 266 项、19,152 字；
- Runtime 有 261 个唯一 Visited Segment，但 Decision Payload 只发送最近 60
  个，约 4,523 字；
- Previous Query 只发送最近 24 个，本次最多 4 个；
- Visited Video 只发送最近 24 个，本次最多 9 个；
- Resolved Question 当前只包含 Question/Citation IDs，不携带完整支持正文；
- Historical Observation、Tool Contract Message、Trace Payload 均不存在。

### D.5 Top growth sources

从 Round 1 到 Round 5：

| Rank | Block | Growth chars |
|---:|---|---:|
| 1 | Evidence metadata | +21,092 |
| 2 | Navigation results | +9,086 |
| 3 | Visited segment IDs | +4,499 |
| 4 | Evidence quote text | +3,326 |
| 5 | Previous query keys | +218 |

首要事实不是“完整历史 Observation 累积”，而是：

```text
每个 Evidence 的完整 segment_ids
+ 重复 Navigation 投影
+ 最近 60 个 Visited Segment IDs
+ 有界 Evidence Quote
```

本次 Evidence metadata 约 21.1k 字，其中完整 Evidence `segment_ids` 本身约
19.2k 字，是最明确的单项增长源。

### D.6 Calibration against real Usage

历史 Goal 3 Deep Provider Usage：

| Case | Per-round authoritative prompt tokens |
|---|---|
| Contextual tool failure | 984 → 5,612 → 19,850 |
| Cross-video | 980 → 9,594 → 25,890 → 25,917 → 28,557 |
| Direct fact | 986 → 7,965 → 23,899 → 24,263 |
| No-evidence | 991 → 7,483 |

Scripted Char/4 估算在后轮明显低估真实 Token，因此只用于字段相对分解。真实
Usage 与 Scripted Audit 在增长形状上相互校准：Navigation 后上升，Evidence 和
Visited IDs 进入后跃升到高成本区。

### D.7 Cache layout

- System Policy + Schema 字节级稳定；
- User Payload 从第一字段开始动态；
- Historical Cache Hit 多为 768–896 Tokens，接近稳定前缀的一部分；
- 一次相同 Case 重跑出现 7,424 Cache Hit Tokens，说明 Provider 也可能命中更长
  的重复 Payload；
- 不能声称动态字段破坏“全部 Cache”；
- 也不能假定 Cache 会稳定覆盖重复 Navigation/Evidence。

### D.8 Candidate DecisionView

H0 只提出字段级候选，不实施：

| Candidate field | Runtime source | Projection | Full Runtime retained | Main risk |
|---|---|---|---|---|
| `original_query` | `state.query` | exact | yes | low |
| `current_search_goal` | prioritized `open_questions` | one bounded goal | yes | wrong priority may steer Replan |
| `open_questions` | `state.open_questions` | max 6 concise questions | yes | truncation may remove qualifiers |
| `resolved_questions` | `state.resolved_questions` | question + Citation IDs only | yes | resolution nuance may be lost |
| `latest_observation` | last action + bounded summary + new Evidence IDs | keep latest detail only | full events remain | older causal chain may be hidden |
| `evidence_inventory` | `state.evidence_spans` | Citation ID, video, time, short relevance note, 1–3 window anchors | full Span/segments remain | short note may omit negation/counterexample |
| `previous_query_summary` | `state.previous_queries` | counts, kinds, recent bounded keys/hashes | full list remains | model may repeat semantically similar search |
| `visited_summary` | visited videos/segments | counts, recent videos, bounded ranges/anchors | full sets remain | model loses arbitrary segment choice |
| `budget_remaining` | Budget + deadlines | exact remaining counters, placed last | full state remains | dynamic time reduces cacheable suffix |
| `available_actions` | Action Schema/static policy | static action names and guards | schema remains | duplication if not deduplicated with Schema |

关键 Guard 继续由确定性代码使用完整 Runtime State：

- repeated action/query；
- repeated segment；
- window anchor existence；
- focused video limit；
- no-new Evidence；
- Round/Tool/Context/Deadline。

### D.9 H2 recommendation and information-loss tests

建议 H2 优先顺序：

1. 从 Decision Payload 移除每个 Evidence 的完整 `segment_ids`，保留 Citation ID
   与少量合法 Window Anchor；
2. 将 Navigation 压缩为当前目标相关的标题/视频 ID/短匹配说明，不重复发送长
   Summary Sections；
3. 将 Visited Segment 改为计数和范围/近期摘要，完整集合只供 Guard；
4. 保留 Latest Observation、Open Questions、Evidence Inventory 和 Replanning；
5. 不引入 LLM Rolling Summary。

H2 必须测试：

- Navigation → Focused Transcript → Window → Replan → Finish；
- Window Anchor 仍可选择；
- Observation 后 Action 仍改变；
- Partial/No-evidence 诚实停止；
- Full Runtime Guard 结果不变；
- Stable Citation/Source Version/Finalizer 不变；
- System Prefix 稳定；
- DecisionView 字符预算有界；
- Scripted 与少量授权真实运行前后对照。

主要信息损失风险是 Window Anchor 选择、旧 Navigation 备选、否定/反例语义和
复杂 Replanning 线索。不能为了 Token 目标删除 Open Questions、Latest
Observation 或 Evidence Inventory。

## E. H0-C Fast Context Diagnostics

### E.1 Method and definitions

六 Case 使用与 H0-A 相同的确定性 Query Plan和当前真实本地 Retrieval。

```text
Raw Materialized Spans
→ fuse_evidence()
→ Candidate Spans
→ per-span Fit
→ overlap/adjacent Merge
→ max-spans/total-character Budget
→ Selected Spans / model_context
```

Runner 还执行一个只读 Shadow Selection Trace，并逐字段证明其最终 Selected
Span 与当前 Builder 完全相同。正式 Builder 输出仍是模型输入；Shadow 结果只
用于解释 Outcome。

`dropped_chars` 定义为非负的 `candidate_chars - selected_chars`，属于
Approximation，因为 Merge/Overlap/Fit 不能精确归因到独立 Span。

### E.2 Six-case results

| Case | Raw | Candidate | Selected | Candidate videos | Selected videos | Exact duplicate Raw | Overlap pairs | Merged | Unique dropped | Chars candidate → selected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct MCP | 150 | 81 | 12 | 29 | 6 | 69 | 34 | 6 | 63 | 53,712 → 11,752 |
| Single-topic compression | 150 | 93 | 12 | 35 | 9 | 57 | 26 | 7 | 74 | 59,774 → 11,963 |
| Contextual tool failure | 150 | 114 | 12 | 46 | 9 | 36 | 26 | 6 | 96 | 74,475 → 11,615 |
| Cross-video | 100 | 68 | 12 | 29 | 9 | 32 | 20 | 5 | 51 | 45,321 → 11,884 |
| Universal/Partial | 150 | 102 | 12 | 36 | 9 | 48 | 29 | 6 | 84 | 67,342 → 11,897 |
| No-direct-support | 150 | 75 | 12 | 24 | 8 | 75 | 34 | 7 | 56 | 48,523 → 11,927 |

全部六例：

```yaml
context_truncated: true
per_span_fit_or_trim_count: 0
different_citation_exact_quote_duplicate_count: 0
stale_count: 0
retrieval_error_count: 0
```

主要 Drop Outcome：

- 12 Span 与 12k Character 联合边界；
- Shadow 优先归类中，`dropped_max_spans` 每例 47–93；
- Merge 增量触发 Character Budget 每例 3–6；
- 每例 5–7 个 Candidate 被 Overlap Merge 吸收；
- 本轮没有 Per-span 2,500 字 Fit。

Builder 的 `dropped_span_count` 是内部 Drop Event Count，不严格等于唯一
Candidate 数。Universal 和 No-direct-support 各出现一次同一 Candidate 的重复
Drop Event；Runner 同时记录 Unique Dropped Candidate 与 Builder Event，不修改
正式 Trace。该差异是诊断语义问题，不改变 Selected Identity、Model Context、
Citation Allowlist、Status 或 Termination。

### E.3 Required questions

**同一视频占用**

- Direct MCP 的最高单视频占 6/12，恰好 50%；
- 其余 Case 最高为 2–3/12；
- 没有 Case 超过 50%，但 Direct Case 存在明显单视频集中信号。

**Rewrite 重复召回**

- Raw Stable Citation 重复额外数量为 32–75；
- `fuse_evidence()` 在 Context Selection 前已将其去重并合并 Provenance；
- 因此重复 Rewrite 明显存在，但没有以相同 Citation 重复占用最终 12 Span；
- Fused Candidate 中没有发现不同 Citation ID 但规范化 Quote 完全相同的额外
  项。

**Cross-video Diversity**

- Cross-video 从 29 个 Candidate Video 保留 9 个 Selected Video；
- 没有在 Context 前退化为单视频或双视频；
- 第三个 Scripted Rewrite 没有进入 Selected Provenance，但前两个 Query Source
  均有 Selected Span。

**Universal/Partial-support**

- 从 36 个 Candidate Video 保留 9 个；
- 三个 Scripted Query Source 均有 Selected Span，包括面向反例/性能下降的
  Rewrite；
- 这说明没有结构性证据证明该方向在 Selection 前完全消失；
- 仅凭 Provenance 不能证明关键反例语义一定被保留，材料性判断需要授权后的
  Full Citation 人工质量复核。

**Truncation source**

六例的 Truncation 不是简单 Raw Top-K，也不是 Per-span Fit。它由：

```text
Multi-query duplicate recall
→ Citation fusion
→ Overlap merge
→ 12 Selected Span / 12k Character combined boundary
```

共同形成。Selected Quote 总字符均接近 12k。

**Selection change trigger**

当前没有重复材料性回答失败证明关键 Evidence 稳定落在 Context 外。因此：

```yaml
reranker_triggered: false
diversity_selector_triggered: false
context_compaction_triggered: false
```

## F. H1/H2 Scope Recommendation

### `proven_and_recommended`

- Thinking Off 配置组合在本次小样本中延迟显著更低，但同时发生材料性质量退化，
  因而拒绝采用；该观察不能隔离为 Thinking 单变量因果；
- H1 修正 Universal/Partial-support 的重复错误拒答，使直接反例能够形成有
  Citation、有限范围、诚实 Limitation 的 `partial` 回答；
- H1 在共享 Grounded Answer 层有界改善 Cross-video 综合和输出纪律；
- H2 实施 Deterministic DecisionView；
- H2 第一优先移除 Evidence 完整 `segment_ids` 的重复模型投影；
- H2 压缩重复 Navigation 和 Visited Segment 投影；
- H2 保留完整 Runtime State 和所有确定性 Guard；
- 保留 H0 Runner-only Context Diagnostics；
- 在 Live Replay 中使用完整配置组合表述、质量复核和 Campaign Fail-fast。

### `not_proven`

- 延迟和质量差异只由 Thinking 引起；
- Thinking Off 能保持 Supportedness/Usefulness/Coverage/Status Honesty；
- Fast Context Selection 需要改排序、Diversity 或 Budget；
- Provider Service Fault 是主要原因。

### `rejected_or_deferred`

- Reduced Reasoning：当前合同不可表达；
- No-evidence Short Path：继续 Deferred；当前有 Evidence 噪声但无直接支持的
  Case 已能诚实返回 `insufficient`；
- Reranker；
- Automatic Context Compaction；
- Runtime Semantic Judge；
- LLM Rolling Summary；
- Native Tool Calling；
- Streaming/Cancellation；
- Provider/Context/Eval/Observability Platform；
- Memory、Persistence、HITL、Multi-Agent；
- Fast/Deep 自动路由。

## G. Tests

### Before H0 changes

```text
63 passed
1 existing Starlette/httpx deprecation warning
```

覆盖既有 Goal 1 Fast、Goal 2 Deep、Goal 3 Ask/Eval、Provider、Deadline/Retry、
Citation/Context。

### H0 focused

```text
27 passed
```

覆盖：

- 配置组合 Request Body；
- 非配置字段完全相同；
- Fixed Request 三 Trial Hash；
- 轮转顺序；
- Reduced Reasoning 拒绝；
- Usage 嵌套提取和 null；
- First-pass Schema/Repair/Retry；
- Provider Error 保留；
- Payload 回算与 Repeated Hash；
- `_decision_messages()` 非改写；
- Raw/Fused/Merged/Selected/Dropped 诊断；
- Model Context/Citation Allowlist/Selected Identity 非回归；
- Draft/Citation ID 只在进程内保留；
- 中位延迟与最差质量选择；
- 输出分歧三 Trial 全审；
- Citation ID 当前完整 Evidence 重建；
- 完整 Answer/Evidence 不序列化；
- 连续三 Provider Failure Fail-fast；
- 成功 Trial 重置连续失败；
- Campaign 不完整状态和已完成 Trial 保留；
- Live Replay 与 E2E 独立授权门；
- 不可 seek PTY 的独立读写流质量复核；
- 真实 TTY Challenge/Response Preflight；
- Provider 前 in-flight WAL 和逐 Trial 原子检查点；
- 六 Trial 后立即 Review；
- 逐 Score Review Checkpoint；
- Provider 返回后、Review 前和 Review 中崩溃恢复；
- 已完成 Request Group 跳过；
- 不确定 in-flight 和丢失私有 Draft 时禁止重复 Provider；
- Checkpoint 私有正文扫描和 Campaign Identity。

### Directed regression

```text
Replay preflight: 90 passed
Post-Replay rerun: 90 passed
1 existing Starlette/httpx deprecation warning
```

### Default full suite

```text
1484 passed, 4 deselected
1 existing Starlette/httpx deprecation warning
```

四项仍是默认排除的既有 `external_artifact` / `live_provider` Marker。

### Static

```yaml
compileall: passed
pip_check: passed
pip_warning: existing user cache not writable
git_diff_check: passed
deterministic_runner:
  provider_calls: 0
  end_to_end_calls: 0
checkpoint_hardening:
  provider_calls: 0
  end_to_end_calls: 0
real_tty_preflight_smoke:
  provider_calls: 0
  network_calls: 0
  status: passed
```

## H. Data and Scope Audit

```yaml
prior_failed_campaign:
  provider_logical_trials: unknown_after_in_process_result_loss
  provider_logical_invocations: unknown_after_in_process_result_loss
  provider_transport_http_attempts: unknown_after_in_process_result_loss
  rewritten_as_zero: false

new_fixed_replay:
  provider_logical_trials: 24
  provider_logical_invocations: 26
  provider_transport_http_attempts: 26
  provider_bounded_result_rows_persisted: 24
  provider_quality_reviews_completed: 17
  provider_failures: 1
  matrix_complete: true
  automatic_resampling: false

end_to_end_runs: 0
checkpoint_hardening_provider_calls: 0
checkpoint_hardening_end_to_end_runs: 0

api_key_loaded_by_deterministic_runner: false
api_key_loaded_by_prior_authorized_live_runner: true
api_key_loaded_by_new_authorized_live_runner: true
authorization_header_written: false
full_provider_messages_written: false
full_evidence_context_written: false
full_answer_written: false
full_private_transcript_written: false
raw_provider_response_written: false
separate_json_result_file_created: false
new_live_campaign_checkpoint_created: true
new_live_campaign_checkpoint_path: .h0/v4_1_fixed_replay_checkpoint.json
new_live_campaign_checkpoint_git_ignored: true
new_live_campaign_checkpoint_mode: "0600"
new_live_campaign_checkpoint_sha256: e8532f9d0815be6067d5654ea5371822801ad155bcb5d06663891dd4796b61e0
checkpoint_private_body_persistence_capability: rejected_by_schema_and_tests

formal_runtime_behavior_changed: false
provider_role_configuration_changed: false
deep_prompt_changed: false
fast_context_selection_changed: false
langgraph_or_tool_or_budget_changed: false
runtime_semantic_judge_added: false
new_platform_added: false

v4_master_state_modified: false
v4_design_proposal_modified: false
v4_decision_ledger_modified: false
frozen_v0_to_v4_report_modified: false

git_stage_commit_push_merge: false
```

## I. Main Session Decision Inputs

当前 Main Session 可以决定：

1. 保持正式 Baseline，不采用 Thinking Off；Replay 已证明低延迟与明显质量退化
   同时出现，而且对照是配置组合，不是 Thinking 单变量；
2. 是否单独调查两个组合共同出现的 Universal/Partial-support 错误拒答；
3. 是否单独调查 Cross-video 综合覆盖不足和一次
   `output_budget_exhausted`；
4. Main Session 已在后续 Continuation Prompt 中独立授权 Paired E2E；不得运行
   旧 H0 双配置 E2E 路径；
5. H2 是否进入 Deterministic DecisionView 实施；
6. H2 是否按 Evidence segment IDs → Navigation → Visited IDs 的顺序缩减；
7. H0-C 暂不触发任何 Selection 行为改动；
8. No-evidence Short Path 在两组合下均表现正确，但是否进入正式 Runtime 仍需
   独立设计与授权；
9. Useful Partial 与状态诚实性问题应结合后续 E2E 或专门质量实验再决定。

H0 Fixed Replay 已完成，没有剩余 Replay 授权门。后续只按 Continuation
Prompt 的 Phase 顺序进入 Baseline-only Paired E2E、H1/H2 和 Closeout；不修改
正式 Provider 配置。
