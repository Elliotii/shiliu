# Shiliu V3.5 Stage 1A — Source Identity, Timeline and Exact Mapping Contract Report

## 1. Stage Result

Candidate classification: **Accepted with Follow-up Candidate**.

Stage 1A is implemented and verified. The contracts establish a deterministic chain from a frozen V3 transcript chunk to an exact source version, timeline run, and raw segment IDs. All 14 new tests and all 532 repository tests pass. Follow-ups are non-blocking: runtime integration belongs to Stage 1B, and `SHILIU_V3_VERSION_DECISION.md` remains absent locally. Final acceptance remains with the V3.5 Version Session.

## 2. Scope Compliance

- Implemented only source/segment identity, validation, timeline derivation, exact chunk replay, evidence safety, data-only SearchCandidateSet drafts, errors, tests, current state, and this requested report.
- Did not change retrieval ranking, routing, embeddings, fusion, chunk policy, grouping, windows, schema, indexes, Web/UI, Gold, Eval results, Snapshot, or raw artifacts.
- Did not implement Search Adapter, trace controls, Candidate Builder, micro-windows, Selector, Prompt, Sufficiency, Answer, Agent, Memory, Harness, Translation, or V4 work.
- No provider, external LLM, model download, formal Eval, or index rebuild was used.

## 3. Repository Before / After State

Repository root, before and after: `/Users/elliot/new-systems/agent-job-prep/Shiliu`.

Branch, before and after: `codex/v3-domain-completion` (ahead of origin by one pre-existing commit).

HEAD, before and after: `8287c8d92378b87290274d02605cdc704cb8c470`.

Before-state manifest: `/tmp/shiliu_v3_5_stage1a_before/` records status, tracked modified files, staged files, untracked files, target-file presence, Eval hashes, Snapshot DB hash, and video 88 hash. All Stage 1A target files were `absent_before_stage`; no staged files existed.

Pre-existing tracked modifications, preserved unchanged in status:

- `V3_CURRENT_STATE.md`
- `src/shiliu/retrieval/__init__.py`
- `src/shiliu/retrieval/product_search.py`
- `src/shiliu/templates/base.html`
- `src/shiliu/web.py`

Pre-existing untracked V3/Eval/Web/Test/Report assets remain present. After-state adds only the intended Stage 1A paths listed below. No staged changes appeared. Unexpected changes: none detected.

## 4. Files Created and Modified

Created:

- `V3_5_CURRENT_STATE.md`
- `V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md`
- `src/shiliu/evidence/__init__.py`
- `src/shiliu/evidence/contracts.py`
- `src/shiliu/evidence/source.py`
- `src/shiliu/evidence/mapping.py`
- `tests/test_evidence_contracts.py`
- `tests/test_evidence_snapshot_regression.py`

Modified by Stage 1A: none of the files that existed at intake.

Pre-existing files deliberately left untouched: all retrieval, Web, template, static, Eval, Snapshot, artifact, Gold, and Phase 0 report files.

## 5. V3_5_CURRENT_STATE Summary

`V3_5_CURRENT_STATE.md` was created as a current-version state document, not an execution log. It records Version Identity; authority/governance; repository state; frozen V3 baseline; Eval intake fingerprints; Search/subtitle facts; source, segment, timeline, and mapping contracts; video 88; reusable assets; Current Stage; Delivered; Active Issues; Eval status; prompt/policy versions; decisions; deviations; escalations; estimated hours; remaining budget; and the current-stage budget.

It includes all approved rules for full-transcript Gold annotation, future `gold_evidence_groups`, one Master Evaluation Case Set, Stage 2 Development/Held-out freeze, non-mechanical Readiness targets, Sufficiency status/reason separation, and the 24-hour hard stop.

## 6. Source Artifact Identity Contract

`source_artifact_id` identifies the logical subtitle source and is generated as:

```text
"source_artifact_" + SHA-256(
  UTF-8(JSON({
    "part": integer part,
    "platform": platform,
    "source_id": source_id/BVID,
    "source_language": source language,
    "source_type": source type
  }, sorted keys, separators=(',', ':'), ensure_ascii=false, allow_nan=false))
)
```

It excludes local paths, Snapshot identity, index state, database IDs, and content bytes. Moving identical bytes does not change this logical identity; updating content retains logical identity but changes `source_version`.

## 7. Source Version Contract

`source_version` is the lower-case SHA-256 hex digest of the exact bytes of authoritative `subtitle-raw.json`. There is no parsing, text normalization, path, mtime, chunk hash, summary hash, or database timestamp in this digest.

If `expected_source_version` differs, reading/mapping raises structured `source_version_mismatch` before parsing or replay. No mapping is returned and no fuzzy recovery is attempted.

## 8. Segment Identity Contract

