# Stage 3R Blocked — Scoring Identity Mapping

## Accepted facts

- Final Development Corpus identity passed: 31 unique Cases, SHA-256
  `a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148`.
- Runtime Projection and Scoring Projection each contain 31 records.
- Runtime leakage and Held-out access audits passed.
- Track A produced 31 frozen typed terminals; Track B produced 27 frozen typed
  terminals.
- Prediction hashes remain
  `6696f3a83449bdbb5df21f7b841bace705633b718a367dc549990238e9b3b4d4`
  and
  `2f188746ccd432e4fc634592e36cd2f0e04e4c27a2bfb8ce9210483d9b9f83fe`.
- Frozen Runtime source hashes were unchanged. External model and network calls
  were zero.

## Blocking defect

The scorer compared Gold logical Segment IDs (`BV..._seg_000NNN`) directly with
Runtime physical Segment IDs (`segment_<sha256>`). These are two identities for
the same frozen Raw timeline. The missing deterministic ordinal/timeline mapping
caused false zero coverage across all 20 evidence-bearing Track B Cases.

## Disposition

- Current metrics and Failure Attribution are not accepted.
- The emitted F1 recommendation is explicitly invalidated.
- No predictions were modified or rerun.
- A separately authorized Stage 3R rerun must add and test the generic identity
  mapping in Stage 3R scoring orchestration before opening Gold.
- No Candidate Builder, Selector, Retrieval, Source, Gold, or Held-out change is
  authorized by this handoff.

```text
Stage 3R Blocked
Execution Identity or Evaluation Isolation Invalid
Predictions Not Accepted
```
