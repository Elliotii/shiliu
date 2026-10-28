"""V3.5 Stage 2 draft schemas and human-review packet tooling."""

from shiliu.eval_v3_5.models import (
    CompletedReviewDecision,
    MasterCaseCandidate,
    ReviewDecisionTemplate,
)


__all__ = [
    "CompletedReviewDecision",
    "MasterCaseCandidate",
    "PacketBuildSummary",
    "ReviewDecisionTemplate",
    "build_review_assets",
    "validate_review_assets",
]


def __getattr__(name):
    # Formal stage4b semantic analysis must not import offline SQLite packets.
    if name in {"PacketBuildSummary", "build_review_assets", "validate_review_assets"}:
        from shiliu.eval_v3_5 import packets
        return getattr(packets, name)
    raise AttributeError(name)
