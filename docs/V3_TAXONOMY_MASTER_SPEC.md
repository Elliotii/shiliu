# Shiliu V3 Taxonomy Master Spec

Status: Active master specification

Baseline branch: `feat/v3-taxonomy-bootstrap`

Baseline commit: `c1b7228`

Current implementation checkpoint: Checkpoint 3.6 completed; final 48-card
low-cost regression passed and is pending this checkpoint's reviewed Git commit

This document is the execution baseline for V3. It records the target product,
the real repository state, checkpoint boundaries, acceptance gates, and Git
discipline. The older detailed design remains useful history, but this file is
authoritative when the two documents differ.

## 1. Status vocabulary

- **Existing**: implemented in the repository and covered by tests or saved
  acceptance evidence.
- **Planned**: approved V3 scope, but not implemented yet.
- **Deferred**: explicitly outside the current V3 production path.
- **Experimental**: may be compared later, but cannot become a production
  dependency without a separate checkpoint and gate.

Planned and Deferred capabilities must never be described as completed.

## 2. Product goal

V3 builds a publishable, versioned content taxonomy from the user's saved
content and uses that taxonomy to classify existing and newly saved videos.

The completed V3 product should provide:

1. an independent Content Type classification system;
2. a stable Domain Taxonomy with at most two levels;
3. auditable assignments for existing content;
4. progressive loading of additional local evidence for ambiguous content;
5. gated resolution of unfamiliar concepts;
6. distinct queues for distinct rejection causes;
7. one bounded diagnosis and structural revision;
8. versioned publication, stable node IDs, and rollback metadata;
9. incremental classification of new videos using the active Taxonomy;
10. Token, latency, cache, retry, Repair, and recovery audits.

## 3. Non-goals

V3 does not implement:

- a general RAG or Hybrid Search platform;
- BERTopic or a general clustering platform;
- a vector database as a required production dependency;
- LangGraph, an Agent Harness, or an autonomous taxonomy Agent;
- an infinite self-revision loop;
- a complex HITL workbench or general Eval platform;
- a human Gold Set that blocks the product path.

Deferred work:

- **V3 optional experiment**: Embedding Candidate Retrieval plus LLM;
- **V4**: taxonomy browsing and editing, review UI, Hybrid Search, and similar
  content;
- **V5**: external-research Taxonomy Agent, complex HITL, and reconsideration
  of workflow frameworks only if ordinary services are no longer sufficient.

## 4. Repository calibration at baseline `c1b7228`

### 4.1 Existing foundations

| Capability | Status | Repository evidence |
|---|---|---|
| Runtime / Eval isolation | Existing | `eval/ANTI_CONTAMINATION.md`, isolation tests |
| Silver Eval Protocol and generator | Existing | `eval/protocols/`, `eval/silver_generator.py` |
| Frozen Silver Reference v1 | Existing local private artifact | ignored under `eval/private_reference/`; runtime cannot read it |
| Immutable Corpus Snapshot | Existing | `taxonomy_corpus_snapshots` |
| Frozen Classification Card | Existing | `taxonomy_classification_cards` |
| A/B/C/D and Discovery eligibility | Existing | `taxonomy/corpus.py`, Snapshot tests |
| Facet Extraction spike | Existing | `taxonomy/facets.py` |
| Compact Discovery View and short IDs | Existing | `build_compact_corpus()` |
| Batched Local Discovery | Existing | `taxonomy/discovery.py` |
| Consolidation and Trial Assignment | Existing checkpoint implementation | `taxonomy/discovery.py`, `taxonomy/workflow.py` |
| Novelty Pool | Existing but semantically coarse | low-confidence and all rejection causes currently share one file |
| Deterministic Quality Gate | Existing | `taxonomy/quality.py` |
| Whole-draft Hierarchy Validation | Existing, to be narrowed in 3.5 | `build_hierarchy_validation_prompt()` |
| JSON Repair without corpus replay | Existing | `taxonomy/model_calls.py` |
| Raw response persisted before validation | Existing | `AuditedJsonCaller` |
| Token, reasoning, cache, latency, retry audit | Existing | call audit plus `taxonomy_stage_runs` |
| CLI run/resume/status | Existing | `taxonomy/cli.py`, workflow recovery tests |

