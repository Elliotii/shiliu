# Shiliu V3–V3.5 Repository Closeout Reconciliation and Reusable Interface Audit

Date: 2026-07-28  
Audit mode: read-only repository audit; no V3/V3.5 algorithm reopening, no frozen-eval rerun, no product-code change, no cleanup, move, commit, or deletion.

## Executive conclusion

The current repository is **not yet a safe branch point for subsequent development**.

The decisive reason is not a new judgment about V3 or V3.5. The V3 decision and V3.5 final closeout remain closed and authoritative. The repository problem is that:

1. the source commit recorded by the V3.5 Final Closeout is the current `HEAD`;
2. that commit does not contain the final V3.5 Evidence package, Stage 5 integration, final closeout/seal files, or their tests;
3. those materials exist only among a very large dirty working tree whose pre-report snapshot contained 2,807 untracked files and 19 tracked changes that have not been reconciled into a self-contained, reproducible repository state;
4. the current full test state is not clean: one historical test module cannot collect and 12 collected tests fail, including two deterministic compatibility regressions caused by current working-tree serialization changes.

The repository does contain highly reusable capability. The strongest reusable boundary is the **conceptual and typed SearchCandidateSet plus authoritative Evidence Identity/Source Version/Segment/Timeline contracts**. However, because the implementation is not present in the recorded source commit and exact request serialization has already drifted, this is currently a **reuse-with-adapter** boundary rather than an already sealed repository ABI.

V3.5 Evidence/Sufficiency maturity is recorded as:

```yaml
V3_5_evidence_sufficiency:
  implementation: implemented
  integration: minimally_product_integrated
  operation: limited_pilot
  evaluation: formally_evaluated_below_target
  maturity: partial
```

It is neither `production-used` nor `research-only`.

# Part A — Repository Closeout Reconciliation

## A1. Authority and scope

This audit applied the following fact priority:

1. current repository code and tests;
2. Final Closeout, Manifest, Seal, and machine-readable results;
3. version-level final reports;
4. phase reports;
5. repository orientation material.

The three externally supplied files were treated as follows:

| File | Role | SHA-256 |
|---|---|---|
| `SHILIU_V3_VERSION_DECISION(2).md` | External formal V3 version decision; V3 is not reopened | `fa6d394926d445ecfc5bfe20a6c2f4586c31adcbc9695dca99fdae9f5e993fa3` |
| `V3_5_FINAL_CLOSEOUT.md` | Formal V3.5 final closeout | `8ff300e13b9cca4283085082d37d0fa32568cb47be0e9086e7875c0da1297df8` |
| `FINAL_HANDOFF_PACKAGE_MANIFEST.md` | V3.5-A → V3.5-B handoff manifest, not the V3.5 final seal manifest | `fb4714d8638266505169e77a48ad4c22a4163739e517f45a48b62facef4817aa` |

The supplied V3.5 Closeout is byte-identical to the repository working-tree copy. Its hash also matches the value required by `V3_5_FINAL_FREEZE_SEAL.json`.

## A2. Formal V3 and V3.5 results remain closed

### V3

The external V3 Version Decision accepts V3 core capability and authorizes closeout with bounded limitations. Its formal facts include:

- 144 videos, 1,555 retrieval units, 1,412 chunks;
- 24 queries, 452 judgments, 10 approved evidence intervals;
- Discovery Recall@10:
  - Lexical: `0.4033`
  - Dense: `0.8801`
  - Hybrid: `0.8820`
  - Auto: `0.8816`
- Product Search and timestamp evidence were accepted with limitations;
- known limitations include broad Product Windows, coarse anchors, missing no-answer behavior, incomplete cross-language evidence, and other documented coverage gaps;
- the historical V3 Product default decision was Lexical, with Auto optional at that time.

This audit does not rerun or reinterpret those results.

### V3.5

`V3_5_FINAL_CLOSEOUT.md`, `V3_5_FINAL_CLOSEOUT.json`, and `V3_5_FINAL_FREEZE_SEAL.json` consistently state that V3.5 is formally closed:

- engineering and evaluation execution were accepted;
- product Evidence Resolution/Sufficiency remained below target;
- no final answer generation, agent loop, memory, agent harness, or remediation system was delivered.

Development results:

| Metric | Result |
|---|---:|
| Retrieval target hit@1 | `0.7143` |
| Retrieval target hit@3 | `0.9286` |
| Retrieval target hit@5 | `0.9286` |
| Retrieval target hit@10 | `1.0000` |
| Candidate Builder complete-group coverage | `0.4615` |
| Selector bundle hit | `0.0769` |
| Track A semantic four-state accuracy | `0.4286` |

Frozen results:

| Metric | Result |
|---|---:|
| Retrieval target hit@1 | `0.8000` |
| Retrieval target hit@3 | `0.8000` |
| Retrieval target hit@5 | `0.9000` |
| Retrieval target hit@10 | `1.0000` |
| Candidate Builder complete-group availability | `0.0000` |
| EvidenceBundle complete-group hit | `0.0000` |
| Bundle required-span recall | `0.0250` |
| Semantic four-state accuracy | `0.2000` |
| Runtime errors | `0` |

Primary formal frozen attribution:

- `5 builder_incomplete`;
- `5 mechanical_source_unverifiable`.

These are historical final results, not open algorithm questions.

## A3. Closeout commit, current HEAD, and working tree

```yaml
repository_state:
  branch: codex/v3-domain-completion
  head: 91a34061f8aebb216749c015a37a4ff1974f4f2a
  closeout_recorded_source_commit: 91a34061f8aebb216749c015a37a4ff1974f4f2a
  upstream_relation:
    ahead: 2
    behind: 0
  tracked_dirty_entries: 19
  tracked_modified: 18
  tracked_deleted: 1
  untracked_files_before_this_report: 2807
  untracked_files_after_adding_this_report: 2808
  untracked_size_approx_mib: 168.94
```

The commit identities match, but their meanings must not be conflated:

| State | What is present | What is absent or unresolved |
|---|---|---|
| V3.5 Closeout recorded source commit | V3 retrieval/Product Search baseline and a substantial `research/v3_5` history | Final V3.5 Evidence package, `stage5.py`, Evidence runtime package, final closeout/seal, Stage 5 UI/API, and final integration tests are not committed |
| Current `HEAD` | Exactly the recorded source commit | Same omissions; full test collection is internally incomplete |
| Current working tree | Adds Product Default Auto changes, Evidence runtime, Stage 5, UI/API, formal closeout artifacts, tests, results, logs, and runtime data | Provenance is mixed; 2,807 untracked files and 19 tracked changes have not been reconciled into a final repository snapshot |

Specific examples absent from `HEAD` but present in the working tree include:

- `src/shiliu/evidence/`;
- `src/shiliu/stage5.py`;
- `src/shiliu/static/search.js`;
- `src/shiliu/templates/search.html`;
- `tests/test_stage5_integration.py`;
- `V3_5_FINAL_CLOSEOUT.md`;
- `V3_5_FINAL_CLOSEOUT.json`;
- `V3_5_FINAL_FREEZE_SEAL.json`.

The current working tree also changes Product Search’s default from the committed `lexical` default to `auto` and adds `ProductSearchService.search_with_raw()`.

Therefore, “Closeout commit equals HEAD” does **not** establish that `HEAD` is the final V3.5 code snapshot. The Closeout records a source reference, while the final integrated implementation and evidence remain outside that commit.

## A4. Working-tree inventory

The following inventory is a mutually exclusive, path/name/content heuristic over the 2,807 untracked files observed before this report was created, supplemented by direct inspection. The report itself is the sole new file produced by this task, so the post-delivery Git count is 2,808. The inventory is useful for reconciliation, but it is not itself a new Manifest and does not confer authority.

```yaml
workspace_inventory:
  source_code_changes:
    tracked: 13
    untracked: 122
    notes:
      - Includes application, retrieval, evidence, Stage5, scripts, UI, and packaging changes.
      - The tracked deletion of scripts/run_stage3r_qc_phase_b_r.py is unresolved.

  test_changes:
    tracked: 5
    untracked: 86
    notes:
      - Includes V3.5 evidence, gate, semantic judge, Stage5, API, seal, and historical contract tests.

  authoritative_docs:
    tracked_modified: 1
    untracked_candidates: 72
    notes:
      - "Candidate" means authority-looking by filename/location; only hashes and seal/manifest chains establish formal authority.
      - Includes V3_5_FINAL_CLOSEOUT.md and multiple phase/freeze/closeout records.

  eval_results_and_manifests:
    untracked: 1872
    notes:
      - Dominated by research/v3_5 JSON, JSONL, Markdown, and result trees.
      - Includes formal results as well as intermediate, superseded, diagnostic, and retry artifacts.

  runtime_data:
    untracked: 9
    notes:
      - Includes SQLite databases and SQLite WAL/SHM sidecars.
      - Must not be assumed suitable for source control.

  generated_logs_and_traces:
    untracked: 603
    notes:
      - Includes execution logs, usage records, runtime traces, and generated execution trees.

  caches:
    visible_untracked: 0
    notes:
      - Ignored Python/test/tool caches are outside this Git-visible count.

  duplicates_or_backups:
    untracked: 20
    notes:
      - Includes handoff draft/revision packages, expanded-plus-archive copies, and historical invalid/replacement branches.

  unknown:
    untracked: 23
    notes:
      - Mostly authority-looking plans, freeze reports, worklogs, triage files, adjudication bundles, and top-level revalidation results that need manifest-level classification.
      - "Unknown" does not mean invalid; it means the audit could not safely infer final authority from path and name alone.
```

The 19 tracked changes are:

- `V3_CURRENT_STATE.md`;
- `pyproject.toml`;
- deleted `scripts/run_stage3r_qc_phase_b_r.py`;
- `src/shiliu/app.py`;
- `src/shiliu/retrieval/__init__.py`;
- `src/shiliu/retrieval/models.py`;
- `src/shiliu/retrieval/orchestrator.py`;
- `src/shiliu/retrieval/product_search.py`;
- `src/shiliu/retrieval/service.py`;
- `src/shiliu/static/app.js`;
- `src/shiliu/static/library.css`;
- `src/shiliu/sync.py`;
- `src/shiliu/templates/base.html`;
- `src/shiliu/web.py`;
- five retrieval/database/API/contract test files.

The tracked diff totals 724 insertions and 143 deletions. This is not a lightweight documentation-only delta.

### Formal-result candidates versus generated material

The following are strong formal-result candidates because the final seal or closeout directly names and hashes them:

