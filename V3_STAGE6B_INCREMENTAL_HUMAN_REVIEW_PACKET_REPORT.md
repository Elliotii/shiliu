# V3 Stage 6B Incremental Human Review Packet Report

Classification: **Ready for Incremental Human Review**

## 1. Outcome

The requested frozen evidence packet was generated for exactly five Query–Video pairs. It contains all 41 snapshot transcript chunks with complete text, deterministic within-video Lexical/Dense/Hybrid highlights, raw-subtitle boundary verification, and blank human decision forms. No semantic label was changed or suggested.

## 2. Authoritative identity

- Snapshot ID: `20260720T094346Z_c7663365`
- Snapshot DB: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db`
- Snapshot DB SHA-256 before: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`
- Snapshot DB SHA-256 after: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`
- Artifact root: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts`
- Git branch: `codex/v3-domain-completion`
- Git HEAD: `8287c8d92378b87290274d02605cdc704cb8c470`

## 3. Delivered evidence

| Query | Video | BVID | Raw segments | Transcript chunks |
|---|---:|---|---:|---:|
| Q02 | 3 | `BV1ToTy6tEyc` | 32 | 2 |
| Q07 | 44 | `BV1ekdhBnEra` | 21 | 1 |
| Q07 | 45 | `BV1XrEZ6NEuD` | 394 | 8 |
| Q07 | 93 | `BV15HXCBkEKY` | 1082 | 20 |
| Q07 | 108 | `BV1KJ61BBEB1` | 523 | 10 |


Total transcript chunks: **41**.

Every chunk matched an authoritative raw-subtitle start boundary, end boundary, and exact reconstructed text. Video 3 is marked with the mechanical warning `asr_machine_transcription_may_contain_recognition_errors`. Video 44 is marked `raw_subtitle_partial_coverage_36.680_of_3609_seconds` because its frozen raw subtitle covers only `0.100–36.680s` of a 3,609-second video. These are source-quality notices, not relevance judgments. No structural boundary, empty-text, Unicode replacement-character, or reconstruction warning was found.

## 4. Retrieval highlight controls

- Candidate domain: only all transcript chunks belonging to the current target video.
- Lexical: frozen FTS5 trigram index, phrase query, negated BM25; non-hits are `null`.
- Dense: pinned `Qwen/Qwen3-Embedding-0.6B` query provider and frozen stored vectors.
- Hybrid: frozen `v3-stage2-rrf-v1`, `rrf_k=60`.
- Provider load count: `1`; one process-scoped provider reused for both unique queries.
- No Search API or trace-writing path was used.

## 5. Integrity

- Snapshot SHA-256 unchanged: `true`.
- Live protected Product/Index hashes unchanged during extraction: `true`.
- Live counts before/after: `{"retrieval_dense_vectors": 1555, "retrieval_units": 1555, "retrieval_units_fts": 1555, "videos": 144}` / `{"retrieval_dense_vectors": 1555, "retrieval_units": 1555, "retrieval_units_fts": 1555, "videos": 144}`.
- Live trace counts before/after: `{"presentation": 52, "raw": 82}` / `{"presentation": 52, "raw": 82}`.
- Live Product database, Live artifacts, and Live Search API were not used as evidence sources.

## 6. Stage state and stop boundary

```text
Stage 6B Gold Lock:
Blocked pending five-row incremental human review

Incremental Review Packet:
Ready for Incremental Human Review

Formal Stage 6B Evaluation:
Not Started
```

No decision ledger modification, semantic adjudication, Gold lock, formal metric run, retriever change, router change, query change, chunk change, or summary substitution was performed.