The full test baseline is 92 passing tests.

### 4.2 Current database boundary

Schema version 6 has exactly four Taxonomy tables:

- `taxonomy_corpus_snapshots`;
- `taxonomy_classification_cards`;
- `taxonomy_runs`;
- `taxonomy_stage_runs`.

`taxonomy_stage_runs` already stores stage status, input/output hashes, Provider
and model, prompt version/hash fields, thinking mode, Token fields, cost fields,
latency, retry state, and output path.

The following product tables do not exist yet and are **Planned**, not Existing:

- classification profiles;
- taxonomy versions and nodes;
- durable assignments;
- concept cards;
- evidence/concept/multi-domain/novelty/exclusion queues.

Checkpoint 3.5 must not add these tables. Its normalized candidates and local
validation plans remain versioned run artifacts plus stage metadata.

### 4.3 Current workflow mismatch to the target design

The existing Checkpoint 3 workflow is:

```text
Compact Cards
-> Local Discovery of Content Type + primary/subdomain Domain + Topic + Entity
-> optional Content Type Recovery
-> Consolidation into Content Type + two-level Domain + Topic + Entity
-> whole-draft Hierarchy Validator with all local candidates
-> deterministic Quality Gate
-> full Trial Assignment
-> one coarse Novelty Pool
```

This path proved the batching, auditing, Repair, and resume foundations, but it
is not the final cost architecture. It amplifies context because:

1. `LocalDiscoveryOutput` permits 12 Content Types, 16 Domains, 20 Topics, and
   30 Entities per batch;
2. Local Domain candidates include includes, excludes, parent hints, and long
   stability reasons;
3. raw local candidate objects are passed directly to Consolidation;
4. Consolidation currently creates a complete two-level tree and repeats Topic
   and Entity output;
5. Hierarchy Validation reads the full Draft and every full local output;
6. Trial Assignment repeats the full Draft in every batch.

Checkpoint 3 measured at least 166,738 Tokens for the 48-card regression. The
dominant cost was repeated intermediate state, not the compact cards.

### 4.4 Provider and thinking constraint

The current OpenAI-compatible integration reliably expresses two practical
Taxonomy modes:

- thinking disabled for `taxonomy_local`, `taxonomy_assignment`, and
  `taxonomy_repair`;
- thinking enabled with `reasoning_effort=high` for `taxonomy_global`.

The current configured Provider does not establish a separately verified
`medium` reasoning control. Until that behavior is verified, “medium” in the
logical design maps to a bounded local call with thinking off; high is reserved
for explicit global or escalated-local calls. Checkpoint 3.5 must not invent an
unsupported Provider parameter.

## 5. Stable architectural principles

### 5.1 User output and machine representation are separate

Existing user-facing summaries remain unchanged:

- one-line conclusion;
- key points;
- complete summary and sections;
- projects, tools, and models;
- actionable items.

`classification_profile_v1` is a separate machine representation. It must not
shorten or overwrite the user summary.

### 5.2 Content Type and Domain are separate pipelines

- Content Type answers how content is expressed or intended to be used.
- Domain answers which durable knowledge area the content belongs to.

Content Type cannot be inserted into the Domain tree.

### 5.3 Domain construction is top-down

```text
discover top-level Domains
-> assign content to top-level Domains
-> discover subdomains only inside parents that need subdivision
-> final two-level assignment
```

Not every top-level Domain needs a child.

### 5.4 Evidence is loaded progressively

```text
L0 classification_profile
L1 one-line conclusion + at most 3 key points
L2 description or relevant complete-summary text
L3 relevant sections or subtitle fragments
```

Each escalation records why it happened, what evidence was added, the changed
result, and the incremental cost. More than roughly 20% of items reaching L2/L3
is a mandatory stop condition.

### 5.5 Concept Search is gated and non-classifying

