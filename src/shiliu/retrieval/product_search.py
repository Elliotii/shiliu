from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import math
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from shiliu.db import Database
from shiliu.retrieval.consolidation import (
    CONSOLIDATION_VERSION,
    TEMPORAL_MERGE_GAP_SECONDS,
    SearchResultConsolidator,
    VideoResultGroupDraft,
)
from shiliu.retrieval.corpus_search import (
    CorpusSearchContextProjection,
    compose_corpus_search_results,
)
from shiliu.retrieval.enrichment import (
    CHAPTER_ENRICHMENT_VERSION,
    JUMP_ANCHOR_VERSION,
    EvidenceEnricher,
)
from shiliu.retrieval.orchestrator import SearchOrchestrator
from shiliu.retrieval.orchestrator import RawSearchResponse
from shiliu.retrieval.planner import SearchFilterRequest, SearchMode, Scope, SearchRequest


PRESENTATION_VERSION = "v3-product-presentation-v1"
PRODUCT_SEARCH_DEFAULT_MODE: SearchMode = "auto"
PRODUCT_DEFAULT_WIRING_VERSION = "v3-product-search-default-auto-v1"
EXISTING_AUTO_ROUTER_VERSION = "v3-search-planner-auto-v1"


class ProductSearchFilterRequest(SearchFilterRequest):
    """Product-only additive filters; frozen Raw Search keeps its exact contract."""

    uploader_contains: str | None = Field(default=None, max_length=200)

    @field_validator("uploader_contains")
    @classmethod
    def normalize_optional_contains(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_serializer(mode="wrap")
    def serialize_compatibly(self, handler):
        """Keep pre-Stage-5 frozen requests byte-compatible when the new filter is unused."""
        value = handler(self)
        if self.uploader_contains is None:
            value.pop("uploader_contains", None)
        return value

    def retrieval_filters(self):
        return replace(
            super().retrieval_filters(),
            uploader_contains=self.uploader_contains,
        )


class ProductSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    mode: SearchMode = PRODUCT_SEARCH_DEFAULT_MODE
    scope: Scope = "all"
    result_limit: int = Field(default=10, ge=1, le=20)
    max_windows_per_video: int = Field(default=2, ge=1, le=5)
    corpus_task_id: str | None = Field(default=None, min_length=1, max_length=160)
    corpus_aware: bool = True
    filters: ProductSearchFilterRequest = Field(
        default_factory=ProductSearchFilterRequest
    )

    @field_validator("corpus_task_id")
    @classmethod
    def normalize_corpus_task_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("filters", mode="before")
    @classmethod
    def promote_raw_filter_contract(
        cls, value: object
    ) -> object:
        if isinstance(value, SearchFilterRequest) and not isinstance(
            value, ProductSearchFilterRequest
        ):
            return value.model_dump(mode="python")
        return value

    @property
    def default_applied(self) -> bool:
        """Whether the Product API supplied its configured mode default."""
        return "mode" not in self.model_fields_set

    @property
    def original_requested_mode(self) -> SearchMode | None:
        return None if self.default_applied else self.mode

    @model_serializer(mode="wrap")
    def serialize_compatibly(self, handler):
        value = handler(self)
        if self.corpus_task_id is None:
            value.pop("corpus_task_id", None)
        if self.corpus_aware:
            value.pop("corpus_aware", None)
        return value


@dataclass(frozen=True)
class ProductSearchTiming:
    raw_search_ms: float
    grouping_ms: float
    anchor_ms: float
    chapter_ms: float
    presentation_trace_ms: float
    total_ms: float

    def as_dict(self) -> dict[str, float]:
        return {key: round(value, 3) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class ProductVideoResult:
    video_id: int
    bvid: str
    title: str
    uploader: str
    cover_url: str | None
    video_url: str
    detail_url: str
    duration: float | None
    reading_state: str
    marked: bool
    folder_names: tuple[str, ...]
    match_excerpt: str
    best_rank: int
    best_score: float
    best_unit_id: str
    best_unit_type: str
    matched_unit_count: int
    supporting_chunk_count: int
    video_level_hit_present: bool
    retrieval_methods: tuple[str, ...]
    windows: tuple[dict[str, object], ...]
    total_window_count: int
    additional_window_count: int
    unwindowed_chunk_count: int

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["retrieval_methods"] = list(self.retrieval_methods)
        value["folder_names"] = list(self.folder_names)
        value["windows"] = list(self.windows)
        return value


@dataclass(frozen=True)
class ProductSearchResponse:
    trace_id: str
    trace_persisted: bool
    trace_error: dict[str, str] | None
    presentation_trace_persisted: bool
    presentation_trace_error: dict[str, str] | None
    plan: dict[str, object]
    executed_mode: str
    fallback: bool
    fallback_reason: str | None
    requested_result_limit: int
    max_windows_per_video: int
    raw_top_k: int
    raw_hit_count: int
    duplicate_raw_hit_count: int
    unique_video_count: int
    duplicate_occupancy_count: int
    duplicate_occupancy_rate: float
    group_count_before_limit: int
    returned_group_count: int
    results: tuple[ProductVideoResult, ...]
    corpus_context: dict[str, object]
    result_contributions: tuple[dict[str, object], ...]
    warnings: tuple[dict[str, object], ...]
    timing: ProductSearchTiming
    error: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "results": [item.as_dict() for item in self.results],
            "result_contributions": list(self.result_contributions),
            "warnings": list(self.warnings),
            "timing": self.timing.as_dict(),
        }


class ProductSearchError(RuntimeError):
    def __init__(self, message: str, *, trace_id: str | None = None) -> None:
        super().__init__(message)
        self.trace_id = trace_id
        self.code = "product_consolidation_failed"
        self.stage = "grouping"
        self.http_status = 500

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "stage": self.stage,
            "message": str(self)[:500],
            "trace_id": self.trace_id,
        }


