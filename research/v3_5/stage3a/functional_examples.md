# Stage 3A Functional Examples

- CASE_001: frozen target chunk IDs are validated against exact Stage 1 Raw segment IDs, split into run-local micro-windows, deduplicated, scored, and bundled.
- CASE_002: the V3 video-level candidate opens only video 40's frozen Raw transcript, scores the full transcript, and emits at most 32 bounded micro-windows.
- CASE_003 / CASE_005 Track A: the empty frozen SearchCandidateSet returns `upstream_retrieval_failure`; no candidate is fabricated.
- CASE_003 Track B: the manifest target video and frozen Raw transcript produce bounded candidates with `oracle_video_used=true` and `end_to_end_claim_eligible=false`; this is not end-to-end performance.
- Stable identity: repeated selected-config runs produced identical candidate IDs, bundle IDs, and ordering.
- Duplicate/overlap: exact spans merge provenance; high segment-Jaccard or interval-overlap windows are suppressed and retained overlaps record related IDs.
- Source mismatch: an expected/actual version mismatch raises `source_version_mismatch`.
- Missing source: an empty CandidateSet produces typed `upstream_retrieval_failure` and no Evidence.