Concept Resolution may produce a canonical name, entity type, aliases, a short
definition, and sources. It cannot decide a Shiliu Domain or create a Taxonomy
node.

### 5.6 Classification is open-set

Rejection reasons remain distinct:

- `insufficient_evidence` -> Evidence Enrichment Queue;
- `unknown_concept` -> Concept Resolution Queue;
- `cross_domain` -> Multi-domain Queue;
- `taxonomy_gap` -> Novelty Pool;
- `out_of_scope` -> Exclusion Pool.

Only repeated `taxonomy_gap` evidence can drive later Taxonomy evolution.

## 6. Target logical data objects

### 6.1 Classification Profile — Implemented by Checkpoint 3.7A

```json
{
  "profile_version": "v1",
  "main_subject": "",
  "content_goal": "",
  "key_concepts": [],
  "usage_contexts": [],
  "entities": [],
  "unknown_terms": [],
  "source_evidence_level": "A|B|C"
}
```

It cannot contain a predicted Domain, a human category name, the full summary,
or a long classification reason.

### 6.2 Taxonomy Version — Planned for Checkpoint 8

Stores version, status, source Snapshot, model/prompt/schema versions, creation
and publication timestamps, parent version, quality report, and rollback target.

### 6.3 Taxonomy Node — Planned for Checkpoints 4/6/8

Stores stable ID, temporary discovery ID, node type, parent ID, name, short
definition, includes/excludes, supporting and representative content IDs,
status, source Run, stability/confidence, created version, and retired version.

### 6.4 Assignment — Planned for Checkpoints 5/7/8

Stores content key, Taxonomy version, Content Type, primary Domain path,
optional secondary Domain, confidence, alternative, rejection reason, evidence
level used, escalation level, Concept Resolution IDs, and model/prompt/run
metadata.

## 7. Checkpoint execution map

Every checkpoint starts from a clean branch, ends with related and full tests,
performs a privacy scan, creates one reviewed commit, pushes it, and stops before
the next checkpoint unless the user explicitly continues.

### Checkpoint 3.5 — Cost architecture correction

Status: **Existing in the Checkpoint 3.5 implementation commit**

Input:

- existing Compact Discovery rows;
- existing Facet/card entities as local deterministic evidence;
- existing run/resume and audited call infrastructure.

Output:

- top-level-only Local Domain candidates;
- independently callable low-cost Content Type spike interface;
- deterministic Compact Candidate Table;
- top-level Domain Consolidation input and Draft;
- deterministic validation plan plus only suspicious local LLM validation units;
- versioned limits and thinking route;
- no database migration and no real model run.

Hard limits:

- Local Domain candidates: at most 8 per batch;
- supporting IDs: at most 5 per candidate after normalization;
- Topic hints: optional, at most 5 per batch, short name plus supporting IDs;
- Local Entity output: zero;
- Local Content Type output: zero in Domain Discovery;
- Consolidation output: top-level Domains only, normally 5–10, hard maximum 12;
- representative IDs: at most 3 per Domain;
- LLM Validator input: one suspicious local unit, never all local history.

Acceptance gates:

- Local output quantity limits are enforced by Schema and deterministic checks;
- Entity is not generated by Local Domain Discovery;
- Compact Candidate normalization is deterministic and tested;
- Consolidation reads the Compact Candidate Table, not raw Local outputs;
- local rules decide whether an LLM Validator call is needed;
- Validator prompts contain only the selected nodes and bounded representative
  profiles;
- Repair still contains only raw response, validation errors, and compact
  Schema;
- run/resume and usage audit tests remain green;
- all existing tests pass or are deliberately updated for the new contract.

Commit:

```text
refactor: reduce taxonomy context amplification
```

### Checkpoint 3.6 — 48-card low-cost regression

Status: **Existing; final Run #4 passed all Checkpoint 3.6 hard gates**

Input: same frozen 48-card regression selection and the Checkpoint 3.5 pipeline.

Output: private raw Run plus a sanitized quality/cost report.

Quality gates:

- independent Content Type output exists;
- top-level Domain output exists;
- all supporting IDs are valid;
- Entity Leakage is zero;
- Local and Consolidation Repair counts are zero;
- resume passes;
- constructed local conflicts are detected.

Cost gates:

- hard total maximum: 90,000 Tokens and 15 minutes;
- optimization target: 60,000–70,000 Tokens and at most 10 minutes;
- Local Discovery total at most 15K;
- Content Type plus Consolidation at most 20K;
- Validator at most 8K;
- ideal Repair count is zero.

If the hard gate fails, stop and analyze before any formal Discovery.

Measured final result:

- 23,134 total Tokens;
- 16,673 prompt Tokens and 6,461 completion Tokens;
- 2,465 reasoning Tokens, contained in the Consolidation completion count;
- 95 seconds end to end;
- Local Discovery: 9,374 Tokens;
- Content Type plus Consolidation: 13,760 Tokens;
- zero Repair, retry, and local Validator calls;
- 8 Content Types and 10 top-level Domains;
- zero invalid supporting IDs, Entity Leakage, or Content Type Leakage;
- completed-Run resume returned without changing any attempt count.

Run #2 and Run #3 are retained as private diagnostic evidence. They exposed
bounded auxiliary-field overflow and motivated deterministic local truncation;
neither is the final acceptance Run.

Commit:

```text
test: validate low-cost taxonomy regression
```

### Checkpoint 3.7A — Classification Profile generation

Status: **Completed and accepted; isolated from production processing**

Input for the same frozen 48-content selection:

- A/B: title, conclusion, at most three key points, at most five extracted
  entities, and evidence level;
- C: title, at most 300 characters of the already frozen description, and
  evidence level;
- D: excluded from this experiment.

It does not reread subtitles, Silver Reference, folder names, user behavior, or
user notes. It does not modify summaries or the production video pipeline.

Output: private `classification_profile_v1` artifacts for 48 items only, plus
generation usage, elapsed time, Repair, missing-field, average-length,
pollution, and offline compression metrics.

Gates:

- conservative estimated Discovery input reduction at least 25%;
- Schema success 100%;
- zero missing or duplicate content IDs;
- no Domain/Taxonomy output fields or explicit classification instructions;
- Repair zero;
- generation cost and Profile length fully audited.

Failure stops before Checkpoint 3.7B.

Acceptance result for Prompt v2 over the frozen 48-content selection:

- 48/48 Profiles completed across four batches;
- Evidence distribution: A 22, B 9, C 17;
- Schema success 100%, Repair 0, retry 0, missing fields 0;
- Domain/Taxonomy pollution 0;
- 15,263 total generation Tokens, including 8,831 prompt and 6,432
  completion Tokens;
- 0 reasoning Tokens and 1,280 cached prompt Tokens;
- 75.505 seconds of Provider-reported model time;
- average compact Profile row length 164.71 characters;
- estimated Discovery-row Token reduction 53.18% and character reduction
  45.31% relative to the Compact View.

Prompt v1 is retained only as private diagnostic evidence. It produced four
empty `content_goal` values on C-level cards and therefore required one JSON
Repair. Prompt v2 requires non-empty scalar fields and the explicit
`information insufficient` sentinel when a goal cannot be supported. A fresh
full 48-card Run then passed without Repair.

Commit:

```text
feat: add classification profile projection
```

### Checkpoint 3.7B — Paired Compact/Profile Discovery comparison

Status: **Planned; forbidden until Checkpoint 3.7A passes and the user approves**

Runs two paired groups over identical IDs, task prompts, output Schemas, model,
thinking configuration, batch membership, and within-pair input order. The only
experimental variable is Compact View versus `classification_profile_v1` and
its necessary row-protocol description.

It compares one-time Profile cost, repeated Discovery savings, Token
break-even, semantic Domain recovery, discovery-support coverage, C-level
support coverage, ambiguity, leakage, Repair, and within-representation
stability. It does not run Trial Assignment or claim classification accuracy.

Commit:

```text
test: compare compact and profile taxonomy discovery
```

### Checkpoint 4 — Formal top-level Taxonomy Discovery

Status: **Planned**