- `V3_5_FINAL_CLOSEOUT.md`;
- `V3_5_FINAL_CLOSEOUT.json`;
- `V3_5_FINAL_FREEZE_SEAL.json`;
- the refreeze seal and component/result files named by those records.

The current hashes of the final Closeout JSON and refreeze seal match the values recorded by the final seal:

```yaml
verified_current_hashes:
  V3_5_FINAL_CLOSEOUT_json: 79e85a945e985ad3e87c464924250f0568a6be4dc7776399b8ab8f3606ab4d38
  stage5_refreeze_seal: 4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c
```

By contrast:

- execution logs, request/response traces, provider-usage files, and generated trees are generated evidence, not source code;
- SQLite/WAL/SHM files are runtime state;
- handoff R1/R2 and invalid/replacement execution branches are historical provenance, not automatically the final state;
- the supplied `FINAL_HANDOFF_PACKAGE_MANIFEST.md` is a V3.5-A → V3.5-B transition package and must not be relabeled as the final V3.5 Manifest;
- no untracked file should be considered formal merely because it is under `research/v3_5`.

## A5. V3 repository closeout-chain gap

The external V3 Decision remains the formal historical decision. The repository lacks an independent `V3_CLOSEOUT.md`, and `V3_CURRENT_STATE.md` still says that closeout has not started and that the closeout file does not exist.

This is a documentation-chain gap, not a reason to reopen V3.

Minimal future repository hygiene:

1. archive the external Decision verbatim under an unambiguous repository name;
2. record its original filename, source, decision date, import date, and SHA-256;
3. add a short `V3_CLOSEOUT.md` or machine-readable Manifest that points to:
   - the archived Decision;
   - the frozen V3 evaluation protocol/results;
   - the accepted source commit or commits;
   - the known bounded limitations;
4. state explicitly that the file is archival and does not recalculate or revise the V3 decision.

## A6. Stale state documentation

Repository documentation is not aligned with final authority:

- `V3_CURRENT_STATE.md` says V3 closeout is not started, the default is Lexical, and `V3_CLOSEOUT.md` is absent;
- `V3_5_CURRENT_STATE.md` contains many layered “current authority” amendments and older “not started/unimplemented” statements below newer completion sections;
- `README.md` does not provide a clear final V3/V3.5 completion map and explicit non-deliverables consistent with the Final Closeout.

Recommended treatment is a single lightweight Repository Hygiene pass after baseline reconciliation:

1. add a prominent `superseded` notice to historical Current State documents;
2. point V3 to the archived Decision/Closeout and V3.5 to the Final Closeout/Seal;
3. update README with actual completed capabilities and explicit non-deliverables;
4. retain historical body text rather than rewriting history.

This should not become a separate large project.

## A7. Test reconciliation

### Recorded observations

Current working tree:

```yaml
current_working_tree_tests:
  full_collection:
    status: collection_error
    missing_module: scripts.export_pqs_v1_authoring_packet
    affected_test_file: tests/test_pqs_v1_authoring_packet_contracts.py

  excluding_the_uncollectable_file:
    collected: 1395
    passed: 1383
    failed: 12
    warnings: 1

  targeted_core_and_product_suite:
    passed: 121
    failed: 0
    files:
      - tests/test_retrieval.py
      - tests/test_dense_retrieval.py
      - tests/test_search_api.py
      - tests/test_product_search_api.py
      - tests/test_evidence_contracts.py
      - tests/test_evidence_stage1b.py
      - tests/test_v3_5_evidence_stage3a.py
      - tests/test_v3_5_stage4a_gate.py
      - tests/test_stage4b_semantic_judge.py
      - tests/test_stage5_integration.py
```

Clean export of current `HEAD`:

```yaml
head_tests:
  full_collection:
    status: collection_error
    errors: 2
    cause: committed Stage3R QC modules import shiliu.evidence.search, which is absent from HEAD
  excluding_the_two_internally_incomplete_test_files:
    passed: 491
    failed: 0
    warnings: 1
```

Thus:

- the committed deterministic core is largely green when internally incomplete test files are excluded;
- `HEAD` is not collection-clean;
- the working tree has much broader functionality and a green targeted product/evidence core, but its full suite is not clean.

### Failure classification

The classification below is narrow and named. It is not a blanket whitelist.

```yaml
test_failure_classification:
  regression:
    - tests/test_v3_5_stage3a_input_projection.py::test_two_independent_generations_are_byte_identical_and_do_not_write_snapshot
    - tests/test_v3_5_stage3a_reachability.py::test_frozen_request_reconstruction_preserves_every_field
    reason:
      - The current ProductSearchFilterRequest adds uploader_contains.
      - Pydantic model_dump now adds that defaulted field to a previously frozen request.
      - Regeneration therefore differs from the locked manifest, and exact reconstruction rejects the changed serialized shape.

  environment_drift: []

  missing_local_asset:
    - tests/test_v3_5_eval_v2_construction_workspace_export.py::test_workspace_manifest_hashes_every_asset
    - tests/test_pqs_v1_authoring_packet_contracts.py
    reason:
      - The first expects `/tmp/shiliu-v3-5-c0-construction-input-v2/workspace_manifest.json`; the directory currently exists, but that required top-level manifest does not.
      - The second imports an absent historical authoring-packet export helper and cannot collect.

  known_historical_failure:
    - tests/test_f1a_scoring_identity_bridge.py::test_canonical_identity_preserves_source_timeline_segments_and_times
    - tests/test_v3_5_handoff_fact_freeze_contracts.py::test_authority_inventory_hashes_match_current_files
    - tests/test_v3_5_handoff_fact_freeze_contracts.py::test_current_state_and_stress_corpus_are_explicitly_classified
    - tests/test_v3_5_handoff_fact_freeze_r1.py::test_current_state_records_corrected_handoff_and_no_completion_claim
    - tests/test_v3_5_handoff_fact_freeze_r2.py::test_r2_hash_inventory_matches_current_recorded_files_and_is_ready
    reason:
      - The canonical matcher returns frozen lineage official while one test expects official_subtitle.
      - Four handoff tests intentionally bind superseded Current State/hash snapshots rather than the final closeout state.

  stale_or_invalid_test:
    - tests/test_pqs_v1_p8_product_initial_baseline_contract.py::test_runtime_component_versions_match_authority
    - tests/test_v3_5_p9_candidate_design_amendment_contract.py::test_no_code_prediction_scoring_or_gold_change
    - tests/test_v3_5_p9_f1a_candidate_builder_decision_restart_contract.py::test_no_code_prediction_scoring_change
    reason:
      - These assert earlier phase component/source hashes after later authorized work.
      - They are historical phase guards, not current Final Seal guards.

  working_tree_contamination:
    - tests/test_v3_5_p9_f1a_candidate_builder_decision_restart_contract.py::test_no_frozen_access
    reason:
      - The test recursively decodes every discovered file as UTF-8 and encounters binary bytes in a generated output tree.
      - This is both workspace contamination and a fragile text-only test assumption.
```

The two deterministic serialization failures share one identified root cause; they are still regressions until compatibility is restored or the frozen test boundary is explicitly adapted. The missing assets are reproducible absences. No unexplained failure is accepted as policy.

### Required policy before a safe baseline

```yaml
test_policy:
  deterministic_core_suite: all_green

  external_or_environment_dependent:
    - explicitly_classified
    - reproducible
    - no_unexplained_failure

  historical_whitelist:
    allowed: true
    requirements:
      - named_test
      - narrow_scope
      - documented_reason
      - linked_closeout_or_issue
```

The current repository does not yet meet this policy because collection is incomplete and two deterministic compatibility tests are red.

## A8. Baseline blockers and deferrable hygiene

### Must be resolved before using the repository as a safe development baseline

1. Reconcile the final V3.5 code, contracts, tests, closeout artifacts, and seals into a self-contained repository state whose provenance is explicit.
2. Decide which of the 2,807 pre-report untracked files are:
   - final authoritative inputs/results;
   - retained historical provenance;
   - generated but reproducible evidence;
   - runtime data;
   - duplicates/backups;
   - disposable local output.
3. Restore collection-clean tests and make the deterministic core all green.
4. Resolve the ProductSearch frozen-request serialization compatibility regression.
5. Resolve the tracked deletion of `scripts/run_stage3r_qc_phase_b_r.py` and all other tracked deltas against the intended final state.
6. Produce a baseline Manifest that binds source files, required tests, formal result artifacts, and their hashes. The existing V3.5-A → V3.5-B handoff Manifest is insufficient for this purpose.

### May be deferred until after baseline identity is established

- V3 archival `V3_CLOSEOUT.md`/Manifest supplementation;
- `superseded` banners on Current State files;
- README completion/non-deliverable update;
- pruning or archiving duplicate historical packages;
- moving generated logs/traces/runtime databases out of the source baseline;
- narrow historical-test whitelist documentation.

## A9. Read-only evidence inspected

Formal and repository-state records:

- external `SHILIU_V3_VERSION_DECISION(2).md`;
- external and repository `V3_5_FINAL_CLOSEOUT.md`;
- external `FINAL_HANDOFF_PACKAGE_MANIFEST.md`;
- `V3_5_FINAL_CLOSEOUT.json`;
- `V3_5_FINAL_FREEZE_SEAL.json`;
- Stage 5 refreeze seal and repository failure triage;
- `V3_CURRENT_STATE.md`, `V3_5_CURRENT_STATE.md`, and `README.md`;
- Git branch, `HEAD`, upstream relation, status, tracked diff, untracked inventory, and clean `HEAD` export.

Primary implementation:

- `src/shiliu/retrieval/product_search.py`;
- `src/shiliu/retrieval/orchestrator.py`;
- `src/shiliu/evidence/contracts.py`;
- `src/shiliu/evidence/search.py`;
- `src/shiliu/evidence/source.py`;
- `src/shiliu/evidence/mapping.py`;
- `src/shiliu/evidence/authority.py`;
- `src/shiliu/evidence/stage3a.py`;
- `src/shiliu/evidence/stage3b.py`;
- `src/shiliu/evidence/stage4.py`;
- `src/shiliu/stage5.py`;
- `src/shiliu/web.py`;
- Search UI template/script and application wiring.

Primary tests:

- retrieval, dense, raw search API, Product Search API;
- Evidence contracts, source authority/mapping, Stage3A;
- Mechanical Gate and Semantic Judge;
- Stage 5 integration/API/UI/trace;
- frozen input projection/reconstruction;
- handoff fact-freeze, P8/P9 hash-guard, and closeout-era repository tests.

# Part B — Reusable Interface Audit

## B1. Actual current call path

The current working-tree product/evidence path is:

