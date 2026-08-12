# Post-V5 Bounded Repair Checkpoints

Date: 2026-08-12 (Asia/Shanghai)

Baseline: `codex/post-v5-product-closeout` at
`5f1bf4dd899e97583a234b224e209f8c6aac9294`.

Repair branch: `codex/post-v5-bounded-repair`.

This is the compact rollback/checkpoint record required by
`POST_V5_BOUNDED_REPAIR_CHARTER.md`. It does not reopen deferred scope.

## Goal A — Ask Finalization Reliability

Related observations: RU-001, RU-004, RU-011.

Root failure family: successful Retrieval/Evidence followed by Grounded Answer Provider
failure was projected as evidence insufficiency; output-budget and empty-output failures
had no eligible role-specific recovery.

Bounded implementation:

- Added the response/trace `execution_outcome` projection without a database migration.
  `generation_failed`, `evidence_insufficient`, `evidence_unavailable`, and
  `answer_generated` remain distinct while the v16 `answer_status` persistence contract
  stays intact.
- Provider/runtime failure now renders `回答生成失败`, never `证据不足`, and cannot emit
  an answer block or Citation.
- Preserved the normal `deepseek-v4-pro` thinking-enabled Grounded Answer path. The prior
  H0 evidence rejected Thinking Off as the primary path because of quality regression.
- Added exactly one eligible recovery for `output_budget_exhausted` or
  `empty_model_output`, using the same evidence and the same deadline through a
  role-specific Pro/Thinking-Off recovery provider. Network, authentication,
  configuration and generic Provider failures do not enter that recovery.
- Every answer Provider invocation now records `call_kind`, finish reason, latency,
  token usage and retry count in existing usage/trace JSON.

Deterministic proof:

- Fast/Deep Ask, contract, page, provider-routing and persistence tests: 76 passed.
- V4.1 H0/Continuation nearby non-regressions: 37 passed.
- Original-family regressions cover output-budget exhaustion in Fast and Deep,
  empty-model output, recovery failure, authentication/network/configuration/deadline,
  invalid JSON, model-declared insufficiency, zero/stale evidence and Citation
  revalidation.

Natural smoke measurements:

| Run | Outcome | Total / final Provider | Prompt / completion / reasoning | Calls / repair | Citations |
|---|---|---:|---:|---:|---:|
| Before Fast `ask_run_0eabf36f514f40a382cc15bbdc1ff3f3` | `partial / answer_ready` | 55.6 s / 49.7 s | 10,067 / 2,690 / 2,358 | 1 / 0 | 6 |
| After Fast `ask_run_0a4a00d56a3a42d580a697e97770d12c` | `partial / answer_generated` | 76.20 s / 63.68 s | 9,948 / 3,464 / 2,679 | 1 / 0 | 5 |
| Before Deep `ask_run_917e153e8c9a4e59a2bc24b4dc7e2005` | `partial / answer_ready` | 80.4 s / 63.9 s | unknown / 3,134 / 2,810 | 1 / 0 | 3 answer blocks |
| After bounded Deep `ask_run_2173c642c9234e03a88db4639977c020` | `complete / answer_generated` | 69.71 s / 50.03 s | 3,531 / 3,730 / 3,446 | 1 / 0 | 3 |

Additional honest terminal checks:

- Fast `ask_run_3cefac1ebc394ea0ad8f5aacb8b03b15`: model-declared
  `evidence_insufficient`, 14.22 s total, 3.36 s final Provider, 103 reasoning tokens.
- Deep `ask_run_02d0729c82614490ba6d9ab69da145a6`: deterministic search stop plus
  model-declared `evidence_insufficient`, 22.48 s total, 3.12 s final Provider, 97
  reasoning tokens.

Gate result: **PASS**. Provider failure and evidence insufficiency are durably and
visibly distinct; Fast/Deep share the semantics; recovery is bounded to one eligible
attempt; Pro model identity, Retrieval, Evidence and Citation Authority are unchanged.

Residual limitation: normal successful Pro calls still show variable latency and can
spend most completion tokens on reasoning. The repair does not claim a latency SLA or
adopt primary Thinking Off. The after-Fast sample was slower than the earlier scoped
sample, while bounded Deep was faster; more natural use is required before attributing
latency change. The new recovery path is deterministically covered but was not induced
against the live Provider.
