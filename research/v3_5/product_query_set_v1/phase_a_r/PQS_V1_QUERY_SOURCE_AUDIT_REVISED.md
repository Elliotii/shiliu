# Product Query Set v1 — Revised Query Source Audit

## Read-only expanded source audit

Newly audited paths:

- `01_V3_SESSION_OPERATING_CONTRACT.md` (main/version-session contract; no eligible standalone user query retained)
- `V3_CURRENT_STATE.md` and `V3_5_CURRENT_STATE.md` (version-state context; no candidate extracted)
- `reports/V3_TAXONOMY_CLOSEOUT_AND_PRODUCT_REFRAME_HANDOFF_2026-07-19.md` (handoff; no candidate extracted)
- `docs/specs/2026-07-15-shiliu-v1.md` (approved product user flows; four verbatim requirements retained)
- `README.md` and `tests/test_product_search_api.py` (product/fixture audit; no candidate outranked the capped pool)

No video title, transcript/subtitle, Gold, retrieval result, Builder/Selector result, or performance result was used as a candidate source.

## Deterministic cap

After exact deduplication, candidates were ordered by: source priority (real user wording → explicit product use need → project-planning information need → test fixture), then source path, source location, and original order. The first 40 were retained. No retrieval-success, answerability, label-balance, or Query Family criterion affected selection.

## Counts

- Original Phase A candidates retained: 36/39
- Newly added-source candidates retained: 4
- Exact duplicates removed: 0
- Possible semantic duplicates marked: 0 (none semantically deleted)
- Candidates excluded only by the 40-item cap: 3
- Final revised candidate pool: 40

### Source contribution in revised pool

- `00_V3_RETRIEVAL_VERSION_BRIEF.md`: 4
- `docs/specs/2026-07-15-shiliu-v1.md`: 4
- `拾流_Shiliu_完整项目上下文与当前行动.md`: 32

### Query family distribution

- `comparison_or_tradeoff`: 10
- `decision_or_troubleshooting`: 11
- `definition`: 4
- `evaluation_or_quality`: 2
- `how_to_or_process`: 12
- `natural_multi_aspect`: 1

## Remaining coverage note

The revised source pool remains visibly thin for `purpose_or_use_case` (zero retained). This is a source-coverage observation only: no Query was generated, revised, or selected to close it. The source breadth now includes an approved product specification in addition to the two Phase A sources.
