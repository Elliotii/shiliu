# V3 Stage 6B Gold Lock Blocking Report

Classification: **Human Review Required**  
Stage 6B state: **Part A stopped; Part B not started**  
Snapshot ID: `20260720T094346Z_c7663365`

## 1. Blocking condition

The deterministic `R_title` / `U_title` evidence-availability audit found five candidates labeled by the human ledger as `U_title / unjudged_due_to_missing_content` even though the immutable Stage 6A snapshot contains a present, parseable, hash-matching authoritative raw-subtitle artifact for each video. Each video also has one or more `transcript_chunk` retrieval units in the snapshot.

The Stage 6B instruction requires an immediate stop when an `R_title` or `U_title` candidate has reviewable body evidence. Codex therefore did not reinterpret any semantic label, did not create Locked Gold, and did not run formal metrics.

## 2. Incremental human re-review list

| Query | Video | BVID | Prior human semantic label | Raw subtitle evidence | Snapshot transcript chunks | Required human decision |
|---|---:|---|---|---|---:|---|
| Q02 — `RAG` | 3 | `BV1ToTy6tEyc` | `U_title` | status `ok`; 32 parsed segments; SHA-256 matches manifest | 2 | Review the frozen raw subtitle and decide `R_evidence` or `N`; retain `U_title` only if the content is affirmatively unusable, with an explicit reason. |
| Q07 — `Claude Code 记忆机制` | 44 | `BV1ekdhBnEra` | `U_title` | status `ok`; 21 parsed segments; SHA-256 matches manifest | 1 | Review the frozen raw subtitle and decide `R_evidence` or `N`; retain `U_title` only if the content is affirmatively unusable, with an explicit reason. |
| Q07 — `Claude Code 记忆机制` | 45 | `BV1XrEZ6NEuD` | `U_title` | status `ok`; 394 parsed segments; SHA-256 matches manifest | 8 | Review the frozen raw subtitle and decide `R_evidence` or `N`; retain `U_title` only if the content is affirmatively unusable, with an explicit reason. |
| Q07 — `Claude Code 记忆机制` | 93 | `BV15HXCBkEKY` | `U_title` | status `ok`; 1,082 parsed segments; SHA-256 matches manifest | 20 | Review the frozen raw subtitle and decide `R_evidence` or `N`; retain `U_title` only if the content is affirmatively unusable, with an explicit reason. |
| Q07 — `Claude Code 记忆机制` | 108 | `BV1KJ61BBEB1` | `U_title` | status `ok`; 523 parsed segments; SHA-256 matches manifest | 10 | Review the frozen raw subtitle and decide `R_evidence` or `N`; retain `U_title` only if the content is affirmatively unusable, with an explicit reason. |

Artifact paths are rooted under:

```text
/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts
```

No semantic inference from those subtitles was performed in this execution.

## 3. Deterministic checks completed before the stop

- All required Stage 6B inputs exist and parse.
- The decision ledger contains 24 unique query records covering Q01–Q24.
- The ledger partitions all 452 pooled Query–Video candidates exactly once: `R_evidence=102`, `R_title=6`, `N=335`, `U_title=9`, current OOS `=0`.
- The immutable Snapshot database exists and its SHA-256 equals manifest value `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.
- `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned zero violations.
- `retrieval_units = retrieval_units_fts = retrieval_dense_vectors = 1,555` as read from the snapshot rather than hard-coded.
- All 452 candidates satisfy snapshot default eligibility: `archived=false` and `ignored=false`.
- No candidate violates the explicit filters for Q19–Q24. The implementation uses inclusive time bounds: `favorite_time >= from` and `favorite_time <= to` against integer Unix-second `favorite_time` values.
- Q04 complete pool does not contain Video 125. The candidate suggestion/review-packet reference to Video 125 is the known isolated cross-file inconsistency; Video 125 was not added to Q04.
- All six `R_title` occurrences lack raw subtitles and transcript chunks in the snapshot.
- The other four `U_title` occurrences—Q07/Video 112, Q09/Video 23, Q22/Video 142, and Q23/Video 41—lack raw subtitles and transcript chunks and remain consistent with missing-content status.

The later Q10 artifact/segment gate and full ten-interval integrity gate were not used to authorize locking because the earlier evidence-availability hard stop had already failed.

## 4. Required remediation

A human reviewer must issue an amended `eval_gold_review.decisions.jsonl` decision for exactly the five rows above. The amended ledger must still partition the same 452-row complete pool exactly once and must explain any decision to retain `U_title` despite the available frozen subtitle.

After the amended ledger is supplied, rerun Part A from the beginning against the same immutable Snapshot. Do not merge these candidates into Gold based on this report alone.

## 5. Prohibited outputs and stop boundary

The following were not created:

```text
research/v3_eval/eval_queries.locked.jsonl
research/v3_eval/eval_gold.locked.jsonl
research/v3_eval/gold_lock_audit.json
research/v3_eval/GOLD_LOCK_SUMMARY.md
research/v3_eval/eval_per_query_results.jsonl
research/v3_eval/eval_results.json
research/v3_eval/eval_results.csv
V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md
V3_CLOSEOUT.md
```

No formal Stage 6B metrics, retriever comparison, failure analysis, routing change, retrieval change, or product change was performed.
