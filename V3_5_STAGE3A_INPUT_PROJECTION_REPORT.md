# Shiliu V3.5 Stage 3A Input Projection Report

## 1. Result

Classification: **Eval Contamination Risk**.

The requested Development-only execution assets are complete and mechanically valid: eight authorized records, deterministic frozen V3 SearchCandidateSets, lock, audit, contract, tests, and handoff documentation. The audit has `errors: []`. However, an initial broad `rg` discovery command accidentally exposed one CASE_015 line from each of two forbidden full semantic assets (`master_gold.18_cases.locked.jsonl` and `review_decisions.master.18_cases.adjudicated.jsonl`). The line was byte-value-equivalent in semantic content to the already authorized Development Gold CASE_015 record and was not used as a projection source, but the access violates the session read boundary. This report therefore does not claim the stronger `Accepted for Stage 3A Input Handoff Candidate` session classification.

## 2. Scope Compliance

Implemented only the execution-input projector, locked manifest, audit, contract, and minimum tests. No Evidence Candidate Builder, Fine Selector, EvidenceBundle Selector, Sufficiency Judge, tuning, Held-out evaluation, API/UI, provider, LLM, network, or V4 work was started. No frozen retrieval behavior was modified.

The accidental forbidden-file discovery is the sole scope-compliance exception and is explicitly recorded in the machine audit warning.

## 3. Repository Before / After

Before identity:

```text
repository: /Users/elliot/new-systems/agent-job-prep/Shiliu
branch: codex/v3-domain-completion
HEAD: 8287c8d92378b87290274d02605cdc704cb8c470
```

The repository began dirty with pre-existing tracked and untracked work. The complete before state and authorized input hashes are stored outside the repository under `/tmp/shiliu_v3_5_stage3a_input_projection_before/`. This session did not modify existing Retrieval, Gold, Snapshot, Raw Artifact, or Stage 1 files. Its authorized changes are the projector helper, one test module, `research/v3_5/stage3a_inputs/**`, this report, and `V3_5_CURRENT_STATE.md`.

## 4. Development Membership

`development_gold.8_cases.locked.jsonl` was verified at required SHA-256 `5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0`. Exact ordered membership is:

```text
CASE_001 CASE_002 CASE_003 CASE_005 CASE_012 CASE_013 CASE_015 CASE_017
```

The manifest contains eight unique records and no other Case.

## 5. Metadata Sources

- Development membership: `research/v3_5/gold/development_gold.8_cases.locked.jsonl`, `case_id` only.
- Original Query, case type, target video ID/BVID: `research/v3_5/master_case_candidates.jsonl`.
- Query identity: `research/v3_eval/eval_queries.locked.jsonl`, exact `query` to `query_id` join only. This minimum frozen query asset was necessary because seven selected master candidate rows had no query ID; the conditional exception in the execution brief authorized this use.
- Packet consistency: `research/v3_5/review_packet_manifest.json` metadata.
- SearchCandidate construction: `src/shiliu/evidence/search.py`, Stage 1 contracts, frozen retrieval, Snapshot, and artifact manifest.

No field from the accidental forbidden-file matches was used.

## 6. Query and Target Projection

| Case | Type | Query ID | Original Query | Target |
|---|---|---|---|---|
| CASE_001 | query_video | Q01 | MCP | 78 / BV1G29EBGE8b |
| CASE_002 | query_video | Q03 | MemoryOS | 40 / BV1oa6uBXE8J |
| CASE_003 | query_video | Q06 | MCP 与 Function Calling 的区别 | 83 / BV1qTYizcEN3 |
| CASE_005 | query_video | Q16 | 哪些内容讨论了 Agent 评测信号设计？ | 51 / BV1qhE26VEbS |
| CASE_012 | query_video | Q01 | MCP | 88 / BV1TxwQz5E4B |
| CASE_013 | query_video | Q03 | MemoryOS | 38 / BV1z6SXBzEYh |
| CASE_015 | query_video | Q07 | Claude Code 记忆机制 | 137 / BV1ZA93BtEKW |
| CASE_017 | query_corpus | Q14 | 量子纠错表面码阈值如何计算？ | null / null |

CASE_017 has `query_corpus_control=true`; all seven query-video Cases have both target identities.

## 7. Frozen Search Execution

All queries used the same request: lexical mode, all scope, requested limit 10, per-channel/raw limit 50, two windows per video, empty filters. SearchCandidate contract is `v3.5-search-candidate-v1`; lexical identity is `v3-stage1-lexical-v1`; dense provider registry identity is `v3-qwen3-embedding-provider-v1`; fusion registry identity is `v3-stage2-rrf-v1`; grouping and presentation are `v3-temporal-consolidation-v1` and `v3-product-presentation-v1`. SearchPlanner has no exported version constant, so the router is honestly recorded as unversioned and bound to planner SHA-256 `0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e`.

