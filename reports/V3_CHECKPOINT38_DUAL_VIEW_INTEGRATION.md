# V3 Checkpoint 3.8 Dual-View Integration Regression

Status: passed

This report contains aggregate audit data only. Frozen card content, Profiles,
Compact View rows, prompts, responses, generated names, and short-ID mappings
remain in ignored private runtime storage.

## 1. Final architecture decision

The unified-Profile experiment is retired. Discovery now uses two sibling views
derived from the same frozen Classification Card:

```text
classification_profile_v1 -> Domain Discovery
compact_form_view_v1       -> Content Type Discovery
```

Profile is a semantic representation for durable knowledge-area recognition.
Compact Form View retains title, bounded description when available, and other
form-bearing evidence for content-form recognition. Neither view replaces or
derives from the other.

New unified-Profile comparison Runs are disabled in code. Historical 3.7B
artifacts remain resumable for audit only.

## 2. Independent pipeline contracts

### Domain path

```text
2 x 24 Profile rows
-> LocalTopLevelDiscoveryOutput
-> CompactCandidateTable
-> TopLevelDomainDraft
```

Domain Consolidation receives only normalized Domain candidates. It does not
receive Content Type candidates or results.

### Content Type path

```text
2 x 24 Compact Form View rows
-> ContentTypeDiscoveryOutputV1
-> CompactContentTypeTable
-> ContentTypeDraftV1
```

Content Type Consolidation receives only normalized Content Type candidates. It
cannot output Domains, Topics, Entities, or a Domain tree.

Both local paths use database-backed batch stages. A failed second batch can be
resumed without repeating the first batch or the other path. Raw responses are
persisted before validation, and JSON Repair remains isolated.

The final `DualViewDiscoveryOutputV1` references both final Drafts in separate
fields and records both input-view versions. Strict Schemas reject a Domain in
the Content Type Draft or a Content Type inside the Domain Draft.

## 3. Frozen regression input

- Snapshot: #2
- Snapshot Hash: `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2`
- Eligible selection: the same frozen 48 cards used by Checkpoints 3.5–3.7
- Evidence distribution: A 22, B 9, C 17
- Seed: 73
- Batch size: 24
- Model: `deepseek-v4-pro`
- Domain local thinking: off
- Content Type local and global thinking: off
- Domain global thinking: high
- Search, Silver Reference, Trial Assignment, and 128-item backfill: disabled

## 4. Stage usage

| Stage | Batches | Prompt | Completion | Reasoning | Total | Seconds | Repair |
|---|---:|---:|---:|---:|---:|---:|---:|
| Domain Local Discovery | 2 | 4,031 | 1,531 | 0 | 5,562 | 23.561 | 0 |
| Content Type Local Discovery | 2 | 7,573 | 1,175 | 0 | 8,748 | 19.452 | 0 |
| Content Type Consolidation | 1 | 1,418 | 1,630 | 0 | 3,048 | 18.378 | 0 |
| Domain Consolidation | 1 | 1,605 | 4,587 | 3,265 | 6,192 | 65.760 | 0 |
| **Total** |  | **14,627** | **8,923** | **3,265** | **23,550** | **127.151** | **0** |

Reasoning Tokens are contained within completion Tokens and are not added
twice. Provider monetary cost was not returned, so cost remains `unknown`.
End-to-end wall time was approximately 128 seconds.

The Content Type path used 11,796 Tokens, below the existing 20,000-Token
Content-Type-plus-Consolidation budget. The complete Run remained below the
45,000-Token per-Run gate.

## 5. Structural result

- Local Domain candidates: 16;
- Local Content Type candidates: 16;
- Final Domains: 8;
- Final Content Types: 8;
- C-level Domain/Topic supporting signal: 8 of 17;
- C-level Content Type support: 15 of 17;
- C-level Content Type ambiguous: 3 of 17;
- invalid supporting IDs: 0;
- Entity Leakage: 0;
- Content Type Leakage into Domain: 0;
- blocking Quality issues: 0;
- Repair: 0;
- request retry: 0.

There was one non-blocking `renamed_domain_without_lexical_match` warning. It
records a semantic rename during Domain Consolidation and does not indicate a
facet leak or invalid structure. No local Validator call was needed.

The integrated artifact declares `classification_profile_v1` as the Domain
view and `compact_form_view_v1` as the Content Type view. The Domain Draft has
no `content_types` field, and the Content Type Draft has no `domains` field.

## 6. Recovery verification

A synthetic interruption in Content Type batch 2 verified that resume:

- does not repeat either completed Domain batch;
- does not repeat Content Type batch 1;
- retries only Content Type batch 2;
- then continues through Content Type normalization and Consolidation.

On the real completed Run, `resume` returned immediately. All ten persisted
stage attempt counts remained one.

## 7. Acceptance decision and next boundary

The 48-card dual-view integration regression passes. It corrects the Content
Type evidence loss observed in Checkpoint 3.7B while preserving the Profile
Domain path and strict facet isolation.

This result makes the dual-view protocol eligible for the next explicitly
approved step: formal 128-card Discovery A/B, with C conditional on A/B
stability. It does not itself start those Runs, generate 128 Profiles, perform
Trial Assignment, or modify production video data.
