# ADR: V3 Faceted Metadata Model

- Status: accepted for Checkpoint 3.10 spike
- Date: 2026-07-18
- Base commit: `b65a866a99163294d7e3b5b81f7f8825894186c1`
- Frozen checkpoint tag: `checkpoint/v3.9-failed`
- Implementation branch: `feat/v3-faceted-metadata`
- Scope: schema, candidate decomposition, controlled vocabularies, a 36–48 item
  assignment spike, and query simulation only

## Context

Checkpoint 3.9 disproved the assumption that one pure, flat `Content Type`
vocabulary can independently contain presentation form, focus object category,
use context, and content goal. Run #13 and Run #14 both passed their automated
gate, while independent review found blocking semantic leakage and sibling
overlap. The final Checkpoint 3.9 result is `FAIL`.

The historical artifacts remain evidence of that experiment. They are not
deleted, overwritten, renamed as a success, or silently migrated into the new
model.

## Frozen history

The tag `checkpoint/v3.9-failed` identifies the exact code, report, and tests at
the end of Checkpoint 3.9. Local private runtime artifacts stay outside Git and
remain unchanged.

| Run | Frozen database status | Manifest SHA-256 |
|---|---|---|
| #10 | `running` (historical incomplete run) | `8af50461d2f1468c1cc51f582c52a27a0bd8d03b8eb2cbba7a1a7c965ab864e9` |
| #11 | `retry_wait` (historical failed run) | `4f082b0bf305d68d9cf51c472177d07d0f32b5a146106879a3805ba18033b8ae` |
| #12 | `completed` | `fe896db14a3afc7d8a4a285c5ed39bf43ccf33f2d9af7cb05841548c6dc0ce97` |
| #13 | `completed` | `fbe82885b9a191dd98a35bb14f6dc10a83ab66fd10779fca5f725899d1e2f03c` |
| #14 | `completed` | `bc69e59b1a6fc1a602c595b4eaf67cb8f6197fa5b8e9813739d3680df0e7bd82` |

The non-completed statuses for Runs #10 and #11 are deliberately preserved.
Changing them would rewrite the historical failure state.

## Decision

Content metadata is separated into four independent facets.

### 1. Domain

Product meaning: the primary knowledge field discussed by the content.

- Reuse the current Domain Taxonomy and Run #12 Domain Draft without mutation.
- Keep at most two levels.
- Require one primary Domain path for the assignment spike; allow optional
  secondary paths.
- Treat Domain as the evolvable primary classification tree.
- Do not rerun Domain Discovery in Checkpoint 3.10.

### 2. Presentation Form (`presentation_form`)

Product name: 内容形式.

It answers: how does the author primarily organize, express, or present the
content?

- Use a global, flat, controlled vocabulary.
- Assign exactly one primary form and at most one secondary form.
- Require forms to be reusable across Domains or focus object types.
- Exclude field names, object categories, and usage scenarios.
- Do not impose a fixed final vocabulary size.

### 3. Focus Object Type (`focus_object_types`)

Product name: 对象类型.

It answers: what category of object does the content mainly focus on?

- Use a global, flat, controlled vocabulary.
- Assign zero to two object types.
- Store categories, not concrete names. Concrete projects, models, tools,
  papers, and people remain Entities.
- Permit an empty result when no object category is prominent.

### 4. Use Context (`use_contexts`)

Product name: 使用场景.

It answers: in what task or goal would a user normally use this content?

- Use a global, flat, controlled vocabulary.
- Assign zero to two contexts.
- Require evidence; otherwise leave it empty or mark ambiguity.
- Do not derive a context mechanically from Domain.
- Treat it as an optional filtering aid, not a classification tree.

## Facet priority

The facets are intentionally asymmetric:

1. Domain is the core classification.
2. Presentation Form is the core filter.
3. Focus Object Type and Use Context are optional auxiliary filters.

Completeness across all four facets is not a goal. Empty optional facets are
valid and preferable to unsupported guesses.

## Versioning and migration

The old and new semantics must never be conflated:

| Version | Meaning | Status |
|---|---|---|
| `content_type_v1` | old experimental compound Content Type | deprecated, retained |
| `presentation_form_v1` | presentation/organization form | active spike schema |
| `focus_object_type_v1` | focus object category | active spike schema |
| `use_context_v1` | user task or usage goal | active spike schema |

- No `content_type_v1` value is copied directly into a new field.
- New assets retain source Run, Snapshot, candidate, card, view, and hash
  lineage.
- Checkpoint 3.10 uses versioned JSON assets and non-destructive code paths.
- It does not delete database fields, migrate production user data, or modify
  Run #12–#14 artifacts.

## Candidate decomposition

The 31 normalized candidates from Run #14 are source evidence, not the new
vocabulary. Each candidate receives an explicit decomposition decision that can
retain multiple components: presentation form, focus object types, use
contexts, Domain, and Entities. Unresolved or discarded parts are recorded.

Decomposition must not be implemented by keyword splitting, hard-coded expected
labels, direct copying into Presentation Form, or forced total coverage.

## Controlled vocabulary and assignment

Each non-Domain facet uses a versioned controlled vocabulary. Nodes are
`stable`, `draft`, or `rejected` and retain definitions, boundaries, aliases,
source candidates, source content, and rejection rationale.

The assignment spike may only select from the frozen vocabularies. `unknown`,
`none`, and `ambiguous` are valid outcomes. New concepts enter a novelty pool;
they do not become stable nodes during assignment.

Hard label budgets are validated without truncation:

- Domain: one primary path plus optional secondary paths.
- Presentation Form: one primary plus at most one secondary.
- Focus Object Type: at most two.
- Use Context: at most two.

## Query semantics

Checkpoint 3.10 does not implement a production UI, but freezes its filtering
semantics:

- selections inside one facet are combined with OR;
- selected facets are combined with AND;
- an unselected facet does not restrict results.

Users may filter by any single facet or any two-, three-, or four-facet
combination. The spike must measure empty, singleton, overly broad, and overly
narrow result sets instead of manufacturing combinations.

## Isolation and evaluation

- Runtime code and prompts cannot read Silver Reference artifacts.
- Candidate Decisions are provenance, not correctness evidence for the
  independent Reviewer.
- The automated gate checks completeness, leakage, budgets, traceability,
  immutable Domain lineage, and unsupported promotion.
- A separate read-only Reviewer evaluates the report and frozen artifacts
  without database writes or Provider calls.

## Consequences

Benefits:

- compound labels can retain their useful components without pretending to be
  one pure Content Type;
- Domain remains stable while browsing gains orthogonal filters;
- optional facets may remain sparse without becoming failures;
- future UI filtering has deterministic Boolean semantics.

Costs and risks:

- decomposition and vocabulary consolidation add two explicit stages;
- multiple facets can fragment queries if vocabularies are too fine-grained;
- a model may still leak Domain, Entity, or Context semantics into a Form;
- small-sample support is insufficient for publication, so Checkpoint 3.10 can
  only authorize a larger validation plan, not production migration.

## Explicitly out of scope

Run B/C, Cross-run Merge, full 128-item Faceted Assignment, Trial Assignment,
Diagnosis, Revision, production UI, Taxonomy publishing, incremental
classification, Taxonomy Evolution, Silver Reference access, embeddings,
BERTopic, vector databases, and Agent Harness are excluded.
