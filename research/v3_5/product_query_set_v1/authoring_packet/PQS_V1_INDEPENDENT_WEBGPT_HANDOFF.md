# Product Query Set v1 — Independent WebGPT Handoff

## Pass 1 — Independent Authoring

Provide only these files first:

- `PQS_V1_PRODUCT_SCENARIO_BRIEF.md`
- `PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md`
- `PQS_V1_INDEPENDENT_AUTHORING_GUIDE.md`
- `independent_query_draft.template.jsonl`

Ask WebGPT to draft 24–30 independent natural Product Queries and complete the blank template. Do not provide Legacy materials during this pass. The internal `pqs_v1_content_map_provenance.jsonl` is private and must not be shared.

## Pass 2 — Legacy Candidate Reconciliation

Only after Pass 1 is complete, provide:

- `PQS_V1_LEGACY_CANDIDATE_PACKET.md`
- `legacy_candidate_review.template.jsonl`

Ask WebGPT to record `absorb`, `revise`, `merge`, `exclude`, or `reserve`, compare Legacy wording with independent drafts, and identify issues for user discussion. It must not validate queries on the user's behalf.

## Final user discussion

WebGPT may present a unified candidate pool, discuss and merge wording, and recommend 20–24 candidates. The user alone records `user_validated_as_plausible: true`. Product Query Set v1 is not frozen here; no Dev/Frozen Eval split, Product Baseline, F1A, or F1B is started.
