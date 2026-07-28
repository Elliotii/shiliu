# Primary Reviewer Draft Contract v1

Independently annotate exactly one supplied synthetic preflight Packet. Read the complete Raw Subtitle/Raw ASR segment sequence. The Packet is the only evidence authority. Do not use tools, network information, outside knowledge, titles, summaries, search results, candidate windows, Safe Projection, mining notes, system predictions, Gold, Agreement, other reviewer outputs, Review, or Adjudication assets.

Return only one JSON object matching `reviewer_draft.v1.schema.json`.

The Draft is index-based:

- `required_aspects` is zero-indexed in array order.
- `required_spans` is zero-indexed in array order.
- All aspect and span references must use those integer indices and remain in range.
- `segment_ids` must be copied only from the supplied Packet.
- Never create, copy, or output formal IDs such as `A1`, `S1`, or `G1`.
- Never output quotes, timestamps, video/source identities, source versions, or timeline runs. Local deterministic code reconstructs them.

Define required aspects before judging support. Evidence groups are alternatives (OR); required spans inside one group are complementary (AND). Every group must contain at least one required span. Optional context does not count toward sufficiency. Use `sufficient` only when every required aspect is supported by at least one complete evidence route; `partial` only when supported and missing aspects are both non-empty; `insufficient` when readable Raw Source gives no material support; and `unverifiable` only when source authority or integrity prevents judgment.

Read all segments before returning the Draft. The local compiler, rather than the model, records full-transcript review and reconstructs the Packet's first and last segment IDs.
