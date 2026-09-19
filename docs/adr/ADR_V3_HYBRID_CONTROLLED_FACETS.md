# ADR: V3 Hybrid Controlled Facets

- Status: accepted for Checkpoint 3.11 spike
- Date: 2026-07-18
- Base commit: `6e0673e85474251f0c5362198076b52754ec36a0`
- Frozen checkpoint tag: `checkpoint/v3.10-failed`
- Implementation branch: `feat/v3-hybrid-controlled-facets`
- Supersedes: the open Form/Object/Context vocabulary-generation decision in
  `ADR_V3_FACETED_METADATA_MODEL.md`

## Context

Checkpoint 3.10 showed that the four-facet data structure is implementable, but
the discovery algorithm is not useful. Decomposing 31 noisy historical Content
Type candidates produced 85 local nodes; 78 had single-item support, none were
rejected, and 80.84% of enumerated two-facet combinations were empty.

The failed assumption is therefore narrower than the faceted model itself:

> A collection should not openly rediscover complete Presentation Form, Focus
> Object Type, and Use Context vocabularies from its historical LLM candidates.

Run #15–#17 and their code remain immutable experimental history. Their
28/28/29 nodes are not migrated into the controlled vocabularies.

## Decision

Use a hybrid metadata model with asymmetric governance.

### Domain

- Remains open, hierarchical, and evolvable.
- Continues to answer what knowledge field the content primarily discusses.
- Keeps the existing maximum two-level structure.
- Checkpoint 3.11 reuses Run #12 Domain Draft without mutation or discovery.
- Controlled facet vocabularies are not preset Domain answers.

### Presentation Form

- Is global, flat, controlled, and semi-open.
- Uses stable IDs `PF01`–`PF11` from `presentation_form_v1.yaml`.
- Runtime assigns an active ID, `unknown`, and at most one secondary ID.
- Runtime cannot create or activate a new term. Uncovered cases become a
  `form_novelty` proposal for a later vocabulary review.

### Focus Object Type

- Is global, flat, and controlled.
- Uses stable IDs `OT01`–`OT09` from `focus_object_type_v1.yaml`.
- Describes a concrete object category, never a specific entity name.
- Is empty when no salient concrete object exists.
- Prefers deterministic, versioned Entity Type mapping. An uncertain mapping
  may be model-assisted, but can only select an active ID or remain empty.

### Suggested Use Context

- Is stored as `suggested_use_contexts`, not `use_contexts`.
- Uses stable IDs `UC01`–`UC08` from `suggested_use_context_v1.yaml`.
- Is an optional AI suggestion about likely tasks, not the user's actual intent
  and not a core classification.
- May be empty and is not a blocking coverage metric.
- Requires later user confirmation before it could become a stable user label.

## Vocabulary governance

Controlled vocabulary assets are versioned source files. Every term contains a
stable ID, canonical name, definition, includes, excludes, aliases, status, and
version. Checkpoint 3.11 permits only `active` and `deprecated`.

Runtime behavior is read-only:

- load and validate the complete asset;
- record its content hash in the Run Manifest;
- assign only active IDs;
- never write back to the asset;
- never promote a novelty proposal;
- require a separately reviewed new file version for additions or semantic
  changes.

The assets use JSON syntax in `.yaml` files. JSON is a YAML 1.2-compatible
subset and lets the local application validate them without adding a YAML
runtime dependency.

## Entity mapping

Entity Type to Object Type mapping is deterministic and versioned. The mapping
records the source entity, normalized source type, target ID, rule version, and
reason. Unsupported or unreliable source types stay unmapped; they do not
trigger free-form Object Type creation.

Old Content Type candidate names are forbidden mapping inputs.

## Assignment

Checkpoint 3.11 uses the same frozen 48-item Manifest as Checkpoint 3.10
(`A/B/C = 22/9/17`). Each batch performs one structured call for:

- Presentation Form;
- only Object Type choices not already determined from Entity mapping;
- Suggested Use Context;
- Novelty Proposals;
- Domain assignment against the frozen Run #12 tree.

It does not execute candidate decomposition, local vocabulary discovery,
vocabulary consolidation, or Domain discovery.

## Novelty

Novelty is a proposal, not a vocabulary mutation. It records the facet,
proposed name and definition, closest existing IDs, semantic difference,
supporting content IDs, evidence, and confidence. Assignment cannot consume a
proposal as if it were active.

Future promotion requires multiple independent contents, clear boundaries,
non-alias status, long-term cross-collection value, and a separate vocabulary
review that publishes a new version.

## Dynamic faceting

Boolean query semantics remain:

- OR within one facet;
- AND across selected facets;
- unselected facets do not constrain results.

The UI-facing simulation is dynamic rather than a full Cartesian product:

1. start from the current result set;
2. expose only values with non-zero support and show their remaining count;
3. after each selection, recompute the available values;
4. hide or disable zero-support values.

Cross-facet label pairs with support at least three are warnings when both
conditional probabilities exceed 0.9. They are not deleted automatically.

## Derived filters

Natural-language compound categories can be report-level derived filters over
atomic facets. A proposal must have at least three real supporting contents and
retain the exact underlying Boolean expression. It does not become a vocabulary
term, database dimension, or UI shortcut in this checkpoint.

## Consequences

Benefits:

- cross-collection Form and Object metadata remain stable;
- local content no longer invents synonyms and granularities;
- Domain discovery remains open and independent;
- Context can add optional user value without being mistaken for truth;
- dynamic filtering avoids presenting known zero-result combinations;
- novelty remains reviewable without mutating production semantics.

Costs and risks:

- the initial controlled vocabularies encode an explicit product decision;
- global unused terms are expected and are not local fragmentation;
- Form coverage may be insufficient and produce `unknown` or novelty;
- deterministic Entity mapping is limited by Entity extraction quality;
- Context may add little independent retrieval value and remain sparse.

## Explicitly disabled

The Checkpoint 3.10 path

```text
historical candidate decomposition
→ open Form/Object/Context vocabulary generation
```

is unavailable from the Checkpoint 3.11 run entry. Its implementation and
artifacts remain read-only history.

## Out of scope

Full 128-item assignment, Run B/C, Cross-run Merge, Domain Trial Assignment,
production UI, vocabulary auto-publication, Taxonomy Evolution, Agent Harness,
embeddings, vector databases, and BERTopic are excluded.
