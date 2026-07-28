# Evidence Identity Contract Audit and Repair Result

## 1. Files and code reviewed

Review was restricted to the three authorized research roots and `src/shiliu/`, excluding
all forbidden path classes. Principal code: `src/shiliu/evidence/contracts.py`,
`source.py`, `stage3a.py`, `stage3b.py`, `mapping.py`,
`src/shiliu/eval_v3_5/stage3a.py`, and `scoring_identity_bridge.py`. Principal data:
sealed Development evidence Gold, fourteen P8 traces, six F1A swap traces, builder seal,
Development seal, and Scorer v2/v3 identity artifacts. Frozen Evaluation Gold was not read.

## 2. Gold field inventory

The 41 sealed Development evidence spans all contain `video_id`, `source_version`,
`timeline_run_id`, `segment_ids`, `start_time`, and `end_time`. They also contain
`span_id`, `segment_identity_version`, `source_type`, `source_language`, quote and quality
metadata. Gold `source_type` has 36 `official_subtitle` and 5 `asr_transcript` values.
Gold does not contain `candidate_id` or `source_artifact_id`.

## 3. Runtime field inventory

The 3,504 frozen P8 candidates all contain `candidate_id`, numeric `video_id`,
`source_artifact_id`, `source_version`, `timeline_run_id`, `segment_ids`, `start_time`,
`end_time`, `source_type`, `source_language`, candidate methods and lineage metadata.
Runtime `source_type` has 3,277 `ai`, 57 `asr`, and 170 `human` values. Bundle-level
`selection_method` is separate.

## 4. Field semantic classification

Canonical identity consists of authoritative platform/video identity, exact source
version, exact timeline run, stable segments, segment-backed evidence form, and normalized
time interval. `source_type`, language, candidate ID, selector/model/builder versions and
candidate lineage are provenance or processing metadata. The complete per-field audit,
including missing policies and evidence, is in the JSON contract.

## 5. source_type semantic finding

Runtime `source_type=ai` is case A with an important qualification: it records AI
generation lineage of the subtitle transcript loaded from the authoritative raw-subtitle
artifact. It is not an AI Selector marker. `FrozenRawSourceResolver` reads
`videos.subtitle_source`, assigns it to both `SourceArtifactReference.source_type` and
`source_lineage`, `load_source_artifact` copies it to raw segments, and Candidate Builder
copies it to candidates. Selector provenance is independently represented by
`EvidenceBundle.selection_method`.

Gold `official_subtitle/asr_transcript` and Runtime `ai/asr/human` are different semantic
axes. The repair parses them as provenance and never directly compares the legacy fields.
It does not erase `source_type` or treat AI summaries as transcript evidence.

## 6. Root causes across Eval v1/v2/v3

- Eval v1 lacked a candidate segment/timeline to Gold identity bridge.
- Eval v2 did not canonicalize BVID and snapshot numeric video aliases.
- Eval v3 compared legacy `source_type` values from different enum domains as identity.

These are scorer-infrastructure defects, not algorithm conclusions.

## 7. Canonical Evidence Identity Contract

Required identity: canonical platform/video tuple, exact `source_version`, exact
`timeline_run_id`, non-empty stable `segment_ids`, segment-backed transcript evidence form,
and a finite non-negative temporal interval. Exact evidence equality requires equal ordered
segments and interval equality within `1e-6` seconds. Split-span coverage requires the same
namespace, complete segment union, and a contributing interval envelope covering Gold.

Unknown, ambiguous, conflicting, `aid`-only, or incomplete identity is unverifiable.
Overlap alone and Candidate ID alone are insufficient.

## 8. Underlying evidence source vs selection provenance

`underlying_evidence_source` distinguishes raw-subtitle segment-backed transcript from
AI-generated summary. `source_generation_lineage` preserves human/AI/ASR provenance.
`selection_method`, `extraction_method`, and model/builder versions remain separate.
Changing selector or builder does not change evidence identity; summary generation does.

## 9. Canonical matcher implementation

`src/shiliu/eval_v3_5/scoring_identity_bridge.py` now provides authoritative multi-alias
video resolution, canonical provenance parsing, conservative identity construction,
three-state exact matching (`match`, `non_match`, `unverifiable`), and segment-union
coverage. No query/video/Gold/result-specific rules were added.

## 10. Positive tests

All required cases pass: BVID/numeric equivalence; same timeline/segment; raw subtitle with
AI provenance/selection; single/split preserved spans; normalized time representation.

## 11. Negative tests

All required cases pass: different video; wrong timeline; wrong segment; overlap without
segment identity; AI summary versus raw subtitle; unknown/ambiguous mapping; missing
required component. Candidate ID alone is unverifiable. Unknown mapping is unverifiable.

## 12. Six preserved-evidence consistency tests

`PQS_V1_Q006`, `Q007`, `Q011`, `Q012`, `Q013`, and `Q019` all pass. Preserved candidate
IDs are obtained generically from each swap trace's Before/After intersection. Their
underlying candidate records are canonicalized with different selector/builder provenance,
and every preserved record retains the same canonical identity. No query-specific rule was
introduced and no coverage/acceptance metric was computed.

## 13. Remaining systemic identity risks

All eight audited risks have contract dispositions: source version, timeline namespace,
segment aggregation, one-to-many mapping, time precision, subtitle-class/lineage,
raw transcript versus summary, and selection versus evidence provenance. Unresolved
systemic identity risks: 0. Detailed statuses and test coverage are in the JSON contract.

## 14. Contract Freeze Seal

The separate `EVIDENCE_IDENTITY_CONTRACT_V1_FREEZE_SEAL.json` locks the final contract,
schema attestations, canonicalizer/matcher source, tests, authoritative mapping hash,
Development Gold schema attestations, and builder seal. No Scorer v4 Freeze Seal exists.

## 15. Builder / Gold / Scorer behavior change status

Candidate Builder: unchanged. Adaptive swap logic: unchanged. Retrieval, Selector,
Mechanical Gate, queries, split, acceptance gates, Development Gold and Stress inputs:
unchanged. The shared scoring identity bridge changed. Existing Scorer v3's source hash
therefore no longer satisfies its old seal, which safely blocks reuse as a formal scorer.

## 16. Outcome

`evidence_identity_contract_frozen`

## 17. Whether formal Eval is authorized

`false`

Recommended next step: `separate_scorer_v4_and_final_eval_authorization`.

## 18. Exact unresolved questions or missing assets

None for Contract V1. An authoritative Bilibili `aid` mapping is not present, so `aid`-only
inputs intentionally remain unverifiable rather than unresolved contract semantics.

## 19. Output paths and SHA-256

Final SHA-256 values are recorded in `EVIDENCE_IDENTITY_CONTRACT_V1_FREEZE_SEAL.json`.
Outputs are this Markdown contract, the JSON contract, test results, test source, repaired
matcher source, and the Freeze Seal in this cycle directory.

Session closure status: yes. Formal Eval remains a separate unauthorized action.
