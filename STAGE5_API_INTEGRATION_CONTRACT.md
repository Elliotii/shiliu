# Stage 5 API Integration Contract

Version: `v3.5-stage5-minimal-integration-v1`

## Route

`POST /api/evidence-sufficiency`

The request reuses the Product Search fields (`query`, `mode`, `scope`,
`result_limit`, `max_windows_per_video`, and `filters`) and adds only
`query_language`.

## Response

The aggregate response contains:

- request and Root Trace identities;
- full `SearchCandidateSet` plus a count summary;
- `EvidenceCandidateSet` summary;
- formal `EvidenceBundle` plus display-only evidence projections preserving
  Evidence ID, Video ID/title, Segment IDs, timestamp range, authoritative
  source text, language/type, source identity/version, and selector method;
- independent Mechanical Gate and Semantic Sufficiency objects;
- frozen component versions, stage latency, warnings, and typed errors;
- `final_answer_generated: false`.

Mechanical `source_unverifiable` and `invalid` are terminal and return a null
SufficiencyDecision. They are never projected as Semantic Judge predictions.

Error types are `input_validation_error`, `retrieval_or_resolution_error`,
`mechanical_invalid`, `source_unverifiable`,
`judge_timeout_or_provider_error`, `structured_output_error`, and
`internal_integration_error`. Provider/timeout/parse failures do not become
`insufficient` or `unverifiable`.

`GET /api/evidence-sufficiency/traces/{trace_id}` reads the persisted Root Trace.

