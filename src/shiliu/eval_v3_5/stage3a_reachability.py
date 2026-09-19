from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.retrieval.product_search import ProductSearchRequest


AUDITED_CASE_IDS = ("CASE_001", "CASE_002", "CASE_003", "CASE_005")
RETRIEVAL_MISS_CLASSIFICATIONS = frozenset(
    {
        "projection_bug",
        "manifest_serialization_bug",
        "search_request_bug",
        "scope_or_filter_bug",
        "router_execution_bug",
        "snapshot_or_index_mismatch",
        "true_v3_retrieval_miss",
        "unknown",
    }
)
FAILURE_ATTRIBUTIONS = frozenset(
    {
        "upstream_retrieval_failure",
        "candidate_generation_failure",
        "selector_failure",
    }
)


def reconstruct_frozen_request(record: dict[str, Any]) -> ProductSearchRequest:
    """Reconstruct only the request serialized by the locked execution manifest."""
    request = ProductSearchRequest.model_validate(record["search_request"])
    if request.model_dump(mode="json") != record["search_request"]:
        raise ValueError("frozen request reconstruction changed serialized fields")
    if request.query != record["original_query"]:
        raise ValueError("frozen request query differs from Original Query")
    return request


def json_payload_equal(left: object, right: object) -> bool:
    """Compare JSON semantics, normalizing dataclass tuple containers to arrays."""
    return json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


@dataclass
class SingleReplayLedger:
    authorized_case_ids: tuple[str, ...] = AUDITED_CASE_IDS
    _counts: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        self._counts = {case_id: 0 for case_id in self.authorized_case_ids}

    def claim(self, case_id: str) -> None:
        if case_id not in self._counts:
            raise ValueError(f"case is not authorized for replay: {case_id}")
        if self._counts[case_id]:
            raise RuntimeError(f"frozen request replay already executed: {case_id}")
        self._counts[case_id] = 1

    @property
    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def assert_complete(self) -> None:
        if any(count != 1 for count in self._counts.values()):
            raise RuntimeError(f"single replay contract incomplete: {self._counts}")


def classify_track_a(
    *, target_video_reachable: bool, candidate_builder_coverage: bool | None,
    selector_success: bool | None,
) -> Literal[
    "upstream_retrieval_failure", "candidate_generation_failure", "selector_failure"
] | None:
    if not target_video_reachable:
        return "upstream_retrieval_failure"
    if candidate_builder_coverage is False:
        return "candidate_generation_failure"
    if candidate_builder_coverage is True and selector_success is False:
        return "selector_failure"
    return None


class OracleVideoConditionalInput(BaseModel):
    """Development-only Track B boundary; it carries no semantic Gold fields."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    original_query: str
    oracle_target_video_id: int = Field(gt=0)
    raw_transcript_path: str
    raw_transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_raw_transcript_identity(self) -> "OracleVideoConditionalInput":
        if Path(self.raw_transcript_path).name != "subtitle-raw.json":
            raise ValueError("Track B requires the authoritative frozen Raw Transcript")
        return self


def validate_oracle_video_boundary(
    payload: dict[str, Any], *, manifest_record: dict[str, Any]
) -> OracleVideoConditionalInput:
    value = OracleVideoConditionalInput.model_validate(payload)
    if value.case_id != manifest_record["case_id"]:
        raise ValueError("Track B case does not match the Development manifest")
    if value.original_query != manifest_record["original_query"]:
        raise ValueError("Track B query must be the Original Query")
    if value.oracle_target_video_id != manifest_record["target_video_id"]:
        raise ValueError("Track B oracle video must match the Development target identity")
    return value
