# V3 Checkpoint 3.6 Low-Cost Regression Report

Status: passed

Acceptance Run: private Run #4

This report contains only aggregate audit data. Raw prompts, model responses,
compact cards, short-ID mappings, and generated taxonomy names remain in the
ignored local runtime directory.

## 1. Frozen input and execution contract

- Snapshot: #2
- Snapshot Hash: `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2`
- Snapshot cards: 131
- Discovery Eligible: 128
- Regression selection: 48 eligible cards
- Seed: 73
- Batch size: 24
- Local batches: 2
- Trial Assignment: disabled
- Search: disabled
- Engine: `top-level-cost-bounded-workflow-v5`
- Model: `deepseek-v4-pro`

Discovery Runtime did not read or transmit Silver Reference artifacts.

## 2. Checkpoint 3.6 implementation delta

Checkpoint 3.6 added the independent Content Type call required by the quality
gate. It uses the same frozen 48 compact rows but has its own prompt, Schema,
Provider role, output artifact, stage hash, and resume boundary. Content Type
names are available only to deterministic leakage checks and never enter the
Domain Consolidation prompt.

Bounded auxiliary model fields now use deterministic local caps before strict
semantic validation:

- Local Domains: 8;
- Local Topic hints: 5;
- Local definition: 140 characters;
- Local supporting IDs: 5;
- Content Types: 8;
- final Domain includes/excludes: 5 each;
- final representative IDs: 3;
- consolidation notes: 5.

This prevents a second LLM call merely to trim one extra list item or a slightly
long definition. Unknown IDs, missing fields, extra facet types, duplicate IDs,
invalid representatives, and other semantic or structural violations remain
strict failures and are not hidden by truncation.

The usage aggregator was also corrected to preserve nested cached and reasoning
Token details when a call has multiple attempts or Repair metadata.

## 3. Final call-level usage

| Stage | Cards | Thinking | Prompt | Completion | Reasoning | Total | Seconds | Repair |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Local Discovery batch 1 | 24 | off | 4,028 | 778 | 0 | 4,806 | 11.680 | 0 |
| Local Discovery batch 2 | 24 | off | 3,715 | 853 | 0 | 4,568 | 12.663 | 0 |
| Content Type | 48 | off | 7,323 | 669 | 0 | 7,992 | 10.258 | 0 |
| Global Consolidation | candidate table | high | 1,607 | 4,161 | 2,465 | 5,768 | 60.211 | 0 |
| **Total** |  |  | **16,673** | **6,461** | **2,465** | **23,134** | **94.812 model time** | **0** |

Reasoning Tokens are a subset of completion Tokens and are not added twice.
The Provider reported zero cached Tokens for the final Run and did not return a
monetary cost, so cost remains `unknown` rather than an inferred amount.

End-to-end wall time from Run start to completion was 95 seconds.

## 4. Cost gates

| Gate | Result | Limit | Verdict |
|---|---:|---:|---|
| Total Tokens | 23,134 | 90,000 hard maximum | pass |
| End-to-end time | 95 seconds | 15 minutes hard maximum | pass |
| Local Discovery | 9,374 Tokens | 15,000 | pass |
| Content Type + Consolidation | 13,760 Tokens | 20,000 | pass |
| Local Validator | 0 Tokens | 8,000 | pass |
| Repair | 0 calls | ideal 0 | pass |
| Request retry | 0 | ideal 0 | pass |

The result is also substantially below the 60K–70K optimization target. This
does not automatically imply equal quality; structural quality is evaluated
separately below.

## 5. Structural output and quality gates

Aggregate output:

- Local top-level Domain candidates: 15 across two batches;
- Local Topic hints: 7 across two batches;
- locally ambiguous cards: 7;
- independent Content Types: 8;
- Content-Type ambiguous cards: 8;
- normalized Domain candidates: 15;
- consolidated top-level Domains: 10;
- selected representative IDs: 25;
- suspicious local Validator units in the real Run: 0.

Quality result:

- Quality Gate: passed;
- blocking issues: 0;
- invalid supporting IDs: 0;
- Entity Leakage: 0;
- Content Type Leakage: 0;
- Repair: 0;
- retry: 0.

There was one non-blocking
`renamed_domain_without_lexical_match` warning. It records that Consolidation
used a unified name not lexically identical to a Local candidate. This is an
expected purpose of semantic Consolidation and remains auditable.

The real Draft did not contain a sibling pair above the deterministic overlap
threshold, so no local Validator call was necessary. A synthetic overlapping
sibling fixture verifies that the rule creates a bounded Validation Unit and a
blocking local Validator finding routes back to Consolidation.

## 6. Resume and recovery

Calling `resume` on completed Run #4 returned the stored result immediately.
All seven stage attempt counts remained exactly one:

- two Local Discovery stages;
- Content Type Discovery;
- Candidate Normalization;
- Consolidation;
- Structural Validation;
- Quality Gate.

No model was called during the resume check.

## 7. Diagnostic Runs retained privately

Two earlier Runs were useful failures and remain private:

- Run #2: one Consolidation Repair because seven auxiliary notes exceeded the
  five-item limit;
- Run #3: one Local and one Consolidation Repair because several definitions
  exceeded the character cap and two includes lists had six items.

Neither failure involved invalid IDs, hierarchy corruption, or facet leakage.
Local replay of Run #3 raw responses verified the deterministic cap before the
final Run. Run #4 then demonstrated Repair=0 with a new real response.

## 8. Risks and interpretation

1. The same fixed input order produced 7, 9, and 10 final Domains across the
   three diagnostic/final Runs. A single model Run is therefore not a stable
   formal Taxonomy. This supports the planned independent Discovery and global
   consolidation strategy rather than weakening it.
2. Checkpoint 3.6 validates cost, boundaries, recovery, and basic structure. It
   does not evaluate Silver Agreement or final browsing utility.
3. No local Validator was needed for the real output, so the 8K Validator cost
   gate was verified as zero-call behavior plus a synthetic conflict test, not
   as a real Provider usage measurement.
4. The final Provider returned no monetary cost. Only actual Token and elapsed
   time are reported.
5. Classification Profile, formal Discovery A/B/C, Assignment, subdomains,
   Concept Search, and Taxonomy publication remain unimplemented.

## 9. Acceptance decision

Checkpoint 3.6 passes. The next allowed checkpoint is 3.7, the bounded
Classification Profile comparison on the same 48 contents. No Checkpoint 3.7
work begins without explicit user approval.
