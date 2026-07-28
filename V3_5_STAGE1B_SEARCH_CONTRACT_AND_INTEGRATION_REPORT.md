# Shiliu V3.5 Stage 1B — Search Contract, Source-version Authority and Integration Closure Report

## 1. Stage Result

Candidate classification: **Accepted for Stage 1B Candidate**.

Stage 1B is implemented and verified. Source identity v2, three explicit source-version authorities, frozen-policy replay binding, full 1,412-chunk accounting, a lossless SearchCandidateSet projection, and trace isolation are complete. All 11 Stage 1B tests, all 25 Stage 1 evidence tests, and all 543 repository tests pass. Only the V3.5 Version Session may formally close Stage 1 and authorize Stage 2.

## 2. Scope Compliance

- No FTS5/BM25, embedding, dense index, pooling, normalization, RRF, routing, planning, query classification, chunking, grouping, window, ranking, filter, index lifecycle, retrieval-unit schema, Gold, Snapshot, or formal metric behavior changed.
- The Product Search default remains trace-enabled and returns the same public response. The only retrieval changes are an explicit default-on trace switch and a method exposing the already-computed Raw response beside its existing Product projection.
- No index rebuild, DB migration, historical source-version/segment backfill, Artifact repair, provider, LLM, model download, formal Eval, API/UI, Evidence Candidate Builder, micro-window, Selector, Prompt, Sufficiency, Answer, Agent, Memory, Harness, Translation, or V4 work occurred.

## 3. Repository Before / After

- Root before/after: `/Users/elliot/new-systems/agent-job-prep/Shiliu`.
- Branch before/after: `codex/v3-domain-completion`.
- HEAD before/after: `8287c8d92378b87290274d02605cdc704cb8c470`.
- Before-state: `/tmp/shiliu_v3_5_stage1b_before/manifest.md`; no staged files.
- Pre-existing tracked modifications: `V3_CURRENT_STATE.md`, `src/shiliu/retrieval/__init__.py`, `src/shiliu/retrieval/product_search.py`, `src/shiliu/templates/base.html`, and `src/shiliu/web.py`.
- Stage 1A changes: `V3_5_CURRENT_STATE.md`, Stage 1A report, `src/shiliu/evidence/{__init__,contracts,source,mapping}.py`, and two evidence tests.
- Stage 1B preserved all unrelated pre-existing and Stage 1A assets. Unexpected changes: none.

## 4. Files Created and Modified

Created by Stage 1B:

- `V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md`
- `src/shiliu/evidence/authority.py`
- `src/shiliu/evidence/audit.py`
- `src/shiliu/evidence/search.py`
- `tests/test_evidence_stage1b.py`

Modified by Stage 1B:

- `V3_5_CURRENT_STATE.md`
- `src/shiliu/evidence/__init__.py`
- `src/shiliu/evidence/contracts.py`
- `src/shiliu/evidence/source.py`
- `src/shiliu/evidence/mapping.py`
- `tests/test_evidence_contracts.py`
- `tests/test_evidence_snapshot_regression.py`
- `src/shiliu/retrieval/orchestrator.py`
- `src/shiliu/retrieval/product_search.py`

`product_search.py` already had pre-existing display metadata and jump-URL modifications. Stage 1B changed only the import/type for `RawSearchResponse`, default-on presentation trace control, `search_with_raw()`, and tuple returns from that path. `src/shiliu/retrieval/__init__.py` remained at its intake hash; its pre-existing change was not touched.

## 5. Stage 1A Implementation Review

The required Stage 1A state, four implementation files, and two tests were read before Stage 1B changes. Code and report agreed at intake:

- identity fields were platform/source/part/type/language;
- source version was SHA-256 of exact authoritative JSON bytes;
- segment identity used artifact ID + version + ordinal;
- digest used canonical parsed floats and unchanged text;
- epsilon was `1e-6`;
- run ID used version + run ordinal;
- exact mapping compared chunk ID/unit suffix/start/end/text/content hash/replay count;
- cross-run status was `invalid_cross_timeline_run`;
- SearchCandidateSet was only a draft.

No unreported Stage 1A discrepancy was found. Identity v1 and mapping spellings were intentionally superseded by the authorized Stage 1B lock, not repaired as hidden defects.

## 6. Source Identity v2

Version discipline:

```text
v3.5-source-identity-v1: Stage 1A provisional; superseded before Gold lock
v3.5-source-identity-v2: Stage 1 frozen identity candidate
```

