# Shiliu V0–V3.5 Final Repository Manifest

Status: `final`

This human-readable manifest contains only artifact identity and aggregate
evaluation information. It does not reproduce Case-level queries, Gold,
video identifiers, evidence text, labels, groups, decisions, or failures.

## Repository baseline

| Field | Value |
|---|---|
| Branch | `codex/v3-domain-completion` |
| Content baseline commit | `CONTENT_BASELINE_COMMIT_PENDING` |
| Commit date | `2026-07-29T00:00:00+08:00` |
| Manifest packaging commit | `SELF` |
| Expected final working tree | `clean_after_manifest_packaging_commit` |

The content baseline commit is the parent of the commit containing the final
Manifest values. `SELF` avoids the impossible requirement for a Git commit
to contain its own hash.

## Formal components

| Component | Version | Status | Authority hash |
|---|---|---|---|
| retrieval | `v3-product-search-default-auto-v1` | `formal_product_path` | `not_asserted` |
| auto_router | `v3-search-planner-auto-v1` | `formal` | `0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e` |
| evidence_identity | `V1` | `formal` | `35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7` |
| candidate_builder | `stage3b-acronym-w3.5-v1` | `formal_retained_after_f1a_rejection` | `7f995a3c1c31eddd0eff6221494dd60032d00a155d431a68c58fb7cf55bbf3c1` |
| fine_selector | `v3.5-deterministic-fine-selector-v1` | `formal_retained_after_f1b_rejection` | `350a2aa6fab58580fb259471a7a6b87fc206701189ebb7bff97d031613444c67` |
| mechanical_gate | `mechanical-gate-v1-r1` | `formal` | `1577a51e57661a0a8bcbd51cfaed31013bdf2859ab786d67c50f7c42fa84f17c` |
| semantic_sufficiency | `v3.5-semantic-sufficiency-policy-v1` | `formal_below_target` | `2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59` |
| stage5_api_ui_trace | `v3.5-stage5-current-integration-refreeze-seal-v1` | `minimally_product_integrated_limited_pilot` | `4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c` |

## Authoritative documents

| Path | SHA-256 | Status | Authority / boundary |
|---|---|---|---|
| `SHILIU_V3_VERSION_DECISION.md` | `fa6d394926d445ecfc5bfe20a6c2f4586c31adcbc9695dca99fdae9f5e993fa3` | `archived_external_formal_decision` | V3 version decision |
| `V3_CLOSEOUT.md` | `6fb23a639aa50945548d5e3a98413176c6bcc99a002e89d09b0497007488262c` | `final` | V3 repository closeout |
| `V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md` | `80e4abfd1d6b87f50a1c3e905a99af6fcc89d0ed2ce55d85c934f25809be9a75` | `final` | V3 formal retrieval evaluation |
| `V3_5_FINAL_CLOSEOUT.md` | `8ff300e13b9cca4283085082d37d0fa32568cb47be0e9086e7875c0da1297df8` | `final` | V3.5 formal narrative closeout |
| `V3_5_FINAL_CLOSEOUT.json` | `79e85a945e985ad3e87c464924250f0568a6be4dc7776399b8ab8f3606ab4d38` | `final` | V3.5 machine-readable closeout |
| `V3_5_V4_READINESS_REPORT.md` | `876a426f1a0108ffd34e7c8bad7192a1c240c35e5fabd04051d53f84f7a846a2` | `historical_final_readiness` | V3.5 readiness record; future-version suggestions not inherited |
| `SHILIU_V0_TO_V3_5_FINAL_CLOSEOUT.md` | `871722800d97e4e5fb29f123c9a923da67c9ef5feea491e09923630427c8804f` | `final` | repository-wide V0-V3.5 closeout |

## Superseded documents

| Path | SHA-256 | Status | Authority / boundary |
|---|---|---|---|
| `V3_CURRENT_STATE.md` | `4d478b68fa612c975b84dbb8fbdf5bc65fbb29dc7b188a5798a4f4192f91421f` | `superseded_historical` | historical V3 current-state ledger |
| `V3_5_CURRENT_STATE.md` | `0574a01958a93b3e032e57e0102930f39e0706e08b5d29395300cdf7f4b912d1` | `superseded_historical` | historical V3.5 checkpoint ledger |
| `03_V3_5_DECISION_AND_ARTIFACT_INDEX.md` | `37d9b1b92bdabc27c193be762dbddc64dc1f53bf641ee6fc586f776bb4a51610` | `superseded_historical_handoff_index` | historical A-to-B artifact index |

## Evaluation artifacts

