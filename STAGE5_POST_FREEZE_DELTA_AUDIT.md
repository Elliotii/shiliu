# Stage 5 Post-Freeze Delta Audit

Audit time: 2026-07-28 (Asia/Shanghai)

Baseline: `STAGE5_INTEGRATION_FREEZE_SEAL.json`  
Baseline SHA-256:
`c65b77dfb8fbce546e8054ec9d57af682db9b8be1c725f1d2b138326ee9d9461`

## Result

The original Stage 5 Freeze remains a valid historical snapshot, but the
current integration differs from it and requires a new seal.

The delta is not UI-only. It contains four distinct behavior classes:

1. Product filter semantics and compatibility;
2. operational sync protection;
3. Product/Frozen runtime isolation and Eval runner safety;
4. UI and cover presentation.

No frozen Candidate Builder, Selector, Mechanical Gate, Semantic Judge, or
Evidence Identity Contract behavior was changed.

The complete machine-readable per-file audit is in
`STAGE5_POST_FREEZE_DELTA_AUDIT.json`.

## Contract defect found and repaired

The post-freeze Product change had replaced the old `uploader` exact predicate
with substring matching. That overloaded one field with two meanings.

The repair is:

```text
uploader          → case-insensitive exact match
uploader_contains → case-insensitive substring match
```

`uploader_contains` lives in the Product Search filter contract. The frozen Raw
Search request and Auto Router keep their original `uploader` contract.

An initial implementation placed the new field in `planner.py`. Repository
revalidation correctly detected an Auto Router source-identity mismatch. The
field was moved out of the frozen Raw Search contract, and the exact Router hash
was restored:

```text
0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e
```

## Runtime isolation

The Product runtime is now explicit:

```yaml
runtime_mode: product_runtime
corpus_identity: shiliu-live-current
sync_allowed: true
mutable_index_allowed: true
```

The Frozen Eval guard requires:

```yaml
runtime_mode: frozen_eval_runtime
sync_allowed: false
mutable_index_allowed: false
database_hash_required: true
lexical_index_hash_required: true
dense_index_hash_required: true
```

`shiliu-live-current`, a mismatched corpus identity, a missing artifact/hash,
enabled sync, a mutable index, or an unsealed snapshot path blocks before frozen
inputs are loaded.

## Operational sync delta

The sync changes are retained because they protect the current Product index:

- retryable source failures enter cooldown;
- an existing unavailable/auth-required/paused source cannot fall back to
  legacy sync;
- a transient source failure cannot turn the current index into an empty
  legacy snapshot.

Frozen Eval does not construct Product Sync and its guard requires sync to be
disabled.

## UI delta

The retained UI changes:

- center search-result covers;
- detect portrait covers using natural dimensions;
- keep content-flow card dimensions fixed;
- detect and crop embedded dark pillarboxes with a generic luminance algorithm;
- use card-colored uncovered background;
- preserve `NO COVER`;
- send `uploader_contains` from `UP 主（名称包含）`;
- update static asset cache versions.

These changes do not modify Evidence text, Evidence IDs, Mechanical status,
Semantic status, or Reason Codes.

## Revalidation requirements

Revalidation is required for:

- Product exact/contains filtering;
- legacy filter-object compatibility;
- Product and Stage 5 API routes;
- Auto Router source identity;
- Frozen runtime preflight and block behavior;
- sync cooldown/no-legacy-fallback behavior;
- Stage 5 routing, trace, error mapping, and UI DOM;
- current Product live search and UI console state.

Frozen Evaluation Query, Gold, Prediction, and Failure Analysis content was not
opened for this audit.