Input: all 128 eligible profiles from the frozen Snapshot.

Output: independent Content Type result plus top-level Discovery A and B;
Discovery C runs only if A/B are structurally unstable.

Each Domain Run contains only:

```text
Local top-level candidates
-> Compact Candidate Table
-> top-level Global Consolidation
```

Gates: at most 45K Tokens per Run; A+B at most 90K; no Silver data is visible
to Discovery. C is conditional.

Commit:

```text
feat: discover top-level taxonomy domains
```

### Checkpoint 5 — Full top-level Assignment

Status: **Planned**

Input: 128 eligible profiles plus three D-level cards and compact top-level
Taxonomy.

Output: top-level assignments, evidence escalation audit, and distinct rejection
queues. Explanations are emitted only for low confidence or rejection cases.

Gates include escalation distribution, Concept Resolution trigger rate, and a
mandatory stop if more than roughly 20% of items need L2/L3 evidence.

Commit:

```text
feat: assign content to top-level taxonomy
```

### Checkpoint 6 — Parent-local subdomain discovery

Status: **Planned**

Input: one parent definition/boundary, only profiles assigned to that parent,
existing children if any, and short neighboring top-level definitions.

Output: zero or more stable children for that parent, followed by local
parent-child, sibling-overlap, and granularity checks.

There is no requirement to create children for every parent.

Commit:

```text
feat: discover subdomains within parent domains
```

### Checkpoint 7 — Final Assignment, diagnosis, and one revision

Status: **Planned**

Input: complete two-level Draft A and all content.

Output: final assignments, distinct queues, diagnostic metrics, structured
operations, and Draft B.

Exactly one automatic revision is allowed. Supported operations are rename,
definition update, merge, split, move, delete, downgrade to Topic, convert to
Entity, or keep unchanged.

Commit:

```text
feat: add taxonomy diagnosis and bounded revision
```

### Checkpoint 8 — Publish Taxonomy v1 and classify new content

Status: **Planned**

Input: automatically gated Draft B, quality report, and Silver Agreement.

Output: active Taxonomy v1 with stable IDs and rollback metadata; new videos
generate a Profile and use the active Taxonomy without triggering full
Discovery.

Commit:

```text
feat: publish taxonomy v1 and classify new content
```

### Checkpoint 9 — Optional experiments

Status: **Experimental / Deferred from V3 acceptance**

- full Profile Discovery versus coverage-sample Discovery;
- full-taxonomy LLM Assignment versus hierarchical top-down Assignment versus
  Embedding Candidate Retrieval plus LLM.

Embedding cannot become a production dependency without Candidate Recall@K,
Silver Agreement, Token, latency, low-confidence, and Taxonomy Gap evidence.

## 8. Checkpoint 3.5 implementation contract

### 8.1 Before and after call graph

Before Checkpoint 3.5:

```text
batch cards
-> mixed Local Discovery
-> raw local objects
-> full two-level Consolidation
-> whole Draft + all Local outputs Validator
-> Quality Gate
-> optional full Assignment
```

Implemented Checkpoint 3.5 path:

```text
batch cards
-> top-level Domain Local Discovery
-> deterministic Candidate Normalizer
-> Compact Candidate Table
-> top-level Consolidation
-> deterministic structural checks
-> zero or more bounded local validation units
-> local LLM Validator only for suspicious units
-> Quality Gate
```

Content Type has an independent bounded prompt/schema interface. It is not run
by the formal top-level workflow yet. Trial Assignment is explicitly rejected
when creating a Checkpoint 3.5 Run and remains planned for Checkpoint 5.

### 8.2 Fields removed from cross-stage transport

Local Domain Discovery no longer transports:

- Content Type candidates;
- subdomain suggestions and parent hints;
- Entity candidates;
- long Topic definitions;
- includes/excludes lists;
- stability-reason prose.

The Compact Candidate Table retains only canonicalized short name, one short
definition, merged/truncated supporting IDs, batch support count, and optional
short evidence codes or bounded Topic hints.

### 8.3 Candidate normalization