| Path | SHA-256 | Status | Authority / boundary |
|---|---|---|---|
| `research/v3_eval/eval_results.json` | `9bf49fe37565bbd8694e4bcd61a2c1126950b3387604797b8936407cd1c3bfbc` | `formal_v3_aggregate_result` | V3 aggregate metrics |
| `research/v3_eval/eval_queries.locked.jsonl` | `21382e8ba058cc6e51ea41c776ad216824363090888ee3a5569e36dc971c36ba` | `formal_v3_case_level` | V3 locked query set; path/hash only in overview documents; no case content reproduced |
| `research/v3_eval/eval_gold.locked.jsonl` | `873b5fbf78ba2e8fc90dfb2fca96776e0e703a1c4fedd56dd20a49e43995b300` | `formal_v3_case_level` | V3 pooled/judged Gold; path/hash only in overview documents; no case content reproduced |
| `research/v3_5/product_query_set_v1/freeze/product_query_set_v1.manifest.json` | `eb1a30ae0b1643c246a9c2c5a1b9ae1113748a3227fa2e10b77a1c1f2d9402eb` | `formal_v3_5_dataset_manifest` | Product Query Set v1 identity |
| `research/v3_5/product_query_set_v1/split_v1/product_query_split_v1.manifest.json` | `34d3ecdb79dfa86d9ac43f48a6a245ab4c996004cacb4191a637798ec1f85ec3` | `formal_v3_5_split_manifest` | Development/Frozen split identity |
| `research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1/development_gold_v1.seal.json` | `1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a` | `formal_v3_5_development_gold_seal` | Development Gold aggregate seal |
| `research/v3_5/product_query_set_v1/gold_construction_v1/frozen_guarded/frozen_cycle_v1/internal_protected/frozen_gold_v1.seal.json` | `166e7c463de06e31d6c831d97c00f54dcf149312fb77cb66505bf15985c584a8` | `formal_v3_5_frozen_gold_seal` | protected Frozen Gold aggregate seal; protected Gold; seal/path/hash only in overview documents |
| `research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_FROZEN_RESULT_FREEZE_SEAL.json` | `9dfe516c354267edbf69db9470a5048499a034ea5c68c2891ceab2a95970e145` | `formal_v3_5_frozen_result_seal` | P14 aggregate result freeze |
| `research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_REPLACEMENT_FORMAL_RUN_MANIFEST.json` | `3d09dd34a62bf4470a7d47cdee753fb68507910b5588f056c3cd3f0f51fda9da` | `formal_v3_5_run_manifest` | replacement formal-run identity |
| `research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_REPLACEMENT_PREDICTIONS_FREEZE.json` | `3612c3f6889a9a05c87d507f42bc748888d386547ab0f43eeae15ee2fd920f2e` | `formal_v3_5_prediction_freeze` | prediction-before-Gold freeze; path/hash only in overview documents; no case content reproduced |

## Seals and manifests

| Path | SHA-256 | Status | Authority / boundary |
|---|---|---|---|
| `V3_5_FINAL_FREEZE_SEAL.json` | `6cbb867d4c0b2ac54ae3249ab40c18fe274786063e1da54abe4ed1c853497518` | `authoritative_top_level_seal` | V3.5 final seal |
| `STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json` | `4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c` | `authoritative_stage5_refreeze` | current API/UI/Trace integration |
| `SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json` | `2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59` | `authoritative_semantic_judge_seal` | semantic sufficiency policy/implementation |
| `STAGE4A_R_MECHANICAL_GATE_FREEZE.json` | `1577a51e57661a0a8bcbd51cfaed31013bdf2859ab786d67c50f7c42fa84f17c` | `authoritative_mechanical_gate_seal` | Mechanical Gate R1 |
| `SELECTOR_V2_FREEZE_SEAL.json` | `4eeef5b26c28c9ebaae95bdd4cf2a5afe936c31d1e7c1e5d61d3408c48ac64fe` | `historical_rejected_candidate_seal` | selector-v2 experiment provenance; not formal selector promotion |

## Test baseline

- Deterministic core: `1405 passed`, `0 failed`, `0 collection errors`, `4` explicitly separated.
- The same core suite passed from a clean staged-index export.
- External requirements are separated with `external_artifact` and
  `live_provider` markers.
- Historical failure whitelist: empty.
- Retrieval key suite: `67 passed`.
- Evidence/Sufficiency key suite: `61 passed`.
- API/Stage 5 key suite: `44 passed`.
- Minimal in-process Smoke: `6 passed`; no new paid
  Provider call was required. Historical live-provider smoke remains
  bound by the Stage 5 seals.

## Aggregate evaluation only

- V3: 144 videos, 1555 retrieval units, 24 queries, 452 judgments; pooled/judged, not exhaustive.
- V3.5: 24 total queries, 14 Development and 10 Frozen.
- V3.5 Frozen Retrieval Hit@10: `1.0`.
- V3.5 Frozen Builder complete-group availability: `0.0`.
- V3.5 Frozen EvidenceBundle complete-group hit: `0.0`.
- V3.5 Frozen semantic four-state accuracy: `0.2`.
- Aggregate primary attribution: 5 Builder-incomplete and 5
  Mechanical source-unverifiable outcomes.

## Representative traces

None. No available raw Trace met the final package's strict redaction
boundary. Formal trace contracts, seals, aggregate results, and test
fixtures are retained without reproducing Query, Gold, video identifiers,
subtitle text, or personal collection data.

## Excluded local artifacts

- `personal_product_data`: ignored and retained outside the formal Git baseline; deleted = `false`.
- `provider_and_runtime_state`: ignored; no credential-dependent state committed; deleted = `false`.
- `bulk_case_level_traces`: ignored; formal manifests retain path/hash lineage where required; deleted = `false`.
- `temporary_and_reproducible`: ignored and reproducible; deleted = `false`.

## Known limitations

- V3 retrieval evaluation is pooled/judged, not exhaustive-corpus relevance judgment.
- V3.5 Evidence/Sufficiency is minimally product-integrated, limited-pilot, formally below target, and partial.
- Semantic Judge latency is high and production proxy timeout configuration is external.
- Final Answer generation, Agentic Search, Memory, Harness, and automatic remediation are not implemented.
- Frozen Builder/Selector implementations are historical baselines, not mandatory future hard dependencies.

## Machine-readable authority

See `SHILIU_V0_TO_V3_5_FINAL_REPOSITORY_MANIFEST.json`.
