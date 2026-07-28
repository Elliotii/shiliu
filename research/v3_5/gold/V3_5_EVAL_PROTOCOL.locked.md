# Shiliu V3.5 Evaluation Protocol — Locked

Status: **Locked**  
Version: `v3.5-eval-protocol-v1`  
Gold lock: `v3.5-gold-lock-v1`

## 1. Mission and scope

One 18-Case Master Set evaluates, where applicable, candidate coverage, fine Evidence selection, deterministic time reconstruction, four-state Sufficiency, abstention, and reason attribution. It does not establish statistical representativeness. Candidate Builder, Selector, Sufficiency Judge, and Formal Eval are later stages.

## 2. Evidence authority and identity

For `query_video`, authority is exactly Query + Target Video + Full Authoritative Raw Transcript. Titles, search hits, chunks, intervals, chapters, summaries, and failure notes are navigation aids only. Evidence binds `v3.5-source-identity-v2`, exact `source_version`, `v3.5-source-version-authority-v1`, and the Packet identity. For `query_corpus`, authority is the bounded frozen-corpus negative-control review; it creates no transcript or target-video Evidence.

Source identity, version, segment ordinal, segment digest, and raw text are never silently repaired. Quote and time output must reconstruct deterministically from the exact ordered Segment IDs. A stored span starts at its first Segment start and ends at its last Segment end.

## 3. Timeline and mapping

Timeline Runs are derived in raw artifact order under `v3.5-timeline-policy-v1`; segments are not globally sorted. Every Evidence Span and every Gold Evidence Group must remain in one run. Reproduced chunks crossing runs are `invalid_cross_timeline_chunk`, ineligible, and never split or rewritten. Mapping uses `v3.5-exact-chunk-mapping-v1`, the frozen V3 chunk policy, and frozen replay implementation.

## 4. Gold Evidence semantics

Gold Evidence Groups are OR alternatives. Required Spans inside one Group are AND: every required span is necessary for that Group hit. A `sufficient` decision has at least one complete Group covering all required Aspects. Fine Evidence Span metrics apply only where authoritative Gold Evidence Groups exist; `query_corpus`, title-only, and other unavailable-source cases are ineligible.

## 5. Four-state Sufficiency

- `sufficient`: at least one complete Evidence Group supports every required Aspect; `missing_aspects` is empty.
- `partial`: real authoritative Evidence supports a meaningful non-empty subset, while `missing_aspects` is also non-empty.
- `insufficient`: readable authority, or an authorized query-corpus control, cannot form a useful primary answer; no useful-answer Gold Group is fabricated.
- `unverifiable`: Raw authority is unavailable; no Gold Group is fabricated.

Abstention is required when useful support is absent or authority is unavailable. `partial` is not automatically equivalent to `sufficient` or to total abstention; later policy must report it distinctly.

## 6. Locked Reason Code Registry

The canonical registry is `reason_code_registry.locked.json`. It preserves `partial_aspect_coverage`, `semantic_neighbor_only`, `query_target_mismatch`, `title_only`, `no_approved_target`, `out_of_domain_negative_control`, `asr_transcription_uncertainty`, and `search_candidate_but_no_supporting_evidence`. `limited_aspect_coverage` is a historical alias of `partial_aspect_coverage`; the alias interprets immutable intake and does not rewrite it. Query-target mismatch remains distinct from semantic-neighbor evidence; no-approved-target remains distinct from an out-of-domain control. ASR uncertainty may coexist as an auxiliary reason, conflict note, or reviewer flag.

## 7. Development, Held-out, and leakage

Development contains exactly CASE_001, CASE_002, CASE_003, CASE_005, CASE_012, CASE_013, CASE_015, and CASE_017. Held-out contains exactly CASE_004, CASE_006, CASE_007, CASE_008, CASE_009, CASE_010, CASE_011, CASE_014, CASE_016, and CASE_018.

Hard same-split groups are LG_MCP (CASE_001/003/012), LG_MEMORYOS (CASE_002/013), LG_RAG_OPTIMIZATION (CASE_007/014), and LG_PI_AGENT (CASE_011/016). CASE_012 remains Development-only. No Case may occur in both splits. CASE_019, CASE_020, and every Reserve are excluded.

Development labels and Evidence may be used for implementation and debugging. Held-out labels, Aspects, Evidence Groups, and reasons must not be inspected or used during Candidate Builder, Selector, or Sufficiency policy development. Held-out Query metadata may be used only as required by the formal runner. Thresholds, prompts, micro-windows, and case/video-specific rules must not be tuned against Held-out. Gold cannot change after Held-out results are seen.

## 8. Human adjudication and granularity

Human decisions are authoritative for labels, Aspects, and Evidence Spans. CASE_004's focused adjudication is the only authorized semantic override to the provisional ledger and retains its exact G1 span. Codex may perform mechanical schema, source, segment, time, run, and invariant validation but may not repair Human semantics.

Every Gold Group receives a granularity audit. Duration alone is not a failure criterion: complementary spans may be broad when each supports a distinct required Aspect and removing one loses necessary support. A provenance error or required semantic edit blocks Gold lock and requires Human review.

## 9. Metrics and reporting

Candidate metrics include Gold Group coverage, best-group Segment recall, compression, characters, and duration. Selector metrics include EvidenceSetHit@1, Segment precision/recall/F1, start-time error, duration ratio, compression, invalid selection, and abstain accuracy. Overlapping intervals are merged only within the same Timeline Run.

Sufficiency reporting includes Macro-F1, per-class precision/recall, confusion matrix, Sufficient precision, Partial→Sufficient, Insufficient→Sufficient, Unverifiable→Sufficient, false-answer rate, primary reason exact match, and action-family match. Every report must show absolute correct/error counts, per-class counts, per-case failures, uncertainty, and sample size. Readiness signals are interpretive evidence, never mechanical pass/fail thresholds.

## 10. Formal-run and isolation rules

Use one frozen semantic Held-out run: no best-of-N or Gold-visible rerun. Infrastructure-only reruns require a recorded pre-response connection failure, unusable provider response, runner crash, or corrupted work DB; preserve the first failed Trace and keep system versions fixed. The original Snapshot remains read-only; traces go only to an authorized work copy.

## 11. Coverage limitations

English positive evidence: **not established**. Cross-language evidence resolution: **not evaluated**. Human-approved partial: **1 Held-out Case**. Development real partial: **0**. Unverifiable: **2 title-only Cases**. Other runtime failure states are covered later by deterministic contract tests, not additional Human Master Cases. A future synthetic partial-state fixture must not reproduce CASE_004's Query, transcript, Segments, Evidence Group, or labels.

