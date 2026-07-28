# Product Query Set v1 — Lightweight Protocol

## Eval role

Product Query Set ≠ Evidence Sufficiency Stress Set.

Product Query Set evaluates natural, standalone user questions on Product Default Auto: ordinary retrieval, regular evidence resolution, product latency, empty results, and layered failure attribution. The Evidence Sufficiency Stress Set remains for complex multi-aspect evidence, long-span claims, boundaries, partial support, insufficiency/unverifiability, and stress testing.

## Scope and split

The final set has a minimum of 20, target of 24, and maximum of 24 approved queries. This phase permits a 28–36 preferred candidate pool and caps it at 40. After humans approve 20–24 queries and before Retrieval, 24 queries will split as 14 development / 10 frozen evaluation; 20–23 queries will use approximately 60% development and 8–10 frozen evaluation. This phase creates only a human preference field, not a split.

## Gold and review policy

Later Gold needs at least one confirmed minimally sufficient evidence group; it does not require exhaustive acceptable-video or Gold-group annotation. Ordinary cases receive initial annotation plus one independent review. No-answer, partially answerable, multi-video, cross-language, severe-ASR-error, and disputed cases escalate to a second reviewer or human adjudication.

## Stop rules

- Maximum final queries: 24
- Maximum query-selection rounds: 1
- Maximum schema-revision rounds: 1
- Full dual review: false
- Expand for label balance: false
- Exhaustive relevant-video annotation: false
- New annotation platform: false
