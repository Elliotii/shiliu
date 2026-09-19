import pytest

from shiliu.eval.metrics import anchor_error, apply_unjudged_policy, duplicate_occupancy, grouping_gain, interval_overlap, oracle_mode, ranking_metrics


def test_ranking_recall_mrr_and_hit():
    assert ranking_metrics([9, 2, 3], {2, 4}) == {"recall": 0.5, "mrr": 0.5, "hit": 1.0}


def test_three_unjudged_policies():
    assert apply_unjudged_policy([8, 2], {2}, {8}, "condensed_judged") == ([2], {2})
    assert apply_unjudged_policy([8, 2], {2}, {8}, "conservative_lower_bound") == ([8, 2], {2})
    assert apply_unjudged_policy([8, 2], {2}, {8}, "discovery_upper_bound") == ([8, 2], {2, 8})


def test_product_window_duplicate_grouping_and_anchor_metrics():
    occupancy = duplicate_occupancy([1, 1, 2])
    assert occupancy["duplicate_count"] == 1
    assert occupancy["duplicate_rate"] == pytest.approx(1 / 3)
    assert grouping_gain([1, 2], [1, 1], {1, 2}) == 1
    assert interval_overlap((1, 5), (4, 6)) == 1
    assert anchor_error(2, (4, 6)) == 2


def test_auto_oracle_uses_fixed_lexical_dense_hybrid_tie_break():
    assert oracle_mode({"lexical": (1, 1), "dense": (1, 1), "hybrid": (1, 1)}) == "lexical"
    assert oracle_mode({"lexical": (0, 0), "dense": (1, 1), "hybrid": (1, 1)}) == "dense"
