# Stage 4B Existing Contract Reuse Audit

- Reused Request: `v3.5-sufficiency-request-v1` (`SufficiencyRequest`).
- Reused Decision: `v3.5-sufficiency-decision-v1` (`SufficiencyDecision`).
- Reused statuses: `sufficient`, `partial`, `insufficient`, `unverifiable`.
- Reused EvidenceBundle: `v3.5-evidence-bundle-v1`.
- Additive compatibility patch: query language, embedded runtime bundle, gate status,
  policy version, plural semantic reason codes, and the Track C enum member.
- No field was renamed; no status or EvidenceBundle semantics changed.
- Patch SHA-256: `5b399dbf2dbd1ba0340a3d738218517738921342f38ce6e410be04bf64095a84`.
- Formal builder/selector/gate: `stage3b-acronym-w3.5-v1`,
  `v3.5-deterministic-fine-selector-v1`, `mechanical-gate-v1-r1`.
- Frozen Evaluation accessed: `false`.
