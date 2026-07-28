# V3.5 Stage 3A Reachability and Conditional Eval Addendum

Status: **Frozen non-destructive addendum**  
Applies to: Stage 3A Development Eval only  
Does not modify: `research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md`

## 1. Reachability Track (Track A)

Track A is the end-to-end path. Its only retrieval input is the frozen V3
`SearchCandidateSet` from Development Execution Manifest v1. It records, separately:

- `target_video_reachable`
- `video_candidate_reachable`
- `transcript_chunk_reachable`
- `candidate_builder_coverage`

Failure attribution is ordered and exclusive at the first failed boundary:

1. target video absent from the frozen set: `upstream_retrieval_failure`;
2. target video present but a future Candidate Builder produces no covering candidate:
   `candidate_generation_failure`;
3. a covering candidate exists but a future Selector fails to select it: `selector_failure`.

Track A never accepts an Oracle video ID.

## 2. Conditional Fine-evidence Track (Track B)

Track B evaluates the bounded within-video capability conditional on the correct Development
video being known. It is not an end-to-end retrieval result. Its complete input boundary is:

```text
case_id
+ original_query
+ oracle_target_video_id
+ frozen Raw Transcript path
+ frozen Raw Transcript SHA-256
```

The runner validates query and video identity against the Development Manifest, accepts only
the authoritative `subtitle-raw.json`, and rejects extra fields. Gold Segment IDs, Gold start
or end times, Gold Evidence Groups, Supported/Missing Aspects, Sufficiency Labels, and semantic
Reason Codes are forbidden runtime inputs.

`oracle_target_video_id` is Development-Eval-only. Track B output must be labelled conditional
and must never be presented as an end-to-end claim.

## 3. Manifest and Projection Version

The active input remains Development Execution Manifest **v1**, SHA-256
`ef08e5c262d9fc885ab38d81c90f10ce4be6820c31d931c03f0ecdcfe71a534e`.
The reachability audit found no Projection, request-reconstruction, serialization, router,
scope/filter, Snapshot, or Index defect. No Manifest v2 is created.

## 4. Frozen Reachability Findings

- CASE_001: target Video and target Transcript Chunks are reachable.
- CASE_002: a raw Video unit and grouped Video candidate are reachable; no Transcript Chunk was
  recalled. `within_video_path_authorized: true`.
- CASE_003: `true_v3_retrieval_miss`; Track A attribution is
  `upstream_retrieval_failure`.
- CASE_005: `true_v3_retrieval_miss`; Track A attribution is
  `upstream_retrieval_failure`.

The CASE_002 bounded path is exactly the Original Query `MemoryOS`, V3-recalled `video_id=40`,
and that video's frozen Raw Transcript. It may not add videos, search the corpus, accept Gold
segments/times, return the entire transcript as an EvidenceBundle, or modify the V3 set.

## 5. Implementation Boundary

This addendum freezes contracts and validation boundaries only. It does not implement an
Evidence Candidate Builder, micro-window generation, Fine Selector, EvidenceBundle Selector,
Sufficiency Judge, Formal Held-out Eval, API/UI work, Stage 3B, or V4.