Each parsed valid raw segment contains `segment_id`, `source_artifact_id`, `source_version`, `original_ordinal`, start/end, exact source text, source type/language, `segment_digest`, `timeline_run_id`, and `run_local_ordinal`.

```text
segment_id = "segment_" + SHA-256(
  canonical UTF-8 JSON({
    "original_ordinal": ordinal,
    "source_artifact_id": source_artifact_id,
    "source_version": source_version
  })
)
```

Tests prove same logical source + same bytes + same ordinal is stable; changing bytes changes version and segment ID; duplicate text at different ordinals has different IDs; and file movement does not affect identity.

## 9. Segment Digest and Canonicalization

`segment_digest` is SHA-256 over canonical UTF-8 JSON with sorted keys and compact separators:

```json
{"content":"exact original string","from":0.0,"to":1.0}
```

`from` and `to` are parsed as finite Python floats and then deterministically JSON-serialized. Text is neither stripped nor Unicode-normalized. This digest binds parsed segment semantics; the source-version byte hash remains authoritative for byte-level differences. The precision boundary is Python/JSON serialization of finite IEEE-754 floats.

Empty text is retained with its original ordinal and stable ID but `evidence_eligible=false`; it is excluded only by the frozen chunk builder, so later ordinals never shift.

## 10. Timeline Run Contract

Policy version: `v3.5-timeline-policy-v1`. Fixed epsilon: `1e-6` seconds; it is not tuned or treated as an Eval parameter.

In original array order:

```text
current.start_time < previous.start_time - epsilon
→ new timeline run
```

Same starts do not split. Ordinary overlap does not split. A previous end later than the next start does not itself split. There is no global sort, rotation, repair, or ordinal change.

`timeline_run_id` is `"timeline_run_" + SHA-256(canonical JSON of source_version + zero-based run_ordinal)`. Each run records its ordinal, first/last original ordinal, first start, last end, and segment count.

Evidence spans, future micro-windows, and future candidates must not cross runs. A readable multiple-run artifact retains eligible run-local segments.

## 11. Exact Chunk Mapping Contract

Method/version: `exact_chunk_replay` / `v3.5-exact-chunk-mapping-v1`.

The mapper loads authoritative bytes, enforces expected version, replays the unchanged V3 `ChunkingConfig` and builder, then requires exact equality for chunk ID, unit-ID chunk suffix, start time, end time, source text, content hash, and replayed segment count. It returns exact raw ordinals/IDs, run ID, deterministic mapping digest, status, and eligibility.

No fuzzy text, semantic similarity, nearest timestamp, LLM, manual exception, or video-specific path exists. Any mismatch returns `chunk_segment_mapping_failed`, empty segment IDs/ordinals, and `candidate_eligibility=false`.

A replayed parent containing multiple runs returns `invalid_cross_timeline_run`, has no single run ID, and is ineligible. It is not split or used to mutate V3.

## 12. video 88 Validation

Confirmed real Snapshot evidence:

| Field | Result |
|---|---|
| video / BVID | `88` / `BV1TxwQz5E4B` |
| source | `human` / `zh` |
| segment count | 1,748 |
| validation | `valid_multiple_runs` |
| run 0 | ordinals `0–1388`, `567.400–2767.800s`, 1,389 segments |
| run 1 | ordinals `1389–1747`, `0.133–567.333s`, 359 segments |
| frozen chunk count | 27 |
| cross-run invalid count | 1 |
| invalid chunk | `chunk_cc3222c5f91a7fa074ec5802f8a21799` |
| invalid frozen range | `2712.466–35.733s` |
| run-local chunks | 26 exact mapped and eligible |
| artifact hash before/after | `cc6afce905dc90ee1c89d1906c2617ba80c4992196c256e5fa8a66db9c0e2f0c` / same |

The two runs are derived by the generic boundary rule. The artifact remained in original order, no video-88 hardcode exists, and the artifact, chunk rows, V3 Gold, and retrieval results were not changed.

## 13. Existing Interval Regression

Result: **10/10 Approved Intervals passed**.

- Source-readable: 10/10.
- Source version: SHA-256 derived from and checked against the frozen manifest artifact.
- Mapped segment count: 24 total raw segments.
- Continuity: 10/10 use an inclusive ordinal range `start_index..end_index`; all reconstructed ordinal sequences are continuous.
- Time boundaries: 10/10 first segment start and last segment end exactly reconstruct the approved interval boundaries (float comparison uses test approximation only at the assertion boundary).
- Timeline safety: 10/10 remain within one run.
- Stable segment IDs: all 24 mapped occurrences received version-safe IDs.

These intervals remain only an Evidence Gold Seed. They were not declared complete V3.5 Gold, used for policy tuning, or divided into Development/Held-out.

