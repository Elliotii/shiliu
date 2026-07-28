# P8 Scoring and Checkpoint 1 Amendment Complete

1. Frozen Prediction / Trace / Gold identity  
   Prediction count `14`; Prediction SHA-256 `b34f173ac99208f4adb72966880ab7e9cf97d3e27157084792502f103e709038`; Prediction Seal SHA-256 `069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617`. Trace count `14`; Trace Root SHA-256 `f8636d55680e4e3ef72b196f31afe8743c692d48c66ed0a647443679e7353071`. DEVELOPMENT_GOLD_V1 Seal SHA-256 `1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a`.

2. P8 Scoring Amendment status and Scoring Seal  
   `P8_SCORING_AMENDMENT_V1`: `complete_execution_candidate`; Scoring Hash Root `54bc35083f4410ace027452b64fc2d22432111be5a2036c0ce245e6319849795`.

3. Q017 amended attribution  
   Original `candidate_builder_failure`; amended generic non-Builder attribution `gold_defined_evidence_absent`.

4. Final amended Builder / Selector metrics  
   Candidate Builder: complete group coverage `6/13`, primary failures `6`, required-span recall `65.38%`, required-aspect coverage `65.38%`. Deterministic Selector: bundle hit `1/13`, primary failures `5`, required-span recall `12.18%`, required-aspect coverage `12.18%`.

5. Final Primary Failure Distribution  
   `candidate_builder_failure: 6`; `deterministic_selector_failure: 5`; `end_to_end_bundle_hit: 1`; `gold_defined_evidence_absent: 1`; `source_unverifiable: 1`.

6. Checkpoint 1 amended authority updates  
   `V3_5_CURRENT_STATE.md`, `03_V3_5_DECISION_AND_ARTIFACT_INDEX.md` (authoritative Decision Ledger), and `02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md` contain the amended values. Checkpoint 1 amended status is `execution_candidate_ready`.

7. Original scoring and checkpoint supersession status  
   Original P8 scoring: `superseded_by_scoring_amendment`. Original Checkpoint 1 derived findings: `superseded_by_checkpoint_1_amendment_for_derived_findings`. P7 remains `complete_and_accepted`; the frozen P8 Prediction Set remains `valid_and_frozen`.

8. F1A entry signal and P9 restart readiness  
   `F1A_entry_signal: true`; `P9_restart_readiness: true`; `P9_restarted: false`.

9. Output paths and SHA-256  
   `research/v3_5/checkpoints/checkpoint_1/amendment_v1/CHECKPOINT_1_AMENDMENT_REPORT.md` — `6be88e8bc4ebfe0e9f28fbb0a4719a94118bac3a8e4060241c069249d31795b6`  
   `research/v3_5/checkpoints/checkpoint_1/amendment_v1/checkpoint_1_amendment.manifest.json` — `cbf210691bc8d0881eedd39e9d286db064d9453d3d26675baa0bba7fd508e1a6`  
   `research/v3_5/checkpoints/checkpoint_1/amendment_v1/checkpoint_1_amendment.audit.json` — `9853847a73eff4e65e03cb1f33cc63e0745d0ac4d7d95c9929cdce97f5fd5f40`  
   `research/v3_5/checkpoints/checkpoint_1/amendment_v1/checkpoint_1_amendment.execution_decision.json` — `2a328016fd1e3ff56355532c91169874aaf3fae33cf45f36c7f4e44d11abe10c`  
   `research/v3_5/checkpoints/checkpoint_1/amendment_v1/checkpoint_1_amendment.file_hash_manifest.jsonl` — `10ac689da35919557a5956c4cdfefcf829544344d0fcdf71b3a5f8a047969283`

10. Test command and result  
    `/Users/elliot/.local/bin/python3.11 -m pytest -o addopts='' -q tests/test_pqs_v1_p8_scoring_amendment_contract.py tests/test_pqs_v1_p8_product_initial_baseline_contract.py tests/test_v3_5_checkpoint_1_amendment_contract.py tests/test_v3_5_checkpoint_1_contract.py tests/test_v3_5_p9_decision_boundary_contract.py`  
    Result: `71 passed in 0.17s`.

11. Prediction / Component / Query / Split / Gold change status  
    Prediction, Trace, Retrieval, Builder, Selector, Gate, Product Component, Query, Split, and Gold changes: `false`. `recompute_scoring_again: false`.

12. Frozen access and downstream stage status  
    `frozen_gold_opened: false`; `P9_restarted: false`; `F1A_authorized: false`; `F1B_authorized: false`; `Stage4_started: false`.

13. Acceptance status: pending V3.5-B review

14. Whether current Codex Session can be closed  
    Yes.
