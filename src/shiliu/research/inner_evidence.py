from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import sqlite3
from typing import Any

from shiliu.ask.citations import stable_citation_id
from shiliu.ask.contracts import (
    CITATION_IDENTITY_VERSION,
    EvidenceSegment,
    TranscriptEvidenceSpan,
)
from shiliu.db import Database
from shiliu.evidence.authority import bind_live_current_version
from shiliu.evidence.contracts import EvidenceContractError, SourceArtifactReference
from shiliu.evidence.source import canonical_json, load_source_artifact
from shiliu.retrieval.product_search import build_bilibili_jump_url


@dataclass(frozen=True)
class CurrentnessResult:
    outcome: str
    reason_code: str
    expected_source_version: str
    observed_source_version: str | None
    span: TranscriptEvidenceSpan | None


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def evidence_identity_payload(span: TranscriptEvidenceSpan) -> dict[str, Any]:
    return {
        "citation_identity_version": span.citation_identity_version,
        "evidence_id": span.citation_id,
        "video_id": span.video_id,
        "source_artifact_id": span.source_artifact_id,
        "source_version": span.source_version,
        "timeline_run_id": span.timeline_run_id,
        "segment_ids": list(span.segment_ids),
        "segment_ordinals": list(span.segment_ordinals),
        "start_time": span.start_time,
        "end_time": span.end_time,
        "quote_hash": hashlib.sha256(span.quote_text.encode("utf-8")).hexdigest(),
    }


def provenance_payloads(
    span: TranscriptEvidenceSpan,
    *,
    fallback_query: str,
) -> tuple[dict[str, Any], ...]:
    values = span.retrieval_provenance or ({},)
    payloads: list[dict[str, Any]] = []
    for value in values:
        query = str(value.get("query") or fallback_query)
        payloads.append(
            {
                "execution_id": _optional_text(value.get("execution_id")),
                "search_trace_id": _optional_text(value.get("search_trace_id")),
                "query_fingerprint": canonical_hash(
                    {"query": " ".join(query.casefold().split())}
                ),
                "rank": _optional_int(value.get("rank")),
                "retrieval_method": str(
                    value.get("retrieval_method")
                    or value.get("action")
                    or "authoritative_transcript"
                ),
                "index_identity": dict(value.get("index_identity") or {}),
                "parent_chunk_ids": list(span.parent_chunk_ids),
                "source_version_authority": span.source_version_authority,
                "mapping_policy_versions": {
                    "citation_identity_version": span.citation_identity_version,
                    "materialization": "v4-transcript-evidence-materializer",
                },
            }
        )
    return tuple(payloads)


