from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
CYCLE = ROOT / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1"
BASELINE = ROOT / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
GOLD = ROOT / (
    "research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1/"
    "sealed/product_evidence_gold.development.v1.sealed.jsonl"
)
PRESERVED = (
    "PQS_V1_Q006",
    "PQS_V1_Q007",
    "PQS_V1_Q011",
    "PQS_V1_Q012",
    "PQS_V1_Q013",
    "PQS_V1_Q019",
)

BRIDGE_PATH = ROOT / "src/shiliu/eval_v3_5/scoring_identity_bridge.py"
SPEC = importlib.util.spec_from_file_location("evidence_identity_bridge_v1_test_target", BRIDGE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load bridge: {BRIDGE_PATH}")
BRIDGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIDGE
SPEC.loader.exec_module(BRIDGE)
CanonicalVideoIdentity = BRIDGE.CanonicalVideoIdentity
VideoIdentityCanonicalizer = BRIDGE.VideoIdentityCanonicalizer
canonical_evidence_match = BRIDGE.canonical_evidence_match
canonical_scoring_identity = BRIDGE.canonical_scoring_identity
span_is_covered = BRIDGE.span_is_covered


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def identity(
    *, video_id=7, source_type="raw_subtitle", source_version="source-v1",
    timeline_run_id="timeline-1", segment_ids=("segment-1",), start_time=1.0,
    end_time=2.0, **extra,
):
    return {
        "evidence_candidate_contract_version": "v3.5-evidence-candidate-v1",
        "video_id": video_id,
        "source_type": source_type,
        "source_version": source_version,
        "timeline_run_id": timeline_run_id,
        "segment_ids": list(segment_ids),
        "start_time": start_time,
        "end_time": end_time,
        **extra,
    }


class EvidenceIdentityContractV1Tests(unittest.TestCase):
    def setUp(self):
        self.mapping = VideoIdentityCanonicalizer(
            [CanonicalVideoIdentity("bilibili", "BV_TEST", 7, 1)],
            source="test-fixture",
            source_sha256="0" * 64,
        )

    def test_positive_same_video_bvid_vs_numeric_id(self):
        left = identity(video_id="bilibili:BV_TEST")
        right = identity(video_id=7)
        self.assertEqual(canonical_evidence_match(left, right, self.mapping).status, "match")

    def test_positive_same_timeline_and_same_segment(self):
        self.assertEqual(
            canonical_evidence_match(identity(), identity(candidate_id="different"), self.mapping).status,
            "match",
        )

    def test_positive_raw_subtitle_with_ai_selection(self):
        gold = identity(source_type="official_subtitle", segment_identity_version="v3.5-source-identity-v2")
        runtime = identity(source_type="ai", selector_method="structured_ai_selector")
        result = canonical_evidence_match(gold, runtime, self.mapping)
        self.assertEqual(result.status, "match")
        self.assertEqual(result.right.provenance.source_generation_lineage, "ai")
        self.assertEqual(result.right.provenance.underlying_evidence_source, "raw_subtitle")

    def test_positive_single_or_split_preserved_spans(self):
        gold = identity(segment_ids=("segment-1", "segment-2"), start_time=1.0, end_time=3.0)
        split = [
            identity(segment_ids=("segment-1",), start_time=1.0, end_time=2.0),
            identity(segment_ids=("segment-2",), start_time=2.0, end_time=3.0),
        ]
        self.assertTrue(span_is_covered(gold, split, self.mapping))

    def test_positive_equivalent_normalized_time_representation(self):
        left = identity(start_time="1.0000000", end_time="2.0000000")
        right = identity(start_time=1.0000004, end_time=2.0000004)
        self.assertEqual(canonical_evidence_match(left, right, self.mapping).status, "match")

    def test_negative_different_video(self):
        mapping = VideoIdentityCanonicalizer(
            [
                CanonicalVideoIdentity("bilibili", "BV_TEST", 7, 1),
                CanonicalVideoIdentity("bilibili", "BV_OTHER", 8, 1),
            ],
            source="test-fixture",
            source_sha256="0" * 64,
        )
        self.assertEqual(canonical_evidence_match(identity(), identity(video_id=8), mapping).status, "non_match")

    def test_negative_wrong_timeline(self):
        self.assertEqual(
            canonical_evidence_match(identity(), identity(timeline_run_id="timeline-2"), self.mapping).status,
            "non_match",
        )

    def test_negative_wrong_segment(self):
        self.assertEqual(
            canonical_evidence_match(identity(), identity(segment_ids=("segment-2",)), self.mapping).status,
            "non_match",
        )

    def test_negative_overlap_does_not_replace_segment_identity(self):
        gold = identity(segment_ids=("segment-1",), start_time=1.0, end_time=3.0)
        wrong = identity(segment_ids=("segment-2",), start_time=1.5, end_time=2.5)
        self.assertFalse(span_is_covered(gold, [wrong], self.mapping))

    def test_negative_ai_summary_vs_raw_subtitle(self):
        raw = identity(source_type="official_subtitle", segment_identity_version="v3.5-source-identity-v2")
        summary = identity(source_type="ai", extraction_method="ai_generated_summary")
        self.assertEqual(canonical_evidence_match(raw, summary, self.mapping).status, "non_match")

    def test_negative_unknown_or_ambiguous_video_mapping(self):
        unknown = identity(video_id="bilibili:BV_UNKNOWN")
        self.assertEqual(canonical_evidence_match(identity(), unknown, self.mapping).status, "unverifiable")
        conflict = identity(video_id=7, bvid="BV_UNKNOWN")
        self.assertIsNone(canonical_scoring_identity(conflict, self.mapping))

    def test_negative_missing_required_identity_component(self):
        for field in ("video_id", "source_version", "timeline_run_id", "segment_ids", "start_time", "end_time"):
            value = identity()
            del value[field]
            self.assertIsNone(canonical_scoring_identity(value, self.mapping), field)

    def test_candidate_id_only_is_insufficient(self):
        result = canonical_evidence_match({"candidate_id": "same"}, {"candidate_id": "same"}, self.mapping)
        self.assertEqual(result.status, "unverifiable")

    def test_selector_method_does_not_change_identity(self):
        left = identity(selector_method="deterministic")
        right = identity(selector_method="ai")
        self.assertEqual(canonical_evidence_match(left, right, self.mapping).status, "match")

    def test_builder_version_does_not_change_identity(self):
        left = identity(builder_version="builder-v1")
        right = identity(builder_version="builder-v2")
        self.assertEqual(canonical_evidence_match(left, right, self.mapping).status, "match")

    def test_source_version_remains_exact_identity_namespace(self):
        self.assertEqual(
            canonical_evidence_match(identity(), identity(source_version="source-v2"), self.mapping).status,
            "non_match",
        )

    def test_all_six_preserved_fixtures_keep_identity(self):
        gold_by_query = {row["query_id"]: row for row in load_jsonl(GOLD)}
        for query_id in PRESERVED:
            trace = load_json(BASELINE / f"blind_run/product_initial_baseline.traces/{query_id}.trace.json")
            candidates = trace["evidence_candidate_set"]["candidates"]
            candidates_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
            swap = load_json(CYCLE / f"f1a_swap_traces/{query_id}.json")
            preserved_ids = set()
            for per_video in swap["per_video"].values():
                preserved_ids.update(set(per_video["original_top_32"]) & set(per_video["final_candidate_ids"]))
            preserved_candidates = [candidates_by_id[value] for value in preserved_ids if value in candidates_by_id]
            self.assertTrue(preserved_candidates, query_id)

            fixture_mappings = [
                CanonicalVideoIdentity(
                    "bilibili", str(value["source_id"]), int(value["video_id"]), 1,
                )
                for value in trace["search_candidate_set"]["video_candidates"]
            ]
            for gold_span in gold_by_query[query_id]["span_registry"]:
                matches = {
                    int(candidate["video_id"])
                    for candidate in candidates
                    if candidate["source_version"] == gold_span["source_version"]
                    and candidate["timeline_run_id"] == gold_span["timeline_run_id"]
                    and set(candidate["segment_ids"]) & set(gold_span["segment_ids"])
                }
                self.assertEqual(len(matches), 1, (query_id, gold_span["span_id"]))
                numeric_id = matches.pop()
                self.assertTrue(any(
                    value.numeric_video_id == numeric_id
                    and value.source_video_id == gold_span["video_id"].split(":", 1)[1]
                    for value in fixture_mappings
                ))
            unique_mappings = list({value.numeric_video_id: value for value in fixture_mappings}.values())
            mapping = VideoIdentityCanonicalizer(
                unique_mappings,
                source="six-preserved-fixture-derived-from-stable-source-timeline-segment-join",
                source_sha256="0" * 64,
            )
            for candidate in preserved_candidates:
                before = deepcopy(candidate)
                before["selector_method"] = "v3.5-deterministic-fine-selector-v1"
                before["builder_version"] = "stage3b-acronym-w3.5-v1"
                after = deepcopy(candidate)
                after["selector_method"] = "ai"
                after["builder_version"] = "stage3b-adaptive-swap-w3.5-v1"
                result = canonical_evidence_match(before, after, mapping)
                self.assertEqual(result.status, "match", (query_id, candidate["candidate_id"], result.reason))


if __name__ == "__main__":
    unittest.main()
