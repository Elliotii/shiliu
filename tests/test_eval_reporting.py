from pathlib import Path
import pytest

from shiliu.eval.reporting import assert_no_closeout, validate_formal_result_payload


def test_reporting_keeps_gold_layers_policies_and_negative_controls_separate():
    policies = {p: {"discovery": {}, "evidence": {}} for p in ("condensed_judged", "conservative_lower_bound", "discovery_upper_bound")}
    payload = {"aggregate_metrics": {"policies": {m: policies for m in ("lexical", "dense", "hybrid", "auto")}, "negative_controls": {m: {"Q14": {}, "Q18": {}} for m in ("lexical", "dense", "hybrid", "auto")}}}
    validate_formal_result_payload(payload)


def test_reporting_forbids_v3_closeout():
    with pytest.raises(ValueError):
        assert_no_closeout([Path("V3_CLOSEOUT.md")])
