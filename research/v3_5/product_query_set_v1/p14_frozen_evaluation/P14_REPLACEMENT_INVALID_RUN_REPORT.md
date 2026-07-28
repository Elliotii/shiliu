# P14 Replacement Invalid Run Report

## Outcome

- Outcome: `p14_replacement_run_blocked_or_invalid`
- Status: `blocked_pending_main_session`
- Replacement run ID: `P14_REPLACEMENT_FROZEN_EVALUATION_20260727T184443+0000`
- Failure class: `orchestration_contract_invalid`
- Failure stage: `predictions_freeze_barrier`
- Replacement formal prediction run count: `1`
- Completed atomic Case/Trace artifacts: `10` / `10`
- Predictions Freeze generated: `false`
- Frozen Gold opened: `false`
- Scoring performed: `false`
- P15 started: `false`
- Rerun authorized: `false`

## Mechanical cause

The frozen pipeline completed and atomically persisted all ten Case and Trace
artifacts. Before Predictions Freeze, the orchestration-only wrapper rejected
the set because it compared each complete `component_versions` object. The
frozen prediction summary intentionally records `semantic_model: null` when
the Mechanical Gate does not call the Judge and `semantic_model:
gpt-5.6-terra` when it does. The formal configuration hash remained identical
for all ten Cases, and every Case/Trace hash validates.

This failure is not an algorithm-quality result. No Case was recomputed or
modified; no wrapper repair or same-ID resume was attempted after the
deterministic Freeze-barrier failure. Frozen Gold remained closed, no scorer
ran, and P15 did not start.

## Required disposition

Stop and escalate to the main Session. A rerun is not authorized by this
Session.