Exact v2 payload:

```json
{
  "artifact_role": "raw_subtitle",
  "part": 1,
  "platform": "bilibili",
  "source_id": "BVID",
  "source_lineage": "human|ai|asr|unknown"
}
```

The payload is serialized as sorted-key, compact UTF-8 JSON with `ensure_ascii=false` and `allow_nan=false`, then SHA-256 hashed with the `source_artifact_` prefix. Language, path, Snapshot ID, CID, DB key, index state, and bytes are excluded. Bytes remain versioned separately.

The Snapshot uses source types as stable origin lineage: AI 1,333 chunks, ASR 14, and human 65. Unknown is the deterministic fallback for an unsupported label. Tests prove language changes do not alter v2 artifact/segment identity; lineage changes do; v1/v2 are distinguishable; and v2 segment IDs are deterministic. No migration is needed because no V3.5 Gold, EvidenceBundle, or persistent Evidence ID exists.

## 7. Source-version Authority Policy

Policy: `v3.5-source-version-authority-v1`.

Snapshot authority (`snapshot_manifest`): select the unique `raw_subtitle` record for the video, validate its BVID/logical source and resolved declared path against the requested source, read its declared SHA-256, hash actual bytes, and require equality. Any logical/path/hash mismatch fails closed as `source_version_mismatch`.

Pinned authority (`pinned_request`): the caller's expected SHA-256 must equal current authoritative bytes. Mismatch returns no mapping and does not adopt, refresh, or fuzzily recover against the current version.

Live authority (`live_current_exact_replay`): require `desired_state=indexed`, lexical state current, and dense state current when the executed mode uses dense; hash current authoritative bytes; then require exact chunk replay. This binds the candidate to the current version. It explicitly does not prove that the historical index was originally built from that version.

Candidate fields retain artifact ID, identity version, version, authority enum, verification flag, expected version, and actual version. When authority succeeded but exact replay failed, the verified binding remains present for diagnosis while the candidate fails closed.

## 8. Chunk Policy and Replay Binding

```text
mapping_version: v3.5-exact-chunk-mapping-v1
source_chunk_policy_version: v3-frozen-transcript-chunk-policy-v1
replay_implementation_version: v3.5-frozen-chunker-replay-v1
```

The mapping imports and calls the existing frozen V3 builder. It does not copy or rewrite it. Exact constants read from code are target 800 characters, maximum 1,200 characters, maximum 120 seconds, and overlap by the last complete segment when a multi-segment chunk is followed by more content.

An unsupported policy or replay version raises `chunk_policy_version_mismatch` before reading/replaying. It never uses the current Chunker to guess an unsupported historical policy.

## 9. Corpus-wide Mapping Audit

The reproducible read-only surface is:

```python
audit_snapshot_chunk_mappings(...) -> MappingAuditSummary
```

It retains terminal counts plus full breakdowns by source type, language, video ID, timeline status, and explicit issues.

| Terminal status | Count |
|---|---:|
| `exact_mapped` | 1,411 |
| `invalid_cross_timeline_chunk` | 1 |
| `chunk_segment_mapping_failed` | 0 |
| `source_missing` | 0 |
| `source_unreadable` | 0 |
| `source_version_mismatch` | 0 |
| `chunk_policy_version_mismatch` | 0 |
| other explicit status | 0 |
| **Total/accounted** | **1,412 / 1,412** |

By source type:

| Type | Exact | Cross-run invalid |
|---|---:|---:|
| AI | 1,333 | 0 |
| ASR | 14 | 0 |
| Human | 64 | 1 |

By language: English 20 exact; Chinese 1,391 exact and 1 cross-run invalid.

By timeline: single-run sources 1,385 exact; multiple-run sources 26 exact and 1 cross-run invalid.

By video: 129 videos contain transcript chunks. All chunks are exact in 128 videos. Video 88 has 26 exact eligible chunks and the one cross-run invalid chunk. Thus all 129 per-video buckets and all 1,412 chunks are represented.

Only issue:

```text
video_id: 88
BVID: BV1TxwQz5E4B
unit_id: transcript_chunk:bilibili:BV1TxwQz5E4B:p1:chunk_cc3222c5f91a7fa074ec5802f8a21799
source_type: human
status: invalid_cross_timeline_chunk
reason: exact replay contains two derived timeline_run_id values
```

This came from the generic run contract; no video-specific rule exists.

## 10. Final SearchCandidateSet Contract

Version: `v3.5-search-candidate-v1`.

