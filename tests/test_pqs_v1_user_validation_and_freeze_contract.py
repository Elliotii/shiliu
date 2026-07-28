from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = Path("/Users/elliot/Downloads/V3_5_PQS_V1_USER_DECISION_LEDGER.json")
P3 = ROOT / "research/v3_5/product_query_set_v1/user_validation"
P4 = ROOT / "research/v3_5/product_query_set_v1/freeze"
SOURCE = ROOT / "research/v3_5/product_query_set_v1/corpus_aware_generation"
EXPECTED_LEDGER_SHA = "fa469c47bcb32595f541b83b571ed86977c0233b6fef1458b770f8cc7b4e7bf6"
EXPECTED_SOURCE_HASHES = {
    "product_query_candidates.user_review.jsonl": "f72e92373ed5ed93a9a82a7e5f88597c4f8e2bdca7f7f781f98062fcb2601213",
    "product_query_candidates.internal_basis.jsonl": "66ddc96e9484e9080b8df92f3aaf192a5c73cbe126e65cf5bfb69731e3f1b008",
    "product_query_corpus_inventory.internal.jsonl": "05e71ce08db5dc92e92035fee3e26ce7156ccfacdb40a4a834d857bb229ffe5f",
    "corpus_aware_candidate_generation.audit.json": "5e50946729ec3afd15a114db802142b926be698f9f3d0dc6547a425f6a4f6269",
    "corpus_aware_candidate_generation_report.md": "47e5d40aa8d8f7da99edcab0abb3cbf48f2247b8f8abde8a0beeeb3ab2d317fb",
    "corpus_aware_candidate_generation_audit_amendment.md": "2dcad60f74278d4663491216f85f3464c17c4580654ea480aedfff4574da87a9",
}
REQUIRED_QUERY_FIELDS = {
    "query_id",
    "query_text",
    "query_language",
    "query_family",
    "intent",
    "single_or_multi_video",
    "complexity",
    "authoring_origin",
    "source_candidate_ids",
    "user_validated_as_plausible",
    "revision_history",
    "leakage_group",
    "topic_cluster",
}
FORBIDDEN_FIELDS = {
    "gold_label",
    "target_video",
    "required_span",
    "expected_failure",
    "expected_status",
    "system_result",
    "retrieval_mode",
    "rank",
    "dev_or_frozen_identity",
    "expected_action",
    "answer",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def completed() -> list[dict]:
    return jsonl(P3 / "product_query_user_validation.completed.jsonl")


def pool() -> list[dict]:
    return jsonl(P3 / "product_query_candidate_pool.after_user_revision.jsonl")


def locked() -> list[dict]:
    return jsonl(P4 / "product_query_set_v1.locked.jsonl")


def canonical(rows: list[dict]) -> bytes:
    return json.dumps(
        sorted(rows, key=lambda row: row["query_id"]),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(all_keys(item) for item in value), set())
    return set()


def test_user_decision_ledger_hash_matches() -> None:
    assert sha256(LEDGER_PATH) == EXPECTED_LEDGER_SHA


def test_all_41_user_decisions_materialized() -> None:
    assert completed() == ledger()["candidate_decisions"]
    assert len(pool()) == 41
    assert [row["draft_query_id"] for row in pool()] == [
        *[f"PQC_{index:03d}" for index in range(1, 41)],
        "PQC_USER_001",
    ]


def test_p3_counts_are_24_11_6() -> None:
    rows = completed()
    assert sum(row["formal_set_selected"] for row in rows) == 24
    counts = Counter(row["user_action"] for row in rows)
    assert counts["reserve"] == 11
    assert counts["reject"] == 6


def test_p3_revision_rounds_is_one() -> None:
    audit = json.loads((P3 / "pqs_v1_user_validation.audit.json").read_text())
    assert audit["revision_rounds_used"] == ledger()["revision_rounds_used"] == 1


def test_p3_has_no_unresolved_discussions() -> None:
    audit = json.loads((P3 / "pqs_v1_user_validation.audit.json").read_text())
    assert audit["unresolved_discussions"] == ledger()["unresolved_discussions"] == 0


def test_locked_query_count_is_24() -> None:
    assert len(locked()) == 24


def test_locked_query_ids_are_unique_and_contiguous() -> None:
    ids = [row["query_id"] for row in locked()]
    assert len(ids) == len(set(ids))
    assert ids == [f"PQS_V1_Q{index:03d}" for index in range(1, 25)]


def test_locked_queries_match_frozen_ledger_exactly() -> None:
    for actual, frozen in zip(locked(), ledger()["final_query_specs"], strict=True):
        assert {key: actual[key] for key in frozen} == frozen


def test_all_locked_queries_user_validated() -> None:
    assert all(row["user_validated_as_plausible"] is True for row in locked())


def test_required_query_fields_complete() -> None:
    assert all(REQUIRED_QUERY_FIELDS <= set(row) for row in locked())
    assert all(all(row[field] not in (None, "", []) for field in REQUIRED_QUERY_FIELDS) for row in locked())


def test_reserve_and_reject_not_in_locked_set() -> None:
    selected = {row["draft_query_id"] for row in completed() if row["formal_set_selected"]}
    not_selected = {row["draft_query_id"] for row in completed() if not row["formal_set_selected"]}
    sources = {source for row in locked() for source in row["source_candidate_ids"]}
    assert sources <= selected
    assert sources.isdisjoint(not_selected)


def test_user_origin_query_is_present() -> None:
    rows = [row for row in locked() if row["source_candidate_ids"] == ["PQC_USER_001"]]
    assert len(rows) == 1
    assert rows[0]["authoring_origin"] == "user_discussion"
    assert rows[0]["query_id"] == "PQS_V1_Q024"


def test_source_candidate_ids_traceable() -> None:
    decision_ids = {row["draft_query_id"] for row in completed()}
    assert all(set(row["source_candidate_ids"]) <= decision_ids for row in locked())


def test_revision_history_complete() -> None:
    decisions = {row["draft_query_id"]: row for row in completed()}
    for row in locked():
        assert len(row["revision_history"]) == 1
        revision = row["revision_history"][0]
        decision = decisions[row["source_candidate_ids"][0]]
        assert revision["original_query"] == decision["original_query"]
        assert revision["final_query"] == decision["final_user_query"] == row["query_text"]
        assert revision["decision_authority"] == "user"
        expected_type = (
            "user_origin_with_editorial_clarification"
            if decision["draft_query_id"] == "PQC_USER_001"
            else "approve_as_is"
            if decision["user_action"] == "approve_as_is"
            else "user_revision"
        )
        assert revision["revision_type"] == expected_type
        assert revision["reason"]


def test_leakage_groups_match_frozen_ledger() -> None:
    expected = {
        row["query_id"]: row["leakage_group"]
        for row in ledger()["final_query_specs"]
    }
    assert {row["query_id"]: row["leakage_group"] for row in locked()} == expected


def test_no_forbidden_fields() -> None:
    assert all_keys(locked()).isdisjoint(FORBIDDEN_FIELDS)


def test_no_exact_duplicate_query_text() -> None:
    texts = [row["query_text"] for row in locked()]
    assert len(texts) == len(set(texts))


def test_canonical_hash_repeatable() -> None:
    first = hashlib.sha256(canonical(locked())).hexdigest()
    second = hashlib.sha256(canonical(jsonl(P4 / "product_query_set_v1.locked.jsonl"))).hexdigest()
    manifest = json.loads((P4 / "product_query_set_v1.manifest.json").read_text())
    audit = json.loads((P4 / "product_query_set_v1.lock.audit.json").read_text())
    assert first == second == manifest["canonical_content_sha256"]
    assert first == audit["first_canonical_sha256"] == audit["second_canonical_sha256"]


def test_manifest_hashes_match_files() -> None:
    manifest = json.loads((P4 / "product_query_set_v1.manifest.json").read_text())
    assert manifest["locked_jsonl_sha256"] == sha256(P4 / "product_query_set_v1.locked.jsonl")
    source_paths = {
        "user_decision_ledger": LEDGER_PATH,
        "corpus_candidate_user_review": SOURCE / "product_query_candidates.user_review.jsonl",
        "corpus_candidate_internal_basis": SOURCE / "product_query_candidates.internal_basis.jsonl",
        "corpus_inventory": SOURCE / "product_query_corpus_inventory.internal.jsonl",
        "generation_audit": SOURCE / "corpus_aware_candidate_generation.audit.json",
        "generation_report": SOURCE / "corpus_aware_candidate_generation_report.md",
        "audit_amendment": SOURCE / "corpus_aware_candidate_generation_audit_amendment.md",
        "p3_completed_validation": P3 / "product_query_user_validation.completed.jsonl",
        "p3_after_revision_pool": P3 / "product_query_candidate_pool.after_user_revision.jsonl",
    }
    assert manifest["source_artifact_hashes"] == {
        name: sha256(path) for name, path in source_paths.items()
    }
    for record in jsonl(P4 / "product_query_set_v1.file_hash_manifest.jsonl"):
        path = ROOT / record["path"]
        assert record["sha256"] == sha256(path)
        assert record["size_bytes"] == path.stat().st_size


def test_candidate_generation_inputs_unchanged() -> None:
    assert {name: sha256(SOURCE / name) for name in EXPECTED_SOURCE_HASHES} == EXPECTED_SOURCE_HASHES


def test_no_retrieval_builder_selector_judge_calls() -> None:
    p3_audit = json.loads((P3 / "pqs_v1_user_validation.audit.json").read_text())
    p4_audit = json.loads((P4 / "product_query_set_v1.lock.audit.json").read_text())
    assert all(
        p3_audit[key] == 0
        for key in ("retrieval_calls", "builder_calls", "selector_calls", "mechanical_gate_calls", "semantic_judge_calls")
    )
    assert all(
        p4_audit[key] == 0
        for key in ("retrieval_calls", "builder_calls", "selector_calls", "mechanical_gate_calls", "judge_calls")
    )


def test_no_split_gold_or_baseline_assets_created() -> None:
    created_names = {path.name.casefold() for directory in (P3, P4) for path in directory.iterdir()}
    assert not any(token in name for name in created_names for token in ("split", "gold", "baseline"))
    audit = json.loads((P4 / "product_query_set_v1.lock.audit.json").read_text())
    assert audit["gold_assets_read"] is False
    assert audit["system_results_read"] is False
    assert audit["split_created"] is False
    assert audit["product_baseline_started"] is False
    decision = json.loads((P4 / "product_query_set_v1.freeze_execution_decision.json").read_text())
    assert decision["acceptance_status"] == "pending_v3_5_b_review"
    assert decision["product_query_set_formally_accepted_by_v3_5_b"] is False
    assert decision["p5_authorized"] is False
