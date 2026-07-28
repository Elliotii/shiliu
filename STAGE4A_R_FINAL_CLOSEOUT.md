# Stage 4A-R Final Closeout

## Result

Stage 4A-R formally closes with
`stage4a_r_pass_after_single_generic_correction`. The formal Mechanical Gate is
`mechanical-gate-v1-r1`. Stage 4B is ready but has not started.

## Frozen formal components

- Candidate Builder: `stage3b-acronym-w3.5-v1`
- Fine Selector: `v3.5-deterministic-fine-selector-v1`
- Evidence Identity Contract: V1, contract hash
  `35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7`
- Mechanical Gate Before: `mechanical-gate-v1`
- Mechanical Gate After: `mechanical-gate-v1-r1`

The Builder, Selector, Evidence Identity Contract, canonical matcher,
Development inputs, Development Gold, and Stress inputs passed their frozen
hash checks and did not change.

## Before and correction

The unmodified Gate reproduced Product `13 / 1 / 0` and produced Stress
`20 / 0 / 0`, with status order `judge_eligible / source_unverifiable /
invalid`. Both sets had zero unhandled exceptions and zero invalid identities.

The authorized direct contract negatives exposed one generic defect: invalid
current artifacts and unavailable external authoritative sources shared the
same historical `terminal_unverifiable` projection. The only allowed behavior
revision split those states into `invalid` and `source_unverifiable` and added
generic mechanical Bundle checks. It added no semantic sufficiency logic and
contains no query, video, or case special rules. The single-revision allowance
is fully consumed.

## Tests, Freeze, and preflight

Evidence Identity Contract V1 tests passed `17/17`; Mechanical Gate and
Gold-free contract tests passed `49/49`; total `66/66`. The tests cover positive
judge eligibility, unsupported/missing authoritative sources, malformed
bundles, wrong timelines, unresolved Segment identity, conflicting duplicate
Evidence IDs, terminal exclusivity, determinism, reason projection, exception
containment, and the absence of semantic sufficiency fields.

The `mechanical-gate-v1-r1` Freeze Seal was issued before formal After
execution. Post-freeze preflight passed. No Gate behavior, config, contract
schema, or test semantics changed after the Seal.

## Formal revalidation

Product Development ran exactly once:

- total: 14
- `judge_eligible`: 13
- `source_unverifiable`: 1
- `invalid`: 0
- invalid identity: 0
- unverifiable identity: 0
- unhandled exception: 0
- judge-eligible Bundle contract pass rate: 100%

Stress ran exactly once:

- total: 20
- `judge_eligible`: 20
- `source_unverifiable`: 0
- `invalid`: 0
- invalid identity: 0
- unverifiable identity: 0
- unhandled exception: 0
- judge-eligible Bundle contract pass rate: 100%

Every case has exactly one mechanical terminal projection. Every
`judge_eligible` case has a legal EvidenceBundle and trace ID.
`source_unverifiable` and `invalid` are terminal and are not sent to the
semantic judge. The Gate does not prepopulate semantic sufficiency fields.

## Isolation and closure

Frozen Evaluation was not accessed. Stage 4B and all later stages were not
started. Stage 4A-R is `formally_closed_pass`; this Session can be closed.

Artifact hashes are recorded in `STAGE4A_R_FINAL_CLOSEOUT.json`.
