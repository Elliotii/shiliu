"""Isolated Shiliu V3 embedding model-selection experiment."""

from research.v3_model_selection.harness import (
    CandidateSpec,
    ExperimentalDenseIndex,
    QwenLocalEmbeddingProvider,
)

__all__ = ["CandidateSpec", "ExperimentalDenseIndex", "QwenLocalEmbeddingProvider"]