```text
ProductSearchRequest (default mode=auto)
  -> ProductSearchService.search_with_raw()
     -> SearchOrchestrator.search_raw()
        -> SearchPlanner
        -> lexical / dense / hybrid retrieval
        -> RawSearchResponse + RawSearchHit
     -> Product grouping/enrichment
        -> ProductSearchResponse + ProductVideoResult + Product Windows
  -> EvidenceSearchService.search_library()
     -> exact source-version binding and chunk-to-segment mapping
     -> SearchCandidateSet
  -> fixed Candidate Builder
     -> EvidenceCandidateSet
  -> fixed deterministic Fine Selector
     -> EvidenceBundle or no bundle
  -> Mechanical Gate
     -> judge_eligible / source_unverifiable / invalid
  -> frozen Semantic Sufficiency Judge when eligible
     -> SufficiencyDecision
  -> Stage5 root response and trace
```

Important default distinction:

- committed `HEAD`: Product Search defaults to `lexical`;
- current working tree: Product Search defaults to `auto`;
- raw `SearchRequest` remains a separate lower-level contract;
- `/api/search` uses current `ProductSearchRequest`;
- `/api/search/raw` uses `SearchRequest`;
- Stage 5 derives a Product Search request and therefore follows the current working-tree Product default.

## B2. Retrieval and evidence terminology

| Object | Meaning | Suitable as formal evidence? |
|---|---|---|
| Raw Retrieval Unit / `RawSearchHit` | Ranked retrieval hit; may be a video-level metadata unit or transcript chunk | No. It is retrieval output and may be metadata-only or tied only to indexed chunk state |
| Product Video / `ProductVideoResult` | One deduplicated, display-oriented video group made from multiple raw units | No. It is a product presentation object |
| Product Window | Temporally consolidated display window, enriched with jump anchors/chapters | No. Useful navigation context, but not authoritative Fine Evidence |
| `SearchRawUnitCandidate` | Raw hit enriched with source-version authority and exact chunk-to-segment mapping | Conditional. Eligible transcript candidates can cross the formal evidence boundary |
| `EvidenceCandidate` | Raw-source-derived, single-timeline, normalized candidate span with segment lineage | Yes, as a candidate—not yet a complete bundle |
| `EvidenceBundle` | One-video selection of EvidenceCandidates with identities, spans, text, versions, and trace | Yes as the selected evidence object, but completeness is not guaranteed |

Product Windows must not be silently promoted to Fine Evidence. Formal Fine Evidence is rebuilt from authoritative raw subtitle bytes and exact segment identities, not copied from display windows.

## B3. Interface records

### 1. ProductSearchRequest / ProductSearchResponse

```yaml
interface: ProductSearchRequest / ProductSearchResponse
location:
  - src/shiliu/retrieval/product_search.py
purpose:
  - Product-facing video search request and grouped presentation response.
current_callers:
  - ProductSearchService.search()
  - ProductSearchService.search_with_raw()
  - POST /api/search
  - Stage5PipelineRequest.search_request()
  - evaluation and smoke runners
input:
  - query
  - mode: lexical | dense | hybrid | auto
  - scope
  - result_limit
  - max_windows_per_video
  - exact filters plus Product-only uploader_contains
output:
  - request schema or grouped ProductSearchResponse
  - video results, display windows, trace IDs, routing/fallback, counts, timings, warnings
stability:
  - Pydantic request is strict, but not independently versioned.
  - Response is an internal frozen dataclass with as_dict(), not a declared public schema version.
  - Current additive filter change already altered exact serialized requests.
product_usage: production-used_local_product_surface
known_limitations:
  - Working-tree default Auto is not present in HEAD.
  - Display windows are broad presentation evidence, not Fine Evidence.
  - Exact model_dump equality is unsafe across additive request fields.
recommended_treatment:
  - reuse_with_adapter
```

Assessment: keep the user-facing semantics, but isolate external callers from exact internal model serialization and explicitly bind the intended default mode.

### 2. ProductSearchService.search()

```yaml
interface: ProductSearchService.search()
location:
  - src/shiliu/retrieval/product_search.py
purpose:
  - Execute Product Search and return only the grouped product response.
current_callers:
  - POST /api/search
  - product UI
  - CLI/application services
  - product tests and evaluation runners
input:
  - ProductSearchRequest
output:
  - ProductSearchResponse
stability:
  - Mature V3 product seam with current V3.5 default/filter additions.
  - Delegates to search_with_raw(), so one execution produces both raw and grouped views.
product_usage: production-used_local_product_surface
known_limitations:
  - Trace persistence is best-effort; result success can coexist with trace persistence warnings.
  - Product Search does not establish Fine Evidence identity.
recommended_treatment:
  - reuse
```

This is the preferred direct seam when the caller only needs product search cards/windows.

### 3. ProductSearchService.search_with_raw()

```yaml
interface: ProductSearchService.search_with_raw()
location:
  - src/shiliu/retrieval/product_search.py
purpose:
  - Return the RawSearchResponse and matching ProductSearchResponse from one retrieval execution.
current_callers:
  - ProductSearchService.search()
  - EvidenceSearchService.search_library()
input:
  - ProductSearchRequest
output:
  - tuple[RawSearchResponse, ProductSearchResponse]
stability:
  - Useful implementation seam, but newly present only in the dirty working tree.
  - Tuple ordering and internal dataclasses are not a versioned external contract.
product_usage: partial_internal_integration
known_limitations:
  - Couples evidence resolution to Product presentation execution.
  - Exposes raw retrieval implementation types.
  - Not present in the recorded Closeout source commit.
recommended_treatment:
  - reuse_with_adapter
```

It should be reused internally to avoid duplicate retrieval, but should not be exposed as an unversioned external ABI.

### 4. EvidenceSearchService.search_library() / SearchCandidateSet

```yaml
interface: EvidenceSearchService.search_library() / SearchCandidateSet
location:
  - src/shiliu/evidence/search.py
  - src/shiliu/evidence/contracts.py
purpose:
  - Convert one Product Search execution into a version-aware retrieval candidate set.
current_callers:
  - Stage5PipelineService.run()
  - V3.5 evaluation and projection tooling
  - evidence contract/integration tests
input:
  - ProductSearchRequest
  - authority mode: snapshot_manifest | pinned_request | live_current_exact_replay
  - optional snapshot, artifact manifest, pinned source versions, runtime corpus identity
output:
  - SearchCandidateSet
  - raw unit candidates with mapping/authority eligibility
  - product video candidates
  - trace/index/fallback/runtime identities
stability:
  - Explicit contract version v3.5-search-candidate-v1.
  - Strong semantic boundary, but represented by dataclasses and asdict rather than a strict schema model.
  - Current implementation is absent from HEAD.
product_usage: minimally_product_integrated
known_limitations:
  - request_parameters embeds exact ProductSearchRequest serialization and has already drifted.
  - created_at and persistence flags make whole-object hashes execution-dependent.
  - live authority proves current raw-byte/index compatibility, not historical index-source binding.
  - video-level candidates are intentionally ineligible as Fine Evidence.
recommended_treatment:
  - reuse_with_adapter
```

Answer to the stability question: `SearchCandidateSet` is the best existing **conceptual stable output boundary**, but not yet a safe repository-level stable ABI. A thin adapter should expose the stable candidate/identity subset and keep product presentation, trace persistence, timestamps, and exact request serialization out of equality-sensitive downstream contracts.

### 5. Evidence Identity / Source Version / Segment / Timestamp

```yaml
interface: Evidence Identity / Source Version / Segment / Timestamp
location:
  - src/shiliu/evidence/contracts.py
  - src/shiliu/evidence/source.py
  - src/shiliu/evidence/authority.py
  - src/shiliu/evidence/mapping.py
purpose:
  - Bind raw source bytes to stable artifact/version identities, segment IDs, timeline runs, and exact timestamps.
current_callers:
  - EvidenceSearchService
  - Stage3A Candidate Builder
  - Stage5 raw-source resolution
  - V3.5 eval/audit/replay tools
input:
  - SourceArtifactReference
  - authoritative raw subtitle bytes
  - expected version or snapshot manifest
  - RetrievalChunkReference for exact replay
output:
  - ParsedSourceArtifact
  - SourceVersionBinding
  - RawEvidenceSegment
  - TimelineRun
  - ChunkSegmentMapping
stability:
  - Explicit versions for identity, authority, timeline, mapping, chunk policy, and replay.
  - Fail-closed validation and deterministic SHA-256 identities.
product_usage: minimally_product_integrated
known_limitations:
  - V3 database rows do not persist historical source versions or raw segment identities.
  - Live mode proves present compatibility only.
  - Multiple timeline runs are legal, but every candidate must remain within one run.
  - Provisional source-identity v1 remains historical; v2 is current.
  - Source artifact identity intentionally relies on normalized platform/source/part/role/lineage; source version carries byte-level change.
recommended_treatment:
  - reuse
```

This is the strongest directly reusable technical asset. Source version, segment ID, exact timestamps, timeline-run boundaries, and exact chunk replay should remain authoritative over Product Window timing.

### 6. EvidenceCandidateSet and fixed Candidate Builder

```yaml
interface: EvidenceCandidateSet / resolve_from_search_candidates()
location:
  - src/shiliu/evidence/stage3a.py
purpose:
  - Build normalized, raw-source-derived candidate spans from eligible SearchCandidateSet units.
current_callers:
  - Stage5PipelineService
  - V3.5 Development/Frozen evaluation tools
input:
  - original query
  - SearchCandidateSet projection
  - raw source resolver
  - fixed CandidateBuilderConfig
  - query/manifest identities
output:
  - EvidenceCandidateSet containing versioned EvidenceCandidates and failure attribution
stability:
  - Evidence candidate contract is versioned.
  - Final runtime config is frozen to stage3b-acronym-w3.5-v1.
product_usage: partial
known_limitations:
  - Frozen complete-group availability was 0.0.
  - Development complete-group coverage was 0.4615.
  - Builder heuristics and acronym repair are historically frozen and not generally complete.
  - CandidateSet contains eval-track and end-to-end-claim fields that are not ordinary product concerns.
recommended_treatment:
  - reuse_with_adapter
```

Reuse the candidate contract, lineage checks, and failure attribution. Do not assume the frozen Builder always creates a complete CandidateSet.

### 7. EvidenceBundle and fixed selectors

