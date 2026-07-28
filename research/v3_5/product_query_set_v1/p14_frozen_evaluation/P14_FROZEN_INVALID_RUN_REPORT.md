# P14 Frozen Evaluation Invalid Run Report

## Status

- Outcome: `p14_frozen_evaluation_invalid`
- Status: `blocked_pending_main_session`
- Rerun authorized: `false`
- Formal prediction run count: `1`
- Unique formal run consumed: `true`

## Valid pre-run state

The resumed Entry Gate passed. The Frozen Runtime Seal passed the existing
runtime guard, and the Formal Run Manifest was frozen before the Frozen Query
was opened.

## Infrastructure failure

The formal process loaded all 10 Frozen Queries and completed retrieval,
Candidate Builder, deterministic Selector, and Mechanical Gate work in memory.
On the first frozen Semantic Judge provider call, `openai-codex-cli` failed
before returning provider output:

- its state database could not be opened because the execution environment made
  it read-only;
- its in-process app-server client could not initialize because the operation
  was not permitted.

This is an infrastructure error, not one of the frozen four semantic states.
No Semantic Judge result was fabricated.

The executor had not yet persisted per-case traces or predictions, and its
in-memory intermediates were lost when the process terminated. Reconstructing
them would require rerunning retrieval and the downstream Case path, which the
formal run contract forbids.

## Access and freeze audit

- Frozen Query opened: `true`
- Frozen Gold opened: `false`
- Per-case predictions generated: `false`
- Predictions Freeze generated: `false`
- Metrics or Failure Analysis generated: `false`
- Result Freeze Seal generated: `false`
- Permission escalation or environment change followed by retry: `false`
- Single-Case or full-run retry: `false`
- Component, prompt, policy, timeout, Gold, scorer, or projection change: `false`

## Evaluation validity

`evaluation_validity: invalid`

The invalidity is caused by an unhandled infrastructure failure and the absence
of a valid Predictions Freeze. It is not an interpretation of algorithm
performance.

P14 must stop and escalate to the main Session. P15 Final Closeout has not
started.
