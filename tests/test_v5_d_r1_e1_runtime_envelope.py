from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from shiliu.research.errors import ResearchValidationError
from shiliu.research.provider_product import (
    ReceiptBoundResearchProductOrchestrator,
)


class _AcceptedEnvelopeBoundaryReached(Exception):
    """Stop the mechanical test after the real envelope validation boundary."""


@pytest.mark.parametrize(
    ("arm", "max_input_tokens"),
    (("baseline", 125_000), ("treatment", 140_000)),
)
def test_r1_e1_caps_reach_accepted_product_runtime_boundary_without_dispatch(
    monkeypatch: pytest.MonkeyPatch, arm: str, max_input_tokens: int
) -> None:
    kernel = Mock()
    kernel._transaction.return_value = nullcontext()
    kernel._existing_receipt.return_value = None
    inner = Mock(provider_runs_authorized=True)
    receipt_service = Mock(provider_dispatch_authorized=True)
    provider_factory = Mock(side_effect=AssertionError("Provider dispatch forbidden"))
    orchestrator = ReceiptBoundResearchProductOrchestrator(
        db=Mock(),
        kernel=kernel,
        inner=inner,
        product=Mock(),
        receipt_service=receipt_service,
        provider_factory=provider_factory,
        deep_executor=Mock(),
        materializer=Mock(),
        provider_product_authorized=True,
    )

    def stop_after_validation(*_args: object, **_kwargs: object) -> None:
        raise _AcceptedEnvelopeBoundaryReached

    monkeypatch.setattr(orchestrator, "_prepare_inner", stop_after_validation)
    with pytest.raises(_AcceptedEnvelopeBoundaryReached):
        orchestrator.run_to_boundary(
            f"mechanical-{arm}",
            command_id=f"v5d-r1-e1:mechanical:{arm}",
            max_logical_calls=15 if arm == "treatment" else 12,
            max_http_attempts=30 if arm == "treatment" else 24,
            max_input_tokens=max_input_tokens,
            max_output_tokens=25_000 if arm == "treatment" else 15_000,
            max_wall_time_seconds=720,
        )
    provider_factory.assert_not_called()
    receipt_service.factory.assert_not_called()


def test_legacy_treatment_cap_is_rejected_before_provider_dispatch() -> None:
    inner = Mock(provider_runs_authorized=True)
    receipt_service = Mock(provider_dispatch_authorized=True)
    provider_factory = Mock(side_effect=AssertionError("Provider dispatch forbidden"))
    orchestrator = ReceiptBoundResearchProductOrchestrator(
        db=Mock(),
        kernel=Mock(),
        inner=inner,
        product=Mock(),
        receipt_service=receipt_service,
        provider_factory=provider_factory,
        deep_executor=Mock(),
        materializer=Mock(),
        provider_product_authorized=True,
    )
    with pytest.raises(
        ResearchValidationError,
        match="input-token cap exceeds the Gate B envelope",
    ):
        orchestrator.run_to_boundary(
            "mechanical-legacy-treatment",
            command_id="v5d-r1-e1:mechanical:legacy-treatment",
            max_input_tokens=175_000,
        )
    provider_factory.assert_not_called()
    receipt_service.factory.assert_not_called()
