# Frozen Eval Runtime Seal

## Status

`seal_version: v3.5-frozen-eval-runtime-seal-v1`

`runtime_mode: frozen_eval_runtime`

`Frozen_Evaluation_content_accessed: false`

## Authoritative binding

The authoritative frozen runtime is Snapshot
`20260720T094346Z_c7663365`, with corpus identity
`61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.

Its database, lexical index, and dense index are all embedded in the same
read-only SQLite Snapshot:

`/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db`

The file SHA-256 is
`61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`.
This matches the existing index and source Snapshot identity.

The existing index metadata identifies:

- lexical index: `v3-stage1-lexical-v1`;
- dense index: `v3-dense-qwen3-0.6b-mrl512-v1`;
- dense provider: `v3-qwen3-embedding-provider-v1`;
- 1,555 stored embedding vectors at dimension 512;
- 1,412 transcript chunks and 143 videos.

No database or index was copied, rebuilt, synchronized, or selected using
Frozen Query content.

## Runtime policy

- Sync is disabled.
- Mutable indexes are forbidden.
- `shiliu-live-current` is forbidden.
- Rebuilding any frozen asset is forbidden.
- The Snapshot, database, lexical index, and dense index are read-only.

## Binding evidence

The binding was mechanically derived from the existing runtime identity,
runtime integrity audit, frozen Stage 3 runtime identity, and Stage 5 current
integration refreeze seal. All named files and hashes are recorded in the JSON
seal.
