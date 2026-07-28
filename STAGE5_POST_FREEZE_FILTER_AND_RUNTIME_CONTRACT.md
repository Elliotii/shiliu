# Stage 5 Post-Freeze Filter and Runtime Contract

Version: `v3.5-stage5-post-freeze-filter-runtime-v1`

## Scope

This additive contract repairs Product Search filter compatibility and separates
the mutable Product runtime from any Frozen Evaluation runtime. It does not
modify Retrieval ranking, the Auto Router, Candidate Builder, Selector,
Mechanical Gate, Semantic Judge behavior, or the Evidence Identity Contract.

## Uploader filters

### `uploader`

- Compatibility: backward compatible.
- Match mode: case-insensitive exact match.
- SQL predicate: `lower(u.uploader) = lower(?)`.
- A full uploader name matches.
- A partial uploader name does not match.
- The field remains available to Raw Search, Product Search, and the Stage 5
  evidence-sufficiency route.

### `uploader_contains`

- Compatibility: additive Product Search field.
- Match mode: case-insensitive substring match.
- SQL predicate: `instr(lower(u.uploader), lower(?)) > 0`.
- A full or partial uploader name matches.
- The field is defined by `ProductSearchFilterRequest`, not the frozen Raw
  Search `SearchFilterRequest`.
- The Product Search page sends this field for its
  `UP 主（名称包含）` control.
- `Stage5PipelineRequest` inherits the Product Search contract and therefore
  supports this field.

Keeping the additive field outside `SearchFilterRequest` preserves the frozen
Auto Router source identity and prevents an implicit Raw/Frozen contract
change.

## Product runtime

The product application uses the explicit configuration:

```yaml
runtime_mode: product_runtime
corpus_identity: shiliu-live-current
sync_allowed: true
mutable_index_allowed: true
```

`/search`, `/api/search`, and `/api/evidence-sufficiency` continue to use the
current locally synced library.

## Frozen Eval runtime

Any Frozen Eval runner must provide a separate JSON runtime seal before it loads
frozen inputs:

```yaml
runtime_mode: frozen_eval_runtime
corpus_identity: <sealed identity>
sealed_corpus_identity: <same sealed identity>
sync_allowed: false
mutable_index_allowed: false
artifacts:
  database: {path: <path>, sha256: <64 lowercase hex>}
  lexical_index: {path: <path>, sha256: <64 lowercase hex>}
  dense_index: {path: <path>, sha256: <64 lowercase hex>}
```

The guard rejects:

- any runtime mode other than `frozen_eval_runtime`;
- `shiliu-live-current`;
- a corpus identity that differs from its seal;
- enabled sync;
- a mutable index;
- a missing database, lexical-index, or dense-index artifact;
- a missing, malformed, or mismatched SHA-256;
- a snapshot path that is not the path named by the runtime seal.

The Frozen Auto Smoke entry requires `--runtime-seal`. Its in-process runner
requires a validated `FrozenEvalRuntimeConfig`. Missing or invalid guard state
blocks before `load_frozen_inputs(...)`.

The guard validates only runtime mode, identities, artifact presence, and
SHA-256. Its synthetic preflight tests do not open Frozen Query, Gold,
Prediction, or Failure Analysis content.

## Sync isolation

The Product runtime retains scheduled and manual sync. The Frozen Eval runtime
has no `SyncService` entry and the guard requires `sync_allowed: false`.

The post-freeze Product sync repairs remain active:

- retryable source errors enter recoverable cooldown;
- existing paused/auth-required/unavailable sources do not fall back to legacy
  sync;
- a transient source failure does not empty the current product index.

## Semantic Judge transport

The frozen Judge behavior is unchanged. The transport resolves the Codex
executable in this order:

1. explicit `SHILIU_CODEX_EXECUTABLE`;
2. current process `PATH`;
3. the bundled Codex executable in the ChatGPT application.

This allows the product LaunchAgent, whose default `PATH` omits the application
bundle, to invoke the same frozen provider. Model, Prompt, Policy, temperature,
retry policy, and decision schema are unchanged.
