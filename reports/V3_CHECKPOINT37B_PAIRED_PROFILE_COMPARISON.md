# V3 Checkpoint 3.7B Paired Profile Comparison

Status: unified-Profile gate failed

The experiment completed successfully. The failure is a product-quality gate,
not an execution failure. This report contains aggregate audit data only; card
contents, prompts, responses, generated Taxonomy names, and ID mappings remain
in ignored private runtime storage.

## 1. Experiment contract

- Snapshot: #2
- Snapshot Hash: `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2`
- Frozen selection: the same 48 A/B/C cards as Checkpoints 3.5–3.7A
- Evidence distribution: A 22, B 9, C 17
- Pair 1 seed: 73
- Pair 2 seed: 137
- Batch size: 24
- Model: `deepseek-v4-pro`
- Local Discovery and Content Type thinking: off
- Global Consolidation thinking: high
- Trial Assignment: disabled
- Search and Silver Reference: disabled

Each Pair used identical IDs, order, batch membership, task contract, output
Schema, model, and thinking configuration. The only variable was Compact View
versus `classification_profile_v1` and its necessary row-protocol description.
The runner rejects a Pair if the persisted batch plans differ.

## 2. Execution health

All four Discovery Runs completed and passed the existing structural Quality
Gate.

| Run | Representation | Domains | Repair | Retry | Entity leakage | Content-Type leakage | Quality |
|---|---|---:|---:|---:|---:|---:|---|
| A1 | Compact | 7 | 0 | 0 | 0 | 0 | pass |
| B1 | Profile | 5 | 0 | 0 | 0 | 0 | pass |
| A2 | Compact | 6 | 0 | 0 | 0 | 0 | pass |
| B2 | Profile | 6 | 0 | 0 | 0 | 0 | pass |

There were no invalid supporting IDs. The four independent Draft-alignment
calls also required zero Repair.

## 3. Representation cost

### Direct representation stages

Local Discovery and Content Type are the stages that directly reread the card
representation. Their average prompt cost was:

| Representation | Average prompt Tokens |
|---|---:|
| Compact | 15,066 |
| Profile | 7,634 |
| Saved per comparable use | 7,432 (49.33%) |

The accepted 3.7A Profile generation cost was 15,263 Tokens. On direct prompt
savings alone, its break-even point is three comparable uses.

### Complete Discovery Runs

| Pair | Compact Tokens | Profile Tokens | Compact seconds | Profile seconds |
|---|---:|---:|---:|---:|
| 1 | 23,110 | 15,214 | 86.283 | 88.494 |
| 2 | 23,218 | 17,729 | 94.261 | 128.950 |

Across the four Runs, Discovery consumed 79,271 Tokens and 397.988 seconds of
Provider-reported model time. Four semantic alignment calls added 8,928 Tokens
and 27.561 seconds. The complete 3.7B experiment therefore used 88,199 Tokens
and 425.549 seconds, excluding the earlier one-time Profile generation.

Profile reduced average complete-Run Tokens by about 28.9%, but did not reliably
reduce latency. Pair 2 produced a longer high-thinking Consolidation response,
showing that smaller input does not guarantee shorter model time.

## 4. Top-level Domain preservation

An independent alignment evaluator compared names, definitions,
includes/excludes, supporting-ID overlap, and representative-ID overlap. It did
not read cards or Silver data.

| Metric | Pair 1 | Pair 2 | Gate |
|---|---:|---:|---|
| Weighted Domain recovery | 91.18% | 100% | pass (minimum 85%) |
| C-level Domain/Topic signal delta | +5.88 pp | 0 pp | pass (drop at most 5 pp) |

Across the two input orders, Compact Domain recovery was 97.06%; Profile Domain
recovery was 100%. Domain count equality was deliberately not a gate.

These results support Profile as a compact Domain-discovery representation.

## 5. Why the unified representation failed

The first analysis used final Draft `supporting_ids` as “C coverage.” That was
too strong an interpretation: the field stores a bounded set of representative
evidence and is not a Trial Assignment for every card. It is now reported only
as `c_representative_support_rate`.

The corrected analysis separates Domain signal from Content Type signal:

| Pair | Compact C Content-Type support | Profile support | Compact C ambiguous | Profile ambiguous |
|---|---:|---:|---:|---:|
| 1 | 82.35% | 0% | 17.65% | 100% |
| 2 | 35.29% | 23.53% | 64.71% | 76.47% |

C-level Content Type ambiguity increased by 82.35 and 11.76 percentage points.
Both exceed the five-point gate.

This is consistent with the representation design. The Profile preserves
`main_subject`, `content_goal`, concepts, contexts, and entities, but removes
the title and description/form evidence that indicates whether content is a
tutorial, project walkthrough, commentary, interview, demonstration, or other
Content Type. In the accepted 48 Profiles, 9 of 17 C-level items also had an
information-insufficient goal and empty concepts, further limiting form
inference.

## 6. Acceptance decision

| Gate | Verdict |
|---|---|
| Profile input reduction at least 25% | pass |
| Weighted Domain recovery at least 85% | pass |
| C-level Domain signal drop at most 5 pp | pass |
| Overall ambiguity increase at most 5 pp | pass |
| Entity and Content Type leakage zero | pass |
| Repair zero | pass |
| Structural Quality Gate | pass |
| C-level Content Type ambiguity increase at most 5 pp | **fail** |

`classification_profile_v1` is therefore not accepted as one unified machine
representation for both Domain and Content Type discovery. It is a viable
Domain representation.

The evidence favors facet-specific routing in a future explicitly approved
checkpoint: use Profile for Domain discovery, while Content Type retains title
and other form-bearing Compact evidence. This report does not authorize that
change, a 128-item Profile backfill, formal Discovery A/B/C, Trial Assignment,
or production integration.