Top level freezes contract version, original query, request parameters, raw and presentation trace IDs/persistence, executed mode, query type, fallback state, index identity, Snapshot/runtime corpus identity, ordered raw units, ordered product videos, timestamp, and set-level reasons.

Every Raw unit retains unit/video/type, raw rank/score, method, source/timing metadata, and original order. Video units use `mapping_status=not_applicable`, receive no fake segment mapping, and remain metadata-only.

Transcript units additionally retain v2 artifact identity, source authority fields, segment IDs/ordinals, run ID, mapping status, eligibility, reasons, policy version, mapping version, and replay version. Failed/ineligible units remain at their original raw rank; no following item is promoted.

Product video candidates retain product order, display identity, best unit/score/type, all component Raw unit IDs in Raw order, retrieval methods, product windows, source types, and video-level-hit semantics. Product windows are explicitly not Fine Evidence.

An empty retrieval returns a successful empty set with `no_search_candidate`. `candidate_not_found` is raised only when a caller requests an absent unit from an existing set.

## 11. Search Projection Implementation

`EvidenceSearchService.search_library(ProductSearchRequest) -> SearchCandidateSet` is a read-only boundary in `src/shiliu/evidence/search.py`.

It obtains one `(RawSearchResponse, ProductSearchResponse)` pair from `ProductSearchService.search_with_raw()`, reads full retrieval/source rows for the returned unit IDs, resolves one of the explicit authorities, exact-replays every Transcript unit, and projects Raw/Product views. It never builds an EvidenceCandidateSet, merges segments, constructs micro-windows, selects evidence, changes top-k, or alters V3 ordering.

## 12. Single-execution Evidence

- `ProductSearchService.search()` now delegates to `search_with_raw()` and returns element 2, preserving its external behavior.
- `search_with_raw()` calls `raw_search.search_raw()` exactly once, then runs the existing consolidator and enricher once and returns both views.
- A counting real-Snapshot test confirms one lexical retrieval call per `search_library()`.
- Raw unit IDs, raw scores, and ranks exactly equal the frozen retriever output.
- Existing `search()` and raw-reuse Product paths produce equal video ordering, windows, component IDs, anchors, and display metadata.
- No second independent retrieval or ranking implementation was introduced.

## 13. Trace Persistence Policy

Version: `v3.5-search-trace-policy-v1`.

- Product runtime default: raw and presentation persistence enabled, unchanged.
- Disabled mode: constructors receive `persist_trace=False`; neither trace schema initializer runs; successful/error searches skip both trace writes but still generate one in-memory trace ID.
- Formal Eval: original Snapshot is copied to a writable work DB; enabled traces go only to the copy.
- Replay/projection tests use disabled mode unless trace behavior itself is under test.

Evidence:

| Mode | Raw table/result | Presentation table/result | Ranking/content |
|---|---|---|---|
| Disabled with tables absent | table remains absent; no row; in-memory ID present | table remains absent; no row | baseline |
| Enabled work copy | raw rows `+1` | presentation rows `+1` | equal to disabled |
| Original Snapshot | remains 82 raw / 52 presentation rows | no Stage 1B write | SHA unchanged |

Enabled/disabled tests compare unit IDs, raw ranks/scores/statuses, video IDs/product ranks, and component IDs; they are equal. Only IDs, persistence metadata, timing, and timestamps may differ.

## 14. Status / Error / Reason Contract

Source validation statuses:

```text
valid_single_run
valid_multiple_runs
invalid_segment_time
source_unreadable
```

Mapping statuses:

```text
exact_mapped
invalid_cross_timeline_chunk
chunk_segment_mapping_failed
source_version_mismatch
source_unavailable
chunk_policy_version_mismatch
not_applicable
```

Stage 1A `mapped` and `invalid_cross_timeline_run` are superseded; only `exact_mapped` and `invalid_cross_timeline_chunk` are formal Stage 1 mapping names. The EvidenceSpan validation error also uses `invalid_cross_timeline_chunk`.

Reasons include `source_contains_multiple_timeline_runs`, `source_version_mismatch`, `invalid_cross_timeline_chunk`, `chunk_segment_mapping_failed`, `chunk_policy_version_mismatch`, `raw_subtitle_missing`, `source_unreadable`, `no_search_candidate`, `candidate_not_found`, `index_not_ready`, and `retrieval_failed`. `valid_multiple_runs` remains readable and does not imply final `unverifiable`; four-state mapping belongs to Stage 4.