```yaml
interface: EvidenceBundle / deterministic and structured selectors
location:
  - src/shiliu/evidence/stage3a.py
  - src/shiliu/evidence/stage3b.py
purpose:
  - Select one-video Fine Evidence candidates into a traceable EvidenceBundle.
current_callers:
  - Stage5PipelineService uses select_deterministic_bundle()
  - eval/diagnostic tools
  - structured selector is research/negative-result tooling, not the Stage5 runtime selector
input:
  - original query
  - EvidenceCandidateSet
  - deterministic SelectorConfig or structured provider/config
output:
  - EvidenceBundle or no bundle/abstention
stability:
  - Bundle contract v3.5-evidence-bundle-v1 is explicit.
  - Deterministic selector version is frozen.
  - Structured selector has a strict JSON contract but was formally rejected as the preferred selector.
product_usage: partial
known_limitations:
  - Development selector bundle hit was 0.0769.
  - Frozen complete-group hit was 0.0 and required-span recall was 0.025.
  - A structurally valid bundle is not evidence of semantic completeness.
  - Structured selector remains research-only/diagnostic and provider-dependent.
recommended_treatment:
  - reuse_with_adapter
```

Reuse the `EvidenceBundle` data and validation contract. Do not make either historical selector implementation a hard dependency. The structured selector should be treated as `research-only`.

### 8. MechanicalGateDecision

```yaml
interface: MechanicalGateDecision / apply_mechanical_sufficiency_gate()
location:
  - src/shiliu/evidence/stage4.py
purpose:
  - Perform pure mechanical validation and route valid evidence to semantic judging.
current_callers:
  - Stage5PipelineService
  - Stage4A evaluation
  - gate and integration tests
input:
  - SufficiencyRequest
  - EvidenceResolutionState
  - EvidenceBundle or None
  - MechanicalGatePolicy
output:
  - judge_eligible
  - source_unverifiable
  - invalid
stability:
  - Strict frozen Pydantic contracts and pure no-I/O implementation.
  - Policy literals bind exact V3.5 Builder, Selector, and Bundle versions.
product_usage: minimally_product_integrated
known_limitations:
  - It validates identity, provenance, structure, source integrity, and operational state only.
  - It cannot decide whether readable evidence semantically supports the query.
  - Exact frozen component-version literals make direct reuse outside the V3.5 chain too tight.
recommended_treatment:
  - reuse_with_adapter
```

Mechanical Gate responsibilities end at structural/operational eligibility. Semantic Sufficiency alone handles supported aspects, missing aspects, conflicts, and the four-state semantic result.

### 9. SufficiencyRequest / SufficiencyDecision

```yaml
interface: SufficiencyRequest / SufficiencyDecision
location:
  - src/shiliu/evidence/stage4.py
  - src/shiliu/eval_v3_5/stage4b.py
purpose:
  - Carry a mechanically eligible evidence bundle into semantic sufficiency judging and return a four-state decision.
current_callers:
  - Stage5PipelineService
  - FrozenSemanticJudgeAdapter
  - Stage4B evaluation and tests
input:
  - query and language
  - evidence identity/bundle
  - mechanical gate state
  - policy/component/eval metadata
output:
  - sufficient | partial | insufficient | unverifiable
  - supported_aspects, missing_aspects, conflicts
  - confidence, evidence IDs, reason/action fields
  - gate/judge/track/trace metadata
stability:
  - Strict frozen Pydantic contracts with explicit versions.
  - Runtime projection was added through defaulted compatibility fields.
product_usage: limited_pilot
known_limitations:
  - Frozen four-state accuracy was 0.2.
  - Judge latency is high and provider-dependent.
  - Contract mixes product-semantic fields with evaluation and frozen-chain bookkeeping.
recommended_treatment:
  - reuse_with_adapter
```

Ordinary product-relevant fields:

- status;
- supported aspects;
- missing aspects;
- conflicts;
- confidence;
- evidence bundle/IDs used;
- operational and semantic reason codes;
- action family;
- trace ID.

Primarily evaluation/diagnostic/frozen-chain fields:

- `evaluation_track`;
- `end_to_end_claim_eligible`;
- candidate/search set IDs used for replay;
- exact candidate Builder/Selector versions;
- mechanical/judge contract, prompt, model, and policy versions;
- validation errors and detailed route metadata.

The latter remain valuable in traces and evaluation records, but should not all be required from an ordinary product caller.

### 10. Stage5PipelineService

```yaml
interface: Stage5PipelineService
location:
  - src/shiliu/stage5.py
purpose:
  - Minimal synchronous integration of retrieval, Evidence resolution, gate, semantic judge, response, and trace.
current_callers:
  - POST /api/evidence-sufficiency
  - Stage5 integration tests
  - limited real-time pilot calls
input:
  - Stage5PipelineRequest
output:
  - dictionary response with candidate summaries, bundle, gate, decision, errors, latencies, and trace
stability:
  - Explicit pipeline and trace versions.
  - Implementation is absent from HEAD and exists only in the dirty working tree.
product_usage: limited_pilot
known_limitations:
  - Hard-binds the frozen Builder, deterministic selector, mechanical gate, Codex CLI provider/model/prompt/policy, and evaluation track.
  - Synchronous semantic judge timeout is 180 seconds.
  - Creates and writes a local trace directory.
  - Returns an untyped dictionary rather than a strict public response model.
  - Gate invalid/source-unverifiable routing and semantic bypass are V3.5-chain-specific.
  - Does not generate a final answer.
recommended_treatment:
  - refactor
```

Reusable parts:

- stage envelope with input/output hashes, timing, retry count, and error type;
- fail-closed source/evidence resolution;
- gate-before-semantic routing;
- final response’s evidence presentation;
- trace persistence pattern.

Over-bound parts:

- exact frozen Builder/Selector/Gate policy literals;
- hard-coded evaluation track;
- Codex CLI transport and frozen semantic judge;
- synchronous endpoint behavior;
- untyped response dictionary.

The frozen `Stage5PipelineService` as a whole should not become a subsequent-version hard dependency.

### 11. POST /api/search and search trace API

```yaml
interface: POST /api/search and GET /api/search/traces/{trace_id}
location:
  - src/shiliu/web.py
  - src/shiliu/static/search.js
  - src/shiliu/templates/search.html
purpose:
  - Product Search HTTP surface and retrieval/presentation trace lookup.
current_callers:
  - local Web Search UI
  - API and UI tests
  - local product operation
input:
  - ProductSearchRequest JSON
  - trace ID for lookup
output:
  - grouped ProductSearchResponse
  - raw retrieval trace plus optional presentation trace
stability:
  - Search endpoint is mature and directly tested.
  - HTTP envelope is practical but not separately versioned.
product_usage: production-used_local_product_surface
known_limitations:
  - Trace records are split between retrieval and presentation stores.
  - Best-effort trace persistence means a successful search may have incomplete trace persistence.
  - Product Window output is not formal Fine Evidence.
recommended_treatment:
  - reuse_with_adapter
```

`POST /api/search/raw` is also present, but it exposes a lower-level retrieval contract and should not replace the Product endpoint for ordinary callers.

### 12. Evidence/Sufficiency HTTP and UI surface

```yaml
interface: POST /api/evidence-sufficiency and GET /api/evidence-sufficiency/traces/{trace_id}
location:
  - src/shiliu/web.py
  - src/shiliu/static/search.js
  - src/shiliu/templates/search.html
  - src/shiliu/stage5.py
purpose:
  - Opt-in execution and trace inspection of the V3.5 Stage5 pipeline.
current_callers:
  - optional sufficiency control in local Search UI
  - integration tests
  - limited pilot calls
input:
  - Stage5PipelineRequest JSON
  - Stage5 trace ID
output:
  - Stage5 response/decision or typed stage errors
  - persisted root trace
stability:
  - End-to-end route is tested, including UI markers and safe DOM use.
  - Not present in HEAD; no separate API version.
product_usage: limited_pilot
known_limitations:
  - Semantic calls can take tens of seconds and may run up to a 180-second timeout.
  - HTTP runs synchronously in a worker thread.
  - 502/504 mapping is coarse.
  - Local-file trace persistence has no retention, concurrency, or operational durability contract.
  - The UI clearly states that no final answer is generated.
recommended_treatment:
  - reuse_with_adapter
```

The API/UI proves real integration, not stable daily production operation.

### 13. Trace Contract

```yaml
interface: V3 Search traces, Product presentation traces, and Stage5 root trace
location:
  - src/shiliu/retrieval/orchestrator.py
  - src/shiliu/retrieval/product_search.py
  - src/shiliu/stage5.py
purpose:
  - Persist routing, retrieval, presentation, stage hashes, timing, retries, errors, and judge metadata.
current_callers:
  - trace GET endpoints
  - local UI
  - tests
  - evaluation/closeout evidence
input:
  - execution state at each layer
output:
  - SQLite retrieval/presentation records
  - JSON Stage5 root trace with ordered stage records
stability:
  - Search trace version: v3-stage4a-search-trace-v1.
  - Stage5 root trace version: v3.5-stage5-root-trace-v1.
  - Stage5 trace is a plain dictionary/file schema, not runtime-validated by a strict model.
product_usage: partial
known_limitations:
  - Search and Product presentation traces are separate from Stage5 JSON traces.
  - Existing consumers may assume known stage names/order even though the endpoint can technically return additional stages.
  - Mutating the frozen v1 trace shape would compromise historical replay/closeout comparability.
recommended_treatment:
  - reuse_with_adapter
```

Extensibility finding:

- additive stage records do not inherently break the current file reader or GET endpoint;
- they can break exact-hash tests, consumers that assume an exact stage sequence, and frozen trace comparisons;
- new phases should not be inserted into historical `v3.5-stage5-root-trace-v1` while claiming the same frozen contract;
- preserve old traces and use an explicit versioned adapter/new trace contract when stage semantics change.

### 14. Typed errors

```yaml
interface: Typed Errors
location:
  - src/shiliu/retrieval/orchestrator.py
  - src/shiliu/retrieval/product_search.py
  - src/shiliu/evidence/contracts.py
  - src/shiliu/evidence/stage3b.py
  - src/shiliu/stage5.py
  - src/shiliu/web.py
purpose:
  - Preserve bounded machine-readable failure categories across retrieval, evidence, selector, Stage5, and HTTP.
current_callers:
  - product/evidence services
  - FastAPI handlers
  - traces and tests
input:
  - validation, index, source, mapping, provider, parse, timeout, and integration failures
output:
  - SearchExecutionError
  - ProductSearchError
  - EvidenceContractError
  - StructuredSelectorError
  - Stage5IntegrationError
stability:
  - Error codes/stages are explicit within each subsystem.
  - No single cross-layer public error envelope or version exists.
product_usage: partial
known_limitations:
  - Field names differ: code versus type/error_type; some include HTTP status/trace persistence and others do not.
  - Stage5 collapses several source/evidence cases into broad HTTP 502 responses.
  - Some generic exceptions are converted using last-stage inference.
recommended_treatment:
  - reuse_with_adapter
```