class ProductSearchService:
    def __init__(
        self,
        *,
        db: Database,
        raw_search: SearchOrchestrator,
        consolidator: SearchResultConsolidator,
        enricher: EvidenceEnricher,
        persist_trace: bool = True,
    ) -> None:
        self.db = db
        self.raw_search = raw_search
        self.consolidator = consolidator
        self.enricher = enricher
        self.corpus_search = CorpusSearchContextProjection(db)
        self.persist_trace = persist_trace
        if self.persist_trace:
            self.initialize_schema()

    def initialize_schema(self) -> None:
        with self.db.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS retrieval_search_presentations (
                    trace_id TEXT PRIMARY KEY,
                    presentation_version TEXT NOT NULL,
                    consolidation_version TEXT NOT NULL,
                    jump_anchor_version TEXT NOT NULL,
                    chapter_enrichment_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    requested_result_limit INTEGER NOT NULL,
                    max_windows_per_video INTEGER NOT NULL,
                    raw_top_k INTEGER NOT NULL,
                    merge_gap_seconds REAL NOT NULL,
                    raw_hit_count INTEGER NOT NULL,
                    unique_video_count INTEGER NOT NULL,
                    duplicate_raw_hit_count INTEGER NOT NULL,
                    duplicate_occupancy_count INTEGER NOT NULL,
                    duplicate_occupancy_rate REAL NOT NULL,
                    group_count_before_limit INTEGER NOT NULL,
                    returned_group_count INTEGER NOT NULL,
                    total_window_count INTEGER NOT NULL,
                    returned_window_count INTEGER NOT NULL,
                    anchored_window_count INTEGER NOT NULL,
                    chapter_enriched_count INTEGER NOT NULL,
                    grouping_ms REAL NOT NULL,
                    anchor_ms REAL NOT NULL,
                    chapter_ms REAL NOT NULL,
                    presentation_total_ms REAL NOT NULL,
                    presentation_trace_ms REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    error_stage TEXT,
                    error_message TEXT,
                    group_summary_json TEXT NOT NULL DEFAULT '[]',
                    product_default_wiring_version TEXT,
                    requested_mode TEXT,
                    default_applied INTEGER NOT NULL DEFAULT 0,
                    configured_default_mode TEXT,
                    router_invoked INTEGER NOT NULL DEFAULT 0,
                    router_version TEXT,
                    router_decision TEXT,
                    effective_mode TEXT,
                    router_reason_codes_json TEXT NOT NULL DEFAULT '[]',
                    embedding_invoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_retrieval_presentations_created
                    ON retrieval_search_presentations(created_at DESC, trace_id);
                """
            )
            existing_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(retrieval_search_presentations)"
                )
            }
            for name, definition in (
                ("product_default_wiring_version", "TEXT"),
                ("requested_mode", "TEXT"),
                ("default_applied", "INTEGER NOT NULL DEFAULT 0"),
                ("configured_default_mode", "TEXT"),
                ("router_invoked", "INTEGER NOT NULL DEFAULT 0"),
                ("router_version", "TEXT"),
                ("router_decision", "TEXT"),
                ("effective_mode", "TEXT"),
                ("router_reason_codes_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("embedding_invoked", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE retrieval_search_presentations ADD COLUMN {name} {definition}"
                    )

    def search(
        self,
        request: ProductSearchRequest,
        *,
        video_ids: tuple[int, ...] = (),
        principal_id: str | None = None,
    ) -> ProductSearchResponse:
        if video_ids:
            return self.search_with_raw(
                request, video_ids=video_ids, principal_id=principal_id
            )[1]
        return self.search_with_raw(request, principal_id=principal_id)[1]

    def search_with_raw(
        self,
        request: ProductSearchRequest,
        *,
        video_ids: tuple[int, ...] = (),
        principal_id: str | None = None,
    ) -> tuple[RawSearchResponse, ProductSearchResponse]:
        started = time.monotonic()
        raw_top_k = min(100, max(50, request.result_limit * 5))
        raw_started = time.monotonic()
        raw_request = SearchRequest(
            query=request.query,
            mode=request.mode,
            scope=request.scope,
            raw_top_k=raw_top_k,
            filters=request.filters,
        )
        raw = (
            self.raw_search.search_raw(raw_request, video_ids=video_ids)
            if video_ids
            else self.raw_search.search_raw(raw_request)
        )
        product_plan = _product_plan(raw, request)
        raw_ms = _milliseconds(raw_started)
        try:
            grouping_started = time.monotonic()
            consolidated = self.consolidator.consolidate(raw.raw_hits)
            grouping_ms = _milliseconds(grouping_started)
            enriched = self.enricher.enrich(
                consolidated.groups,
                normalized_query=raw.plan.normalized_query,
                query_type=raw.plan.query_type,
            )
            projection = self.corpus_search.project(
                task_id=request.corpus_task_id,
                principal_id=principal_id,
                normalized_query=raw.plan.normalized_query,
                enabled=request.corpus_aware,
            )
            selected, corpus_context, result_contributions = (
                compose_corpus_search_results(
                    consolidated.groups,
                    result_limit=request.result_limit,
                    projection=projection,
                )
            )
            display_metadata = self._display_metadata(
                [group.video_id for group in selected]
            )
            results = tuple(
                _product_result(
                    group,
                    request.max_windows_per_video,
                    display_metadata.get(group.video_id, {}),
                )
                for group in selected
            )
        except Exception as exc:
            raise ProductSearchError(
                f"{type(exc).__name__}: {exc}", trace_id=raw.trace_id
            ) from exc

        raw_hit_count = len(raw.raw_hits)
        duplicate_occupancy = raw_hit_count - consolidated.unique_video_count
        rate = duplicate_occupancy / raw_hit_count if raw_hit_count else 0.0
        warnings = list(enriched.warnings)
        for group in consolidated.groups:
            warnings.extend({"video_id": group.video_id, **warning} for warning in group.warnings)
        presentation_ms = grouping_ms + enriched.anchor_ms + enriched.chapter_ms
        provisional_timing = ProductSearchTiming(
            raw_search_ms=raw_ms,
            grouping_ms=grouping_ms,
            anchor_ms=enriched.anchor_ms,
            chapter_ms=enriched.chapter_ms,
            presentation_trace_ms=0.0,
            total_ms=_milliseconds(started),
        )
        response = ProductSearchResponse(
            trace_id=raw.trace_id,
            trace_persisted=raw.trace_persisted,
            trace_error=raw.trace_error,
            presentation_trace_persisted=False,
            presentation_trace_error=None,
            plan=product_plan,
            executed_mode=raw.executed_mode,
            fallback=raw.fallback,
            fallback_reason=raw.fallback_reason,
            requested_result_limit=request.result_limit,
            max_windows_per_video=request.max_windows_per_video,
            raw_top_k=raw_top_k,
            raw_hit_count=raw_hit_count,
            duplicate_raw_hit_count=consolidated.duplicate_raw_hit_count,
            unique_video_count=consolidated.unique_video_count,
            duplicate_occupancy_count=duplicate_occupancy,
            duplicate_occupancy_rate=round(rate, 6),
            group_count_before_limit=len(consolidated.groups),
            returned_group_count=len(results),
            results=results,
            corpus_context=corpus_context,
            result_contributions=result_contributions,
            warnings=tuple(warnings),
            timing=provisional_timing,
        )
        if not self.persist_trace:
            return raw, response
        trace_started = time.monotonic()
        try:
            self._persist_presentation(
                response,
                consolidated_total_windows=consolidated.total_window_count,
                anchored_window_count=enriched.anchored_window_count,
                chapter_enriched_count=enriched.chapter_enriched_count,
                presentation_total_ms=presentation_ms,
            )
        except Exception as exc:
            trace_ms = _milliseconds(trace_started)
            return raw, _replace_response_timing(
                response, started=started, trace_ms=trace_ms, persisted=False,
                error={"code": "presentation_trace_persistence_failed",
                       "message": f"{type(exc).__name__}: {exc}"[:300]},
            )
        trace_ms = _milliseconds(trace_started)
        return raw, _replace_response_timing(
            response, started=started, trace_ms=trace_ms, persisted=True, error=None
        )

    def _display_metadata(
        self, video_ids: list[int]
    ) -> dict[int, dict[str, object]]:
        if not video_ids:
            return {}
        placeholders = ",".join("?" for _ in video_ids)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT v.id, v.cover_url, v.cover_path, v.reading_state, v.is_marked,
                       s.folder_title
                FROM videos v
                LEFT JOIN video_source_memberships m
                  ON m.video_id=v.id AND m.removed_at IS NULL
                LEFT JOIN favorite_sources s ON s.id=m.source_id
                WHERE v.id IN ({placeholders})
                ORDER BY v.id, s.sort_order, s.id
                """,
                video_ids,
            ).fetchall()
        result: dict[int, dict[str, object]] = {}
        for row in rows:
            video_id = int(row["id"])
            value = result.setdefault(
                video_id,
                {
                    "cover_url": (
                        f"/media/{video_id}/cover"
                        if row["cover_path"]
                        else _absolute_cover_url(row["cover_url"])
                    ),
                    "detail_url": f"/videos/{video_id}/transcript",
                    "reading_state": str(row["reading_state"] or "unread"),
                    "marked": bool(row["is_marked"]),
                    "folder_names": [],
                },
            )
            title = str(row["folder_title"] or "").strip()
            folders = value["folder_names"]
            if title and isinstance(folders, list) and title not in folders:
                folders.append(title)
        return result

    def get_presentation(self, trace_id: str) -> dict[str, object] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM retrieval_search_presentations WHERE trace_id=?",
                (trace_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["group_summary"] = json.loads(str(result.pop("group_summary_json")))
        result["router_reason_codes"] = json.loads(
            str(result.pop("router_reason_codes_json"))
        )
        for name in ("default_applied", "router_invoked", "embedding_invoked"):
            result[name] = bool(result[name])
        return result

    def _persist_presentation(
        self,
        response: ProductSearchResponse,
        *,
        consolidated_total_windows: int,
        anchored_window_count: int,
        chapter_enriched_count: int,
        presentation_total_ms: float,
    ) -> None:
        returned_windows = sum(len(group.windows) for group in response.results)
        summary = [_trace_group(group) for group in response.results]
        values = (
            response.trace_id,
            PRESENTATION_VERSION,
            CONSOLIDATION_VERSION,
            JUMP_ANCHOR_VERSION,
            CHAPTER_ENRICHMENT_VERSION,
            datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            response.requested_result_limit,
            response.max_windows_per_video,
            response.raw_top_k,
            TEMPORAL_MERGE_GAP_SECONDS,
            response.raw_hit_count,
            response.unique_video_count,
            response.duplicate_raw_hit_count,
            response.duplicate_occupancy_count,
            response.duplicate_occupancy_rate,
            response.group_count_before_limit,
            response.returned_group_count,
            consolidated_total_windows,
            returned_windows,
            anchored_window_count,
            chapter_enriched_count,
            response.timing.grouping_ms,
            response.timing.anchor_ms,
            response.timing.chapter_ms,
            presentation_total_ms,
            0.0,
            "success",
            None,
            None,
            json.dumps(summary, ensure_ascii=False),
            PRODUCT_DEFAULT_WIRING_VERSION,
            response.plan["requested_mode"],
            int(bool(response.plan["default_applied"])),
            response.plan["configured_default_mode"],
            int(bool(response.plan["router_invoked"])),
            response.plan["router_version"],
            response.plan["router_decision"],
            response.plan["effective_mode"],
            json.dumps(response.plan["router_reason_codes"], ensure_ascii=False),
            int(bool(response.plan["embedding_invoked"])),
        )
        trace_started = time.monotonic()
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_search_presentations(
                    trace_id, presentation_version, consolidation_version,
                    jump_anchor_version, chapter_enrichment_version, created_at,
                    requested_result_limit, max_windows_per_video, raw_top_k,
                    merge_gap_seconds, raw_hit_count, unique_video_count,
                    duplicate_raw_hit_count, duplicate_occupancy_count,
                    duplicate_occupancy_rate, group_count_before_limit,
                    returned_group_count, total_window_count, returned_window_count,
                    anchored_window_count, chapter_enriched_count, grouping_ms,
                    anchor_ms, chapter_ms, presentation_total_ms,
                    presentation_trace_ms, status, error_stage, error_message,
                    group_summary_json, product_default_wiring_version,
                    requested_mode, default_applied, configured_default_mode,
                    router_invoked, router_version, router_decision, effective_mode,
                    router_reason_codes_json, embedding_invoked
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                values,
            )
            trace_ms = _milliseconds(trace_started)
            connection.execute(
                "UPDATE retrieval_search_presentations SET presentation_trace_ms=? WHERE trace_id=?",
                (trace_ms, response.trace_id),
            )


def _product_plan(raw: RawSearchResponse, request: ProductSearchRequest) -> dict[str, object]:
    """Expose Product-request provenance alongside the existing resolved raw plan."""
    plan = raw.plan.as_dict()
    router_invoked = request.mode == "auto"
    plan.update(
        {
            "requested_mode": request.original_requested_mode,
            "resolved_requested_mode": request.mode,
            "default_applied": request.default_applied,
            "configured_default_mode": (
                PRODUCT_SEARCH_DEFAULT_MODE if request.default_applied else None
            ),
            "router_invoked": router_invoked,
            "router_version": EXISTING_AUTO_ROUTER_VERSION if router_invoked else None,
            "router_decision": raw.plan.planned_mode if router_invoked else None,
            "effective_mode": raw.executed_mode,
            "router_reason_codes": [raw.plan.routing_reason] if router_invoked else [],
            "embedding_invoked": raw.executed_mode in {"dense", "hybrid"},
            "product_default_wiring_version": PRODUCT_DEFAULT_WIRING_VERSION,
        }
    )
    return plan


def _product_result(
    group: VideoResultGroupDraft,
    max_windows: int,
    display_metadata: dict[str, object],
) -> ProductVideoResult:
    displayed_values: list[dict[str, object]] = []
    for window in group.windows[:max_windows]:
        value = window.as_dict()
        value["jump_url"] = build_bilibili_jump_url(
            group.video_url, group.bvid, window.jump_time
        )
        displayed_values.append(value)
    displayed = tuple(displayed_values)
    chunks = [hit for hit in group.hits if hit.unit_type == "transcript_chunk"]
    return ProductVideoResult(
        video_id=group.video_id,
        bvid=group.bvid,
        title=group.title,
        uploader=group.uploader,
        cover_url=(
            str(display_metadata["cover_url"])
            if display_metadata.get("cover_url")
            else None
        ),
        video_url=group.video_url,
        detail_url=str(
            display_metadata.get("detail_url") or f"/videos/{group.video_id}/transcript"
        ),
        duration=group.duration,
        reading_state=str(display_metadata.get("reading_state") or "unread"),
        marked=bool(display_metadata.get("marked")),
        folder_names=tuple(
            str(value) for value in display_metadata.get("folder_names", ())
        ),
        match_excerpt=group.best_hit.excerpt[:300],
        best_rank=group.best_hit.rank,
        best_score=group.best_hit.score,
        best_unit_id=group.best_hit.unit_id,
        best_unit_type=group.best_hit.unit_type,
        matched_unit_count=len(group.hits),
        supporting_chunk_count=len(chunks),
        video_level_hit_present=any(hit.unit_type == "video" for hit in group.hits),
        retrieval_methods=group.retrieval_methods,
        windows=displayed,
        total_window_count=len(group.windows),
        additional_window_count=max(0, len(group.windows) - len(displayed)),
        unwindowed_chunk_count=group.unwindowed_chunk_count,
    )


def build_bilibili_jump_url(
    video_url: str | None, bvid: str | None, jump_time: float | int | None
) -> str | None:
    """Return a stable Bilibili URL with an integer-second ``t`` parameter."""
    base = str(video_url or "").strip()
    identity = str(bvid or "").strip()
    if not base and identity:
        base = f"https://www.bilibili.com/video/{identity}"
    if base.startswith("//"):
        base = "https:" + base
    if not base:
        return None
    try:
        seconds = max(0, math.floor(float(jump_time or 0)))
    except (TypeError, ValueError, OverflowError):
        seconds = 0
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "t"]
    query.append(("t", str(seconds)))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _absolute_cover_url(value: object) -> str | None:
    url = str(value or "").strip()
    if url.startswith("//"):
        return "https:" + url
    return url or None


