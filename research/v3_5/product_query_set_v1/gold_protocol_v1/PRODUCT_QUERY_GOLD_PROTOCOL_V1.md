# Product Query Gold Protocol v1

Status: execution candidate; pending V3.5-B and user review. Formal annotation has not started.

## Mechanical separation

Retrieval Gold, Evidence Gold, and Sufficiency Gold are three distinct objects and schemas. System predictions, ranks, Builder/Selector/Judge output, expected failures, and downstream failure attribution are not Gold fields.

## Retrieval Gold

The evaluation model is `bounded_pooled_judgment`, never exhaustive. `exhaustive` is fixed to `false`; a return outside the reviewed pool is `unjudged`, not an automatic negative. Known relevant videos must be a subset of explicitly acceptable videos. Hard negatives must be explicitly human-reviewed and disjoint from positives. Multiple acceptable videos are supported and no single Target Video is privileged.

A future Development pool addendum must be versioned, follow a frozen prediction, receive independent relevance judgment, preserve existing positives, and leave the Query unchanged.

## Evidence Gold

Only `official_subtitle` and `asr_transcript` are authoritative evidence. Title, description, AI summary, and AI chapter are navigation-only. Original source text, replayable segment/time identity, source language/version, timeline run, segment identity, quality flag, and optional translated gloss are recorded. A translation never replaces source text.

Alternative evidence sets for an Aspect are OR; required spans inside one set are AND. Complete acceptable Evidence Groups are OR; required span sets inside a group are AND. Groups may cross videos and discontinuous transcript regions. Aspect evidence remains recordable when no complete group exists. Optional context cannot replace a required span. Retrieval or Builder output never limits Gold.

## Sufficiency Gold

The exact states are `sufficient`, `partial`, `insufficient`, and `unverifiable`. Sufficient supports every material aspect. Partial reliably supports at least one material aspect while at least one remains missing or source-blocked. Insufficient means authoritative sources were reviewable but no material subset was supported. Unverifiable means authoritative material was not reliably reviewable enough to judge even one material aspect. JSON Schema and the cross-object validator jointly enforce these boundaries.

## Review and adjudication

Normal route: Initial Annotation → Independent Review. High-risk route: Initial Annotation → Independent Review → Second Independent Review or User Adjudication. Reviewers cannot see system predictions, must review complete authoritative transcripts for Evidence Gold, and may not treat majority vote as truth. The user is final authority for unresolved disagreement.

## Isolation, reason codes, and amendments

Frozen Evaluation content follows the separate isolation contract. Gold-state reason codes and downstream failure-attribution codes are separate namespaces; downstream codes are forbidden in Gold. After acceptance, non-semantic corrections require versioned amendments preserving hashes and supersession; semantic changes require a new protocol version and re-annotation of affected cases. Sealed Frozen Gold may change only for proven annotation or identity defects, never because of system results.
