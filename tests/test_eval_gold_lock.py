import pytest

from shiliu.eval.gold_lock import amendment_changes, assert_positive_coverage, move_to_out_of_scope


def test_amendment_scope_accepts_only_allowed_u_transitions():
    original = {("Q02", 3): "U_title", ("Q01", 1): "N"}
    amended = {("Q02", 3): "R_evidence", ("Q01", 1): "N"}
    assert amendment_changes(original, amended, {("Q02", 3)})[0]["final"] == "R_evidence"
    with pytest.raises(ValueError):
        amendment_changes(original, {("Q02", 3): "N", ("Q01", 1): "R_evidence"}, {("Q02", 3)})


def test_eligibility_migration_preserves_prior_label():
    value = move_to_out_of_scope(query_id="Q01", video_id=7, prior_label="R_evidence", failures=["archived"])
    assert value["prior_human_semantic_label"] == "R_evidence"
    assert value["eligibility_source"] == "snapshot"


def test_positive_query_without_relevant_is_blocked():
    with pytest.raises(ValueError):
        assert_positive_coverage([{"query_id": "Q01", "negative_control": False, "video_discovery_relevant_ids": [], "evidence_retrieval_relevant_ids": []}])

