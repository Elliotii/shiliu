# P10-A F1B Entry Gate and Failure Anatomy Audit Report

## Decision

- Q006 control reproduced: **yes**
- Five failure cases examined: **5/5**
- Genuine Selector Failures: **5**
- Identity and scorer preconditions: **all pass**
- F1B Entry Gate: **PASS**
- Authorize the single F1B Major Cycle: **yes, in a later task**
- Frozen Evaluation accessed: **no**
- This audit session can close: **yes**

## Frozen assets and preconditions

The audit used the six sealed P8 traces under
`research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/blind_run/product_initial_baseline.traces/`,
the sealed Development Gold evidence file, formal builder version
`stage3b-acronym-w3.5-v1`, deterministic selector
`v3.5-deterministic-fine-selector-v1`, and Evidence Identity Contract V1.

Contract SHA-256 is
`35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7`.
The freeze Seal is valid, the canonical matcher source hash matches, and all
17 contract tests pass. All six CandidateSets and bundles contain zero invalid
and zero unverifiable identities. The read-only projection freezes:
match contributes; non-match does not; unverifiable does not and is reported
separately; preserved split-window aggregate coverage is allowed by Contract V1.

The frozen Selector was mechanically replayed from every frozen CandidateSet.
For all six cases, selected Candidate IDs, bundle ID, score, and trace ID exactly
match the sealed P8 trace. Configuration is a six-candidate budget with greedy
per-video ranking; candidate tie-break is `(-score, start_time, candidate_id)`
and bundle tie-break is `(-score, bundle_id)`.

## Per-case result

| Case | Candidate count | Candidate complete group | Selected coverage | Classification |
|---|---:|---|---|---|
| PQS_V1_Q006 | 268 | Q006_GROUP_01 | both required spans/aspects; complete group | successful control |
| PQS_V1_Q007 | 249 | Q007_GROUP_01 | 0/3 spans, 0/3 aspects | genuine_selector_failure |
| PQS_V1_Q011 | 296 | Q011_GROUP_01 | 1/4 spans, 1/4 aspects | genuine_selector_failure |
| PQS_V1_Q012 | 275 | Q012_GROUP_01 | 0/3 spans, 0/3 aspects | genuine_selector_failure |
| PQS_V1_Q013 | 265 | Q013_GROUP_01 | 1/3 spans, 1/3 aspects | genuine_selector_failure |
| PQS_V1_Q019 | 254 | Q019_GROUP_01 | 0/3 spans, 0/3 aspects | genuine_selector_failure |

The complete candidate/group/span/aspect identities, selected IDs and segment
IDs, projection counts, overlap pairs, and case reasons are in the per-case
JSONL. No case is a scorer/identity artifact, mixed, or inconclusive.

## Failure anatomy

All five failed bundles consume the full six-candidate budget. Q007 and Q012
select a higher-scoring bundle from the wrong video. Q011, Q013, and Q019 select
the Gold-bearing video but fail to assemble the available complementary time
regions into a complete group. Several selected bundles also contain overlapping
windows. The common mechanism is relevance/locality-first greedy assembly
without enough marginal span/temporal complementarity and redundancy control;
stable tie-breaks reproduce the result but are not themselves shown to cause it.

## F1B Major Cycle recommendation

Authorize one later, bounded **Greedy Marginal Bundle Assembly** cycle. Keep it
deterministic and Gold-free at runtime. Add general query anchor/term coverage,
span and temporal complementarity, redundancy/overlap penalties, and stable
tie-breaks. Do not modify Candidate Builder, Retrieval, Auto Router, Gold,
Evidence Identity Contract, or the six-candidate bundle budget; do not revive
Structured LLM Selector v1.

Stop after this one cycle. Also stop if Q006 regresses, identity/timeline
invalidity becomes nonzero, any required Product gate fails, or the proposed
change escapes the stated component boundary.

## Proposed Product Development gates

- Selector hits on builder-complete cases: before **1/6**, after at least **4/6**
- Recovered previous misses: at least **3/5**
- Q006 regressions: **0**
- Selector-to-builder span capture ratio: at least **50%**
- Selector-to-builder aspect capture ratio: at least **50%**
- Selected candidate budget: at most **6**
- Compactness: absolute drop at most **10 percentage points**
- Mean latency: at most **min(100 ms, 2x Before)**
- Invalid identity/timeline: **0**

Product Development is the promotion authority; Stress is regression/boundary
evidence.

## Frozen Stress Before and proposed gates

The formal Stress Before asset records bundle hit **1/20**, invalid
identity/runtime failures **0**, and selected candidate count **6 in all 20
cases**. It does not record selector required-span recall, required-aspect
coverage, compactness, or selector mean latency. Those omissions are reported
as null rather than fabricated as frozen values.

Proposed exact Stress After gates:

- Bundle hit: at least **1/20**
- Required-span recall: at least **5%**
- Required-aspect coverage: at least **5%**
- Invalid identity/timeline: at most **0**
- Compactness: at least **73.09555256740688%**
- Selected candidate count: at most **6**
- Mean selector latency: at most **100 ms**

The compactness floor is the frozen Product Before compactness
83.09555256740688% minus the permitted 10-point absolute drop. The absence of
four Stress fields is a frozen Stress instrumentation limitation, not a defect
in the six-case Entry Gate projection.

## Scope confirmation and outputs

Frozen Evaluation Gold, queries, predictions, scoring, and failure analysis were
not accessed. No Selector, Builder, matcher, Gold, Retrieval, Router, budget, or
evaluation corpus was changed; no F1B Major Cycle was consumed.

- `p10_a_f1b_entry_gate.per_case.jsonl`:
  `59ad7cd3f335774394f19279ca3547cc587adfd468c17a87c93268edcf1a5f27`
- `p10_a_f1b_entry_gate.audit.json`:
  `947854fe587239bba376cb8d5d163878d1593e3260fd66707e667bd4ef21c46b`

This P10-A audit is complete and the Session can be closed.
