# Shiliu V3.5-B Final Closeout

## Final status

- Outcome: `v3_5_final_closeout_complete`
- V3.5 status: `formally_closed`
- Next action: `report_to_main_session`
- Repository source commit: `91a34061f8aebb216749c015a37a4ff1974f4f2a`

## Formal components

- Retrieval / Auto Router: `v3-product-search-default-auto-v1` / `unversioned:SearchPlanner@sha256:0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e`
- Candidate Builder: `stage3b-acronym-w3.5-v1`
- Fine Selector: `v3.5-deterministic-fine-selector-v1`
- Evidence Identity Contract: `V1`
- Mechanical Gate: `mechanical-gate-v1-r1`
- Semantic Judge: `openai-codex-cli`, `gpt-5.6-terra`, policy `v3.5-semantic-sufficiency-policy-v1`, temperature `0`
- Stage5 current integration refreeze: `4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c`

## Development and Frozen results

Development Product Retrieval Hit@1/3/5/10 was
`0.7143 / 0.9286 / 0.9286 / 1.0`; Builder complete-group coverage was
`0.4615`, Selector bundle hit was `0.0769`, and formal Track A Semantic
Sufficiency accuracy was `0.4286`.

Frozen Retrieval Hit@1/3/5/10 is
`0.8 / 0.8 / 0.9 / 1.0`.
Builder complete-group availability and EvidenceBundle complete-group hit are
both `0.0`; four-state accuracy is `0.2`.
All `10` predictions completed with `0` runtime errors. Formal primary
attribution is `5 builder_incomplete` and `5 mechanical_source_unverifiable`.
No unfrozen diagnostic Track substitutes for these Product results.

## Completed capabilities

- PQS v1 with sealed Development/Frozen split
- V3 Search and default Auto retrieval
- SearchCandidateSet to EvidenceBundle
- fine-grained evidence identity and timeline lineage
- Mechanical Gate three-outcome routing
- Semantic Sufficiency four-state decision
- API, UI, and end-to-end Trace integration
- valid Frozen Evaluation with prediction-first Gold isolation

## Limitations

V3.5 does not implement Final Answer generation, Agentic Search, Memory,
Harness, or automatic evidence remediation/iterative search. Evidence
resolution is the dominant Product bottleneck. Semantic Judge latency remains
material: Development Track A/B/C means were approximately `75.1s / 79.3s /
89.2s`, and the P14 Judge batch took `49.088s`.

Track A is the formal Development Product path and is constrained by upstream
evidence. Track B is a diagnostic known-relevant-video projection without a
full Builder/Selector replay. Track C is a diagnostic legal-Gold-bundle
projection. Six historical non-blocking repository tests, one missing
authoring-packet dependency, and external production proxy timeout
configuration remain documented debt.

## P14 Frozen Evaluation Infrastructure and Orchestration Audit

### First invalid run

- Cause: `openai-codex-cli` state database was read-only.
- Classification: `infrastructure_invalid_run`.
- Frozen Query opened: `true`; Frozen Gold opened: `false`.
- Semantic Judge output: unavailable.
- Predictions Freeze: not generated.
- Algorithm-quality result: unavailable.

### Replacement Freeze barrier issue

- Atomic Case/Trace artifacts completed: `10 / 10`.
- Configuration hash identical: `true`.
- Cause: full `component_versions` equality incorrectly rejected legal,
  route-dependent `semantic_model: null` values.
- Classification: `orchestration_contract_invalid`.
- Algorithm or Prediction failure: `false`.

### Final disposition

- Same replacement run ID reused: `true`.
- Existing Case artifacts reused: `10`.
- Case recomputation / Provider recall / Prediction modification:
  `false / false / false`.
- Correction scope: `freeze_barrier_orchestration_validation_only`.
- Frozen Gold opened only after Predictions Freeze: `true`.

This was an evaluation-orchestration validation defect, not a Retrieval,
Builder, Selector, Mechanical Gate, or Semantic Judge algorithm failure. Final
scoring uses the ten original atomically persisted replacement artifacts
without recomputation, replacement, or selective rerun.

The orchestration debt is non-blocking. Future validators should explicitly
separate stable configuration fields from route-dependent audit fields.

## V4 readiness

V4 is ready to start as a new versioned cycle. The recommended first scope is
authoritative-source reviewability plus Builder/Selector complete-group
coverage, accompanied by explicit stable-versus-route-dependent validator
tests. No V4 implementation was started in this Session.
