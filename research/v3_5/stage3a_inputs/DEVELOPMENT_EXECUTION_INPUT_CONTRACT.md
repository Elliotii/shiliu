# Shiliu V3.5 Development Execution Input Contract

Contract version: `v3.5-development-execution-input-contract-v1`

## Authority Separation

- Development Gold is the semantic evaluation authority. It alone supplies Development labels, Required Aspects, Gold Evidence Groups, and evaluation reason codes.
- `development_execution_manifest.8_cases.locked.jsonl` is the query identity, target identity, and frozen retrieval execution authority for the eight authorized Development Cases.
- Frozen Raw Artifacts are the quote text and timestamp authority.
- Stage 1 Contracts are the source identity, source version, segment identity, timeline, chunk mapping, candidate schema, and replay authority.

The Execution Manifest is not Gold. It must not be interpreted as a label, relevance judgment, sufficiency decision, Aspect definition, or evidence approval.

## Forbidden Semantic Content

The Execution Manifest must not contain semantic evaluation labels, Required Aspects, supported or missing Aspects, Gold Evidence Groups, Gold Segment IDs, semantic evaluation reason codes, support notes, reviewer decisions, or Held-out membership. Operational `reason_codes` inside the frozen `SearchRawUnitCandidate`/`SearchCandidateSet` serialization are search and source-mapping contract fields only; they are not Gold reason codes.

## Frozen Development Membership

Only these Cases are authorized:

```text
CASE_001 CASE_002 CASE_003 CASE_005 CASE_012 CASE_013 CASE_015 CASE_017
```

No other Primary or Reserve Case may be added to the execution input.

## Search Execution Contract

- SearchCandidate contract: `v3.5-search-candidate-v1`
- Router: the frozen `SearchPlanner` has no exported version constant, so its honest identity is `unversioned:SearchPlanner@sha256:0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e`.
- Request: lexical, all scopes, result limit 10, raw/per-channel limit 50, at most 2 windows per video, no filters.
- Grouping: `v3-temporal-consolidation-v1`
- Presentation: `v3-product-presentation-v1`
- Fusion registry identity: `v3-stage2-rrf-v1` (not executed by the lexical request)
- Trace policy: `v3.5-search-trace-policy-v1`, persistence disabled.
- Snapshot: `20260720T094346Z_c7663365`; the original database is never opened for writes by the projection generator. Each generation searches an independent working copy.

The ordered `raw_unit_candidates` and `video_candidates` arrays are the canonical frozen candidate payload. Runtime UUID trace IDs, runtime timing, and creation timestamps are deliberately excluded from the locked serialization and stable identity.

## Stable Identity

`search_candidate_set_id` is SHA-256 over canonical UTF-8 JSON containing exactly the SearchCandidate contract version, Snapshot database hash, search configuration identity, query ID, Original Query, and ordered candidate payload. Canonical JSON uses sorted object keys, compact separators, preserved list order, normalized LF newlines, and no runtime timestamp.

## Fresh Stage 3A Read Whitelist

A fresh isolated Stage 3A implementation session may read only:

```text
research/v3_5/gold/development_gold.8_cases.locked.jsonl
research/v3_5/stage3a_inputs/development_execution_manifest.8_cases.locked.jsonl
research/v3_5/stage3a_inputs/DEVELOPMENT_EXECUTION_INPUT_CONTRACT.md
research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md
research/v3_5/gold/HELDOUT_ISOLATION_CONTRACT.md
src/shiliu/evidence/contracts.py
src/shiliu/evidence/source.py
src/shiliu/evidence/authority.py
src/shiliu/evidence/mapping.py
the frozen Snapshot database and its declared Raw Artifacts
research/v3_eval/artifact_manifest.jsonl
```

It must not read the full query registry, Master Gold, Held-out Gold, adjudicated master decisions, Human Review assets, master candidate metadata, or review packets. The lock and audit are projection verification artifacts, not Stage 3A semantic inputs.

## Isolation

This projection session is not eligible for Stage 3A implementation. Stage 3A must begin in a fresh session and may use this Manifest only as execution input alongside the separately authorized Development Gold, Stage 1 Contracts, Snapshot, and Raw Artifacts.
