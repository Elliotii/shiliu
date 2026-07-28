# P14 Replacement Environment Delta

## Original environment

- Codex state root: `/Users/elliot/.codex`
- SQLite state: `/Users/elliot/.codex/state_5.sqlite`
- `CODEX_HOME`: unset, defaulting to `/Users/elliot/.codex`
- `CODEX_SQLITE_HOME`: unset, defaulting to `CODEX_HOME`
- Provider initialization: failed because the original execution sandbox made
  the SQLite-backed state effectively read-only.

## Repaired environment

- `CODEX_HOME` and all authentication/provider configuration remain unchanged.
- Only `CODEX_SQLITE_HOME` is set for Provider subprocesses, to:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/p14_frozen_evaluation/replacement_provider_state`
- The isolated SQLite directory exists with mode `0700`.
- Repository source commit remains
  `91a34061f8aebb216749c015a37a4ff1974f4f2a`.

Official Codex configuration documentation identifies `CODEX_SQLITE_HOME` as
the location override specifically for CLI/app-server SQLite-backed state. This
keeps the repair limited to the original failure root cause.

## Authorized orchestration differences

- isolated writable SQLite state directory;
- directly related state path and permission change;
- atomic Case artifact and trace persistence;
- safe resume under the same replacement run ID.

Unauthorized differences: `0`.

Frozen Query, Frozen Gold, and Development Gold were not used to construct or
validate this environment change.