The normalizer is ordinary deterministic code:

1. Unicode/whitespace/case/punctuation normalization creates a comparison key;
2. exact normalized names merge without an LLM;
3. supporting IDs are deduplicated, sorted by frozen short-ID order, and capped;
4. long definitions are truncated to the contract limit;
5. candidates with invalid/empty support are rejected;
6. per-batch and global candidate limits are enforced;
7. output is stable-sorted and hashed;
8. the raw response remains an audit artifact but is not a Consolidation input.

Semantic near-synonym merging remains Consolidation's job; the deterministic
normalizer must not pretend lexical equality proves semantic equivalence.

### 8.4 Minimal Consolidation input

Consolidation receives:

- Compact Candidate Table version;
- normalized candidate ID;
- short name and short definition;
- total supporting count;
- at most five supporting IDs;
- at most three representative IDs;
- optional short evidence codes;
- no cards, raw local response, Content Type, Entity, subdomain tree, or full
  Validator history.

### 8.5 Validator split

Deterministic rules check Schema, ID format, valid support, empty/duplicate
nodes, depth, parent count, node count, representative membership, support
overlap, known Entity/Content Type leakage, and basic structural completeness.

Those rules generate `ValidationUnit` records only for suspicious cases, such
as one parent with proposed children or one high-overlap sibling pair. Each LLM
Validator prompt receives one unit plus bounded representative Profiles. A
clean top-level Draft can therefore require zero LLM Validator calls.

### 8.6 Thinking route

| Stage | Repository route for Checkpoint 3.5 |
|---|---|
| Content Type spike | thinking off |
| Local top-level Domain Discovery | thinking off |
| Candidate Normalization | local code |
| Global top-level Consolidation | thinking on, high |
| Deterministic Validator | local code |
| suspicious local Validator | thinking off; a later explicit escalation route is Planned |
| JSON Repair | thinking off |

### 8.7 Cost prediction and measurement boundary

Checkpoint 3.5 performs no real model call. Offline prompt construction and
fixture outputs should show:

- Local completion surface reduced by roughly 50–75%;
- Consolidation input characters reduced by roughly 60–80%;
- Validator input characters reduced by more than 80% for each local unit;
- overall 48-card Token reduction plausibly 45–65% from the Checkpoint 3
  baseline.

These are predictions, not acceptance evidence. Checkpoint 3.6 must measure
actual Provider usage and enforce the 90K hard gate.

### 8.8 Rollback

No migration or production Taxonomy publication occurs. Rollback is one Git
revert of the Checkpoint 3.5 commit. Existing frozen Snapshots, Silver files,
Run records, and saved raw artifacts remain unchanged. Prompt/engine/schema
versions must change so an old Run cannot silently resume under the new
contract; existing completed runs remain readable as historical artifacts.

## 9. Eval, privacy, and Git discipline

- Runtime never reads private Silver files.
- Silver Agreement is not true accuracy.
- Reference-free Judges report only and never edit a Draft.
- Raw prompts/responses, actual Silver data, candidate video exports, databases,
  and cost-analysis source files remain ignored local artifacts.
- Every checkpoint uses explicit reviewed staging, `git diff --cached`,
  `git diff --check`, related tests, full tests, and a tracked-data privacy scan.
- No force push, history rewrite, or unreviewed `git add .`.
- V3 remains on `feat/v3-taxonomy-bootstrap` until final acceptance.

## 10. Mandatory stop conditions

Stop and report before expanding architecture if:

- Checkpoint 3.6 exceeds 90K Tokens;
- Local or Consolidation still frequently needs Repair;
- Profile compression is below about 25% or harms major/long-tail Domains;
- A/B/C Discovery cannot converge;
- more than roughly 20% of content needs L2/L3 evidence;
- Concept Search, `taxonomy_gap`, or forced subdomain creation is abnormally
  frequent;
- a large migration or run/resume rewrite appears necessary;
- private data may enter Git;
- Provider or structured-output behavior differs materially from assumptions.

The report must include actual evidence, root cause, options, and cost/impact,
then wait for user direction.
