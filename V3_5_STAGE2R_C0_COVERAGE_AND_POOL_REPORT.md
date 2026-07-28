# Shiliu V3.5 Stage 2R-C0 — Coverage and Pool Report

## Result

```text
Stage 2R-C0 Blocked
Development Expansion Pool Not Safe
```

## Isolation Failure

During initial read-only asset discovery, this Session ran an overly broad repository text scan. The scan returned existing Stage 3 Development execution data containing Case and locked-query/Gold-derived provenance. That asset was outside the C0 authorized input set.

The two explicitly prohibited Query Pool files were not directly opened, but the returned Gold-derived Development data is sufficient to violate the required Gold-blind Session boundary. This Session is therefore contaminated for C0 Case construction and cannot certify any candidate pool it designed.

## Containment

- All generated Candidate Pool, first-batch, coverage, review, generator, and C0 test artifacts were moved out of the formal `stage2r_c0/` handoff location.
- They are retained only for forensic inspection under `research/v3_5/eval_v2/stage2r_c0_unsafe_quarantine_20260723/`.
- The quarantined artifacts must not be approved, sent to Reviewers, or used as Stage 2R-C1 input.
- The formal `research/v3_5/eval_v2/stage2r_c0/` directory contains only the isolation-failure audit.

## Integrity State

- Existing four Pilot adjudications modified: **No.**
- Freeze Manifest modified: **No**; SHA-256 remains `d64d72ebd283fb86d798b9c026a230569d924cdcf2c77471b5a5e0b2c72df394`.
- Reviewer calls: `0`.
- Provider calls: `0`.
- Annotation Reviews created: `0`.
- Agreements created: `0`.
- Human Decisions created: `0`.
- Final Gold created: `0`.
- Stage 2R-C1 entered: **No.**

## Required Recovery

Restart Stage 2R-C0 in a new isolated Session. That Session must read only the four authorized B2 adjudication/audit files, the Freeze Manifest, and an explicitly enumerated Development Source inventory. Repository-wide content searches must be excluded.

The current Session remains permanently ineligible for Primary Review, Secondary Review, human adjudication, judge evaluation, and Held-out evaluation for any C0 Case.

## Final Status

```text
Stage 2R-C0 Blocked
Development Expansion Pool Not Safe
```
