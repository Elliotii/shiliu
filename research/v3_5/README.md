# V3.5 Stage 2A Human Review Assets

These files are candidate review materials, not Gold and not a Development/Held-out split.

- `active_review_calibration.jsonl`: the only active Round 1 workload, six cases in authorized order.
- `review_decisions.calibration.template.jsonl`: six blank calibration decisions.
- `HUMAN_REVIEW_CALIBRATION_GUIDE.md`: compact human workflow.
- `master_case_candidates.jsonl`: 20 primary sampling candidates; not all are active at once.
- `master_case_reserves.jsonl`: 8 inactive reserve candidates. RESERVE_007/008 are real frozen `U_title` + `no_supported_subtitle` follow-up candidates, not final labels.
- `review_packets/`: one human packet per candidate, with full Raw Transcript whenever authority exists.
- `review_decisions.template.jsonl`: the unchanged original 26-record blank template; it is not the active Round 1 workload.
- `review_packet_manifest.json`: packet hashes and transcript counts.
- `preliminary_leakage_report.json`: preliminary duplicate/leakage keys only.

## Review Workflow and Workload

1. Round 1: six-case Label Calibration.
2. Round 2: remaining necessary Primary cases after calibration.
3. Round 3: targeted Reserve activation only when required.

Reserve candidates are inactive by default. Activation is permitted only when a Primary is unusable/ambiguous, class or source coverage becomes insufficient, leakage invalidates a Primary, or additional unverifiable coverage is required. It must record `activation_reason`, `replaced_or_supplemented_case`, `activated_at`, and `authorized_by`. No Reserve is active now.

Workload classes are Quick authority confirmation, Seed-assisted evidence verification, Focused semantic review, Deep multi-aspect review, and Robustness review. **Full Transcript Accessible ≠ Full Transcript Linearly Read From Start to End.** Start from navigation aids, inspect context and alternative relevant locations, and consult the complete transcript whenever needed.

Every navigation section is labeled **Navigation Aid Only — Not Annotation Boundary**. V3 intervals, hits, windows, ranks, titles, and summaries never define the annotation boundary.

## Coverage Boundary

English-source coverage is one readable semantic-neighbor candidate. English-source positive evidence is not established. Cross-language evidence resolution is not evaluated because the frozen pool contains only one distinct English-source pooled query-video pair and it is not a cross-language positive case.