The named codes and fail-closed behavior are reusable; callers should not hard-code every subsystem’s current exception class or field naming.

## B4. Research-only, partial, and unsuitable hard dependencies

```yaml
asset_classification:
  production_used:
    - V3 local Product Search path
    - POST /api/search
    - grouped Product Video and Product Window presentation
    - retrieval and presentation trace persistence

  minimally_product_integrated_or_partial:
    - EvidenceSearchService and SearchCandidateSet
    - authoritative raw-source identity and exact segment mapping in live mode
    - EvidenceCandidateSet and EvidenceBundle path
    - Mechanical Gate
    - Sufficiency API/UI/trace
    - Stage5PipelineService

  research_only_or_diagnostic:
    - Structured LLM selector from stage3b.py
    - Track B oracle-video conditional evaluation
    - Track C legal-Gold-bundle diagnostic projection
    - eval harnesses, adjudication packets, failure-analysis trees, and phase-specific hash guards

  not_implemented:
    - final answer generation
    - complete RAG answer loop
    - agent loop
    - memory
    - agent harness
    - automatic remediation
    - proven stable daily Evidence/Sufficiency operation
```

The following historical implementations should not become subsequent-version hard dependencies:

- fixed `stage3b-acronym-w3.5-v1` Candidate Builder behavior;
- fixed `v3.5-deterministic-fine-selector-v1` selection behavior;
- rejected Structured LLM selector;
- exact V3.5 Mechanical Gate component-version literals;
- `FrozenSemanticJudgeAdapter`’s Codex CLI transport/model/prompt;
- `Stage5PipelineService`’s synchronous, dictionary-shaped, frozen-chain orchestration;
- Product Windows as a substitute for authoritative Fine Evidence;
- evaluation tracks, Gold projections, or phase hash guards as ordinary product request fields.

## B5. Reuse priority

Highest-value reusable assets, in order:

1. authoritative Source Artifact/Version/Segment/Timeline identities and exact replay;
2. `SearchCandidateSet` as the conceptual retrieval-to-evidence boundary, behind a thin adapter;
3. `EvidenceCandidate`/`EvidenceBundle` contracts and validation, without assuming historical Builder/Selector completeness;
4. Mechanical Gate’s pure structural/operational separation from Semantic Sufficiency;
5. the product-facing `ProductSearchService.search()` path;
6. versioned trace stage envelopes and typed reason/error codes, behind normalization adapters.

## B6. Decisions required from the repository owner

No decision below reopens V3 or V3.5:

1. What repository state should be designated as the post-closeout baseline:
   - a provenance-reconciled snapshot of selected current working-tree files; or
   - a separately reconstructed clean tree verified against the final seals?
2. Which final V3.5 artifacts and generated evidence must be retained in Git, and which should live in an external/archive package?
3. Should the external V3 Decision be archived verbatim under its supplied hash, followed by the minimal pointer-style `V3_CLOSEOUT.md`/Manifest?
4. For each named historical test failure, should the repository:
   - preserve a narrow documented historical whitelist; or
   - update/relocate the test so the default deterministic suite is all green?
5. Is the tracked deletion of `scripts/run_stage3r_qc_phase_b_r.py` intentional?
6. After baseline reconciliation, may the lightweight Current State/README hygiene pass proceed?

Until these are decided and the baseline is made self-contained and test-clean, subsequent development should not branch from the current dirty working tree.

# Part C — Candidate Final Repository Baseline and Manifest Plan

## C1. Scope, added evidence, and authority boundary

This Part C adds three sources to the audit:

| Source | SHA-256 at audit time | Use in this audit | Authority limit |
|---|---|---|---|
| External `03_V3_5_DECISION_AND_ARTIFACT_INDEX.md` | `0fe82cedb0252337bb691eb6119120d18b1c7f1fff678ba0925187e4dfbe5725` | Historical 32-artifact starting inventory | V3.5-A → V3.5-B handoff index; not the final V3.5 repository manifest |
| `STAGE5_MINIMAL_API_UI_TRACE_INTEGRATION_WORKLOG.md` | `5fd32621458fd8136c6d7e13e9151597289a6fe086247181c84f2fac9239eef8` | Stage 5 implementation, Freeze, post-Freeze repair, Refreeze, tests, and hash provenance | Worklog evidence; current code, tests, seals, and machine-readable results remain higher authority |
| External `01_V3_5_B_OPERATING_CONTRACT.md` | `7d145ded07c730f1bc3d32c3aa1ef34991da64ed65133e98acdc0ead27131788` | Manifest structure, hash/status/supersession requirements, and closeout criteria | Draft operating contract; planned artifacts are not treated as existent without repository evidence |

The repository also contains a later file at `03_V3_5_DECISION_AND_ARTIFACT_INDEX.md`, SHA-256
`37d9b1b92bdabc27c193be762dbddc64dc1f53bf641ee6fc586f776bb4a51610`.
It contains 97 records and later F1A-era information, but its top-level state still describes
Stage 4, Stage 5, Frozen Evaluation, and final closeout as incomplete. It is therefore a later
historical index, not the final repository index. The final closeout and seals supersede both
copies for final V3.5 status.

No Frozen Eval was rerun, no historical algorithm was reopened, and no file other than this
audit report was intentionally changed by this audit.

## C2. Historical Artifact Index reconciliation

### C2.1 Result

- All 32 paths recorded in the external historical Index exist in the current working tree.
- 28 files still have the exact recorded SHA-256.
- Four files differ. Every one of the four differences has later repository evidence explaining
  the evolution; none should be labelled unexplained working-tree contamination.
- The historical status labels are not carried forward mechanically. Several assets were later
  superseded, rejected, or reduced to historical/diagnostic status.

### C2.2 Item-by-item path and hash audit

In the table below, `exact` means the current SHA-256 is byte-for-byte equal to the historical
Index SHA-256 shown in the third column.

| # | Historical path | Historical SHA-256 | Current result | Current classification / supersession |
|---:|---|---|---|---|
| 1 | `V3_5_CURRENT_STATE.md` | `115bad56457cc53e40b03640a66f34d51cbbf3fc586a7bc31a043c282b2f8597` | Present; current `92b77a1f26df6fe589366966a8d3cec11ad15e7d57d45e7ce308d54612e82ed6` | Historical status document; amended after handoff and ultimately superseded by final closeout/seal |
| 2 | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.r2.json` | `01189effe05e75af0736d388f996801fbae16fe90264638c00c4ddecf986226e` | Present; exact | Historical handoff fact freeze; superseded for final state |
| 3 | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze_r2_execution.audit.json` | `08653df1d369fd794340ec679de9d1964ff8db873caa16c8f7ef22a808019603` | Present; exact | Historical handoff audit |
| 4 | `research/v3_5/handoff_draft/fact_freeze/HANDOFF_FACT_FREEZE_R2_REPORT.md` | `091fc61f86f853d94e10e4b168860a429c8501e6eb05ae0bdcd91014fa5ffa4a` | Present; exact | Historical handoff report |
| 5 | `research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md` | `01f1dd8d6f26bd68962ccb42b489f5be3d086cef2ed0fe90616cb9d3e43db90f` | Present; exact | Authoritative for historical Eval v1 only |
| 6 | `research/v3_5/gold/master_case_membership.locked.json` | `e95e23e6f9d4043b01d43e04c7a53ed56fe7577d2a1bcfc0b7b8996d12d60a93` | Present; exact | Authoritative historical Eval v1 split |
| 7 | `research/v3_5/gold/development_gold.8_cases.locked.jsonl` | `5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0` | Present; exact | Authoritative historical Eval v1 development asset |
| 8 | `research/v3_5/gold/heldout_gold.10_cases.locked.jsonl` | `6b7d06a6a0f3eeb61a9bc542ee8c2a8d12fc6d52fbb6576f64eff72d0d662789` | Present; exact | Authoritative historical Eval v1 frozen-evaluation asset; not evidence that an evaluation was run |
| 9 | `research/v3_5/gold/gold_lock_manifest.json` | `268d9b68e29cc7f242375ba108d9d99ef536e2f413c3747d9f95f7ab97588075` | Present; exact | Authoritative historical Eval v1 lock |
| 10 | `research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.manifest.json` | `bc557d87f6c457aba74af06ee6c3408399b619cb3a21b3f13411f1173923da5f` | Present; exact | Historical/diagnostic Stress Set v2 manifest |
| 11 | `research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.jsonl` | `a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148` | Present; exact | Historical/diagnostic Stress Set v2 corpus |
| 12 | `V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md` | `51d49541c2bbda28b96618b7df6299ea060135be5e25aecdbbd4dd69f471931d` | Present; exact | Formal historical Stage 1A report; final roots/seals are stronger identity evidence |
| 13 | `V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md` | `606a86078f61ad7c564a7c673b247e88314cc26630d6a85c176d67b968f7220f` | Present; exact | Formal historical Stage 1B report |
| 14 | `research/v3_5/stage3r_s1/contracts/segment_identity_bridge_contract.json` | `daa53e497bbb7da315f645e7016d5394e9fab86ff0c4fe45daf335720cea2668` | Present; exact | Formal segment scoring identity bridge |
| 15 | `src/shiliu/evidence/stage3b.py` | `8a2ed841efdf42f048347bf23ed1170a67ce7be0f3b03823eabef31847a80458` | Present; exact | Rejected structured-selector code; the historical Index label “Candidate Builder” is semantically wrong. Formal Builder/Selector-v1 implementation is in `stage3a.py` and its identity is established by accepted roots/seals |
| 16 | `research/v3_5/stage3b/stage3b_run_manifest.json` | `74a6e5cc2fef342b77022257ae4b623423342c8fc94adc74208e6028c728aba8` | Present; current `b6d567164274df97b7386143d976a7b2c0e828776f6b1746bebf15c0eea59e8d` | Later adaptive-builder experiment; recorded by F1A/F1B seals, rejected, and not the final formal builder identity |
| 17 | `src/shiliu/evidence/stage3a.py` | `34774d6c166680e7523010f9d1d950f9aa1b890487f46427279164cdedaed552` | Present; current `ce2f3d19834f4438852e2097a5c7ed24abd28a5720c784e546d99f66eca26ee8` | Later source contains frozen selector-v2 experiment; current hash is recorded in the selector-v2 Freeze Seal, but v2 was rejected and formal selector v1 was retained |
| 18 | `research/v3_5/stage3b/structured_selector_contract.json` | `a5ab067151f06aa3417b1f2cd305146a1667b59655be47a2647a6965dedbaf2a` | Present; exact | Rejected research asset; do not make it a product dependency |
| 19 | `research/v3_5/stage4a/mechanical_gate_contract.json` | `f255c42a46825b77f45b7d8c54b1f5746cfed2f5d8d501a4cb9aef6d09b93051` | Present; current `18d7297bd1eb1ada2261ec58d7df40bd877b5d7b6d32db2cfed3b98ad06685b9` | Documented Stage 4A-R replacement; current contract belongs to accepted `mechanical-gate-v1-r1` |
| 20 | `research/v3_5/product_default_auto_wiring/product_default_auto_wiring_manifest.json` | `5d5d42ad7501f8a9d917a17b7b6116da4f84f3d5d974f8a54e3dbcd88cb588f9` | Present; exact | Formal product wiring evidence |
| 21 | `research/v3_5/auto_smoke/frozen_auto_smoke_manifest.json` | `565c1ff6209143c386bef8ddb308d9cf9e0ab5f793be59d45fb8fe90fc7c04ea` | Present; exact | Historical frozen smoke evidence |
| 22 | `research/v3_5/stage3r_qc/track_a_auto_refresh/stage3r_track_a_auto_refresh_manifest.json` | `f09a6895ffb4d3bc3112871fadf3962815aa93054c174d13f08da2cf05f92ad9` | Present; exact | Historical diagnostic result, not the final product evaluation |
| 23 | `research/v3_5/stage3r_s1/rescore/track_b_metrics.json` | `4b2816b194cbc66fcb6dfd9c04f59c6509df3ae9c3f5d7b3ee64e96e4ab84ea4` | Present; exact | Historical oracle-video diagnostic, not end-to-end |
| 24 | `research/v3_5/product_query_set_v1/phase_a/product_query_set_phase_a_manifest.json` | `8fdf1e9d78eb7ff863ef98a6ad0922fa285358ab56962ed0d2253e9447be2274` | Present; exact | Historical authoring input; superseded by final Product Query Set flow |
| 25 | `research/v3_5/product_query_set_v1/phase_a_r/product_query_set_phase_a_r_manifest.json` | `806f78e93c617e7c4b0b71ad0db4e10ecb36015e4ed7a574e9f1dd4f1fc181dd` | Present; exact | Historical reconciliation input; superseded by final Product Query Set flow |
| 26 | `research/v3_5/product_query_set_v1/authoring_packet/STAGE3R_PQS_B0_NEUTRAL_AUTHORING_PACKET_EXPORT_TASK.md` | `2e2eea765e7400141b715cea77c89e0e88f98ef3f9d1f69b468110acf8dc1cc0` | Present; exact | Historical task contract |
| 27 | `research/v3_5/product_query_set_v1/authoring_packet/V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md` | `fe9033d74f2820cc37f1051409cc25af29561b8c4aa0abd13986f5249f8bf7aa` | Present; exact | Historical execution candidate; later final PQS artifacts are authoritative |
| 28 | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.json` | `17811fe8fad57d3f0850c24afa5868b94790d46b9204132716f9e1d5eb084959` | Present; exact | Superseded historical draft |
| 29 | `research/v3_5/handoff_draft/fact_freeze/HANDOFF_FACT_FREEZE_REPORT.md` | `91e5abb8f61556143792beefadd61f3de0089d35ea728387c072829d422d3576` | Present; exact | Superseded historical report |
| 30 | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.r1.json` | `8e9bb58ff6f6be3fe791803e1638ca50a20a85ffdf752a9889be024a9088826c` | Present; exact | Superseded historical fact freeze |
| 31 | `research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze_r1_execution.audit.json` | `c5a85def10fa5837a3b97b2ba48ac2dc49bad52d0dd79ce540c788f9d03ba502` | Present; exact | Historical execution audit |
| 32 | `research/v3_5/handoff_draft/fact_freeze/HANDOFF_FACT_FREEZE_R1_REPORT.md` | `3dbae1c23c2482ebf29445032f52c8b78182e6e727b56c26a6217025bc10c084` | Present; exact | Historical report |

