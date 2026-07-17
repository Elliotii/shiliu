# V3 Checkpoint 3.7A Classification Profile Report

Status: passed

This report contains aggregate audit data only. Card contents, short-ID
mappings, prompts, responses, and generated Profiles remain in the ignored
private runtime directory.

## 1. Frozen input and boundary

- Snapshot: #2
- Snapshot Hash: `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2`
- Selection: the same 48 eligible contents used by Checkpoints 3.5 and 3.6
- Seed: 73
- Batch size: 12
- Batches: 4
- Evidence distribution: A 22, B 9, C 17
- Model: `deepseek-v4-pro`
- Thinking: off
- Prompt: `classification-profile-generation-v2`

The experiment did not read subtitles, Silver Reference, folder names, user
behavior, notes, or production summary data beyond the approved compact input.
It did not update a video, a user summary, or the production processing flow.

Input projection:

- A/B: short ID, evidence level, title, one-line conclusion, at most three key
  points, and at most five existing entities;
- C: short ID, evidence level, title, and at most 300 characters of the frozen
  description;
- D: excluded.

## 2. Output contract

Each private Profile contains only:

- `main_subject`;
- `content_goal`;
- at most five `key_concepts`;
- at most three `usage_contexts`;
- at most five `entities`;
- at most three `unknown_terms`;
- `source_evidence_level`.

The strict Schema forbids extra fields. Deterministic validation also rejects
missing or duplicate IDs, changed evidence levels, explicit classification
instructions, and Domain, Subdomain, Content Type, or Taxonomy markers.

## 3. Prompt v1 diagnostic

The first full Run was not accepted. Four C-level cards in one batch returned
an empty `content_goal`. JSON Repair filled only those four fields; all other
Profiles in that batch were unchanged.

This was a Prompt/Schema mismatch: the Schema required non-empty scalar fields,
while the Prompt did not explicitly define how to represent an unsupported
goal. The Schema was not relaxed. Prompt v2 instead requires non-empty
`main_subject` and `content_goal`, with an explicit information-insufficient
sentinel when evidence cannot support the goal.

Diagnostic aggregate:

| Metric | Prompt v1 |
|---|---:|
| Completed Profiles | 48 |
| Raw Schema success | 75% of batches |
| Repair | 1 |
| Total Tokens | 19,070 |
| Model time | 89.939 seconds |
| Estimated Token reduction | 53.40% |

## 4. Prompt v2 acceptance Run

| Batch | Cards | Prompt Tokens | Completion Tokens | Total Tokens | Cached | Seconds | Repair |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 12 | 2,295 | 1,510 | 3,805 | 256 | 17.388 | 0 |
| 2 | 12 | 2,277 | 1,481 | 3,758 | 256 | 17.418 | 0 |
| 3 | 12 | 2,273 | 1,838 | 4,111 | 384 | 20.754 | 0 |
| 4 | 12 | 1,986 | 1,603 | 3,589 | 384 | 19.945 | 0 |
| **Total** | **48** | **8,831** | **6,432** | **15,263** | **1,280** | **75.505** | **0** |

The Provider reported no reasoning Tokens. A monetary cost was not returned,
so cost remains `unknown` rather than inferred.

## 5. Compression result

The comparison serializes the same ordered 48 Compact View rows and generated
Profile rows using the same compact line protocol and local mixed-language
Token estimator.

| Metric | Compact View | Profile | Reduction |
|---|---:|---:|---:|
| Characters | 14,457 | 7,906 | 45.31% |
| Estimated Tokens | 10,039 | 4,700 | 53.18% |

Average Profile row length was 164.71 characters. This measures representation
size only; it does not claim that Discovery quality is preserved.

## 6. Acceptance gates

| Gate | Result | Verdict |
|---|---:|---|
| Estimated input Token reduction | 53.18% | pass (minimum 25%) |
| Schema success | 100% | pass |
| Missing or duplicate IDs | 0 | pass |
| Changed evidence levels | 0 | pass |
| Domain/Taxonomy pollution | 0 | pass |
| Repair | 0 | pass |
| Retry | 0 | pass |

Checkpoint 3.7A passes.

## 7. Interpretation and next boundary

`classification_profile_v1` is materially smaller than the current Compact
View and can now be tested as a candidate reusable machine representation. The
result does not yet show that it retains sufficient Domain-discovery signal.
That is the sole purpose of the separately approved Checkpoint 3.7B paired
comparison.

Checkpoint 3.7B has not started. It still requires explicit user approval and
must keep card IDs, batches, order, Prompt, Schema, model, and thinking settings
paired so that only the input representation changes.