## 15. Real SearchCandidateSet Example

Simplified real Snapshot query; subtitle body is omitted:

```text
request: query=MCP, mode=lexical, scope=all, result_limit=3
trace: one in-memory UUID; raw and presentation identities equal
executed_mode: lexical
query_type: exact_entity
lexical_index_version: v3-stage1-lexical-v1
raw_count: 50
```

Raw top five remain:

| Raw rank | Unit | Score | Mapping | Eligible |
|---:|---|---:|---|---|
| 1 | video 78 transcript `chunk_6c982…` | 6.1191677542 | `exact_mapped` | yes |
| 2 | video 78 transcript `chunk_b054…` | 5.9709100256 | `exact_mapped` | yes |
| 3 | video 78 metadata unit | 5.8905306390 | `not_applicable` | no |
| 4 | video 43 metadata unit | 5.7775673745 | `not_applicable` | no |
| 5 | video 71 transcript `chunk_2161…` | 5.6552512433 | `exact_mapped` | yes |

Video 78 transcript candidates bind Snapshot version `6555e8b2118e80ae3bf504f543fb6dfd013da65181ab45a9d9df773c4b165b36`. Product top three remain videos 78, 43, and 71; their component IDs are retained in original Raw order. A separate real `ClaudeCode` projection retains video 88's cross-run chunk at its Raw rank with `candidate_eligibility=false`.

## 16. Tests and Regression

Stage 1B targeted:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evidence_stage1b.py
```

Exit 0; 11 collected, 11 passed, 0 failed, 0 skipped, 0 warnings; 8.40s.

All Stage 1 evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evidence_contracts.py tests/test_evidence_snapshot_regression.py tests/test_evidence_stage1b.py
```

Exit 0; 25 collected, 25 passed, 0 failed, 0 skipped, 0 warnings; 8.56s.

Full regression:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

Exit 0; 543 collected, 543 passed, 0 failed, 0 skipped, 7 warnings; 27.03s. The existing 532 tests have no regression; 11 Stage 1B tests were added. Warnings are the existing one Starlette/httpx deprecation and six multiprocessing/fork deprecations.

## 17. Snapshot / Artifact / Eval Integrity

| Asset | Before | After | Result |
|---|---|---|---|
| Snapshot DB | `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1` | same | unchanged |
| video 88 Raw | `cc6afce905dc90ee1c89d1906c2617ba80c4992196c256e5fa8a66db9c0e2f0c` | same | unchanged |
| 372 manifest `status=ok` artifacts | manifest size/hash | all Stage 1 regression checks pass | unchanged |
| 11 canonical Eval/report assets | Stage 1A intake hashes | same | unchanged |

The amended ledger remains `e93fd09bd06151d8665f50a17cc24bc2673105d21886e77b8a4cfa12f7ba0257`. No Eval file was written. Search/trace mutation tests used copied work DBs only.

## 18. V3_5_CURRENT_STATE Update

`V3_5_CURRENT_STATE.md` now records identity v2/v1 supersession, source authority, policy/replay binding, the corpus audit, frozen SearchCandidateSet, trace policy, normalized statuses/reasons, Stage 1B delivery, active limitations, unchanged Eval governance, policy registry, hours, and budget.

It proposes Stage 1 closure for Version Session review. Stage 2 is explicitly not started; V3.5 Eval Protocol is not frozen; Development/Held-out do not exist; Gold annotation has not started; EvidenceCandidateSet is not implemented.

## 19. Findings Ledger

| Type | Finding | Evidence / impact |
|---|---|---|
| Confirmed Fact | Language can be excluded from identity without losing lineage. | v2 migration tests; lineage remains human/AI/ASR/unknown. |
| Confirmed Fact | Snapshot authority is path/logical/hash/byte verified. | Real video 78 match and corrupted-manifest failure tests. |
| Confirmed Fact | Full corpus mapping closes at 1,412/1,412. | 1,411 exact + one known cross-run invalid. |
| Confirmed Fact | SearchCandidateSet preserves Raw/Product order and ineligible ranks. | Real Snapshot and forced mapping-failure tests. |
| Confirmed Fact | Disabled traces cause no trace schema or row writes. | Tables absent before/after; in-memory trace retained. |
| Confirmed Fact | Enabled and disabled substantive results are equal. | Unit/rank/score/status and product/component comparisons. |
| Inference | Live exact replay is an adequate current-version authority but cannot establish historical index provenance. | Retrieval rows have no historical source hash. |
| Unknown | Most Eval files lack an external historical hash authority before V3.5 intake. | No conflict exists; only the amended ledger is historically verified. |
| Blocking Risk | None for Stage 1B. | No unexplained corpus failure or stop condition occurred. |
| Recommendation | Version Session may close Stage 1 and begin Stage 2 governance work. | Contracts and integrity checks are complete; Stage 2 remains untouched. |