def _trace_group(group: ProductVideoResult) -> dict[str, object]:
    return {
        "video_id": group.video_id,
        "best_rank": group.best_rank,
        "matched_unit_count": group.matched_unit_count,
        "additional_window_count": group.additional_window_count,
        "windows": [
            {
                "window_start": window["window_start"],
                "window_end": window["window_end"],
                "jump_time": window["jump_time"],
                "best_chunk_id": window["best_chunk_id"],
                "component_chunk_ids": window["component_chunk_ids"],
                "chapter_title": (
                    window["chapter"].get("title") if window.get("chapter") else None
                ),
            }
            for window in group.windows
        ],
    }


def _replace_response_timing(
    response: ProductSearchResponse,
    *,
    started: float,
    trace_ms: float,
    persisted: bool,
    error: dict[str, str] | None,
) -> ProductSearchResponse:
    timing = ProductSearchTiming(
        raw_search_ms=response.timing.raw_search_ms,
        grouping_ms=response.timing.grouping_ms,
        anchor_ms=response.timing.anchor_ms,
        chapter_ms=response.timing.chapter_ms,
        presentation_trace_ms=trace_ms,
        total_ms=_milliseconds(started),
    )
    values = {
        **response.__dict__,
        "presentation_trace_persisted": persisted,
        "presentation_trace_error": error,
        "timing": timing,
    }
    return ProductSearchResponse(**values)


def _milliseconds(started: float) -> float:
    return (time.monotonic() - started) * 1000
