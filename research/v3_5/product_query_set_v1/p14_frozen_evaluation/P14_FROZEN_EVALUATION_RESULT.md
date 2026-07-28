# P14 Frozen Evaluation Result

## Outcome

- Outcome: `p14_frozen_evaluation_complete`
- Status: `formally_closed`
- Evaluation validity: `valid`
- Replacement run ID: `P14_REPLACEMENT_FROZEN_EVALUATION_20260727T184443+0000`
- Existing atomic Case artifacts reused: `10`
- Case recomputation / Provider recall / Prediction modification: `false / false / false`
- Frozen Gold opened only after Predictions Freeze: `true`

## Frozen metrics

- Retrieval Hit@1/3/5/10: `0.8` / `0.8` / `0.9` / `1.0`
- Builder complete-group availability: `0.0`
- EvidenceBundle complete-group hit: `0.0`
- Mechanical routing accuracy: `0.5`
- Sufficiency four-state accuracy: `0.2`
- Severe false sufficient: `0`
- Completed predictions / runtime errors: `10` / `0`
- Component-joint correct Cases: `0/10`

The Freeze barrier correction was limited to orchestration validation. It
separated globally stable component fields from the legal route-dependent
`semantic_model` audit field. No frozen component or prediction changed.
