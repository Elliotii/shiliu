# P8 Scoring Amendment Report

## Identity

P8 Attempt 3's fourteen Predictions and fourteen Traces remain immutable.
Prediction SHA-256 is `b34f173ac99208f4adb72966880ab7e9cf97d3e27157084792502f103e709038` and Prediction Seal SHA-256 is
`069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617`. DEVELOPMENT_GOLD_V1 Seal SHA-256 is
`1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a`. Frozen Gold was not opened.

## Generic scoring repair

`candidate_builder_failure` now requires Retrieval success, a reviewable
authoritative source, at least one Gold-defined acceptable evidence group,
constructible material evidence, and no complete group in the CandidateSet.
The generic terminal `gold_defined_evidence_absent` applies when reviewable
Development Gold explicitly has no constructible material evidence. No Query,
Case, or Video ID participates in this rule.

`PQS_V1_Q017` is therefore amended from `candidate_builder_failure` to
`gold_defined_evidence_absent`.

## Metric amendment

| Metric | Original | Amended |
|---|---:|---:|
| Builder complete-group coverage | 6/14 (0.428571) | 6/13 (0.461538) |
| Builder required-span recall macro | 0.653846 | 0.653846 |
| Builder required-aspect coverage macro | 0.607143 | 0.653846 |
| Builder primary failures | 7 | 6 |
| Selector bundle hit | 1/14 (0.071429) | 1/13 (0.076923) |
| Selector required-span recall macro | 0.121795 | 0.121795 |
| Selector required-aspect coverage macro | 0.113095 | 0.121795 |

Complete Group, Span Recall, Aspect Coverage, and Builder Primary Failure each
carry their own explicit numerator, denominator, eligibility count, excluded
IDs, and exclusion reason in `p8_scoring_amendment.scores.json`.

Retrieval and Gate metrics are byte-for-value unchanged. Candidate count,
window width, latency, source/language breakdowns, selected count,
compactness, and redundancy are also unchanged because no Product Component
was rerun.

## Primary attribution

Amended distribution:
`{"candidate_builder_failure": 6, "deterministic_selector_failure": 5, "end_to_end_bundle_hit": 1, "gold_defined_evidence_absent": 1, "source_unverifiable": 1}`.

Every one of the fourteen queries has exactly one eligibility-valid primary
outcome.

## Supersession and boundary

The original scoring assets remain present and are marked
`superseded_by_scoring_amendment` for reason
`builder_failure_eligibility_defect`. The amended baseline is:

`P8 Attempt 3 Frozen Prediction Set + P8 Scoring Amendment v1`.

F1A entry signal remains true because six real Builder-primary failures remain.
P9 restart readiness is true only after V3.5-B accepts this Amendment. P9 was
not restarted; F1A/F1B remain unauthorized; Stage 4 was not started.
