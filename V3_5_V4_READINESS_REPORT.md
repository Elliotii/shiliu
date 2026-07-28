# Shiliu V4 Readiness Report

## Decision

`ready_to_start: true`

V3.5-B is formally closed. V4 may start as a separately versioned cycle; this
Session did not implement V4.

## Reusable assets

- PQS v1, sealed Development/Frozen split, and sealed Gold.
- Frozen V3 runtime and corpus identity.
- Evidence Identity Contract V1.
- Formal Builder, Selector, Mechanical Gate, and Semantic Judge contracts.
- Stage5 API/UI/Trace integration.
- P14 atomic Case/Trace artifacts, scorer outputs, and audit lineage.

## Technical debt

There is no procedural blocker to starting V4. Priorities are authoritative
source reviewability, Builder/Selector complete-group evidence coverage, and
Semantic Judge latency. Non-blocking debt includes six historical repository
tests, one missing authoring-packet dependency, external proxy-timeout
configuration, and the evaluation-orchestration stable/route-dependent field
validation rule.

## Recommended first scope

Run a newly governed Development cycle for source reviewability and
Builder/Selector evidence coverage. Add explicit orchestration validator tests
that distinguish globally frozen configuration from legitimate per-route
execution metadata.
