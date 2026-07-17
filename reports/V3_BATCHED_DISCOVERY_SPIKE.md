# V3 Batched Discovery Spike

Date: 2026-07-17
Snapshot: #2
Snapshot Hash: `<private-snapshot-hash>`

## Silver giant-call baseline

- Frozen successfully as Silver Reference v1.
- Wall time: about 21m23s.
- 9 logical calls, 10 actual requests; one 20-item label batch was replayed after a coverage validation failure.
- Initial taxonomy prompt reconstructed from the frozen Snapshot and prompt version: 89,640 characters / 164,877 UTF-8 bytes.
- Provider usage was not captured by the old provider path, so actual baseline tokens and cost are unknown and must not be invented.
- Result: 8 Content Types, 6 top-level Domains, 17 Subdomains; 40 Silver Eval rows and 25 adjudicated A/B disagreements.

## Compact view

Version: `compact-discovery-view-v1`

- A/B: short ID, evidence, title, conclusion, at most 3 deduplicated key points, at most 5 entities.
- C: short ID, evidence, title, description capped at 300 characters.
- D: short ID, evidence and title; excluded from Discovery and included in Trial Assignment.
- Uploader, folder context and user behavior fields are absent.
- IDs use a reversible `C001` mapping saved beside the run outputs.
- A full 128-card eligible corpus would produce six 24-item local prompts totaling 44,624 characters; the largest reconstructed batch is 9,598 characters.

## Spike 1: discovery plus assignment

Run: `discovery-spike-s2-20260717T102619Z`
Scope: 48 eligible cards, two 24-item local batches, plus all three D cards in Trial Assignment.

### Performance

- Wall time recorded by calls: 221.563s (about 3m42s).
- 6 logical calls and 1 JSON Repair request.
- Actual usage: 32,821 prompt tokens + 17,984 completion/reasoning tokens = 50,805 total tokens.
- Local batch 1: 8,366 characters, 3,967 prompt tokens, 28.423s.
- Local batch 2: 7,220 characters, 3,654 prompt tokens, 20.222s.
- Consolidation: 9,295 characters, 3,344 prompt tokens, 7,296 completion tokens, 102.345s.
- Assignment: three batches, 15,653 prompt tokens and 4,122 completion tokens in total, 39.53s.

### Recovery evidence

- Every request had an audit and prompt on disk before the HTTP call.
- Raw model content was saved before parsing.
- Consolidation returned structurally invalid Topic/Entity IDs. The original raw response and validation error were saved.
- JSON Repair received the raw response, validation error and compact schema only; the 48 original cards were not replayed.
- Repair completed in 31.043s. This validates repair isolation, although the initial validation error was too verbose and was capped in the subsequent implementation.

### Result

- 5 Content Types, 5 top-level Domains, no Subdomains.
- 51 assignments: 39 high, 5 medium, 7 low.
- 44 cards received a primary Domain; 7 were rejected as `insufficient_evidence`.
- All three D cards were correctly rejected. The other four rejected cards were C evidence.
- Novelty Pool contained those seven low-confidence/rejected cards.

The result is operationally valid but too coarse to accept as the final Taxonomy.

## Spike 2: hierarchy signal only

Run: `discovery-spike-s2-20260717T103209Z`
Scope: same 48 eligible cards, Assignment skipped.

Changes:

- local Domain candidates gained `suggested_level` and `parent_hint`;
- Topic/Entity ID rules were clarified;
- validation error supplied to Repair was capped;
- usage aggregation counts Repair as a separate request.

Results:

- 3 requests, no Repair.
- 139.046s.
- 11,709 prompt tokens + 10,165 completion/reasoning tokens = 21,874 total tokens.
- 9 top-level Domains and no Subdomains.
- The local batches still proposed only primary Domains; the consolidator correctly refused to invent unsupported children.
- No Content Type candidates were produced in this run.

This shows that a 48-card sample is inadequate for evaluating final hierarchy depth. It also shows that hierarchy and Content Type candidate recall need an explicit quality check before a formal full run.

## Parameter decision

Accepted for the next full-corpus experimental run:

- local batch size: 24;
- full 128 eligible cards, not a 48-card sample;
- local Discovery, Facet and Assignment: no thinking / no high effort;
- global Consolidation, hierarchy validation and revision: high thinking;
- Assignment batch size: 24;
- D cards: Trial Assignment only;
- raw-first audit and isolated JSON Repair;
- Repair validation-error excerpt capped at 3,500 characters;
- short-ID row protocol and reversible mapping.

Not yet accepted as production behavior:

- the generated 48-card Taxonomy structure;
- automatic publication;
- a claim that batching improves classification quality;
- formal process resume. The Spike persists independent batch artifacts, but the production `run/resume` state machine still needs to skip already completed batches after process exit.

Before the first full Discovery A/B/C, add a semantic acceptance check that rejects a Draft when Content Type candidates are missing or all Domain nodes remain at one level despite sufficient repeated local support. The check must report a quality failure; it must not silently invent nodes or loop indefinitely.
