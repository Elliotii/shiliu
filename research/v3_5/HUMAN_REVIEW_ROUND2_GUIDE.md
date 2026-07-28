# Shiliu V3.5 — Human Review Round 2 Guide

Status: active review guide only; not final Gold and not a Development/Held-out split.

The first ten validated decisions are frozen calibration references. Do not edit them while reviewing Round 2. Fill a copy of `review_decisions.round2.template.jsonl` in the exact order defined by `active_review_round2.jsonl`.

## Governing Semantics

Full Raw Transcript remains the final authority, but start from Navigation Aids and inspect surrounding or alternative relevant locations as needed. Full Transcript Accessible ≠ Full Transcript Linearly Read From Start to End.

Four states:

- `sufficient`: at least one complete Evidence Group covers all required Aspects.
- `partial`: real Evidence supports a meaningful subset while another required Aspect is missing.
- `insufficient`: readable authority exists but provides no useful primary answer, or a curated query-corpus control has no obvious approvable target.
- `unverifiable`: reliable Raw Source authority is unavailable.

Gold Evidence Groups are OR alternatives. Required spans inside one Group are AND. Every Group must remain inside one Timeline Run and cite exact Segment IDs.

## Review Order

### CASE_002 — MemoryOS positive counterpart

Use CASE_013 only as a boundary reference, not as a source of labels. Determine whether the Raw source supports MemoryOS identity/mechanism and build Evidence Groups independently. CASE_002 and CASE_013 must remain together in a future split.

### CASE_004 — ASR coverage

Judge the rendered ASR source as the available authority. Record transcription uncertainty if it changes semantic confidence; do not silently repair the transcript.

### CASE_005 — Highest-priority partial boundary

Decompose the question's Agent-evaluation-signal Aspects before selecting Evidence. Review carefully for a genuine `partial` boundary, but **CASE_005 must not be forced to partial**. Sampling stratum is not Gold.

### CASE_006 — English-source semantic neighbor

This is the only distinct readable English-source pooled case. It is an English semantic-neighbor review only—not English positive coverage and not cross-language positive evidence.

### CASE_011 — Human-subtitle coverage

Review Pi Agent plugin/configuration support using the human subtitle authority. CASE_011 and CASE_016 must remain together in a future split.

### CASE_014 — RAG industrial semantic neighbor

Use reviewed CASE_007 only as a semantic-boundary reference. Determine independently whether CASE_014 forms useful support. CASE_007 and CASE_014 must remain together in a future split.

### CASE_016 — Title-only boundary

Confirm source authority. Do not infer body evidence from the title; no nonexistent transcript reading is required.

### CASE_018 — Curated corpus control

Determine whether frozen V3 results reveal an obvious target that should become `query_video`. This is not an exhaustive proof that no sentence in 144 videos is related. It does not participate in Fine Evidence Span Metrics.

## Partial-class Rule

The validated ten-case ledger contains no human-approved `partial`. This is not a defect and does not authorize relabeling. If no genuine partial appears after Round 2, record the fact. Version Session—not Codex—will decide whether to activate a Reserve or add another real Case. Do not activate one automatically.

## Second Review

Set `needs_second_review=true` when Aspect decomposition is unstable; sufficient/partial or partial/insufficient boundaries are unclear; alternative spans may not be equivalent; Evidence conflicts; language cannot be judged reliably; or Timeline Run boundaries are uncertain.