### C2.3 Explanation of the four hash differences

1. `V3_5_CURRENT_STATE.md` evolved after the A → B handoff. Its changed bytes are expected
   historical amendments, but the document is now stale relative to `V3_5_FINAL_CLOSEOUT.md`
   and `V3_5_FINAL_FREEZE_SEAL.json`.
2. `stage3b_run_manifest.json` moved to an adaptive experimental builder configuration. Its current
   hash is bound by later F1A/F1B seals. The candidate was rejected, and the formal builder remained
   `stage3b-acronym-w3.5-v1`.
3. `stage3a.py` gained later experimental selector-v2 implementation. The current hash is bound by
   `SELECTOR_V2_FREEZE_SEAL.json`; F1B rejected selector v2 and retained
   `v3.5-deterministic-fine-selector-v1`.
4. `mechanical_gate_contract.json` was intentionally replaced during Stage 4A-R. Its current hash
   is bound by `STAGE4A_R_MECHANICAL_GATE_FREEZE.json` and belongs to the accepted
   `mechanical-gate-v1-r1`.

The key manifest lesson is that a source-file hash can record later experimental code without
promoting that experiment into the formal V3.5 chain. Final component identity must come from the
accepted root/seal and decision chain, not from “latest file wins.”

## C3. Stage 5 Freeze, repair, Refreeze, and current status

### C3.1 What the original Stage 5 Freeze formally covered

`STAGE5_INTEGRATION_FREEZE_SEAL.json`
(SHA-256 `c65b77dfb8fbce546e8054ec9d57af682db9b8be1c725f1d2b138326ee9d9461`)
froze the minimal product integration:

- `src/shiliu/stage5.py` orchestration over the already frozen Search → Builder → Selector →
  Bundle → Mechanical Gate → Semantic Sufficiency chain;
- application wiring in `src/shiliu/app.py`;
- reuse of `POST /api/search`;
- new `POST /api/evidence-sufficiency`;
- new `GET /api/evidence-sufficiency/traces/{trace_id}`;
- a Stage 5 panel in the existing `/search` UI;
- root trace contract v1 and persisted trace retrieval;
- integration, API, trace, UI, bypass, live-judge smoke, and DOM checks.

The original seven closeout artifacts are all present and byte-identical to the Worklog:

| Artifact | Current SHA-256 | Status |
|---|---|---|
| `STAGE5_EXISTING_INTEGRATION_AUDIT.md` | `13c138ef087f82e01dffd55cf534a17218c5e5c9bb4aad1c0fb58587fa2b9186` | Exact original closeout asset |
| `STAGE5_API_INTEGRATION_CONTRACT.md` | `b9093379015fd88af1e3016fb72e5f873ebae6f5d5bde7cd0a341d3b6073ed2e` | Exact original closeout asset |
| `STAGE5_TRACE_CONTRACT.md` | `4ccd0716bda3ea40f5d3ea90829d766969e8e0f0fb53ff72137e2e09a78bde8c` | Exact original closeout asset |
| `STAGE5_INTEGRATION_TEST_RESULTS.json` | `8c3bf69e1e3bc60030ff81297c79ce91df2ab60fb49975111f663364f50b84db` | Exact original test result |
| `STAGE5_LIVE_SMOKE_RESULTS.json` | `55b36c8d6b4969ed43a8433ece38b7b31d4ebfc56fa5cab41932c968c7f1c83e` | Exact historical live-provider smoke |
| `STAGE5_INTEGRATION_FREEZE_SEAL.json` | `c65b77dfb8fbce546e8054ec9d57af682db9b8be1c725f1d2b138326ee9d9461` | Exact original Freeze Seal |
| `STAGE5_FINAL_CLOSEOUT.md` | `062fd7c8d000a65014af60274663e86693313b39aa5b90cae599a470f5eaa62a` | Exact original Stage 5 closeout |

The original recorded baseline was:

- focused Stage 5 tests: `78 passed`;
- repository scope: `1371 passed`, `9` historical failures, and one collection dependency
  missing;
- one live eligible semantic-judge path, deterministic bypass paths, and UI DOM validation;
- provider timeout: `180` seconds.

### C3.2 Documented post-Freeze repair

The original Freeze was followed by a deliberately bounded product repair:

- restored exact uploader compatibility while adding `uploader_contains`;
- separated live-current product runtime from sealed frozen evaluation runtime;
- added synchronous cooldown behavior without restoring legacy fallback;
- repaired UI cover, display, and product presentation behavior;
- did not reopen Builder, Selector, Mechanical Gate, Semantic Judge policy, Gold, or Frozen Eval.

Consequently, seven original source/test hashes no longer match the original Freeze:

- `src/shiliu/stage5.py`
- `src/shiliu/app.py`
- `src/shiliu/static/search.html`
- `src/shiliu/static/search.js`
- `src/shiliu/static/search.css`
- `tests/test_stage5_integration.py`
- `tests/test_search_page.py`

These are not unexplained differences. They are covered by
`STAGE5_POST_FREEZE_REPAIR_CLOSEOUT.json` and then by
`STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json`
(current SHA-256 `4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c`).
All nine post-repair output hashes recorded by the Worklog still match current files, and all
28 directly path-checkable hashes in the Refreeze Seal match the current working tree.
`V3_5_FINAL_FREEZE_SEAL.json` binds this Refreeze Seal, making the repair part of the final V3.5
historical chain.

The repair closeout recorded:

- focused scope: `139 passed`;
- safe repository scope: `948 passed`, `6` known nonblocking failures;
- one missing collection dependency.

### C3.3 Current API/UI/Trace run status

Current evidence supports this maturity statement:

- the `/api/search`, `/api/evidence-sufficiency`, trace retrieval, and `/search` UI paths exist
  in current code;
- their repaired implementation is exactly bound by the current Refreeze Seal;
- in-process integration tests and historical live smoke evidence exist;
- no HTTP service was listening at `127.0.0.1:18520` during this read-only audit, so the audit
  does not claim that the product is currently running;
- current status is therefore **implemented, minimally product-integrated, limited-pilot,
  formally evaluated below target, and partial**, not `production-used`.

### C3.4 Relationship between the Stage 5 baselines and the current 12 failures

The counts are compatible once scope and time are made explicit:

