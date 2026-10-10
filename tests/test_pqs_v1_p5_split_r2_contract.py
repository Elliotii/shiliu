from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research/v3_5/product_query_set_v1"
P3 = BASE / "user_validation"
P4 = BASE / "freeze"
OUT = BASE / "split_v1"
FROZEN = OUT / "frozen_locked"
LEDGER_SOURCE = Path("/Users/elliot/Downloads/V3_5_PQS_V1_P5_SPLIT_DECISION_LEDGER_R2.json")
LEDGER_COPY = OUT / "PQS_V1_P5_SPLIT_DECISION_LEDGER_R2.json"
EXPECTED_LEDGER_SHA = "af33dee545a577b1f467f9092396ec74ddfbe4d965f1ab0855b62a99b62b184c"
EXPECTED_P4_CANONICAL_SHA = "fadf21c1992d848f2904192af479f6720a059c9aeb772ccfc4cee3b220942825"
EXPECTED_P4_LOCKED_SHA = "35d33dcf4dd77f12cad4e0c118f2c2f2e371a3019320906a3d2134bb933dd59c"
EXPECTED_P3_P4_HASHES = {
    "user_validation/PQS_V1_USER_VALIDATION_REPORT.md": "823dbfcfb931d5bc8771a2ce598881e1840b7150931ac4a327970728dec849d5",
    "user_validation/pqs_v1_user_validation.audit.json": "0acb8f6b88e5d60579dc03b0808862deff6fccd9611dcaaae79fa12b4622b58e",
    "user_validation/pqs_v1_user_validation.manifest.json": "a2de9d806f911a80d0b921827fcde53e5614e43afc13daca85e9dda6ddbb6587",
    "user_validation/product_query_candidate_pool.after_user_revision.jsonl": "a0f7748b8dc2eb71d9204e3042558ae615db9d908e693970f4a6654c28afb667",
    "user_validation/product_query_user_validation.completed.jsonl": "b66bdd7ae2dd778a629f266aa867330db172f9d63c972768d734ddee6f6f911d",
    "freeze/PRODUCT_QUERY_SET_V1_FREEZE_REPORT.md": "1c60574b1a84afb1160b66a8423dfa37640b88c7a56a63b0166864ab2a4b342b",
    "freeze/product_query_set_v1.file_hash_manifest.jsonl": "27a8c052f3697b19a8ffe49a8e87a9715a6d7c9ed86cccfa8ac89e93da4a5bf5",
    "freeze/product_query_set_v1.freeze_execution_decision.json": "2e22eb39013ecaa83fa0378ba3b48e80c5e42674620b9735ea0e471ab9cf285e",
    "freeze/product_query_set_v1.lock.audit.json": "95f00c022a9cf2afb0bd7e189798c8ef5e3b8b2575ec51a78edb246c703075bd",
    "freeze/product_query_set_v1.locked.jsonl": EXPECTED_P4_LOCKED_SHA,
    "freeze/product_query_set_v1.manifest.json": "eb1a30ae0b1643c246a9c2c5a1b9ae1113748a3227fa2e10b77a1c1f2d9402eb",
}
ADDED_FIELDS = {
    "split_version",
    "split_assignment",
    "split_decision_authority",
    "split_decision_ledger_sha256",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def ledger() -> dict:
    return json.loads(LEDGER_COPY.read_text(encoding="utf-8"))


def locked_split() -> dict:
    return json.loads((OUT / "product_query_split_v1.locked.json").read_text(encoding="utf-8"))


def p4_rows() -> list[dict]:
    return jsonl(P4 / "product_query_set_v1.locked.jsonl")


def development_rows() -> list[dict]:
    return jsonl(OUT / "product_query_development_v1.locked.jsonl")


def frozen_rows() -> list[dict]:
    return jsonl(FROZEN / "product_query_frozen_evaluation_v1.locked.jsonl")


def canonical_assignment(rows: list[dict]) -> bytes:
    projection = [
        {
            "query_id": row["query_id"],
            "split_version": row["split_version"],
            "split_assignment": row["split_assignment"],
            "leakage_group": row["leakage_group"],
        }
        for row in rows
    ]
    return json.dumps(
        sorted(projection, key=lambda row: row["query_id"]),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_r2_decision_ledger_hash_matches() -> None:
    assert sha256(LEDGER_SOURCE) == EXPECTED_LEDGER_SHA
    assert sha256(LEDGER_COPY) == EXPECTED_LEDGER_SHA
    assert LEDGER_COPY.read_bytes() == LEDGER_SOURCE.read_bytes()


def test_old_10_14_package_is_not_authoritative() -> None:
    data = ledger()
    assert data["authority_status"] == "authoritative"
    assert data["supersession"]["previous_package_must_not_be_executed"] is True
    assert data["supersession"]["superseded_decision"] == "10 Development / 14 Frozen Evaluation"
    assert data["split_policy"]["development_count"] == 14
    assert data["split_policy"]["frozen_evaluation_count"] == 10
    assert locked_split()["development"]["count"] == 14
    assert locked_split()["frozen_evaluation"]["count"] == 10


def test_p4_locked_query_set_hashes_match() -> None:
    manifest = json.loads((P4 / "product_query_set_v1.manifest.json").read_text())
    rows = p4_rows()
    canonical = json.dumps(
        sorted(rows, key=lambda row: row["query_id"]),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_P4_CANONICAL_SHA
    assert manifest["canonical_content_sha256"] == EXPECTED_P4_CANONICAL_SHA
    assert sha256(P4 / "product_query_set_v1.locked.jsonl") == EXPECTED_P4_LOCKED_SHA
    assert manifest["locked_jsonl_sha256"] == EXPECTED_P4_LOCKED_SHA


def test_locked_query_count_is_24() -> None:
    assert len(p4_rows()) == len(locked_split()["assignments"]) == 24


def test_all_queries_assigned_exactly_once() -> None:
    ids = [row["query_id"] for row in development_rows() + frozen_rows()]
    assert len(ids) == len(set(ids)) == 24


def test_development_count_is_14() -> None:
    assert len(development_rows()) == locked_split()["development"]["count"] == 14


def test_frozen_evaluation_count_is_10() -> None:
    assert len(frozen_rows()) == locked_split()["frozen_evaluation"]["count"] == 10


def test_no_overlap_or_missing_query() -> None:
    p4_ids = {row["query_id"] for row in p4_rows()}
    development_ids = {row["query_id"] for row in development_rows()}
    frozen_ids = {row["query_id"] for row in frozen_rows()}
    assert development_ids.isdisjoint(frozen_ids)
    assert development_ids | frozen_ids == p4_ids


def test_assignments_match_r2_ledger() -> None:
    actual = {
        row["query_id"]: row["split_assignment"]
        for row in development_rows() + frozen_rows()
    }
    expected = {
        row["query_id"]: row["split_assignment"]
        for row in ledger()["split_records"]
    }
    assert actual == expected
    assert [row["query_id"] for row in development_rows()] == ledger()["development_query_ids"]
    assert [row["query_id"] for row in frozen_rows()] == ledger()["frozen_evaluation_query_ids"]


def test_leakage_groups_do_not_cross_splits() -> None:
    groups: dict[str, set[str]] = defaultdict(set)
    for row in development_rows() + frozen_rows():
        groups[row["leakage_group"]].add(row["split_assignment"])
    assert all(len(assignments) == 1 for assignments in groups.values())
    audit = json.loads((OUT / "product_query_split_v1.audit.json").read_text())
    assert audit["assignment"]["leakage_groups_crossing_splits"] == 0


def test_query_text_and_frozen_metadata_unchanged() -> None:
    p4 = {row["query_id"]: row for row in p4_rows()}
    for row in development_rows() + frozen_rows():
        assert {key: value for key, value in row.items() if key not in ADDED_FIELDS} == p4[row["query_id"]]
        assert set(row) == set(p4[row["query_id"]]) | ADDED_FIELDS


def test_development_records_match_p4_locked_records() -> None:
    p4 = {row["query_id"]: row for row in p4_rows()}
    assert all({key: value for key, value in row.items() if key not in ADDED_FIELDS} == p4[row["query_id"]] for row in development_rows())
    assert all(row["split_assignment"] == "development" for row in development_rows())


def test_frozen_records_match_p4_locked_records() -> None:
    p4 = {row["query_id"]: row for row in p4_rows()}
    assert all({key: value for key, value in row.items() if key not in ADDED_FIELDS} == p4[row["query_id"]] for row in frozen_rows())
    assert all(row["split_assignment"] == "frozen_evaluation" for row in frozen_rows())


def test_family_topic_scope_complexity_distributions_recorded() -> None:
    manifest = json.loads((OUT / "product_query_split_v1.manifest.json").read_text())
    balance = ledger()["balance_summary"]
    for split_name in ("development", "frozen_evaluation"):
        actual = manifest["distributions"][split_name]
        expected = balance[split_name]
        assert actual["query_family"] == expected["query_family"]
        assert actual["topic_cluster"] == expected["topic_cluster"]
        assert actual["single_or_multi_video"] == expected["single_or_multi_video"]
        assert actual["complexity"] == expected["complexity"]


def test_language_and_authoring_origin_distributions_recorded() -> None:
    manifest = json.loads((OUT / "product_query_split_v1.manifest.json").read_text())
    balance = ledger()["balance_summary"]
    for split_name in ("development", "frozen_evaluation"):
        assert manifest["distributions"][split_name]["query_language"] == balance[split_name]["query_language"]
        assert manifest["distributions"][split_name]["authoring_origin"] == balance[split_name]["authoring_origin"]


def test_no_library_gap_or_label_quota_preassigned() -> None:
    manifest = json.loads((OUT / "product_query_split_v1.manifest.json").read_text())
    assert manifest["library_gap_risk"] == {"preassigned_labels": False, "quota_used": False}
    assert ledger()["split_policy"]["library_gap_labels_preassigned"] is False
    assert ledger()["balance_summary"]["explicit_no_answer_or_library_gap_quota_used"] is False


def test_frozen_protected_path_exists() -> None:
    split = locked_split()
    assert ROOT / split["frozen_evaluation"]["protected_path"] == FROZEN / "product_query_frozen_evaluation_v1.locked.jsonl"
    assert (ROOT / split["frozen_evaluation"]["protected_path"]).is_file()


def test_frozen_access_guard_complete() -> None:
    guard_path = FROZEN / "FROZEN_EVALUATION_ACCESS_GUARD.json"
    guard = json.loads(guard_path.read_text())
    protected = ROOT / guard["protected_file"]
    assert guard["status"] == "sealed_before_formal_evaluation"
    assert guard["protected_file_sha256"] == sha256(protected)
    assert set(guard["allowed_before_formal_frozen_run"]) == {
        "identity_hash_verification",
        "schema_validation",
        "authorized_gold_construction_under_future_contract",
        "case_completeness_validation",
    }
    assert set(guard["forbidden_before_formal_frozen_run"]) == {
        "run_retrieval_for_tuning",
        "inspect_prediction_failures_for_development",
        "modify_query_or_split",
        "move_difficult_queries_to_development",
        "rerun_until_metrics_improve",
    }
    assert all(guard["future_access_requirement"].values())
    assert guard["frozen_prediction_created"] is False
    assert guard["frozen_gold_created"] is False


def test_canonical_split_hash_repeatable() -> None:
    rows = development_rows() + frozen_rows()
    first = hashlib.sha256(canonical_assignment(rows)).hexdigest()
    second = hashlib.sha256(canonical_assignment(json.loads(json.dumps(rows)))).hexdigest()
    split = locked_split()
    audit = json.loads((OUT / "product_query_split_v1.audit.json").read_text())
    assert first == second == split["canonical_assignment_sha256"]
    assert first == audit["canonical_assignment"]["first_sha256"]
    assert first == audit["canonical_assignment"]["second_sha256"]
    assert audit["canonical_assignment"]["repeatable"] is True


def test_manifest_and_file_hashes_match() -> None:
    manifest = json.loads((OUT / "product_query_split_v1.manifest.json").read_text())
    output_paths = {
        "locked_split": OUT / "product_query_split_v1.locked.json",
        "development_jsonl": OUT / "product_query_development_v1.locked.jsonl",
        "frozen_evaluation_jsonl": FROZEN / "product_query_frozen_evaluation_v1.locked.jsonl",
        "frozen_access_guard": FROZEN / "FROZEN_EVALUATION_ACCESS_GUARD.json",
        "audit": OUT / "product_query_split_v1.audit.json",
        "report": OUT / "PRODUCT_QUERY_SPLIT_V1_REPORT.md",
        "execution_decision": OUT / "product_query_split_v1.execution_decision.json",
        "repository_ledger_copy": LEDGER_COPY,
    }
    assert manifest["output_hashes"] == {name: sha256(path) for name, path in output_paths.items()}
    for record in jsonl(OUT / "product_query_split_v1.file_hash_manifest.jsonl"):
        path = ROOT / record["path"]
        assert record["sha256"] == sha256(path)
        assert record["size_bytes"] == path.stat().st_size


def test_p3_p4_assets_unchanged() -> None:
    assert {relative: sha256(BASE / relative) for relative in EXPECTED_P3_P4_HASHES} == EXPECTED_P3_P4_HASHES
    audit = json.loads((OUT / "product_query_split_v1.audit.json").read_text())
    assert audit["immutability"]["p3_p4_assets_changed"] is False
    assert audit["immutability"]["p3_p4_baseline_hashes"] == EXPECTED_P3_P4_HASHES


def test_no_gold_target_video_or_system_results_accessed() -> None:
    audit = json.loads((OUT / "product_query_split_v1.audit.json").read_text())
    assert audit["scope"]["gold_assets_read"] is False
    assert audit["scope"]["target_videos_read"] is False
    assert audit["scope"]["system_results_read"] is False


def test_no_pipeline_calls() -> None:
    scope = json.loads((OUT / "product_query_split_v1.audit.json").read_text())["scope"]
    assert all(scope[key] == 0 for key in ("retrieval_calls", "builder_calls", "selector_calls", "judge_calls"))


def test_no_gold_baseline_f1_or_stage4_assets_created() -> None:
    downstream = json.loads((OUT / "product_query_split_v1.audit.json").read_text())["downstream"]
    assert downstream == {
        "gold_created": False,
        "product_baseline_started": False,
        "f1a_or_f1b_started": False,
        "stage4_started": False,
    }
    decision = json.loads((OUT / "product_query_split_v1.execution_decision.json").read_text())
    assert decision["execution_status"] == "complete"
    assert decision["acceptance_status"] == "pending_v3_5_b_review"
    assert decision["p5_formally_accepted_by_v3_5_b"] is False
    assert decision["next_phase_authorized"] is False
