# V3 Checkpoint 3.5 Cost Architecture Report

Status: implemented without real model calls

Scope: cost architecture correction only. No 48-card regression, formal
Discovery A/B/C, Classification Profile, Trial Assignment, Concept Search, or
Taxonomy publication was executed or added to the formal Runner.

## 1. Call graph change

Before Checkpoint 3.5:

```text
Compact Cards
-> mixed Local Discovery
   (Content Type + primary/subdomain Domain + Topic + Entity)
-> full raw local outputs
-> full two-level Consolidation
-> whole Draft + all Local outputs Hierarchy Validator
-> Quality Gate
-> optional Trial Assignment
```

Implemented formal Runner:

```text
Compact Cards
-> top-level-only Local Domain Discovery
-> deterministic Candidate Normalization
-> Compact Candidate Table
-> top-level-only Consolidation
-> deterministic structural validation
-> zero or more suspicious sibling Validation Units
-> bounded local LLM Validator only for those units
-> deterministic Quality Gate
-> stop
```

The existing `discovery-spike` service remains as a historical Checkpoint 3
experiment. It is not used by `taxonomy create-run`, `run`, or `resume` and is
not evidence for the new cost architecture.

## 2. Cross-stage fields removed

Local Domain Discovery no longer emits or transports:

- Content Type candidates;
- subdomain level and parent hints;
- Entity candidates;
- Topic definitions;
- Domain `includes` / `excludes`;
- long stability reasons;
- full structure diagnostics.

The normalizer keeps only:

- stable normalized candidate ID;
- short name and definition;
- total support count and source batch count;
- at most five supporting IDs;
- at most three representative IDs;
- at most three short evidence codes.

Bounded Topic hints may be saved in the normalized artifact for later analysis,
but are deliberately omitted from the Consolidation prompt.

## 3. Hard output limits

| Output | Limit |
|---|---:|
| Local top-level Domains per batch | 8 |
| Local Topic hints per batch | 5 |
| Local Entity output | 0 |
| Local Content Type output | 0 |
| supporting IDs per Local candidate | 5 |
| evidence codes per Local candidate | 3 |
| normalized supporting IDs transmitted | 5 |
| normalized representative IDs | 3 |
| Consolidated top-level Domains | 12 |
| representative IDs per final Domain | 3 |
| representative Profiles per local Validator unit | 6 |

Content Type now has an independent prompt, Schema, validation function, and
Provider role. It is not called by the Checkpoint 3.5 formal workflow.

## 4. Validator boundary

Schema and deterministic rules reject mixed facet output, unknown supporting
IDs, duplicate IDs/names, invalid representatives, excessive node counts, and
known Entity or Content Type leakage. Supporting-ID overlap creates a bounded
`ValidationUnit` only when two top-level siblings share at least two items and
their Jaccard overlap is at least 0.5.

The local Validator receives only:

- the one selected Validation Unit;
- its two selected top-level nodes;
- at most six representative compact rows.

It never receives all Local Discovery outputs or unrelated cards. A clean
Draft schedules zero LLM Validator calls.

## 5. Thinking route

| Stage | Route |
|---|---|
| Content Type interface | thinking off |
| Local top-level Discovery | thinking off |
| Candidate Normalization | local code |
| Global Consolidation | thinking on, `high` |
| Structural checks | local code |
| suspicious local Validator | thinking off |
| JSON Repair | thinking off |

The current Provider has no separately verified `medium` control. Bounded local
calls therefore use thinking off; high is reserved for global Consolidation.

## 6. Recovery and audit

- The engine version changed to `top-level-cost-bounded-workflow-v2`.
- Completed historical Runs remain readable.
- An unfinished Run from another engine version is rejected instead of being
  silently resumed with incompatible prompts or Schemas.
- Candidate Normalization, structural validation, and Quality Gate are saved as
  independently hashed `taxonomy_stage_runs`.
- Local batches remain independently resumable.
- Raw model output is still saved before parsing.
- JSON Repair still receives only raw response, validation error, and compact
  Schema; it does not replay the corpus.
- Usage, reasoning, cache, latency, and retry aggregation remains covered by the
  existing audit tests.

## 7. Offline cost evidence

No model was called. A deterministic synthetic fixture containing three legacy
mixed Local outputs measured:

| Consolidation input fixture | Characters |
|---|---:|
| legacy raw mixed candidate prompt | 7,141 |
| compact top-level candidate prompt | 1,004 |
| reduction | 85.9% |

This is a structural character comparison, not a Provider Token result. Actual
Token, cache, reasoning, latency, and quality gates remain Checkpoint 3.6 work.

## 8. Tests

Full suite result:

```text
103 passed, 1 third-party deprecation warning
```

New or updated coverage includes:

- Local output quantity limits;
- Entity and Content Type exclusion from Local Domain Discovery;
- Topic limit enforcement;
- deterministic normalized-name merge and ID truncation;
- Compact Candidate Table-only Consolidation;
- top-level Draft facet/depth boundary;
- known Entity leakage detection;
- suspicious sibling localization and clean-Draft zero-call behavior;
- Provider thinking routing;
- old-engine resume rejection;
- Assignment rejection at the Checkpoint 3.5 boundary;
- run/resume and usage audit regression coverage;
- Repair without corpus replay.

## 9. Unresolved risks

1. The 85.9% figure uses a synthetic worst-case legacy payload. Checkpoint 3.6
   must measure the same frozen 48-card selection with actual Provider usage.
2. Deterministic normalization merges lexical equivalents only. Semantic
   near-synonyms remain the bounded global Consolidation model's job.
3. Content Type has an interface but no measured Spike or formal output yet.
4. Only suspicious top-level sibling pairs need LLM validation at this stage;
   parent-child checks belong to the later subdomain checkpoint.
5. The historical `discovery-spike` command still exposes the old experimental
   path and must not be mistaken for the formal cost-bounded Runner.
6. No database migration was added. Durable taxonomy nodes, assignments, and
   publication remain later checkpoints.

## 10. Rollback

No Snapshot, Silver artifact, production video data, or database Schema was
modified. The code change can be reverted as one checkpoint commit. Old raw
Run artifacts remain local and ignored.
