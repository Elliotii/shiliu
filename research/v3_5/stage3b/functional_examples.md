# Stage 3B Functional Examples

- Generic acronym policy: an uppercase 2–8 character query token is compacted, compared case-insensitively to compact subtitle tokens, and a generic equal-length one-substitution anchor can retain its bounded local window. No correction dictionary exists.
- CASE_001 regression: deterministic remained a hit in both tracks; every valid structured selection used six Candidates but missed, with 105.88–108.18 seconds of union duration.
- CASE_002 comparison: the complete CandidateSet was available and deterministic missed. Track A structured output became valid only after repair but also missed; Track B exhausted repair and emitted no Bundle.
- CASE_003 robustness: generic `MCP`/one-substitution anchoring recognized ASR-like acronym variants without a dictionary, but the selected bounded CandidateSet still missed one required segment boundary; coverage stayed 3/4 cases and 6/7 spans, so the selector remained ineligible.
- CASE_005 complementary evidence: all four required spans existed in 14 Candidates. Both Provider attempts failed schema validation, so no valid complementary Bundle was produced.
- Invalid output fixtures cover unknown/duplicate IDs, invalid actions, extra fields, malformed JSON, timeout/failure, one repair success, and repair exhaustion.
- Reconstruction maps returned IDs back to immutable Candidates, sorts locally, restores Raw-derived text/time, computes interval-union duration, and hashes a stable Bundle ID.
