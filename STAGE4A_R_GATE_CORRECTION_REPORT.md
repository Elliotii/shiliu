# Stage 4A-R Mechanical Gate Correction Report

## Scope

Stage 4A-R used the only authorized substantive generic Mechanical Gate revision.
No Builder, Selector, Evidence Identity Contract, canonical matcher, Retrieval,
Auto Router, Query, Gold, Stress input, or semantic-judging behavior changed.

## Before evidence

The unmodified `mechanical-gate-v1` reproduced the historical Product projection:
13 `judge_eligible`, 1 `source_unverifiable`, 0 `invalid`, with no unhandled
exceptions. The formal 20-case Stress replay produced 20 `judge_eligible`, 0
`source_unverifiable`, 0 `invalid`, also with no unhandled exceptions.

Direct negative contract cases exposed a generic terminal-projection defect:
malformed bundles, invalid lineage, manifest mismatch, invalid timeline, and
source unavailability were all represented by the same
`terminal_unverifiable` outcome. This prevented the required mechanical
distinction between an unavailable external authoritative source and an invalid
current artifact.

## Single generic correction

The corrected Gate:

- projects external authoritative-source failures to `source_unverifiable`;
- projects bundle, identity, lineage, timeline, manifest, selector, and
  normalization contract failures to `invalid`;
- retains `judge_eligible` only for mechanically valid, segment-backed bundles;
- adds generic structural checks for unique evidence IDs, non-empty and
  resolvable segment lineage, source versions, timeline run IDs, finite
  non-negative intervals, authoritative source text, source language, video
  identity, and trace identity;
- keeps all terminal cases out of the semantic judge;
- does not calculate sufficiency, supported aspects, missing aspects, conflicts,
  confidence, or a final answer.

The correction is query-, video-, and case-agnostic. The formal corrected
version is `mechanical-gate-v1-r1`. No further Gate behavior correction is
authorized in Stage 4A-R.

## Non-semantic execution repair audit

Before execution initially failed before producing an artifact because the new
runner could not import the frozen-asset verifier as a package. The runner was
changed to load the same verifier by exact file path. This was a path-only
repair and did not consume the behavior-revision allowance.

The Before artifact's `unverifiable_identity_count` instrumentation was corrected
from 1 to 0 for the `no_supported_subtitle` case. A missing supported source is
source unavailability, not an unverifiable Evidence Identity. Terminal counts,
reason codes, Gate behavior, and the recorded Before run were unchanged.
