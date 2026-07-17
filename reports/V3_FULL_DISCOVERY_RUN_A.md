# V3 Full Discovery Run A

## Verdict

```text
FAIL
```

The frozen dual-view Run A did not reach either Consolidation or the Quality
Gate. All twelve local model batches completed successfully, but deterministic
Content Type normalization produced 45 unique candidates while the frozen
`CompactContentTypeTable` allowed at most 24. Pydantic therefore rejected the
table before the Content Type Consolidation call.

This is a scale-bound implementation defect, not an API, model-output, Repair,
or private-input failure. Run B/C, Trial Assignment, Diagnosis, Revision, Silver
Eval, review UI, and publication were not started.

## 1. Frozen protocol

| Field | Frozen value |
|---|---|
| Run ID | 10 |
| Protocol | `full-discovery-run-a-v1` |
| Snapshot | #2 |
| Snapshot Hash | `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2` |
| Snapshot Cards | 131 |
| Discovery Eligible | 128 |
| Trial Assignment Only | 3 |
| A/B/C/D | 76 / 17 / 35 / 3 |
| Domain View | `classification_profile_v1` |
| Content Type View | `compact_form_view_v1` |
| Batch size | 24: five batches of 24 plus one batch of 8 per path |
| Seed | 101 |
| Provider | OpenAI-compatible DeepSeek endpoint |
| Model | `deepseek-v4-pro` |
| Local/Content Type thinking | off |
| Global Domain thinking | on, high |
| Git Commit | `f364005083e3a2510c75f424487fc7ef0bcabeff` |
| Git worktree at freeze and execution | clean |

The Profile prerequisite was completed separately before Run A: 128/128 rows,
48 reused and 80 newly generated, with zero Repair, zero pollution, and zero
missing fields. Its frozen Profile Hash is
`07a814d37dacf397790c6928f9e4f84768d2eb138a3112152cac383edd7f39ba`.
Profile materialization used 28,317 Tokens and 151.584 Provider-reported
seconds; those values are not included in the Run A totals below.

## 2. Actual execution summary

| Metric | Actual value |
|---|---:|
| Started | 2026-07-17 18:14:08 UTC |
| Last completed model batch | 2026-07-17 18:17:40 UTC |
| Provider-reported model time | 211.927 s |
| Model calls | 12 |
| Successful model calls | 12 |
| Failed model calls | 0 |
| Deterministic stage failures | 1 |
| Request attempts | 12 |
| Retry | 0 |
| Repair | 0 |
| Prompt Tokens | 33,854 |
| Completion Tokens | 13,831 |
| Cached Prompt Tokens | 1,024 |
| Reasoning Tokens | 0 |
| Total Tokens | 47,685 |

Every batch saved its prompt, raw response, parsed output, audit record, input
Hash, output Hash, model, Prompt version, elapsed time, and usage before the
normalization failure. Every batch has `attempt_count=1` and a valid parsed
output. No completed batch was replayed during this execution.

The process terminated with:

```text
CompactContentTypeTable.content_types
List should have at most 24 items after validation, not 45
```

Because this exception occurred outside the model-stage failure handler, the
database currently records Run #10 as `running` and
`content_type_normalization/main` as `processing`, although the process has
exited. This is a second, smaller recovery-state defect and must not be
interpreted as an active background job.

## 3. Domain local discovery

| Batch | Cards | Domain candidates | Topic hints | Ambiguous IDs |
|---:|---:|---:|---:|---:|
| 1 | 24 | 8 | 5 | 6 |
| 2 | 24 | 8 | 5 | 4 |
| 3 | 24 | 7 | 3 | 4 |
| 4 | 24 | 7 | 2 | 3 |
| 5 | 24 | 8 | 3 | 6 |
| 6 | 8 | 5 | 2 | 1 |

Actual Domain local totals:

- 43 local Domain candidates;
- 42 candidates after deterministic normalized-name grouping;
- 16 normalized Topic hints;
- 12,238 prompt Tokens and 7,199 completion Tokens;
- 19,437 total Tokens;
- 100.416 seconds;
- zero invalid batch supporting IDs, Repair, or retry.

Evidence-level local signal:

| Evidence | Cards | Domain/Topic-supported | Domain ambiguous |
|---|---:|---:|---:|
| A | 76 | 68 | 6 |
| B | 17 | 17 | 0 |
| C | 35 | 17 | 18 |

Domain Consolidation did not run. Consequently the following requested Run A
results are not available and must not be inferred from local candidates:

- final first-level Domain count;
- final second-level Domain count;
- final node support and representative content;
- candidate merge targets;
- Topic/Entity downgrade decisions;
- rejected candidates and final reasons;
- parent-child and sibling quality findings.

## 4. Content Type local discovery

| Batch | Cards | Content Type candidates | Ambiguous IDs |
|---:|---:|---:|
| 1 | 24 | 8 | 2 |
| 2 | 24 | 8 | 2 |
| 3 | 24 | 8 | 9 |
| 4 | 24 | 8 | 7 |
| 5 | 24 | 8 | 5 |
| 6 | 8 | 6 | 0 |

Actual Content Type local totals:

- 46 local Content Type candidates;
- 45 unique candidates after normalized-name grouping;
- 21,616 prompt Tokens and 6,632 completion Tokens;
- 28,248 total Tokens;
- 111.511 seconds;
- zero invalid batch supporting IDs, Repair, or retry.

Evidence-level local signal:

| Evidence | Cards | Content Type-supported | Content Type ambiguous |
|---|---:|---:|---:|
| A | 76 | 68 | 5 |
| B | 17 | 16 | 0 |
| C | 35 | 20 | 20 |

Support and ambiguity may overlap because a card can support one candidate and
also remain ambiguous between forms. For C-level Cards, local support was
57.14% and local ambiguity was 57.14%. These are local discovery signals, not
final Content Type coverage.

Content Type Consolidation did not run. Final Content Type count, merged or
rejected candidates, final C-level coverage, and Domain/Content Type confusion
are therefore unavailable.

## 5. Quality result

The structured Quality Gate did not run because its required Domain and Content
Type Drafts do not exist.

Confirmed before the failure:

- twelve raw responses were parseable;
- all local Schemas passed without Repair;
- all local supporting IDs belonged to their frozen batches;
- D-level Cards did not enter either Discovery path;
- no request retry occurred;
- the frozen Manifest, Git Commit, and Profile Hash checks passed.

Not evaluated:

- Entity Leakage in the stable Domain tree;
- Content Type Leakage in the Domain tree;
- Domain Leakage in Content Types;
- final invalid supporting IDs;
- parent-child adequacy;
- sibling overlap;
- granularity balance;
- missing reasonable subdomains;
- maximum final-node coverage ratio;
- lost local candidates after Consolidation.

The effective blocking issue is:

```json
{
  "code": "content_type_candidate_table_capacity_exceeded",
  "stage": "content_type_normalization",
  "actual_candidates": 45,
  "maximum_candidates": 24,
  "retry_stage": "content_type_normalization",
  "requires_model_replay": false
}
```

The final field means the failed deterministic calculation itself needs no
model replay. It does not mean frozen Run #10 may be resumed under changed code.

## 6. Scale comparison with the 48-card Run #9

The comparison is directional rather than perfectly controlled: Run #10 uses
the formal v2 local output contracts, which preserve includes/excludes,
representatives, parent hints, confidence, and later candidate-decision audit
requirements. Run #9 used the smaller Checkpoint 3.8 contract.

| Metric | Run #9 | Run #10 completed portion | Change |
|---|---:|---:|---:|
| Cards | 48 | 128 | 2.67x |
| Domain local batches | 2 | 6 | 3.00x |
| Content Type local batches | 2 | 6 | 3.00x |
| Local Domain candidates | 16 | 43 | 2.69x |
| Local Content Type candidates | 16 | 46 | 2.88x |
| Discovery-only Tokens | 14,310 | 47,685 | 3.33x |
| Discovery-only time | 43.013 s | 211.927 s | 4.93x |
| Discovery Tokens/card | 298.13 | 372.54 | +24.96% |
| Discovery time/card | 0.896 s | 1.656 s | +84.82% |
| Repair | 0 | 0 | unchanged |
| Retry | 0 | 0 | unchanged |

Run #10 spent 59.24% of its completed Tokens in Content Type Discovery and
40.76% in Domain Discovery. No Consolidation, Validator, or Repair cost was
incurred. Growth was worse than linear in Tokens and time, partly because the
formal v2 outputs are richer and because six sequential network calls were
needed per path. Candidate count itself remained approximately proportional to
corpus size.

The most important scale result is structural: the Content Type normalized
candidate count grew from 16 to 45, exceeding a bound that had only been tested
against the 48-card regression.

## 7. Failure recovery and cache impact

Safe, reusable artifacts:

- Snapshot #2 and its Hash;
- the complete 128-row Profile Corpus and Profile Hash;
- all twelve Run #10 raw responses, parsed outputs, audits, and hashes for
  diagnosis;
- the frozen batch plan and short-ID map.

Run #10 cannot be silently resumed after changing the candidate-table bound.
Its Manifest binds execution to Commit `f364005`; changing code or versions must
create a new Run Manifest. Updating the old Manifest or bypassing its Git check
would break the reproducibility contract.

The current workflow has no reviewed cross-Run import mechanism for completed
batch outputs. Therefore the simplest safe follow-up Run would replay the twelve
local batches. An explicit hash-verified artifact-import feature could avoid
that cost, but it would expand scope and is not recommended solely to save the
47,685 Tokens already spent.

## 8. Minimum required changes

Before another formal Run A:

1. Raise the normalized Content Type candidate-table capacity from 24 to the
   theoretical six-batch maximum of 48. Do not change the final Draft limit of
   2–8 Content Types.
2. Add an offline test with six disjoint eight-candidate batches and assert that
   45–48 normalized candidates can reach Consolidation.
3. Bump the affected table, normalization, workflow, and frozen Manifest
   versions; do not mutate Run #10.
4. Catch deterministic normalization exceptions and persist both stage and Run
   as `failed` with a non-retryable error code, instead of leaving them
   `processing`/`running` after process exit.
5. Re-run the full offline test suite and create a new clean-Commit Run A
   Manifest.

No evidence currently requires changing either local Discovery Prompt, either
input view, batch size, Provider route, or JSON Repair strategy. Whether 45
Content Type candidates can be consolidated coherently is precisely what the
next corrected Run A must measure; it should not be pre-emptively hidden by a
new semantic heuristic.

## 9. Acceptance decision

```text
FAIL
Current dual-view implementation cannot complete at 128-card scale because a
deterministic Content Type candidate-table bound rejects valid full-corpus
output before Consolidation.
```

The failure is narrow and fixable, but Run B/C must not start. A corrected Run A
must complete both Consolidations and the structured Quality Gate before the
project can receive `PASS` or `PASS_WITH_CHANGES`.
