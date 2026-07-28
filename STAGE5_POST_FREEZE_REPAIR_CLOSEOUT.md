# Stage 5 Post-Freeze Delta Repair and Re-Freeze Result

## 1. Original Stage 5 Freeze status

The original `STAGE5_INTEGRATION_FREEZE_SEAL.json` remains an unmodified,
valid historical snapshot.

```yaml
original_outcome: stage5_minimal_integration_pass_with_documented_limitations
original_status: formally_closed_pass_with_limitations
parent_freeze_sha256: c65b77dfb8fbce546e8054ec9d57af682db9b8be1c725f1d2b138326ee9d9461
```

The current repository no longer equals that snapshot, so a separate current
integration seal was created.

## 2. Post-freeze Delta Audit

Generated:

- `STAGE5_POST_FREEZE_DELTA_AUDIT.md`
- `STAGE5_POST_FREEZE_DELTA_AUDIT.json`

The audit classifies each relevant file as UI-only, operational sync, API
integration, retrieval-filter semantics, test-only, or documentation.

The delta was not misclassified as UI-only. It includes filter semantics, sync
protection, Product/Frozen runtime isolation, Eval safety guard, UI presentation,
and tests.

## 3. Uploader exact/contains contract repair

Backward compatibility is restored:

```yaml
uploader:
  match_mode: case_insensitive_exact
  partial_name_matches: false

uploader_contains:
  match_mode: case_insensitive_substring
  additive_product_field: true
```

The old `uploader` request keeps its original meaning. The new Product-only
field does not modify the frozen Raw Search request or Auto Router.

## 4. Product UI field behavior

The `/search` control `UP 主（名称包含）` sends
`filters.uploader_contains`.

The Product UI no longer sends a partial name through `filters.uploader`.
Stage 5 inherits the Product Search request contract and accepts both fields.

## 5. Live runtime configuration

Product runtime is explicit:

```yaml
runtime_mode: product_runtime
corpus_identity: shiliu-live-current
sync_allowed: true
mutable_index_allowed: true
```

`/search`, `/api/search`, scheduled sync, and
`/api/evidence-sufficiency` continue to use the current local library.

## 6. Frozen Eval runtime guard

The Frozen Auto runner now requires a sealed runtime configuration before it
loads frozen inputs.

The guard requires:

- `runtime_mode=frozen_eval_runtime`;
- corpus identity equal to its seal;
- exact database, lexical-index, and dense-index SHA-256;
- sync disabled;
- mutable indexes disabled;
- requested snapshot path equal to the sealed path.

It rejects `shiliu-live-current`, active sync, mutable or unsealed indexes,
missing hashes, and mismatched hashes.

A synthetic sealed fixture passes preflight. Frozen Query, Gold, Prediction, and
Failure Analysis content was not opened.

## 7. Sync repair validation

The Product sync repairs remain:

- retryable errors enter cooldown;
- existing unavailable/auth-required/paused sources do not fall back to legacy
  sync;
- transient failure cannot empty the current index.

Regression tests pass. Frozen Eval cannot enable Product sync because its guard
requires `sync_allowed: false`.

## 8. UI and cover repair validation

Retained and revalidated:

- centered search covers;
- portrait detection and centered crop;
- fixed content-flow cover/card dimensions;
- generic pillarbox luminance detection and bounded zoom;
- card-colored uncovered background;
- `NO COVER` fallback;
- static cache-version updates.

JavaScript syntax passed. DOM/component tests passed. Evidence rendering still
uses safe nodes and `textContent`; no uncontrolled `innerHTML` exists. The live
browser smoke reported zero console errors.

## 9. Repository failure triage

Generated:

- `STAGE5_REPOSITORY_FAILURE_TRIAGE.md`
- `STAGE5_REPOSITORY_FAILURE_TRIAGE.json`

Safe no-Frozen-content repository run:

```text
948 passed
6 failed
1 warning
```

All six failures are individually classified:

- one stale F1A canonical-lineage expectation whose implementation hash exactly
  matches the Stage 4A-R freeze;
- one missing ephemeral construction workspace;
- four historical handoff state/hash expectations.

None is caused by this repair or blocks Product Search, Stage 5, frozen
components, Trace, or the Frozen Eval guard.

The missing `scripts/export_pqs_v1_authoring_packet.py` dependency is required
only by an older authoring-packet test module and is non-blocking.

## 10. Contract and regression tests

Focused affected suite:

```text
139 passed
0 failed
1 warning
```

Coverage includes:

- uploader exact and contains contracts;
- old filter-object compatibility;
- `/api/search`;
- `/api/evidence-sufficiency`;
- Gate Judge-call and bypass routing;
- Evidence ID preservation;
- Trace propagation and typed errors;
- safe UI DOM rendering;
- sync cooldown/no-legacy-fallback;
- Product/Frozen runtime guard;
- Builder, Selector, Gate, and Judge regressions.

Python compilation, JavaScript syntax, JSON parsing, and `git diff --check`
passed.

## 11. Live smoke tests

Product live runtime:

| Case | Result | Count | Trace |
|---|---|---:|---|
| Normal `AI` search | pass | 10 | `0b3a72db-4485-480f-80df-e176a615c8da` |
| Exact `晓辉博士` | pass | 4 | `88aedafc-cf24-4d01-8995-1708e2e6401d` |
| Exact partial `晓辉` | pass | 0 | `3f80fb00-042f-4522-8594-28c2d9f7a9fe` |
| Contains partial `晓辉` | pass | 4 | `6a00322c-9957-43c5-b810-3e2c6e891f89` |

