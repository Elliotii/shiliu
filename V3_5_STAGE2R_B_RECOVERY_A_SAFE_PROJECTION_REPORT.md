# Shiliu V3.5 Stage 2R-B Recovery A — Safe Projection Report

## Final status

```text
Stage 2R-B Recovery A Complete
Safe Candidate Projection Ready for Clean B0 Restart
```

This session stops permanently after delivery of the deterministic safe projection. It is not eligible to participate in pilot mining, annotation review, adjudication, judge development, or held-out evaluation.

## Repository and isolation record

- Repository: `/Users/elliot/new-systems/agent-job-prep/Shiliu`
- Branch: `codex/v3-domain-completion`
- Starting HEAD: `8287c8d92378b87290274d02605cdc704cb8c470`
- The pre-existing dirty worktree, pre-run Git status, and pre-run file inventory were recorded before implementation. Existing changes were preserved; no rollback, cleanup, broad formatting, or destructive Git command was used.
- Exact authorized source: `research/v3_eval/eval_queries.candidate.jsonl`
- No other split-aware, held-out, gold, transcript, review, span, aspect, or assignment data file was read. In particular, `research/v3_eval/eval_queries.locked.jsonl` was not read.
- The authorized source was read only inside the deterministic `safe_projection` CLI. Codex did not display, read in natural language, summarize, assess, or select any real query.
- Codex Reviewer calls: 0. DeepSeek calls: 0. Other provider/LLM calls made by the projection workflow: 0. No embeddings or external language inference were used.

## Projection contract

The output record allowlist is exactly:

```text
candidate_id
query
query_language
lineage_source
source_record_digest
pilot_candidate_allowed
projection_version
```

Records were included only when `held_out` existed, had the exact Boolean type, was `false`, and `query` was a non-empty string. Any equivalent split field also had to be absent or consistently indicate non-held-out status.

The following cases fail closed and are excluded: `held_out=true`; missing, null, or non-Boolean `held_out`; missing, empty, or non-string `query`; malformed or non-object records; an unknown or invalid equivalent split value; an equivalent field that may indicate held-out status; and conflicts among assignment fields. Invalid `query_language` is not inferred and becomes `unknown` only on an otherwise includable record.

No ambiguous real records were found. No candidate-ID, normalized-query-digest, or source-record-digest duplicate was found. Included/excluded normalized query digest overlap was zero. Excluded digests were held only in memory and were not persisted or logged.

The strict allowlist proves that the output contains no split, held-out, gold, label, sufficiency, video, span, aspect, evidence, review, reviewer, decision, adjudication, selector, or judge field. It also contains neither raw source JSON nor original record IDs or source ordinals.

## Build results

| Check | Result |
|---|---:|
| Source SHA-256 | `bad3312f5fba38e0e4a37fd4554627ddbf02e57a48e86807e7b70059276eeb28` |
| Output SHA-256 | `2c2fd3e0d06452201119f22ab3b68dcdfc738f91d19a916e50dbb9fd2051b564` |
| Input records | 24 |
| Included records | 4 |
| Excluded records | 20 |
| Ambiguous records | 0 |
| Duplicate candidate IDs | 0 |
| Duplicate normalized query digests | 0 |
| Duplicate source record digests | 0 |
| Excluded digest overlap | 0 |
| Forbidden-field scan | Passed |
| Secret scan | Passed |
| Output parse validation | Passed |
| Repeated build bytes/hashes | Identical |
| Provider calls | 0 |
| LLM calls | 0 |

The builder independently projected the same in-memory source bytes twice before writing and required byte equality. The CLI was then run a second time; aggregate output plus projection, manifest, and audit hashes were identical. Canonical output uses UTF-8, sorted keys, compact separators, finite JSON values, newline-delimited records, and source ordering. No time field participates in output or manifest bytes.

## Assets and changed files

- `src/shiliu/eval_v3_5/eval_v2/safe_projection.py` — exact-path deterministic builder, validator, CLI, and aggregate-only result type.
- `tests/test_v3_5_eval_v2_safe_projection.py` — synthetic fixtures and isolation/safety/reproducibility tests; no real query fixture content.
- `research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.jsonl` — safe candidate projection. This session did not open or inspect its query content after generation.
- `research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.manifest.json` — deterministic aggregate manifest.
- `research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.audit.json` — isolation and usage audit.
- `V3_5_STAGE2R_B_RECOVERY_A_SAFE_PROJECTION_REPORT.md` — this report.

The existing `Stage2RAAccessGuard` was not modified or weakened. Its tests continue to reject both raw assignment paths. The projection builder is a separately named entry point, enforces the one exact source and one exact output path after resolution, uses an independent usage identifier, and returns aggregate metadata rather than records.

## Integrity declarations

- Eval v1 was not modified.
- Frozen V3 was not modified.
- Stage 2R-A frozen schemas, protocols, prompts, policies, manifests, and audits were not modified.
- No locked master case, development/held-out manifest, gold lock, annotation review, agreement, adjudication, or formal pilot packet was created or modified.
- Final repository status and metadata comparisons were used to verify that task changes are confined to the six files listed above while preserving all pre-existing dirty-worktree changes.

## Test result and residual risk

The dedicated synthetic suite and the pre-existing Stage 2R-A suite pass together. The synthetic cases cover explicit false inclusion; true/missing/null/string assignment exclusion; invalid query exclusion; split conflicts; strict allowlisting and forbidden fields; stable opaque IDs and hashes; byte-identical reruns; duplicate rejection; excluded-overlap failure and cleanup; safe malformed-JSON logging; exact path enforcement; aggregate-only returns; zero-call declarations; and continued ordinary-guard rejection.

No unresolved projection blocker remains. The residual operational risk is misuse by a future session, controlled by the following read boundary and permanent eligibility declaration.

## Clean B0 restart boundary

A new, clean Case Mining Orchestrator session may read only:

- `research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.jsonl`
- `research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.manifest.json`
- Stage 2R-A public schemas, protocols, and prompts
- an otherwise authorized raw-source inventory

It must not read either raw V3 assignment file, this session's source-access logs, excluded-record information, or historical held-out facts in `V3_5_CURRENT_STATE.md`. Reviewer sessions must not receive even the safe projection; it is solely an input to the future Case Mining Orchestrator.

```yaml
session_future_eligibility:
  pilot_case_mining: false
  annotation_review: false
  gold_adjudication: false
  judge_development: false
  heldout_evaluation: false
```

This session must not continue into B0, B1, B2, Stage 2R-C, Stage 3R, Stage 4A-R, Stage 4B, or V4.
