# Stage 5 Repository Failure Triage

## Test boundary

The current executable repository suite was run with 29 test files excluded
because their source indicates that they open Frozen Query, Gold, Prediction, or
Failure Analysis artifacts. This obeys the explicit no-Frozen-content boundary.

Safe repository result:

```text
948 passed
6 failed
1 warning
```

An unfiltered collection attempt also found the known missing dependency:

```text
scripts/export_pqs_v1_authoring_packet.py
required by tests/test_pqs_v1_authoring_packet_contracts.py
```

The machine-readable record with every required field is
`STAGE5_REPOSITORY_FAILURE_TRIAGE.json`.

## Failures introduced during this repair

Two compatibility failures were detected and fixed:

1. Adding `uploader_contains` directly to `planner.py` changed the frozen Auto
   Router source identity.
2. The first Product-only filter subtype rejected legacy
   `SearchFilterRequest` instances used by the candidate-pool code.

The final implementation:

- leaves `planner.py` at frozen hash
  `0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e`;
- keeps the new field in `ProductSearchFilterRequest`;
- promotes legacy exact-filter instances without changing their values.

No post-freeze repair failure remains.

## Remaining non-blocking failures

### Frozen canonical matcher expectation

`tests/test_f1a_scoring_identity_bridge.py` expects the lineage string
`official_subtitle`, while the frozen canonical matcher returns `official`.

The matcher SHA-256 is
`e317a8056b39a409fe5e63b3a45950bc7c1c2f98e77bce6550fcb6e7a5d278c3`,
exactly the hash recorded by `STAGE4A_R_MECHANICAL_GATE_FREEZE.json`. Changing
it here would violate the frozen boundary. The stale test expectation is
therefore accepted as non-blocking historical debt.

### Missing temporary construction workspace

`tests/test_v3_5_eval_v2_construction_workspace_export.py` expects:

```text
/tmp/shiliu-v3-5-c0-construction-input-v2/workspace_manifest.json
```

That separately generated temporary workspace no longer exists. It is not used
by Product Search, Stage 5, or the guarded Frozen Auto runner.

### Historical handoff state and hash drift

Four tests under the old handoff fact-freeze suites bind earlier versions of
`V3_5_CURRENT_STATE.md` or expect it to remain marked stale. The current file
hash is:

```text
92b77a1f26df6fe589366966a8d3cec11ad15e7d57d45e7ce308d54612e82ed6
```

The historical expectations are `29c9...134f` and `115b...8597`. These handoff
manifests are not current Stage 5 or Frozen Eval runtime seals.

## Missing dependency

`tests/test_pqs_v1_authoring_packet_contracts.py` cannot collect because
`scripts/export_pqs_v1_authoring_packet.py` is absent.

It is an earlier authoring-packet export helper, not a Product Search, Stage 5,
or Frozen Eval runtime dependency. Restoring it is unnecessary for this repair
and is classified as non-blocking historical technical debt.

## Conclusion

- All failures caused by the post-freeze delta repair are resolved.
- The remaining six executable-suite failures are individually evidenced and
  do not affect Search, Builder, Selector, Mechanical Gate, Semantic Judge,
  Stage 5 Trace, or the Frozen Eval runtime guard.
- The missing authoring dependency is classified and non-blocking.
- Frozen Evaluation content was not opened during this triage.
