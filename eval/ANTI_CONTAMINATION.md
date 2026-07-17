# V3 Anti-Contamination Contract

The open-discovery runtime may read only frozen Discovery Views and runtime-owned
outputs. It must not read, import, serialize, or receive:

- Silver Reference files or labels;
- historical human category names or proportions;
- prior evaluation reports;
- folder names, source identifiers, or membership metadata;
- reading state, Mark, archive, ignore, or user notes.

The Silver generation side may read only the frozen Snapshot and its Discovery
Views. It must not read Discovery A/B/C, consolidation, drafts, assignments,
diagnostics, prior taxonomy reports, or historical human category discussions.
Production runtime code must never import from or open files under `eval/`.

Before the first full-corpus real Discovery run, Eval must freeze a Silver
Reference created by independent initial-label, review, and disagreement-
adjudication calls. Freezing is append-only by version and a manifest records
the SHA-256 of every artifact. Runtime orchestration may require only an opaque
freeze receipt recorded outside the Discovery prompt; it must not inspect the
private Silver content.

Silver Agreement is not accuracy and Silver Reference is not Ground Truth.
Human satisfaction and Human Modification Rate are reported as
`not_evaluated` until a later human study exists.

Search results are untrusted evidence. Search may explain what an entity is,
but neither retrieved text nor a search query may recommend, create, rename, or
move a taxonomy node.