## 20. Remaining Risks

- Live authority cannot prove the historical source version used at index-build time; it proves current sync state plus exact current replay only.
- The frozen video 88 cross-run Retrieval Unit remains in V3 by design. Every later consumer must honor `candidate_eligibility=false`.
- Historical replay depends on retaining/supporting the versioned frozen Chunk policy implementation.
- `SHILIU_V3_VERSION_DECISION.md` remains absent locally; this is an authority-document gap, not a hash conflict.
- Search projection is an internal read contract, not yet an API or Evidence Candidate Builder.

## 21. Stage 1 Closure Assessment

Codex proposes Stage 1 closure. The complete chain now exists:

```text
V3 request
→ one frozen retrieval
→ Raw + Product views
→ frozen SearchCandidateSet
→ explicit source-version authority
→ exact policy-bound mapping
→ eligible/ineligible accounting
```

Every frozen Snapshot Transcript Chunk has one terminal state, all failures remain visible, trace-disabled operation is isolated, and V3 ranking behavior is unchanged. Formal closure remains a Version Session decision.

## 22. Stage 2 Inputs

- Treat `v3.5-search-candidate-v1`, identity v2, source-authority v1, timeline v1, mapping v1, frozen chunk policy v1, replay v1, and trace policy v1 as Stage 1 lock candidates.
- Build the V3.5 Eval Protocol and Gold governance against full target-video Raw Transcript, never Candidate output alone.
- Preserve one Master Evaluation Case Set; freeze Development/Held-out before any later tuning.
- Carry `gold_evidence_groups` support into Gold schema design.
- Use corpus audit and 10 existing intervals as regression/provenance evidence only, not as complete Gold or tuning data.
- Do not silently discard ineligible Search candidates when defining later failure attribution.

## 23. Escalation Assessment

No stop condition occurred. Search ranking, second retrieval, Chunk policy change, schema migration, index rebuild, backfill, Artifact/Gold modification, fuzzy mapping, harness binding, unexplained corpus failure, or large trace refactor was not required.

No blocking escalation is requested. The Version Session must decide only whether to accept this candidate and formally close Stage 1.

## 24. Exact Commands Executed

Intake:

```bash
cd /Users/elliot/new-systems/agent-job-prep/Shiliu
pwd -P
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git rev-parse HEAD
git diff --name-status
git diff --cached --name-status
git ls-files --others --exclude-standard
```

Snapshot baseline:

```bash
sqlite3 -readonly /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db "select count(*) from retrieval_units where unit_type='transcript_chunk'; select count(*) from retrieval_search_traces; select count(*) from retrieval_search_presentations;"
```

Integrity:

```bash
shasum -a 256 /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db
shasum -a 256 /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV1TxwQz5E4B/subtitle-raw.json
shasum -a 256 research/v3_eval/eval_queries.locked.jsonl research/v3_eval/eval_gold.locked.jsonl research/v3_eval/eval_gold_review.decisions.amended.jsonl research/v3_eval/gold_lock_audit.json research/v3_eval/human_ledger_amendment_audit.json research/v3_eval/eval_results.json research/v3_eval/eval_results.csv research/v3_eval/eval_per_query_results.jsonl research/v3_eval/failure_cases.md research/v3_eval/V3_EVAL_PROTOCOL.md V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md
```

Tests:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evidence_stage1b.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evidence_contracts.py tests/test_evidence_snapshot_regression.py tests/test_evidence_stage1b.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

Final repository checks:

```bash
git status --short --branch
git diff --name-status
git diff --cached --name-status
git branch --show-current
git rev-parse HEAD
```

## 25. Stop Statement

Shiliu V3.5 Stage 1B execution is complete.

No V3 Retrieval ranking, router, embedding, fusion, chunk policy, grouping, window policy, Gold, Snapshot, Raw Artifact, or Formal Eval result was intentionally modified.

No Evidence Candidate Builder, Micro-window, Selector, Sufficiency Judge, Answer Generation, Agent, Memory, Harness, Translation Pipeline, or V4 work was started.

Additional recommendations were recorded only and were not implemented.
