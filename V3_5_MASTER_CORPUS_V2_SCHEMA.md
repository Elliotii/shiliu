# Shiliu Master Evaluation Corpus v2 Schema

Status: locked for Stage 2R-A. Version: `v3.5-master-case-v2`.

The record has exactly five formal layers: `case_identity`, `corpus_truth`, `retrieval_gold`, `evidence_gold`, and `sufficiency_gold`. `answer_gold` and `agentic_search_gold` are forbidden until V4 answer, claim, citation, tool-space, budget, and stop contracts are frozen.

`case_id` is an opaque stable `V2C_…` identifier and may not encode labels. `query_family` and `leakage_group` are assigned before splitting. Lineage records V3 Query, Eval v1, or new-case origin without silently migrating v1.

Raw Subtitle and Raw ASR are evidence authority. Navigation metadata cannot establish truth. Target videos express intended targets; acceptable videos include every source that may validly answer. Missing/unreadable sources are explicit and must not be represented as empty transcripts. Artifact, version, language, and timeline identity are traceable.

Semantic Gold (`required_aspects`) is separate from Span Gold. Evidence groups are OR; required spans inside one group are AND. Multiple spans in one video are allowed. Multiple videos are allowed only with complete identity and run-local spans per source. Alternative expressions use alternate groups/notes. Conflict spans are distinct. Optional context cannot satisfy a required aspect.

Every span binds video, artifact, version, timeline run, segment IDs, locally reconstructed time, language, type, role, and (for required spans) one or more aspect IDs. Segment IDs must exist, time must reconstruct deterministically, and a span may not cross a timeline run. Wider complete evidence may succeed; irrelevant over-expansion is not precise Gold.

Four-state invariants are enforced in code: sufficient supports all required aspects with a complete group; partial has both substantive supported and missing aspects from readable Raw Source; insufficient has readable Raw Source and no substantive support; unverifiable requires missing/unreliable authority. Confidence is independent from status.