class PersistentEvidenceAuthority:
    """Reconstruct current evidence from immutable identity, never from previews."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def observe(self, identity: sqlite3.Row | dict[str, Any]) -> CurrentnessResult:
        expected = str(identity["source_version"])
        video_id = int(identity["video_id"])
        video = self.db.get_video(video_id)
        if video is None or video.get("removed_at") is not None:
            return CurrentnessResult(
                outcome="missing",
                reason_code="citation_source_unavailable",
                expected_source_version=expected,
                observed_source_version=None,
                span=None,
            )
        reference = SourceArtifactReference(
            platform=str(video["platform"]),
            source_id=str(video["source_id"]),
            part=int(video["part"]),
            source_type=str(video.get("subtitle_source") or "unknown"),
            source_language=str(video.get("subtitle_language") or "unknown"),
            artifact_path=str(video.get("raw_subtitle_path") or ""),
        )
        observed: str | None = None
        try:
            binding = bind_live_current_version(
                reference, db=self.db, video_id=video_id
            )
            observed = binding.source_version
            if (
                binding.source_artifact_id != str(identity["source_artifact_id"])
                or observed != expected
            ):
                return CurrentnessResult(
                    outcome="stale",
                    reason_code="citation_source_version_stale",
                    expected_source_version=expected,
                    observed_source_version=observed,
                    span=None,
                )
            artifact = load_source_artifact(
                reference, expected_source_version=expected
            )
            segment_ids = tuple(json.loads(str(identity["segment_ids_json"])))
            ordinals = tuple(
                int(value)
                for value in json.loads(str(identity["segment_ordinals_json"]))
            )
            by_id = {value.segment_id: value for value in artifact.segments}
            try:
                segments = tuple(by_id[value] for value in segment_ids)
            except KeyError:
                return CurrentnessResult(
                    outcome="invalid",
                    reason_code="citation_segment_missing",
                    expected_source_version=expected,
                    observed_source_version=observed,
                    span=None,
                )
            if (
                not segments
                or tuple(value.original_ordinal for value in segments) != ordinals
                or any(
                    value.timeline_run_id != str(identity["timeline_run_id"])
                    for value in segments
                )
            ):
                return CurrentnessResult(
                    outcome="invalid",
                    reason_code="citation_lineage_invalid",
                    expected_source_version=expected,
                    observed_source_version=observed,
                    span=None,
                )
            citation_id = stable_citation_id(
                source_artifact_id=str(identity["source_artifact_id"]),
                source_version=expected,
                timeline_run_id=str(identity["timeline_run_id"]),
                segments=segments,
            )
            quote = "\n".join(
                value.source_text.strip()
                for value in segments
                if value.source_text.strip()
            )
            quote_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
            start_time = segments[0].start_time
            end_time = segments[-1].end_time
            jump_url = build_bilibili_jump_url(
                str(video.get("video_url") or ""),
                str(video["source_id"]),
                start_time,
            )
            if (
                citation_id != str(identity["evidence_id"])
                or quote_hash != str(identity["quote_hash"])
                or start_time != float(identity["start_time"])
                or end_time != float(identity["end_time"])
                or jump_url is None
            ):
                return CurrentnessResult(
                    outcome="invalid",
                    reason_code="citation_reconstruction_failed",
                    expected_source_version=expected,
                    observed_source_version=observed,
                    span=None,
                )
            span = TranscriptEvidenceSpan(
                citation_id=citation_id,
                citation_identity_version=str(
                    identity["citation_identity_version"]
                    or CITATION_IDENTITY_VERSION
                ),
                video_id=video_id,
                bvid=str(video["source_id"]),
                title=str(video["title"]),
                source_type=_source_type(
                    str(video.get("subtitle_source") or "unknown")
                ),
                source_language=str(
                    video.get("subtitle_language") or "unknown"
                ),
                source_artifact_id=str(identity["source_artifact_id"]),
                source_version=expected,
                source_version_authority="live_current_exact_replay",
                timeline_run_id=str(identity["timeline_run_id"]),
                segment_ids=segment_ids,
                segment_ordinals=ordinals,
                start_time=start_time,
                end_time=end_time,
                quote_text=quote,
                jump_url=jump_url,
                parent_chunk_ids=(),
                retrieval_provenance=(),
                segments=tuple(
                    EvidenceSegment(
                        segment_id=value.segment_id,
                        original_ordinal=value.original_ordinal,
                        run_local_ordinal=value.run_local_ordinal,
                        start_time=value.start_time,
                        end_time=value.end_time,
                        source_text=value.source_text,
                    )
                    for value in segments
                ),
            )
            return CurrentnessResult(
                outcome="current",
                reason_code="current",
                expected_source_version=expected,
                observed_source_version=observed,
                span=span,
            )
        except EvidenceContractError as exc:
            outcome = (
                "missing"
                if exc.code
                in {
                    "raw_subtitle_missing",
                    "source_unavailable",
                    "citation_source_unavailable",
                }
                else "stale"
                if exc.code == "source_version_mismatch"
                else "invalid"
            )
            return CurrentnessResult(
                outcome=outcome,
                reason_code=exc.code,
                expected_source_version=expected,
                observed_source_version=observed,
                span=None,
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return CurrentnessResult(
                outcome="error",
                reason_code=type(exc).__name__,
                expected_source_version=expected,
                observed_source_version=observed,
                span=None,
            )


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_type(value: str) -> str:
    normalized = value.lower()
    return normalized if normalized in {"human", "ai", "asr"} else "unknown"