## 14. SearchCandidateSet Draft

Data-only frozen dataclass drafts were defined for `SearchCandidateSet`, `SearchCandidateVideo`, and `SearchCandidateChunk`. They preserve original query, trace ID, executed mode, index identity, Snapshot ID, creation time, video/chunk candidates, component unit IDs, rank, score, retrieval method, subtitle source, and time range.

No Search adapter, orchestrator/service modification, ranking change, Search API, `search_library()`, or `persist_trace=false` implementation was created. These are Stage 1B inputs.

## 15. Error Contract

Stage 1 vocabulary is centrally recorded:

```text
raw_subtitle_missing
source_unreadable
source_version_mismatch
segment_identity_invalid
segment_time_invalid
source_timeline_non_monotonic
chunk_segment_mapping_failed
invalid_cross_timeline_chunk
candidate_not_found
```

The mapping result status required for a reproduced cross-run chunk is separately `invalid_cross_timeline_run`. Errors/reasons are not mapped to four-state Sufficiency in Stage 1A.

## 16. Tests and Regression

Targeted command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evidence_contracts.py tests/test_evidence_snapshot_regression.py
```

Result: exit 0; 14 collected, 14 passed, 0 failed, 0 skipped, 0 warnings; 0.83s wall time on the final run.

Coverage includes source/version/ordinal/path identity; negative and reversed time; empty/duplicate text; same start; overlap; true backward reset; order preservation; cross-run span; exact mapping; AI, human, and real ASR Snapshot chunks; version/text/hash/start/end mismatches; run-local eligibility; real video 88; all 10 intervals; Snapshot DB; and all 372 `status=ok` Snapshot manifest artifacts.

Full command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

Result: exit 0; 532 collected, 532 passed, 0 failed, 0 skipped; 7 warnings; 7.34s wall time on the final run. This is the original 518 tests with no regression plus 14 Stage 1A tests. Warnings are one pre-existing Starlette/httpx deprecation and six multiprocessing/fork deprecations.

Git status was captured before and after. The same five pre-existing tracked modifications remain; no staged files appeared; intended Stage 1A untracked paths were added.

## 17. Snapshot / Artifact / Eval Integrity

| Asset | Before SHA-256 | After SHA-256 | Result |
|---|---|---|---|
| Snapshot DB | `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1` | same | unchanged |
| video 88 raw artifact | `cc6afce905dc90ee1c89d1906c2617ba80c4992196c256e5fa8a66db9c0e2f0c` | same | unchanged |
| 372 manifest `status=ok` Snapshot artifacts | manifest hash/size per record | all match after | unchanged against frozen manifest |

All 11 present canonical Eval/report assets were hashed before and after and match exactly:

```text
21382e8ba058cc6e51ea41c776ad216824363090888ee3a5569e36dc971c36ba  eval_queries.locked.jsonl
873b5fbf78ba2e8fc90dfb2fca96776e0e703a1c4fedd56dd20a49e43995b300  eval_gold.locked.jsonl
e93fd09bd06151d8665f50a17cc24bc2673105d21886e77b8a4cfa12f7ba0257  eval_gold_review.decisions.amended.jsonl
46d81526341a9e7c1e311aed3a03a964563e9e91f87c17be0fc796b7f0975db0  gold_lock_audit.json
d3a488a57fcc7a8e41c6c06ce46cde61498336cb3a201dc505b038011baa4ee1  human_ledger_amendment_audit.json
9bf49fe37565bbd8694e4bcd61a2c1126950b3387604797b8936407cd1c3bfbc  eval_results.json
3412f7e5e3be2732b68042d8066612f828b9599b3c324d14b24f3554c34ebaa9  eval_results.csv
2b540e4c2ab7c7580ee4b4df212fe8aeb854845d6d4c55e743ef2e82b637d647  eval_per_query_results.jsonl
3f08db8086089a6545cd244775ced1894ec071c5b14995c1197f2cf6dad82d3e  failure_cases.md
225d39836fcee67adfe9fc567bdc2b759dd3daf94f9940ecb7b4100063d00bbe  V3_EVAL_PROTOCOL.md
80e4abfd1d6b87f50a1c3e905a99af6fcc89d0ed2ce55d85c934f25809be9a75  V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md
```

The amended ledger hash is historically verified. The others are newly fingerprinted at V3.5 intake and do not prove they never changed before intake. `SHILIU_V3_VERSION_DECISION.md` remains missing. No actual hash conflict exists.

## 18. Findings Ledger

| Type | Finding | Evidence / impact |
|---|---|---|
| Confirmed Fact | Deterministic source and segment identities are path-independent and version-safe. | Synthetic identity tests pass. |
| Confirmed Fact | Exact replay maps real AI, human, and ASR chunks without fuzzy logic. | Snapshot videos 78, 77, 14, and 2 pass. |
| Confirmed Fact | video 88 is readable with two runs and exactly one invalid cross-run chunk. | 1,748 raw segments and all 27 frozen chunks replayed. |
| Confirmed Fact | Run-local evidence in a multiple-run source remains usable. | 26/27 video 88 chunks map and remain eligible. |
| Confirmed Fact | Existing interval regression is 10/10, covering 24 raw segments. | Exact ordinal continuity, boundaries, source version, and single-run checks pass. |
| Confirmed Fact | Snapshot, artifacts, and Eval assets were not changed. | DB hash, manifest checks for 372 files, video 88 hash, and Eval hashes pass. |
| Inference | Exact replay is safe for Stage 1A only while the frozen V3 chunk implementation remains available and unchanged. | The mapping layer deliberately imports that frozen builder. |
| Unknown | The canonical external authority for most Eval hashes before V3.5 intake is unavailable. | Only the amended ledger has a verified historical hash. |
| Blocking Risk | None for Stage 1A. | All acceptance tests pass without forbidden changes. |
| Recommendation | Stage 1B should pass/freeze expected source versions and honor mapping eligibility at the Candidate boundary. | Do not backfill or mutate V3 retrieval rows in Stage 1A. |

## 19. Remaining Risks

- Retrieval units do not persist `source_version`, raw segment IDs, or segment count. Stage 1A therefore requires a caller-supplied expected version and derives segment count during replay; integration authority must be resolved in Stage 1B.
- The frozen video 88 cross-run chunk remains present in V3. This is intentional baseline preservation, but downstream code must fail it closed.
- Changing or removing the frozen V3 chunk implementation would require an explicitly versioned replay implementation to keep historical mapping reproducible.
- Structural parsing returns structured invalid status while malformed JSON bytes raise `source_unreadable`; downstream integration must handle both without guessing.
- Missing `SHILIU_V3_VERSION_DECISION.md` is an authority-document gap, not a hash conflict.

## 20. Stage 1B Inputs

- Use the SearchCandidateSet schema as a draft, then review it against the actual V3 response without changing rank.
- Establish how `expected_source_version` is obtained/frozen at the adapter boundary.
- Preserve index identity, trace identity, component unit IDs, executed mode, source type, and Snapshot ID.
- Ensure every candidate chunk calls exact mapping and excludes failed/cross-run mappings.
- Decide trace persistence control in Stage 1B only.
- Do not start Candidate Builder, micro-windows, Gold restriction, Selector, or Sufficiency as part of the adapter.

## 21. Escalation Assessment

No Stage 1A stop condition was reached. Exact replay succeeded; no chunk policy, retrieval schema, index, artifact, Gold, DB migration, fuzzy matching, or video-specific rule was required. No blocking escalation is needed.

Follow-up for Version Session: confirm the authority/location of the missing `SHILIU_V3_VERSION_DECISION.md` and approve the Stage 1B source-version handoff/persistence boundary. Codex recommendation: accept Stage 1A with those follow-ups, without historical backfill.

## 22. Exact Commands Executed

Repository intake:

```bash
cd /Users/elliot/new-systems/agent-job-prep/Shiliu
pwd -P
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git rev-parse HEAD
git diff --name-only
git diff --cached --name-only
```

Read-only Snapshot inspection used `sqlite3 -readonly` against:

```text
/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db
```

Material integrity commands:

```bash
shasum -a 256 /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db
shasum -a 256 /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV1TxwQz5E4B/subtitle-raw.json
shasum -a 256 research/v3_eval/eval_queries.locked.jsonl research/v3_eval/eval_gold.locked.jsonl research/v3_eval/eval_gold_review.decisions.amended.jsonl research/v3_eval/gold_lock_audit.json research/v3_eval/human_ledger_amendment_audit.json research/v3_eval/eval_results.json research/v3_eval/eval_results.csv research/v3_eval/eval_per_query_results.jsonl research/v3_eval/failure_cases.md research/v3_eval/V3_EVAL_PROTOCOL.md V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md
```

Final test commands:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evidence_contracts.py tests/test_evidence_snapshot_regression.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

Final worktree check:

```bash
git status --short --branch
git diff --name-only
git diff --cached --name-only
git branch --show-current
git rev-parse HEAD
```

## 23. Stop Statement

Shiliu V3.5 Stage 1A execution is complete.

No V3 Retrieval ranking, router, embedding, fusion, chunk policy, grouping, window policy, Gold, Snapshot, Raw Artifact, or Formal Eval result was intentionally modified.

No Candidate Builder, Selector, Sufficiency Judge, Answer Generation, Agent, Memory, Harness, Translation Pipeline, or V4 work was started.

Additional recommendations were recorded only and were not implemented.
