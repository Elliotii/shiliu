# Eval v2 Functional Examples

All examples are synthetic and are not formal cases or Gold.

- Single-span sufficient: one required aspect A1, one group G1, one required span S1.
- Multi-span sufficient / AND: G1 requires S1 and S2; omission of either fails even if the remaining span is short and relevant.
- Multi-group OR: G1=[S1,S2], G2=[S3]; either complete path supports all aspects.
- Genuine partial: A1 is materially supported and A2 is absent in readable Raw Source.
- Semantic-neighbor insufficient: readable source shares terminology but supports no required aspect.
- Source-unavailable unverifiable: source availability is `missing`; no empty transcript is fabricated.
- Optional context: C1 may widen interpretation but is never counted as required support.
- Conflict: a conflict-role span is shown to adjudication and triggers human review.
- Wider prediction: a window containing the entire necessary source region can overlap Gold and succeed without exact segment equality; missing a necessary complementary span fails.

Validation fixtures also cover identical labels with divergent aspects/regions, invalid segment IDs, cross-run references, input-hash mismatch, one successful repair, failure after repair, deterministic 20% selection, leakage conflict, secret redaction, and all three allowed projections.

