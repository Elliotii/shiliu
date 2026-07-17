# V3 Checkpoint 2 — Quality Gate and Minimal Run/Resume

Date: 2026-07-17
Scope: code and deterministic/Fake Provider tests only; no real 48-card model run.

## Implemented

- Dedicated Content Type and Domain candidate schemas.
- Stable Draft node completeness fields: temporary ID, name, definition, includes,
  excludes, supporting IDs, representative IDs, parent ID and node type.
- Local subdomain stability signal and parent hint.
- Content Type-only recovery stage for missing local output dimensions.
- Independent Hierarchy Validation report schema and prompt.
- Deterministic Taxonomy Quality Gate with structured blocking issues, warnings,
  metrics and retry stage.
- Checks for missing Content Types/Domains, invalid IDs, invalid support IDs,
  representative support, parent-child consistency, sibling support overlap,
  Entity leakage, Content Type leakage and supported-but-missing subdomains.
- Database-backed `taxonomy_runs` and `taxonomy_stage_runs` repository.
- Stable run directory, frozen batch plan and per-stage output Hash validation.
- CLI create/run/resume/status entry points.
- Completed Batch skipping after interruption.
- Quality failure retry from Content Type Recovery, Consolidation or Hierarchy
  Validation without resetting completed local Discovery batches.
- Raw-response resume before a new provider request.
- Repair-only resume after JSON Repair request or validation failure.

## Recovery tests

- Batch 2 interruption: Batch 1 remained completed and was not called again.
- Failed Batch 2 resumed independently; attempt count increased from 1 to 2.
- Missing local Content Types triggered only Content Type Recovery for affected
  batches.
- First Consolidation quality failure reset Consolidation and downstream stages;
  both local batches remained at one call.
- Repair request failure resumed only Repair; the original corpus request stayed at
  one call.
- A persisted raw response with no parsed output was parsed locally on resume; no
  provider method was called.

## Verification

- 87 tests passed.
- `compileall` passed.
- `git diff --check` passed.
- Runtime taxonomy code has no Eval imports.
- Real database still contains zero Taxonomy Runs and zero Taxonomy Stage Runs.
- Snapshot #2 remains 131 cards / 128 eligible with hash
  `<private-snapshot-hash>`.

## Intentional boundary

Checkpoint 2 did not call a real model, so Token/cost usage is zero for this
checkpoint and no latency comparison is claimed. The next action is Checkpoint 3:
create one 48-card regression Run, execute it through Quality Gate and one Trial
Assignment, and report actual structure, usage, latency and recovery evidence before
any full A/B/C run.
