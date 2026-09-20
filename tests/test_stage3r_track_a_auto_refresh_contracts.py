from shiliu.eval_v3_5.stage3r_track_a_auto_refresh import build_omitted_mode_request, classify_failure


def test_track_a_auto_refresh_omits_mode_field():
    payload, request = build_omitted_mode_request("original query")
    assert "mode" not in payload and request.default_applied and request.mode == "auto"


def test_track_a_auto_refresh_separates_failure_attribution():
    assert classify_failure(target_hit=False, complete_group=False, bundle_hit=False) == "retrieval_failure"
    assert classify_failure(target_hit=True, complete_group=False, bundle_hit=False) == "candidate_builder_failure"
    assert classify_failure(target_hit=True, complete_group=True, bundle_hit=False) == "deterministic_selector_failure"
    assert classify_failure(target_hit=True, complete_group=True, bundle_hit=True) == "end_to_end_bundle_hit"
