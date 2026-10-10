from __future__ import annotations

from hashlib import sha256
import inspect
import json
from pathlib import Path

from shiliu.eval_v3_5 import frozen_auto_smoke as smoke


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_auto_smoke_reuses_phase_a_case_set() -> None:
    frozen = smoke.load_frozen_inputs(ROOT)
    assert len(frozen["cases"]) == 10
    assert {row["case_id"] for row in frozen["decisions"]} == set(frozen["cases"])


def test_frozen_auto_smoke_reuses_approved_q1_q2() -> None:
    frozen = smoke.load_frozen_inputs(ROOT)
    assert len(frozen["decisions"]) == 10
    assert sum(len(row["q2_retrieval_intents"]) for row in frozen["decisions"]) == 29


def test_frozen_auto_smoke_validates_approved_query_hash() -> None:
    frozen = smoke.load_frozen_inputs(ROOT)
    assert frozen["approved_query_sha256"] == smoke.APPROVED_QUERY_SHA256


def test_frozen_auto_smoke_does_not_modify_queries() -> None:
    frozen = smoke.load_frozen_inputs(ROOT)
    for decision in frozen["decisions"]:
        control = frozen["controls"][decision["case_id"]]["lexical"]
        assert control["q1"]["query"] == decision["q1_discovery_query"]
        assert control["q2"]["intents"] == decision["q2_retrieval_intents"]


def test_frozen_auto_smoke_reuses_phase_b_r_lexical_controls() -> None:
    frozen = smoke.load_frozen_inputs(ROOT)
    assert all(row["lexical"]["source"] == "reused_phase_b" for row in frozen["controls"].values())


def test_frozen_auto_smoke_reuses_phase_b_r_hybrid_controls() -> None:
    frozen = smoke.load_frozen_inputs(ROOT)
    assert all(
        row["hybrid"]["q0"]["requested_mode"] == "hybrid"
        for row in frozen["controls"].values()
    )


def test_frozen_auto_smoke_does_not_rerun_frozen_controls() -> None:
    source = inspect.getsource(smoke.run_frozen_auto_smoke)
    assert '"mode": "lexical"' not in source
    assert '"mode": "hybrid"' not in source


def test_frozen_auto_smoke_selects_exact_entities_from_frozen_assets() -> None:
    selected = smoke.select_exact_entities(ROOT)
    assert [row["source_case_or_fixture_id"] for row in selected] == [
        "Q01",
        "Q02",
        "Q20",
    ]
    assert all(row["expected_auto_branch"] == "lexical" for row in selected)


def test_frozen_auto_smoke_freezes_exact_entity_selection_before_execution() -> None:
    source = inspect.getsource(smoke.run_frozen_auto_smoke)
    assert source.index("exact_entity_selection_manifest.json") < source.index(
        "TemporaryDirectory"
    )


def test_frozen_auto_smoke_does_not_create_new_gold() -> None:
    selected = smoke.select_exact_entities(ROOT)
    assert all(row["gold_source_artifact"] == str(smoke.FORMAL_GOLD_RELATIVE) for row in selected)


def test_frozen_auto_smoke_reports_exact_entity_regression() -> None:
    source = inspect.getsource(smoke._write_execution)
    assert "auto_vs_lexical_regression" in source


def test_frozen_auto_smoke_uses_canonical_video_identity() -> None:
    frozen = smoke.load_frozen_inputs(ROOT)
    assert all(
        row["runtime_canonical_video_identity"]["product_video_id"]
        for row in frozen["identities"].values()
    )


def test_frozen_auto_smoke_excludes_insufficient_from_main_recall() -> None:
    rows = [
        {"label_role": "evidence_bearing", "q0": {"target_video_hit": True}},
        {"label_role": "insufficient_diagnostic", "q0": {"target_video_hit": False}},
    ]
    result = smoke._recall(rows, "q0")
    assert result["numerator"] == 1 and result["denominator"] == 9


def test_frozen_auto_smoke_reports_insufficient_separately() -> None:
    source = inspect.getsource(smoke.run_frozen_auto_smoke)
    assert "analysis/insufficient_diagnostic.json" in source
    assert smoke.INSUFFICIENT_CASE_ID == "C2C_ee3fac675fc7d408"


def test_frozen_auto_smoke_does_not_modify_router() -> None:
    identity = smoke.auto_runtime_identity(ROOT)
    assert identity["auto_router_version"] == smoke.ROUTER_VERSION
    assert identity["router_rules_modified"] is False


def test_frozen_auto_smoke_does_not_modify_retrieval_config() -> None:
    identity = smoke.auto_runtime_identity(ROOT)
    assert identity["retrieval_configuration_modified"] is False
    assert identity["top_k"] == 10 and identity["raw_top_k"] == 50


def test_frozen_auto_smoke_does_not_rebuild_index() -> None:
    source = inspect.getsource(smoke.run_frozen_auto_smoke)
    assert "index_rebuilt" in source
    assert ".build(" not in source and "rebuild(" not in source


def test_frozen_auto_smoke_records_the_historical_lexical_product_default() -> None:
    product = json.loads(
        (ROOT / "research/v3_5/auto_smoke/runtime_preflight/product_default.before.json")
        .read_text(encoding="utf-8")
    )
    assert product["frontend_default_mode"] == "lexical"
    assert product["backend_default_mode"] == "lexical"


def test_frozen_auto_smoke_does_not_call_candidate_builder() -> None:
    assert smoke.q2_union([])["candidate_builder_called"] is False


def test_frozen_auto_smoke_does_not_call_selector() -> None:
    assert smoke.q2_union([])["selector_called"] is False


def test_frozen_auto_smoke_does_not_access_heldout() -> None:
    selected = smoke.select_exact_entities(ROOT)
    assert all(row["source_case_or_fixture_id"] in {"Q01", "Q02", "Q20"} for row in selected)


def test_frozen_auto_smoke_does_not_call_external_llm() -> None:
    source = inspect.getsource(smoke.run_frozen_auto_smoke)
    assert "openai" not in source.lower()


def test_frozen_auto_smoke_input_query_hashes_are_byte_based() -> None:
    frozen = smoke.load_frozen_inputs(ROOT)
    row = frozen["decisions"][0]
    assert len(sha256(row["q1_discovery_query"].encode()).hexdigest()) == 64
