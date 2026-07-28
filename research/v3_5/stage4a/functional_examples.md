# Stage 4A Functional Examples

These examples exercise only mechanical state. No evidence text semantics, Gold field, Provider, or model is a gate input.

## A. Track A retrieval failure

An empty frozen `SearchCandidateSet` resolves to `upstream_retrieval_failure`, then `terminal_unverifiable` and `retrieval_action`.

## B. Candidate generation failure

An available target video whose frozen Stage 3 final CandidateSet is incomplete resolves to `candidate_generation_failure`, then `terminal_unverifiable` and `evidence_resolution_action`.

## C. Selector failure

A CandidateSet with no valid deterministic Bundle (including selector failure, abstain, no selected Bundle, and invalid selection reference aliases) normalizes to `selector_failed`, then `terminal_unverifiable` and `selector_recovery_action`.

## D. Source failure

`raw_source_unavailable`, `no_supported_subtitle`, `title_only`, `source_unreadable`, and `language_unresolved` terminate as `unverifiable` with `source_recovery_action`.

## E. Valid Bundle

A normalized `v3.5-evidence-bundle-v1` Bundle selected by `v3.5-deterministic-fine-selector-v1`, referencing existing Raw-derived Candidates under consistent frozen identities, becomes `judge_eligible`. Stage 4A emits no semantic SufficiencyDecision.

## F. Integrity failure

A source-version mismatch, execution/search identity mismatch, normalization failure, or invalid Bundle reference terminates as `unverifiable` with `data_integrity_action`.

## G. Stable identity

Repeating the same gate call yields the same canonical JSON bytes, field ordering, and SHA-256 Gate Decision ID. Trace IDs, clocks, UUIDs, process ordinals, and database IDs are excluded from decision identity.

## H. S0 / S1 difference

After predictions froze and Development Gold opened, readable-insufficient CASE_012 and CASE_013 were `sufficient` under both S0 and S1 because their Bundles were mechanically valid. S1 therefore has two insufficient-to-sufficient errors. The Mechanical Gate cannot replace the future Semantic Judge.
