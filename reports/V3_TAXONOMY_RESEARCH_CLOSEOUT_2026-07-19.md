# V3 Taxonomy Research Closeout

Date: 2026-07-19
Status: Taxonomy Research Phase completed; product route undecided.

## Original problem

The research asked whether Shiliu could take a new favorite folder, discover explainable knowledge domains without receiving human category names, build a personalized hierarchy with at most two levels, and later support full-corpus assignment, filtering, and user correction.

## What was actually completed

The verified research chain is:

```text
Snapshot #2
→ Classification Profile
→ Local Discovery
→ Candidate Normalize
→ Cross-run Alignment
→ Unresolved Adjudication
→ Semantic Contract v2
→ Domain Draft A
→ Hierarchy Review
```

The engineering substrate includes evidence lineage, raw-first persistence, Schema validation, bounded JSON Repair, resume and tail completion, independent read-only review, hashes and manifests, Provider single-flight, attempt leases, and an immutable response ledger.

Run #24 freezes M1–M5. Draft A has 25 nodes: 20 top-level and 5 second-level; 19 probable, 1 weak, 5 uncertain, and 0 stable. It consumes 26 of 31 eligible M3 clusters and explicitly excludes 5 uncertain clusters. Hierarchy review was `PASS_WITH_CONCERNS`; complexity remains a concern because the tree is broad and close to one node per eligible cluster. This is a research draft, not an official product Taxonomy.

## Verified conclusions

- An LLM can discover meaningful thematic directions from this favorite-folder corpus.
- Independent runs differ in names, granularity, and boundaries; run repetition is evidence, not a semantic vote.
- `unresolved` does not imply that a new Domain is needed. M2 resolved 12 groups into 6 merges and 6 Topic downgrades, with no new Domain proposal.
- Domain, Topic, Entity, Object, Use Context, and Content Type must remain separate axes.
- Cross-run Alignment plus independent review reduced duplicate scopes and dimension leakage while preserving candidate provenance.
- Draft A is reproducible and useful as a research artifact.
- The complete hierarchy has not been validated through full-corpus Trial Assignment.

## Not verified

- Whether 25 nodes are useful for real browsing.
- Whether 20 top-level nodes are too many.
- Whether every video needs a complete Domain Assignment.
- Whether a full Taxonomy should be the primary front-end entry point.
- Whether users would frequently use a Topic Map.
- Whether classification is more useful than dynamic labels, search, or related-content discovery.
- Whether the Taxonomy remains stable as new content arrives.
- How Domains should be reused across multiple favorite folders.

## Engineering and Provider cost

All token figures are reported Provider usage, not estimated money. The Provider did not return a reliable monetary cost, so no currency value is claimed.

| Scope | Calls / attempts | Input or prompt tokens | Output or completion tokens | Reasoning tokens | Elapsed |
|---|---:|---:|---:|---:|---:|
| Run A accepted lineage | 14 calls | included in total | included in total | not fully separated | 538.655 s |
| Run A accepted lineage total | 14 calls | — | — | — | 83,228 total tokens |
| Run A historical failed call overhead | 1 failed call | — | — | — | 132.284 s / 14,029 total tokens |
| Run B relevant lineage | local + consolidation + repairs + tail | — | — | ≥15,762 known in consolidation/tail subset | 497.200 s / 71,076 total tokens |
| Run C1 | 13 calls | 40,668 | 39,542 | 17,787 subset | 543.588 s |
| M1 Semantic Contract | primary + repair | 13,610 | 14,358 | 5,525 | 181.126 s |
| M2 Adjudication | 3 batches + repairs | 24,679 | 20,409 | 13,323 | 346.233 s |
| M3 Alignment, including failures/repairs | 10 recorded stage attempts | 102,876 | 105,375 | 71,652 | 1,535.258 s |
| Draft A incident, known minimum | 2 Primary + 2 Repair | 46,800 | 42,128 | 14,481 | 560.049 s |
| M1–M5 known minimum | — | 187,965 | 182,270 | 104,981 | 2,622.666 s |

Run A's accepted lineage was 83,228 total tokens; including its failed historical call raises the observed total to 97,257. Run C1 repairs consumed 5,309 tokens and 21.612 seconds. M3 used JSON Repair in seven batches; repair traffic was approximately 16,906 input plus 14,085 output tokens and 201.678 seconds. M3 Batch 002's length-truncated attempt added 10,168 input and 8,191 output/reasoning tokens and 146.285 seconds; Batch 005's TLS failure has unknown token usage.

### Cost interpretation

- **Necessary semantic cost:** compact discovery, semantic contract, adjudication, alignment, bounded synthesis, and independent review required to test whether an open hierarchy could be made coherent.
- **Engineering-error overhead:** Run A's failed call, M3 truncation/TLS failures, repeated repairs, and especially Draft A's concurrency accident. The Draft A incident created two Primary and two Repair responses; one Repair's usage is unrecoverable. It must not be described as one normal call.
- **Audit and recovery cost:** raw-first storage, repair diffs, manifests, reviewers, resume, and single-flight implementation add engineering effort but limit silent corruption and future duplicate billing. The single-flight checkpoint made zero real Provider calls.

## Handoff boundary

The research artifacts show that Taxonomy can be generated and audited; they do not establish its final product role. V3 产品形态与后续路线尚未决定，等待用户与规划 AI 在 Taxonomy 收口后重新讨论。本报告不选择路线，也不授权 M6。
