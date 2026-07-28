# F1B Final Closeout

## Decision

F1B completed its single authorized Major Cycle. The evaluation is valid, but
Selector v2 fails both the Product promotion gates and the Stress bundle-hit
regression gate. The final outcome is `rejected_keep_selector_v1`.

The formal selector remains `v3.5-deterministic-fine-selector-v1`.
`v3.5-deterministic-fine-selector-v2` is sealed as a rejected experimental
candidate. F1B is `formally_closed_fail`; no additional F1B cycle is allowed.

## Frozen Before and failure mechanism

The frozen Builder is `stage3b-acronym-w3.5-v1`, the frozen selector is
`v3.5-deterministic-fine-selector-v1`, and the bundle budget is six. Before
performance on Builder-complete cases was 1/6. Product compactness was
83.09555256740688%, and mechanically extracted selector latency was
48.081785714285715 ms, fixing the After ceiling at 96.16357142857143 ms.

P10-A established that the relevance/locality-first per-video greedy assembly
filled the budget with wrong-video, overlapping, or locally redundant windows
while complementary evidence remained available in the CandidateSet.

## Selector v2 and Gold-free freeze

The single behavioral change implemented generic Greedy Marginal Bundle
Assembly using base relevance, query-atom novelty, new-segment coverage,
temporal-region novelty, segment/text redundancy, temporal overlap, and stable
tie-breaks. It uses no Gold, query-specific rule, video-specific rule, model, or
external service.

Gold-free validation passed 37 tests. The six frozen v1 bundles replayed exactly
for Candidate IDs, Bundle ID, score, and Trace ID. Six v2 Development stability
replays were deterministic, stayed within budget, and preserved identity and
timeline fields. The v2 Freeze Seal and post-freeze preflight passed before any
formal After scoring.

## Formal Product Development After

The single formal Product After run produced:

- Builder-complete hits: 0/6 (minimum 4/6, fail)
- Recovered previous misses: 0/5 (minimum 3/5, fail)
- Q006 regressions: 1 (maximum 0, fail)
- Selector-to-Builder span capture: 0/18 = 0% (minimum 50%, fail)
- Selector-to-Builder aspect capture: 0/18 = 0% (minimum 50%, fail)
- Invalid identity/timeline: 0 (pass)
- Maximum selected candidates: 6 (pass)
- Compactness: 99.74638860805051% (pass)
- Mean selector latency: 75.35663095768541 ms (pass)

## Formal Stress After

The single formal Stress After run produced:

- Bundle hits: 0/20 (minimum 1/20, fail)
- Required-span recall: 7.017543859649122% (absolute guardrail pass)
- Required-aspect coverage: 8.333333333333332% (absolute guardrail pass)
- Invalid identity/timeline: 0 (pass)
- Maximum selected candidates: 6 (pass)
- Compactness: 98.6058119777711% (pass)
- Mean selector latency: 81.47559789940715 ms (pass)

## Evaluation validity and scope

Gate Freeze and Selector v2 Seal hashes are valid. Builder, identity contract,
canonical matcher, Development Gold, Product inputs, Stress inputs, bundle
budget, and Mechanical Gate were unchanged. Product and Stress formal run counts
are exactly one each. Stress retained nonzero projected span/aspect coverage, so
the failed bundle outcomes are not a systemic all-zero projection defect.

Frozen Evaluation was not accessed. Stage 4A-R was not started.

## Closure

- Outcome: `rejected_keep_selector_v1`
- Formal selector: `v3.5-deterministic-fine-selector-v1`
- Experimental v2: `frozen_rejected_candidate`
- Major Cycles used: 1/1
- Additional F1B cycles: prohibited
- F1B status: `formally_closed_fail`
- Next stage: `Stage4A_R`
- Stage 4A-R status: `not_started`
- Session can be closed: yes

Machine-readable gate results, validity checks, paths, and hashes are recorded
in `F1B_FINAL_CLOSEOUT.json`.