| Baseline | Result | Meaning |
|---|---|---|
| Original Stage 5 Freeze | `78 passed`; repository `1371 passed`, `9` historical failures, one missing dependency | Before bounded product repair |
| Stage 5 post-repair Refreeze | `139 passed`; safe scope `948 passed`, `6` known nonblocking failures, one missing dependency | After repair; deliberately selected safe scope |
| Current broad suite, excluding the collection-blocked export test | `1383 passed`, `12 failed`, `1395 collected` | Later, broader, dirty working-tree scope |

The current 12 failures are:

| Classification | Count | Current fact |
|---|---:|---|
| `regression` | 2 | Exact frozen-request serialization and manifest projection now include additive default `uploader_contains`; known and reproducible, but unresolved |
| `missing_local_asset` | 1 | `/tmp/shiliu-v3-5-c0-construction-input-v2/workspace_manifest.json` is absent even though its directory exists |
| `known_historical_failure` | 5 | One `official` versus `official_subtitle` canonicalization expectation and four handoff current-state hash/status expectations |
| `stale_or_invalid_test` | 3 | One P8 runtime-component hash guard and two P9 `stage3a.py` old-hash guards predate documented F1/Stage 5 evolution |
| `working_tree_contamination` | 1 | No-frozen-access scanner treats a UTF-8 binary/local artifact as a normal scannable source |
| `environment_drift` | 0 among the 12 | None of these twelve requires that label |

Separately, full collection is blocked by the absent
`scripts/export_pqs_v1_authoring_packet.py`. This is a collection blocker, not one of the
12 executable failures.

All failures now have a concrete classification; **unexplained failures = 0**. However, the
two deterministic compatibility regressions are still real. Classification is not the same as
acceptance, so the current broad suite is not yet an acceptable all-green deterministic-core
baseline.

## C4. Final V3.5 formal chain and authoritative artifacts

### C4.1 Final seal chain verified in the current tree

`V3_5_FINAL_FREEZE_SEAL.json` has current SHA-256
`6cbb867d4c0b2ac54ae3249ab40c18fe274786063e1da54abe4ed1c853497518`.
Its bound final outputs exist and match:

| Final output | SHA-256 | Status |
|---|---|---|
| `V3_5_FINAL_CLOSEOUT.md` | `8ff300e13b9cca4283085082d37d0fa32568cb47be0e9086e7875c0da1297df8` | Authoritative final narrative closeout |
| `V3_5_FINAL_CLOSEOUT.json` | `79e85a945e985ad3e87c464924250f0568a6be4dc7776399b8ab8f3606ab4d38` | Authoritative machine-readable closeout |
| `V3_5_V4_READINESS_REPORT.md` | `876a426f1a0108ffd34e7c8bad7192a1c240c35e5fabd04051d53f84f7a846a2` | Authoritative final readiness report; its V4 suggestions are historical and are not inherited by this audit |
| `STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json` | `4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c` | Final current Stage 5 integration seal |

The final seal binds these formal component roots/seals:

| Component | Final identity |
|---|---|
| Retrieval | `v3-product-search-default-auto-v1`; the final seal records no monolithic retrieval hash |
| Auto Router | `0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e` |
| Candidate Builder | retained `stage3b-acronym-w3.5-v1`; root `7f995a3c1c31eddd0eff6221494dd60032d00a155d431a68c58fb7cf55bbf3c1` |
| Fine Selector | retained `v3.5-deterministic-fine-selector-v1`; root `350a2aa6fab58580fb259471a7a6b87fc206701189ebb7bff97d031613444c67` |
| Mechanical Gate | accepted `mechanical-gate-v1-r1`; root `1577a51e57661a0a8bcbd51cfaed31013bdf2859ab786d67c50f7c42fa84f17c` |
| Evidence Identity | V1; root `35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7` |
| Semantic Sufficiency | `SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json`; SHA-256 `2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59` |
| Stage 5 API/UI/Trace | `STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json`; SHA-256 `4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c` |
| Repository source-commit reference | `91a34061f8aebb216749c015a37a4ff1974f4f2a` |

The `retrieval: null` hash in the final seal must not be silently replaced with an invented
monolithic hash. A final repository manifest should bind the versioned Product Default Auto
manifest and the selected source/test files explicitly.

### C4.2 Candidate authoritative evaluation and decision set

At minimum, the final repository manifest should explicitly bind:

| Path | Current SHA-256 | Proposed status |
|---|---|---|
| `research/v3_5/product_query_set_v1/freeze/product_query_set_v1.manifest.json` | `eb1a30ae0b1643c246a9c2c5a1b9ae1113748a3227fa2e10b77a1c1f2d9402eb` | Authoritative final Product Query Set manifest |
| `research/v3_5/product_query_set_v1/split_v1/product_query_split_v1.manifest.json` | `34d3ecdb79dfa86d9ac43f48a6a245ab4c996004cacb4191a637798ec1f85ec3` | Authoritative final split manifest |
| `research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1/development_gold_v1.seal.json` | `1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a` | Authoritative development-Gold seal |
| `research/v3_5/product_query_set_v1/gold_construction_v1/frozen_guarded/frozen_cycle_v1/internal_protected/frozen_gold_v1.seal.json` | `166e7c463de06e31d6c831d97c00f54dcf149312fb77cb66505bf15985c584a8` | Authoritative protected Frozen-Gold seal; access policy still applies |
| `research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1/f1a_final_execution_decision.json` | `36447553130bbcb78976209b0f676cb7c52cf2b788642f785216d4c994a9e363` | Authoritative F1A rejection/retention decision |
| `F1B_FINAL_CLOSEOUT.json` | `1a2b80659c0f4bba691b85ded1dbb542ec40e61a6da1a6c4a5f8350eddd0ce6b` | Authoritative F1B rejection/retention closeout |
| `STAGE4A_R_FINAL_CLOSEOUT.json` | `51f0cbce9b7ff7d33a8cdc2c86d5c2963244f998133fdf52beaa232db305df68` | Authoritative Mechanical Gate R1 closeout |
| `STAGE4B_FINAL_CLOSEOUT.json` | `a881fdc4cea3fd0a625009181ef0eda0b029f26608a11e98e1acdb4cd94f24c0` | Authoritative semantic-sufficiency closeout |
| `SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json` | `2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59` | Authoritative semantic-sufficiency seal |
| `STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json` | `4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c` | Authoritative current Stage 5 seal |
| `research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_FROZEN_RESULT_FREEZE_SEAL.json` | `9dfe516c354267edbf69db9470a5048499a034ea5c68c2891ceab2a95970e145` | Authoritative frozen-result seal |
| `research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_REPLACEMENT_FORMAL_RUN_MANIFEST.json` | `3d09dd34a62bf4470a7d47cdee753fb68507910b5588f056c3cd3f0f51fda9da` | Authoritative replacement formal-run manifest |
| `research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_REPLACEMENT_PREDICTIONS_FREEZE.json` | `3612c3f6889a9a05c87d507f42bc748888d386547ab0f43eeae15ee2fd920f2e` | Authoritative prediction-freeze record |
| `V3_5_FINAL_CLOSEOUT.md` | `8ff300e13b9cca4283085082d37d0fa32568cb47be0e9086e7875c0da1297df8` | Authoritative final narrative |
| `V3_5_FINAL_CLOSEOUT.json` | `79e85a945e985ad3e87c464924250f0568a6be4dc7776399b8ab8f3606ab4d38` | Authoritative final machine result |
| `V3_5_FINAL_FREEZE_SEAL.json` | `6cbb867d4c0b2ac54ae3249ab40c18fe274786063e1da54abe4ed1c853497518` | Authoritative top-level V3.5 seal |

This is a candidate minimum set, not permission to expose protected Gold or to treat every file
under `research/v3_5/` as authoritative.

## C5. Working-tree reconciliation refined by the new Stage 5 evidence

### C5.1 Tracked modifications

The current tracked-dirty count remains 19. The Stage 5 Refreeze explains 13 of them exactly:

- `src/shiliu/app.py`
- `src/shiliu/retrieval/models.py`
- `src/shiliu/retrieval/product_search.py`
- `src/shiliu/retrieval/service.py`
- `src/shiliu/static/app.js`
- `src/shiliu/static/library.css`
- `src/shiliu/sync.py`
- `src/shiliu/templates/base.html`
- `src/shiliu/web.py`
- `tests/test_database_and_sync.py`
- `tests/test_dense_retrieval.py`
- `tests/test_product_search_api.py`
- `tests/test_retrieval.py`

The other six have these current classifications:

| Path | Classification | Final-baseline status |
|---|---|---|
| `V3_CURRENT_STATE.md` | Authoritative-history update but now a stale Current State document | Explainable; mark superseded rather than use as current truth |
| `pyproject.toml` | Adds `openai>=2,<3`; plausible provider integration dependency | Provenance/final inclusion decision still required because it is not bound by the Stage 5 Refreeze |
| `scripts/run_stage3r_qc_phase_b_r.py` | Tracked deletion | Unresolved; owner must decide whether deletion is intentional |
| `src/shiliu/retrieval/__init__.py` | Exports `build_bilibili_jump_url`; plausible product UI integration | Provenance/final inclusion decision still required; not directly bound by the Stage 5 Refreeze |
| `src/shiliu/retrieval/orchestrator.py` | Adds optional trace persistence | Explained by multiple V3.5 runtime freezes with matching current hash, despite omission from the Stage 5 Refreeze path list |
| `tests/test_stage3r_qc_phase_b_r_contracts.py` | Historical default-path test adjustment | Current hash is recorded by Product Default Auto wiring evidence; explainable historical correction |

Thus the new evidence materially narrows tracked ambiguity, but does not eliminate it:
`pyproject.toml`, `src/shiliu/retrieval/__init__.py`, and the deleted script still need an explicit
repository-owner disposition before a final clean baseline can be named.

### C5.2 Untracked files

The current porcelain view has 285 untracked path entries; recursively, those directories contain
approximately 2,808 untracked files, including this audit report. The earlier inventory remains
valid as a coarse classification:

- formal V3/V3.5 code, tests, closeouts, seals, and evaluation results;
- runtime SQLite/database state and imported data;
- generated logs, traces, caches, reports, and temporary exports;
- duplicate/backup copies;
- still-unknown files.

The Stage 5 evidence proves that many currently untracked code, tests, closeouts, and seals are
formal V3.5 outcomes rather than contamination. It does **not** prove that all untracked files
should be committed. A final manifest requires a selected, path-specific authoritative set plus
an explicit generated-artifact policy; it must not use a blanket “track all” or “ignore all” rule.

## C6. Candidate Final Repository Baseline

### C6.1 Baseline conclusion

There is a valid historical V3.5 source reference:

