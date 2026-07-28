# F1A Candidate Builder Major Cycle Blocking Report

Status: `blocked_invalid_cycle`

The single authorized Major Cycle reached its Implementation Freeze Seal, then
the sealed Development replay failed on `PQS_V1_Q014`. Its persisted frozen
SearchCandidateSet has the authorized `no_supported_subtitle` source terminal,
but the sealed scoring runner propagated `EvidenceContractError` instead of
emitting the required complete source-unverifiable terminal.

## Contract consequence

- The Builder implementation, configuration, tests, and scoring runner remain
  byte-identical to the Implementation Freeze Seal.
- No Development Gold semantic file was opened; the failure occurred while
  constructing the 14 frozen runtime outputs.
- One Development scored-run attempt was made and did not complete.
- Stress scoring was not started.
- No retry, scorer repair, post-seal behavior change, parameter change, or
  second Major Cycle is permitted.
- Major Cycles used: 1. Major Cycles remaining: 0.

## Preserved evidence

Before metrics and Stress Before were frozen before implementation. The
Gold-free P8 replay completed with 3,504 candidates, zero invalid candidates,
unchanged caps, and at most four swaps per query. Fifty-one directly runnable
mechanism and contract tests passed. The partial sealed Development run
persisted swap traces through `PQS_V1_Q013`; it stopped at `PQS_V1_Q014`.

## Change and access status

Candidate Builder source and its authorized configuration/tests were changed
before the seal. Retrieval, Router, Anchor Discovery, Selector, Mechanical Gate,
Query, Split, Development Gold, and Frozen Evaluation Gold were not changed.
Frozen Evaluation Gold was not opened. F1B, Stage 4, and P10 were not started.

The effective Builder candidate remains `stage3b-acronym-w3.5-v1` pending
V3.5-B review. F1A is not closed by Codex.
