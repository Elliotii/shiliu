from __future__ import annotations


# Real query/video pairs selected only from the frozen V3 judgment/pool assets.
PRIMARY_SELECTIONS = (
    ("CASE_001", "Q01", 78, "likely_evidence_positive", "v3_approved_interval"),
    ("CASE_002", "Q03", 40, "likely_evidence_positive", "v3_approved_interval"),
    ("CASE_003", "Q06", 83, "possible_partial", "v3_approved_interval"),
    ("CASE_004", "Q02", 3, "likely_evidence_positive", "v3_relevant_evidence"),
    ("CASE_005", "Q16", 51, "possible_partial", "v3_relevant_evidence"),
    ("CASE_006", "Q23", 37, "semantic_neighbor_negative", "v3_pooled_candidate"),
    ("CASE_007", "Q08", 30, "possible_partial", "v3_approved_interval"),
    ("CASE_008", "Q11", 58, "possible_partial", "v3_relevant_evidence"),
    ("CASE_009", "Q12", 136, "possible_partial", "v3_relevant_evidence"),
    ("CASE_010", "Q13", 50, "possible_partial", "v3_relevant_evidence"),
    ("CASE_011", "Q09", 43, "likely_evidence_positive", "v3_relevant_evidence"),
    ("CASE_012", "Q01", 88, "multi_timeline_robustness", "stage1_multi_timeline"),
    ("CASE_013", "Q03", 38, "semantic_neighbor_negative", "v3_judged_negative"),
    ("CASE_014", "Q08", 135, "semantic_neighbor_negative", "v3_judged_negative"),
    ("CASE_015", "Q07", 137, "title_only_source_state", "v3_title_only"),
    ("CASE_016", "Q09", 49, "title_only_source_state", "v3_title_only"),
    ("CASE_017", "Q14", None, "negative_control", "v3_negative_control"),
    ("CASE_018", "Q18", None, "negative_control", "v3_negative_control"),
    ("CASE_019", "Q17", 117, "likely_evidence_positive", "v3_approved_interval"),
    ("CASE_020", "Q05", 68, "likely_evidence_positive", "v3_relevant_evidence"),
)

RESERVE_SELECTIONS = (
    ("RESERVE_001", "Q15", 78, "likely_evidence_positive", "v3_approved_interval"),
    ("RESERVE_002", "Q24", 125, "title_only_source_state", "v3_title_only"),
    ("RESERVE_003", "Q04", 117, "likely_evidence_positive", "v3_approved_interval"),
    ("RESERVE_004", "Q07", 44, "possible_partial", "v3_missing_content_judgment"),
    ("RESERVE_005", "Q10", 135, "likely_evidence_positive", "v3_approved_interval"),
    ("RESERVE_006", "Q20", 34, "likely_evidence_positive", "v3_relevant_evidence"),
)


def rationale(stratum: str) -> str:
    values = {
        "likely_evidence_positive": "Sampling hypothesis: exercise full-transcript evidence-group review; not a Gold label.",
        "possible_partial": "Sampling hypothesis: inspect multi-aspect or distributed support; not a Sufficiency label.",
        "semantic_neighbor_negative": "Sampling hypothesis: distinguish readable neighboring content from useful support.",
        "title_only_source_state": "Exercise title-only/no-body human authority without inventing transcript evidence.",
        "negative_control": "Corpus-level negative control requiring a human decision about any approvable target.",
        "multi_timeline_robustness": "Development-only robustness review for run-local evidence and cross-run fail-closed behavior.",
    }
    return values[stratum]
