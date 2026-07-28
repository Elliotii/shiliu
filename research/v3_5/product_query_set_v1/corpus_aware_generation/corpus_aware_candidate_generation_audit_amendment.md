# Corpus-aware Candidate Generation Audit Identity Amendment

## Decision

```yaml
amendment_status: complete
resolved_case: B_actual_metadata
candidate_regeneration_performed: false
candidate_text_changed: false
```

## Verified Facts

- The current Codex session command record shows that the file actually opened for this source was `/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/metadata.json`, using `sed -n '1,220p'`.
- No command in the generation session opened `/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/subtitle-raw.txt`. Its presence in the same directory is not treated as evidence that it was read.
- `metadata.json` is a JSON video-metadata container. Its top-level fields include video identity, title, uploader, description, duration, `subtitle_track`, and an embedded `subtitle_segments` array. Under the amendment contract, the file identity is metadata; embedded subtitle-related fields do not turn the file into the canonical subtitle asset.
- The actual source types retained for `PQC_004` are:
  - metadata: `/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/metadata.json`
  - transcript: `/Users/elliot/Documents/Shiliu/videos/BV1atjU6KEJF/subtitle-raw.txt`
  - AI summary: `/Users/elliot/Documents/Shiliu/videos/BV1qhE26VEbS/summary.refined.md`
- Because `PQC_004` has a separate, genuine transcript basis, its aggregate `source_types_consulted` still includes `transcript` and `transcript_inspection_used` remains `true`.

## Before / After

```yaml
path_before: /Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/metadata.json
path_after: /Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/metadata.json
source_type_before: transcript / official_subtitle_or_asr
source_type_after: metadata / canonical_video_metadata_container
transcript_checked_before: true
transcript_checked_after: false
transcript_body_read_before: true
transcript_body_read_after: false
transcript_inspection_count_before: 17
transcript_inspection_count_after: 16
```

## Files Changed

- `product_query_candidates.internal_basis.jsonl`
  - `PQC_004.internal_source_basis[video_id=6].asset_type`: `transcript` → `metadata`
  - `PQC_004.internal_source_basis[video_id=6].transcript_checked`: `true` → `false`
  - `PQC_004.source_types_consulted`: unchanged because video 12 remains a genuine transcript basis
  - `PQC_004.transcript_inspection_used`: unchanged at `true` for the same reason
- `corpus_aware_candidate_generation.audit.json`
  - removed `BV1o87764Ebs/metadata.json` from `transcript_files_or_items_inspected`
  - reclassified its `read_audit.source_type`
  - changed its `read_audit.transcript_body_read` to `false`
  - retained the path in `allowed_sources_read`
- `corpus_aware_candidate_generation_report.md`
  - changed transcript inspection count from 17 to 16
  - recorded the combined amendment test result
- `tests/test_pqs_corpus_aware_candidate_generation_audit_identity.py`
  - added a focused regression test for the corrected identity and derived count
- `corpus_aware_candidate_generation_audit_amendment.md`
  - added this amendment record

## SHA-256 Before / After

| File | Before | After |
|---|---|---|
| `product_query_candidates.internal_basis.jsonl` | `a53eb58fa445673b37ed6ef67a9bf00c4fbac87f9136767265d96eecaba67e5b` | `66ddc96e9484e9080b8df92f3aaf192a5c73cbe126e65cf5bfb69731e3f1b008` |
| `corpus_aware_candidate_generation.audit.json` | `89a07dd58d88014e103781544bf0666bce41ce8e4bc55eade98c32ed9efc003c` | `5e50946729ec3afd15a114db802142b926be698f9f3d0dc6547a425f6a4f6269` |
| `corpus_aware_candidate_generation_report.md` | `6ea237f87d383589ccbe704aafe5cb3e4046447d63e8b54f7b85b8313f952e06` | `47e5d40aa8d8f7da99edcab0abb3cbf48f2247b8f8abde8a0beeeb3ab2d317fb` |
| `product_query_candidates.user_review.jsonl` | `f72e92373ed5ed93a9a82a7e5f88597c4f8e2bdca7f7f781f98062fcb2601213` | `f72e92373ed5ed93a9a82a7e5f88597c4f8e2bdca7f7f781f98062fcb2601213` |
| `product_query_corpus_inventory.internal.jsonl` | `05e71ce08db5dc92e92035fee3e26ce7156ccfacdb40a4a834d857bb229ffe5f` | `05e71ce08db5dc92e92035fee3e26ce7156ccfacdb40a4a834d857bb229ffe5f` |

## Non-changes

```yaml
candidate_count: 40_unchanged
candidate_ids: unchanged
candidate_queries: unchanged
user_review_file: unchanged
inventory_file: unchanged
candidate_generation_rerun: false
corpus_inventory_rebuilt: false
gold_or_system_results_read: false
formal_pipeline_calls: 0
user_validation_started: false
```

## Mechanical Checks

```yaml
candidate_count_still_40: true
candidate_ids_still_PQC_001_to_PQC_040: true
user_review_hash_unchanged: true
corpus_inventory_hash_unchanged: true
internal_basis_and_user_review_ids_match: true
metadata_json_not_classified_as_transcript: true
transcript_inspection_count_matches_actual_list: true
audit_and_report_counts_match: true
prohibited_pipeline_calls_still_zero: true
```

## Tests

Command:

```bash
.venv/bin/pytest -q \
  tests/test_pqs_corpus_aware_candidate_generation_contract.py \
  tests/test_pqs_corpus_aware_candidate_generation_audit_identity.py
```

Result:

```text
....................                                                     [100%]
20 passed
```

This amendment stops after correcting and validating source identity. It does not begin user validation, regenerate candidates, freeze queries, construct Gold, run evaluation, or call any formal retrieval or evidence pipeline.
