from __future__ import annotations

import unittest

from scorer_v4_projection import project_gold_span
from shiliu.eval_v3_5.scoring_identity_bridge import (
    CanonicalVideoIdentity,
    VideoIdentityCanonicalizer,
)


def span(**changes):
    value = {
        "evidence_candidate_contract_version": "v3.5-evidence-candidate-v1",
        "video_id": 7,
        "source_type": "raw_subtitle",
        "source_version": "source-v1",
        "timeline_run_id": "timeline-1",
        "segment_ids": ["segment-1"],
        "start_time": 1.0,
        "end_time": 2.0,
    }
    value.update(changes)
    return value


class ScorerV4ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.mapping = VideoIdentityCanonicalizer(
            [CanonicalVideoIdentity("bilibili", "BV_TEST", 7, 1)],
            source="test-fixture",
            source_sha256="0" * 64,
        )

    def test_match_contributes_to_coverage(self):
        result = project_gold_span(span(), [span()], self.mapping)
        self.assertTrue(result.covered)
        self.assertEqual(result.match_count, 1)

    def test_non_match_does_not_contribute_to_coverage(self):
        result = project_gold_span(
            span(), [span(timeline_run_id="timeline-2")], self.mapping,
        )
        self.assertFalse(result.covered)
        self.assertEqual(result.non_match_count, 1)

    def test_unverifiable_does_not_contribute_and_is_reported(self):
        result = project_gold_span(span(), [{"candidate_id": "only"}], self.mapping)
        self.assertFalse(result.covered)
        self.assertEqual(result.unverifiable_count, 1)

    def test_split_preserved_spans_contribute_by_contract_union(self):
        gold = span(
            segment_ids=["segment-1", "segment-2"], start_time=1.0, end_time=3.0,
        )
        candidates = [
            span(segment_ids=["segment-1"], start_time=1.0, end_time=2.0),
            span(segment_ids=["segment-2"], start_time=2.0, end_time=3.0),
        ]
        result = project_gold_span(gold, candidates, self.mapping)
        self.assertTrue(result.covered)
        self.assertTrue(result.aggregate_preserved_span_coverage)
        self.assertEqual(result.match_count, 0)


if __name__ == "__main__":
    unittest.main()