Stage 5:

- source-unverifiable bypass: pass, Judge not called;
- synthetic invalid bypass: pass, Judge call count 0;
- judge-eligible: pass;
- Judge status: `sufficient`;
- Provider / Model: `openai-codex-cli` / `gpt-5.6-terra`;
- Parse status: valid;
- Retry count: 0;
- Total / Judge latency: 39,908 / 38,137 ms;
- Judge Trace:
  `stage5_trace_4caa20d399dec2a8b49894dc3117ba6798d518fd62adf963ac750ec2d4a92acf`.

Frozen guard:

- live-current rejected: pass;
- missing/mismatched hash rejected: pass;
- enabled sync rejected: pass;
- sealed synthetic fixture preflight: pass.

## 12. Frozen component integrity

Mechanically verified unchanged:

```yaml
formal_builder_root_sha256: 7f995a3c1c31eddd0eff6221494dd60032d00a155d431a68c58fb7cf55bbf3c1
formal_selector_root_sha256: 350a2aa6fab58580fb259471a7a6b87fc206701189ebb7bff97d031613444c67
Evidence_Identity_Contract_V1: 35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7
Stage4A_R_freeze: 1577a51e57661a0a8bcbd51cfaed31013bdf2859ab786d67c50f7c42fa84f17c
SufficiencyRequest_schema: 93ff095b2d01062194c1a663e06bd37ae57dd9f3e3fa5edda11c18db4a0a594c
SufficiencyDecision_schema: cf23071972bb34580dfe3ed075697f689b0dbeb67b3d0468df9d9141cc3477aa
semantic_judge_implementation: 55cd6811b0bb4e801a4f499ea0ea3b965db33323f7b2740f0ebb237d6aa687c9
Semantic_Judge_Final_Freeze_Seal: 2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59
```

The Auto Router source identity was restored to
`0876dbaf...bdaa7e`. No Stage 4B, F1A, or F1B algorithm was reopened.

## 13. Current Integration Re-Freeze Seal

Generated:

```text
STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json
SHA-256: 4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c
```

Recorded status:

```yaml
original_stage5_freeze:
  status: valid_historical_snapshot
current_integration:
  status: revalidated_and_refrozen
Stage5_algorithmic_reopen:
  occurred: false
```

## 14. Remaining documented limitations

- Six historical, individually triaged non-blocking tests remain red in the
  no-Frozen-content repository scope.
- One historical authoring-packet test dependency is missing and non-blocking.
- Production proxy timeout configuration remains outside this repository.
- The existing Stage 4B limitations remain: Track A is constrained by
  Retrieval/Evidence Resolution; Track B is an approved-span diagnostic
  projection; Semantic Judge latency remains high.

## 15. Frozen Evaluation content access confirmation

```yaml
Frozen_Evaluation_content_accessed: false
```

No Frozen Query, Gold, Prediction, or Failure Analysis content was opened or
used for tuning. Guard tests use synthetic sealed artifacts only.

## 16. Final Answer / Agentic Search status

```yaml
Final_Answer_added: false
Agentic_Search_added: false
Memory_added: false
Harness_added: false
```

## 17. Final outcome

```yaml
outcome: stage5_post_freeze_repair_and_refreeze_pass_with_limitations
status: formally_closed_pass_with_limitations
next_stage: Pre_Frozen_Checklist
```

The limitations are historical/non-blocking repository debt and external proxy
configuration. Current Product Search, Stage 5 API/UI/Trace, sync protection,
and Frozen Eval guard pass their acceptance criteria.

## 18. Output paths and SHA-256

```text
STAGE5_POST_FREEZE_DELTA_AUDIT.md
804510078d69181ed0db53d87cea3ffe7e1719fac13878c52baf8f0beebb4d1b

STAGE5_POST_FREEZE_DELTA_AUDIT.json
757f07294e75e35834c8457743307c194a2e0e62c3a8413e65c05ab5cd71609f

STAGE5_POST_FREEZE_FILTER_AND_RUNTIME_CONTRACT.md
e22698e5c75c8c5902a8fe4d7abf3552839c0b2f6c25c79a69ba1d4aebcce4d8

STAGE5_REPOSITORY_FAILURE_TRIAGE.md
909b80ed2eeea43ec7557d54cfb5daca1affd9e69e91b20a6bac94ee7ef73ef6

STAGE5_REPOSITORY_FAILURE_TRIAGE.json
ccd3e43e23c2c5c0dbad984750e83334c907c9ace162ef99cfd4fd34756166ef

STAGE5_CURRENT_INTEGRATION_TEST_RESULTS.json
7dfba4a97039495371bc2473dd423a046f2c1e28a044ab0e9bb266a8af04383f

STAGE5_CURRENT_INTEGRATION_LIVE_SMOKE_RESULTS.json
ddb9508b162c41e80407728df4294bba51a185cba2e3837b9e6fa4405d28efac

STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json
4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c
```

## 19. Pre-Frozen Checklist status

```yaml
Pre_Frozen_Checklist_started: false
next_stage: Pre_Frozen_Checklist
```

This closeout does not start the next stage.

## 20. Whether the Session can be closed

```yaml
Session_can_be_closed: true
```

The post-freeze repair, revalidation, and current-integration re-freeze are
complete.
