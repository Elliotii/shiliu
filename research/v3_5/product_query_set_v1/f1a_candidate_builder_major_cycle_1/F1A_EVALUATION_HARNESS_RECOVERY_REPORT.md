# F1A Evaluation Harness Recovery and Closeout

Status: **complete; rejected_keep_existing_builder**

The original Builder Implementation Freeze remained byte-identical. Recovery
changed only the F1A evaluation runner so the contract-recognized
`no_supported_subtitle` source terminal produces a complete
`source_unverifiable` output without invoking Builder, Selector, or Mechanical
Gate behavior that can raise `EvidenceContractError`. The rule contains no
Query ID, Video ID, Gold label, required span, or required aspect dependency.

## Gold-free validation and runner freeze

The Development dry replay produced 14/14 legal runtime terminals, including
the generic Q014 source terminal, with zero contract errors and zero invalid
terminals. The Stress dry replay produced 20/20 legal outputs with the same
zero-error result. Candidate totals were 3,504 and 5,362 respectively; maximum
swap count remained four. The Evaluation Runner Freeze Seal was generated
before Development Gold semantic access.

## Formal results

The single complete Development score produced 0/13 complete-group coverage,
12 Builder primary failures, 0% required-span recall, 0% required-aspect
coverage, and six regressions among the six frozen prior Builder hits. Candidate
count remained 3,504 and invalid-candidate count remained zero.

The single Stress regression produced 14/20 complete-group coverage, improving
over the frozen 11/20 floor, with 5,362 candidates and zero invalid candidates.

## Decision

Development fails the unchanged quality and no-regression gates, while Stress
passes. The outcome candidate is therefore `rejected_keep_existing_builder`.
The final Builder candidate remains `stage3b-acronym-w3.5-v1`; the frozen F1A
implementation `stage3b-adaptive-swap-w3.5-v1` is rejected after the valid
single Major Cycle.

Builder Major Cycles used: one; remaining: zero. No Builder or Runner behavior
changed after its respective freeze. Retrieval, Router, Anchor Discovery,
Selector, Mechanical Gate, Query, Split, and Gold were unchanged. Frozen
Evaluation Gold was not opened. F1B, Stage 4, and P10 were not started. F1A
formal closure remains pending V3.5-B review.
