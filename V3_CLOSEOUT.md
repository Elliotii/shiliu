# Shiliu V3 Retrieval Closeout

Status: `formally_closed`  
Closeout date: 2026-07-29  
Historical source commit: `91a34061f8aebb216749c015a37a4ff1974f4f2a`

## Decision authority

The formal external Version Decision was archived byte-for-byte as
`SHILIU_V3_VERSION_DECISION.md`.

```yaml
source_filename: SHILIU_V3_VERSION_DECISION(2).md
source_supplied_date: 2026-07-28
archived_path: SHILIU_V3_VERSION_DECISION.md
sha256: fa6d394926d445ecfc5bfe20a6c2f4586c31adcbc9695dca99fdae9f5e993fa3
decision: close_v3_without_further_stage6_retrieval_tuning
```

This closeout archives and points to that decision. It does not rerun V3 Eval,
change Gold, or reconsider the historical decision.

## Delivered capability

V3 delivers a rebuildable local retrieval layer over Shiliu product data:

- FTS5 lexical retrieval, Qwen dense retrieval, RRF hybrid retrieval, and
  deterministic Auto routing;
- video and transcript-chunk retrieval units with incremental reconciliation;
- structured product filters;
- same-video consolidation, bounded evidence windows, and coarse timestamp
  navigation to raw subtitle evidence;
- Product Search API, Web search surface, Raw/Presentation Trace, and typed
  error behavior;
- snapshot-isolated, pooled/judged retrieval evaluation.

The authoritative formal evaluation report is
`V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md`. Its machine-readable
aggregate results are in `research/v3_eval/eval_results.json`; query-, Gold-,
and per-result artifacts remain referenced by path and hash only in repository
manifests.

## Formal result

The accepted aggregate evaluation covered 24 queries and 452 query–video
judgments over a frozen 144-video, 1,555-unit corpus. Dense and Hybrid
materially exceeded Lexical discovery recall on the judged pool; pooled
Recall@10 was approximately 0.88 for Dense/Hybrid and held-out Recall@10 was
approximately 0.90. These are pooled/judged results, not exhaustive-corpus
relevance claims.

## Boundary

V3 is a reliable video-discovery and transcript-candidate retrieval foundation.
It does not claim:

- precise sentence-level evidence selection;
- stable no-answer rejection;
- validated cross-language retrieval for all language pairs;
- claim–evidence alignment;
- multi-video cited answer generation;
- agentic search or automatic remediation.

Those gaps were not failures to close V3. Evidence identity, fine evidence
selection, mechanical gating, and semantic sufficiency were handled in V3.5;
final answer generation and agentic behavior remain unimplemented through V3.5.

## Supersession

`V3_CURRENT_STATE.md` is retained for history and marked `superseded`. This
closeout, the archived Version Decision, and the repository-wide V0–V3.5
Closeout are the current authorities.
