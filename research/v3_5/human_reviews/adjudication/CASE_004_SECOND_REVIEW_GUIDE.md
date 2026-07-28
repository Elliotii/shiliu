# CASE_004 Focused Second-review Guide

Status: adjudication preparation only. No second review has been performed.

## Prior Human Decision — Not Final Adjudicated Gold

- Label: `partial`
- Confidence: `medium`
- `needs_second_review`: `true`
- Supported Aspect: A3 — a concrete RAG application/capability
- Missing Aspects: A1 (what RAG is), A2 (core mechanism/use)
- Reasons: `limited_aspect_coverage`, `asr_transcription_uncertainty`
- Prior Group: G1, one Span, 129.16–138.91s, run-local

The prior Human Decision is the object under review. Do not treat it as final Gold, and do not silently repair ASR text.

## Exact Frozen ASR Evidence Under Review

```jsonl
{"original_ordinal":20,"segment_id":"segment_29e70d2062a444b6421fe4bd3c46cf68474d929f556190b21d29f811896f5a0c","start_time":129.16,"end_time":135.68,"source_text":"然后还有什么多模态的内容理解和资产系统，比如说多模态ra文本图像视频统一索引对吧？","timeline_run_id":"timeline_run_f710676b394f8e735bec0dbf32407591d0a657e5eeb4496868ee1b15df274ce0"}
{"original_ordinal":21,"segment_id":"segment_12dc3adced5bef04fabe5e3739ca4fc840a1faf8b298732064a9f6caf95c8ad3","start_time":136.46,"end_time":138.91,"source_text":"语义桥接联合推理，很多都不虚的。","timeline_run_id":"timeline_run_f710676b394f8e735bec0dbf32407591d0a657e5eeb4496868ee1b15df274ce0"}
```

The full CASE_004 Review Packet remains the annotation authority. The excerpt is navigation, not an annotation boundary.

## Focused Questions

1. Can ASR `ra` be interpreted reliably as `RAG` from this exact context, without repairing the source text?
2. Does the current Span genuinely support A3's concrete RAG application/capability?
3. Is the support strong enough for `partial`, or only unreliable semantic proximity consistent with `insufficient`?
4. Are A1 and A2 genuinely absent from the complete authoritative transcript?
5. Should the prior Gold Span be retained exactly, modified by the Human adjudicator, or rejected?

## Adjudication Boundary

The second Human Reviewer has final semantic authority. Codex must not choose among `partial`, `insufficient`, or another label; change Aspect semantics; repair `ra`; or alter the Span. If the adjudicator changes any field, preserve both the original Round 2 intake and the new adjudication record with explicit provenance.

If CASE_004 remains `partial`, continue with the existing 18 Cases and record partial underrepresentation; do not activate a Reserve. If it changes to another label, return to Version Session to decide whether RESERVE_004 should be activated. Codex must not activate it automatically.