```yaml
branch_at_audit: codex/v3-domain-completion
head_at_audit: 91a34061f8aebb216749c015a37a4ff1974f4f2a
head_commit_date: 2026-07-24T06:06:00+08:00
head_subject: "eval(v3.5): complete Stage 3R-QC mode-corrected diagnostic"
final_closeout_source_commit_reference: 91a34061f8aebb216749c015a37a4ff1974f4f2a
```

But `91a340…` is **not** a self-contained final repository baseline: the clean commit lacks the
later Evidence package, Stage 5 implementation and tests, final closeout, and final seals that
exist only in the current dirty/untracked tree. Therefore the candidate baseline must remain:

```yaml
candidate_final_repository_baseline:
  status: not_yet_freezable
  branch: to_be_selected
  commit: to_be_created_after_reconciliation
  commit_date: to_be_recorded
  expected_working_tree_state: clean
  source_history_reference: 91a34061f8aebb216749c015a37a4ff1974f4f2a
  v3_5_top_level_seal:
    path: V3_5_FINAL_FREEZE_SEAL.json
    sha256: 6cbb867d4c0b2ac54ae3249ab40c18fe274786063e1da54abe4ed1c853497518
  stage5_current_refreeze:
    path: STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json
    sha256: 4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c
```

This distinguishes “the source commit named by historical seals” from “the commit that will
actually contain the complete final repository package.”

### C6.2 Closeout-completeness gate

| Required condition | Current status | Evidence / blocker |
|---|---|---|
| `formal_commit_identified` | `false` | `91a340…` is only a historical source reference; no clean self-contained final commit exists |
| `authoritative_documents_identified` | `true` for V3.5; `partial` for V0–V3.5 repository history | V3.5 final chain is identified; V3 Decision is still external and no repository `V3_CLOSEOUT.md` exists |
| `authoritative_eval_results_identified` | `true` | Candidate minimum set and top-level seal chain identified |
| `modified_files_classified` | `partial` | Most are explained; three tracked changes still require owner disposition |
| `untracked_files_classified` | `false` | High-level buckets exist, but not a path-specific final include/exclude inventory |
| `tests_classified` | `true` | All current executable failures and collection blocker have explanations |
| `unexplained_test_failures` | `0` | Classification complete |
| `generated_artifact_policy_defined` | `candidate_only` | Proposed below; not yet owner-approved or applied |
| `final_repository_manifest_created` | `false` | No `V3_5_FINAL_REPOSITORY_MANIFEST.md` exists |

Therefore the repository is **not yet ready to freeze**
`V3_5_FINAL_REPOSITORY_MANIFEST.md`.

### C6.3 Missing or still-unknown items

| Item | Current fact | Required for final V3.5 repository manifest? |
|---|---|---|
| `V3_5_FINAL_REPOSITORY_MANIFEST.md` | Does not exist | Yes |
| Formal clean repository commit containing the complete accepted V3.5 package | Does not exist | Yes |
| Repository copy of `SHILIU_V3_VERSION_DECISION.md` | Only the externally supplied Decision was verified | Required if the baseline claims complete V0–V3.5 historical coverage |
| `V3_CLOSEOUT.md` or pointer Manifest | Does not exist | Required if the baseline claims complete V0–V3.5 historical coverage |
| `scripts/export_pqs_v1_authoring_packet.py` | Absent; one test cannot collect | Owner disposition required |
| `/tmp/shiliu-v3-5-c0-construction-input-v2/workspace_manifest.json` | Absent; containing directory exists | Owner disposition required |
| `01_V3_5_B_OPERATING_CONTRACT.md` repository copy | External Draft exists; no repository copy found | Historical only; not required unless owner chooses to archive the handoff package |
| `04_V3_5_B_START_PROMPT.md` | Exists in the external handoff folder but not in the repository; it was not an authority source requested for this audit | Historical only; not required unless owner chooses to archive the handoff package |
| `pyproject.toml`, `src/shiliu/retrieval/__init__.py`, deleted Stage 3R-QC runner | Present as unresolved tracked changes | Explicit include/revert/delete decision required |
| Remaining unknown untracked files | Coarse categories exist, but no path-level disposition | Must be reduced to zero unknowns for the selected final package |

## C7. Proposed `V3_5_FINAL_REPOSITORY_MANIFEST.md`

The future manifest should be created only after repository reconciliation and should bind the
actual final commit. A suitable minimum structure is:

```yaml
manifest:
  name: V3_5_FINAL_REPOSITORY_MANIFEST
  schema_version: 1
  status: final
  created_at:
  created_by:

repository_baseline:
  branch:
  commit:
  commit_date:
  expected_working_tree_state: clean
  historical_source_commit_reference: 91a34061f8aebb216749c015a37a4ff1974f4f2a
  top_level_freeze_seal:
    path: V3_5_FINAL_FREEZE_SEAL.json
    sha256: 6cbb867d4c0b2ac54ae3249ab40c18fe274786063e1da54abe4ed1c853497518

formal_components:
  retrieval:
    status: formal_product_path
    version: v3-product-search-default-auto-v1
    identity_path:
    selected_source_hashes: []
  evidence_identity:
    status: formal
    version: V1
    root_hash: 35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7
  candidate_builder:
    status: formal_retained_after_f1a_rejection
    version: stage3b-acronym-w3.5-v1
    root_hash: 7f995a3c1c31eddd0eff6221494dd60032d00a155d431a68c58fb7cf55bbf3c1
  fine_selector:
    status: formal_retained_after_f1b_rejection
    version: v3.5-deterministic-fine-selector-v1
    root_hash: 350a2aa6fab58580fb259471a7a6b87fc206701189ebb7bff97d031613444c67
  mechanical_gate:
    status: formal
    version: mechanical-gate-v1-r1
    root_hash: 1577a51e57661a0a8bcbd51cfaed31013bdf2859ab786d67c50f7c42fa84f17c
  semantic_sufficiency:
    status: formal_below_target
    seal:
      path: SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json
      sha256: 2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59
  stage5_api_ui_trace:
    status: minimally_product_integrated_limited_pilot
    refreeze_seal:
      path: STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json
      sha256: 4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c

authoritative_documents:
  - path:
    sha256:
    status:
    authority_for:

superseded_documents:
  - path: V3_5_CURRENT_STATE.md
    superseded_by: V3_5_FINAL_CLOSEOUT.md
    retention: historical
  - path: 03_V3_5_DECISION_AND_ARTIFACT_INDEX.md
    superseded_by: V3_5_FINAL_REPOSITORY_MANIFEST.md
    retention: historical_handoff_index

evaluation_artifacts:
  - path:
    sha256:
    status:
    access_policy:
    supersedes:

seals_and_runtime_manifests:
  - path:
    sha256:
    status:
    binds:

test_baseline:
  deterministic_core:
    command:
    collected:
    passed:
    failed: 0
  external_or_environment_dependent:
    - named_test:
      dependency:
      reproduction:
      expected_status:
  explained_failures: []
  historical_whitelist:
    - named_test:
      narrow_reason:
      linked_closeout_or_issue:

generated_artifact_policy:
  tracked_and_authoritative:
    - final closeouts
    - final decisions
    - machine-readable eval results required by the final seal chain
    - freeze/refreeze seals and small reproducibility manifests
  retained_locally_not_tracked:
    - provider traces or runtime captures retained for local audit but containing local state
    - large runtime databases and imported media-derived data not required for source checkout
  reproducible_and_excluded:
    - caches
    - temporary exports
    - compiled files
    - pytest and tool caches
    - regenerable logs
  unknown_pending_review: []

unresolved_items: []

supersession_rules:
  latest_file_does_not_imply_formal_promotion: true
  accepted_decision_and_seal_chain_controls: true

integrity:
  manifest_sha256:
```

The final manifest should contain exact per-path hashes and exact test commands. It should not
embed protected Gold contents merely to make the repository appear self-contained; it should
bind them through an access-aware seal.

## C8. Minimum work needed before a final repository manifest can be frozen

These are repository-closeout tasks, not a future-version project:

1. Select the exact formal file set from the dirty/untracked tree and create a clean,
   self-contained repository commit containing accepted V3.5 code, tests, final documents,
   evaluation-result manifests, and seals.
2. Decide the disposition of `pyproject.toml`, `src/shiliu/retrieval/__init__.py`, and the deleted
   `scripts/run_stage3r_qc_phase_b_r.py`.
3. Repair or explicitly version the two `uploader_contains` deterministic compatibility
   regressions; classification alone does not satisfy the all-green deterministic-core policy.
4. Decide whether to restore `scripts/export_pqs_v1_authoring_packet.py`, retire its collection
   test as stale, or supply a documented replacement path.
5. Define whether the missing `/tmp/.../workspace_manifest.json` is a required reproducibility
   input to archive, a locally regenerated asset, or an obsolete dependency.
6. Finish path-level classification of unknown untracked files and approve the generated-artifact
   policy.
7. Archive the external V3 Decision into the repository with source/date/hash and add the minimal
   V3 closeout pointer, if the final repository manifest is intended to cover all V0–V3.5 history.
8. Add superseded markers to `V3_CURRENT_STATE.md`, `V3_5_CURRENT_STATE.md`, and the obsolete
   handoff Index; update README to the final V3/V3.5 status.
9. Run the named deterministic baseline on the candidate clean commit, record zero unexplained
   failures and zero deterministic-core failures, then create
   `V3_5_FINAL_REPOSITORY_MANIFEST.md` with the actual branch, commit, date, hashes, and test
   results.

Items 7 and 8 are repository hygiene and may follow settlement of the exact V3.5 artifact set and
test baseline, provided the candidate manifest records the temporary document gap. Items 1–6 and
9 block a trustworthy final repository baseline.

## C9. Owner decisions still required

1. Should the final repository package cover V3.5 only, or be the single V0–V3.5 historical
   baseline? The latter makes the external V3 Decision archive and minimal V3 closeout pointer
   mandatory.
2. Are the `pyproject.toml` dependency change, `build_bilibili_jump_url` export, and deletion of
   `scripts/run_stage3r_qc_phase_b_r.py` intended final outcomes?
3. For the two `uploader_contains` regressions, is compatibility to preserve the exact old
   serialized shape, or should the contract/test receive a versioned successor? This is contract
   closeout, not algorithm reopening.
4. Is the missing PQS export helper required to remain supported, or should its stale collection
   test and task contract be retired with a documented reason?
5. Which local runtime datasets/traces must be retained for audit, and which must remain excluded
   because they are large, reproducible, private, or provider-dependent?
6. May a later repository-hygiene pass create the final baseline commit and manifest after these
   decisions, or should this audit remain purely advisory?