Trace persistence was disabled. Each generation copied the frozen database to a separate temporary working database. Snapshot SHA-256 before and after remained `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.

## 8. SearchCandidateSet Serialization

Each manifest record retains the complete ordered `SearchRawUnitCandidate` and `SearchCandidateVideo` serialization, including ranks, scores, retrieval methods, mapping outcomes, eligibility, source identities/versions, segment identities, windows, and product grouping. It is not a count, top-ID summary, or trace reference.

Random trace UUIDs, runtime timings, and creation timestamps are not candidate payload and are excluded to preserve reproducibility. Candidate arrays retain their frozen list order; object keys use canonical sorting.

## 9. Stable Set Identity

Each set ID is SHA-256 over canonical JSON of contract version, Snapshot hash, configuration identity, query ID, Original Query, and ordered candidates. Search configuration identity is `0afedb3411774894ccde7a95ffe2e3796e12d30f5bf5019728dd552e23719d62`.

Cases sharing the exact same query and execution configuration intentionally share a set ID: CASE_001/CASE_012 and CASE_002/CASE_013. Target identity is Case metadata and is not part of the specified SearchCandidateSet identity formula.

## 10. Development Execution Manifest

Path: `research/v3_5/stage3a_inputs/development_execution_manifest.8_cases.locked.jsonl`

```text
records: 8
SHA-256: ef08e5c262d9fc885ab38d81c90f10ce4be6820c31d931c03f0ecdcfe71a534e
```

Candidate counts by Case are: CASE_001 50 raw/10 video; CASE_002 2/2; CASE_003 0/0; CASE_005 0/0; CASE_012 50/10; CASE_013 2/2; CASE_015 0/0; CASE_017 0/0. Empty sets are deterministic frozen lexical outcomes, not fabricated candidates.

## 11. Manifest Lock

`development_execution_manifest.lock.json` records the manifest hash/count/membership, Development Gold hash, Snapshot and artifact hashes, Stage 1 versions, full search configuration and its identity, per-Case set IDs, forbidden semantic fields, limitations, and a non-identity `locked_at` value.

Artifact manifest SHA-256 is `36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f`.

## 12. Projection Audit

`development_execution_manifest.audit.json` reports `errors: []`. It verifies record membership, query/target invariants, candidate schemas and order, set identity, chunk-unit resolution, source identity validity, input hashes, no frozen DB write, two-run byte identity, and absence of semantic Gold/Held-out fields.

It also carries the mandatory warning about the two accidental forbidden-file line exposures. Operational SearchCandidate `reason_codes` remain only where required by the frozen search/source mapping schema; no semantic Gold reason code field was copied.

## 13. Determinism Verification

Generation A and Generation B used independent temporary database copies and fresh in-memory trace UUIDs. After canonical projection, their Manifest bytes, SHA-256, all set IDs, and candidate ordering were identical. The committed locked Manifest also matches a later independent two-generation test.

## 14. Functional Examples

Query-video example, CASE_001:

```text
query_id: Q01
original_query: MCP
target_video_id: 78
target_bvid: BV1G29EBGE8b
SearchCandidateSet ID: 5f94b48e019504e751502e3b1fce7bf6ff331a7a6d89d7cede09d6f3d7f2e531
candidate count: 50 raw / 10 product videos
top raw identities:
  transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_6c982f17915950d79bd4ab0f296e00ee
  transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_b054f1bd553c27a5e404f8c761765571
  video:bilibili:BV1G29EBGE8b:p1
```

Query-corpus example, CASE_017:

```text
query_id: Q14
original_query: 量子纠错表面码阈值如何计算？
target_video_id: null
target_bvid: null
query_corpus_control: true
SearchCandidateSet ID: 587782d9c8e809e530d76d197c3a40d383e85a2f85a605c12db2cdab7a89392c
candidate count: 0 raw / 0 product videos
```

## 15. Tests and Regression

The new targeted module covers schema, exact eight-Case membership, query/target identity, corpus null target, both candidate schemas, stable set ID, canonical serialization, forbidden semantic/held-out fields, hashes, two-run reproducibility, and no Snapshot write. Targeted result: 5 passed. Full repository regression: 582 passed; only the existing Starlette/httpx and multiprocessing fork deprecation warnings were reported.

## 16. Snapshot / Stage 1 / Gold Integrity

- Snapshot SHA-256 before/after: unchanged at `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.
- Development Gold: unchanged at required hash `5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0`.
- Artifact manifest: unchanged at `36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f`.
- No Stage 1 Contract, Retrieval, Snapshot, Raw Artifact, or Gold file was modified.

## 17. Isolation Statement

This projection session is not eligible for Stage 3A implementation. Its controlled metadata access and the recorded accidental forbidden-file line exposures make a fresh isolated session mandatory. No Held-out Gold content was read, copied, evaluated, or emitted.

## 18. Current State Update

`V3_5_CURRENT_STATE.md` now records that the missing Development execution inputs have been projected and locked, while preserving the isolation warning and the rule that Candidate Builder remains unimplemented.

## 19. Next Stage 3A Handoff

A fresh Stage 3A session must use only the whitelist in `DEVELOPMENT_EXECUTION_INPUT_CONTRACT.md`. It must not read this session's broad candidate sources, query registry, Master/Held-out Gold, adjudication records, or Human Review assets. It may begin Candidate Builder work only after accepting the manifest hash and confirming the fresh-session boundary.

## 20. Exact Commands

```bash
pwd -P
git status --short --branch
git branch --show-current
git rev-parse HEAD
git diff --name-status
git diff --cached --name-status
git ls-files --others --exclude-standard
shasum -a 256 research/v3_5/gold/development_gold.8_cases.locked.jsonl research/v3_5/master_case_candidates.jsonl research/v3_5/review_packet_manifest.json research/v3_eval/eval_queries.locked.jsonl research/v3_eval/artifact_manifest.jsonl /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_v3_5_stage3a_input_projection.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

Generation itself calls `write_projection_assets(...)` from `src/shiliu/eval_v3_5/stage3a_inputs.py` twice on independent temporary Snapshot copies and fails closed on any byte difference.

## 21. Stop Statement

Shiliu V3.5 Development Execution Manifest projection is complete.

The locked Development-only execution input contains the Original Queries, target identities and deterministic frozen V3 SearchCandidateSets required by Stage 3A.

No semantic Gold, Held-out label, Held-out Evidence, Candidate Builder, Fine Selector, Sufficiency Judge, Formal Eval, API/UI or V4 work was started.

This projection session is not eligible for Stage 3A implementation. A fresh isolated Stage 3A session is required.
