from __future__ import annotations

import json
import base64
import binascii
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from shiliu.artifacts import ArtifactStore, extract_urls
from shiliu.assistant.contracts import MaterialDescriptor, SourceView, ToolResult
from shiliu.assistant.snapshots import CapturedSource, SourceSnapshotStore
from shiliu.db import Database
from shiliu.domain import VideoBundle
from shiliu.retrieval.product_search import ProductSearchRequest, ProductSearchService


DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class SourceScope:
    source_db_ids: frozenset[int] = frozenset()
    video_ids: frozenset[int] = frozenset()
    all_active: bool = False


class MetadataAdapter(Protocol):
    def fetch_video_metadata(self, bvid: str) -> VideoBundle: ...


class CollectionSourceService:
    def __init__(
        self,
        *,
        db: Database,
        artifacts: ArtifactStore,
        snapshots: SourceSnapshotStore,
        product_search: ProductSearchService | None = None,
        metadata_adapter: MetadataAdapter | None = None,
    ) -> None:
        self.db = db
        self.artifacts = artifacts
        self.snapshots = snapshots
        self.product_search = product_search
        self.metadata_adapter = metadata_adapter
        self._coverage_cache: tuple[str, float, dict[str, int]] | None = None

    def visible_video_ids(
        self,
        scope: SourceScope,
        *,
        order: Literal["id", "collected_desc"] = "id",
    ) -> list[int]:
        allowed_sources = self._allowed_sources(scope, None)
        if not allowed_sources:
            return []
        values, _unknown = self._candidate_video_ids(
            allowed_sources,
            published_from=None,
            published_to=None,
            collected_from=None,
            collected_to=None,
            uploader=None,
            order=order,
            video_ids=scope.video_ids,
        )
        return values

    def source_refs_visible(self, source_refs: list[str], scope: SourceScope) -> bool:
        allowed_sources = self._allowed_sources(scope, None)
        for source_ref in source_refs:
            if not source_ref.startswith("video:"):
                continue
            try:
                video_id, _revision = _parse_source_ref(source_ref)
            except ValueError:
                return False
            if not self._video_is_available(video_id, allowed_sources, scope=scope):
                return False
        return True

    def search(
        self,
        *,
        call_id: str,
        scope: SourceScope,
        query: str | None = None,
        query_variants: list[str] | None = None,
        require_transcript: bool = False,
        mode: Literal["auto", "metadata", "content"] = "auto",
        cursor: str | None = None,
        scope_version: int = 1,
        folder_ids: set[int] | None = None,
        published_from: int | None = None,
        published_to: int | None = None,
        collected_from: int | None = None,
        collected_to: int | None = None,
        uploader: str | None = None,
        sort: Literal["relevance", "collected_desc", "published_desc"] = "relevance",
        limit: int = 10,
    ) -> ToolResult:
        if limit < 1 or limit > 10:
            return ToolResult(
                call_id=call_id, status="invalid_arguments", summary="limit 必须在 1 到 10 之间",
                error_code="invalid_limit",
            )
        allowed_sources = self._allowed_sources(scope, folder_ids)
        if not allowed_sources:
            if cursor:
                return ToolResult(call_id=call_id, status="invalid_arguments",
                    summary="范围已变化，请从第一页重新查询", error_code="cursor_scope_mismatch")
            return ToolResult(
                call_id=call_id, status="empty", summary="当前 Space 没有可搜索的活跃收藏范围",
                error_code="empty_scope",
                coverage={"mode": mode, "visible_count": 0, "exhaustive": True,
                          "unknown_published_count": 0},
            )
        candidate_ids, unknown_published = self._candidate_video_ids(
            allowed_sources,
            published_from=published_from,
            published_to=published_to,
            collected_from=collected_from,
            collected_to=collected_to,
            uploader=uploader,
            video_ids=scope.video_ids,
        )
        pre_material_candidate_count = len(candidate_ids)
        if require_transcript:
            candidate_ids = self._transcript_available_ids(candidate_ids)
        if not candidate_ids:
            if cursor:
                return ToolResult(call_id=call_id, status="invalid_arguments",
                    summary="范围或筛选结果已变化，请从第一页重新查询", error_code="cursor_scope_mismatch")
            return ToolResult(
                call_id=call_id,
                status="empty",
                summary=f"范围内没有匹配视频；其中 {unknown_published} 个视频发布时间未知",
                error_code="no_matches",
                coverage={"mode": mode, "visible_count": 0, "exhaustive": True,
                          "unknown_published_count": unknown_published,
                          "sort": sort, "scope_version": scope_version,
                          "require_transcript": require_transcript,
                          "pre_material_candidate_count": pre_material_candidate_count},
            )
        normalized_query = " ".join((query or "").split())
        variants = list(dict.fromkeys(
            " ".join(value.split()) for value in [normalized_query, *(query_variants or [])]
            if value.strip()
        ))
        if len(variants) > 3 or any(len(value) > 2000 for value in variants):
            return ToolResult(call_id=call_id, status="invalid_arguments",
                              summary="最多三条有界查询", error_code="query_variants_limit")
        resolved_mode = ("content" if normalized_query else "metadata") if mode == "auto" else mode
        if resolved_mode == "content" and not normalized_query:
            return ToolResult(call_id=call_id, status="invalid_arguments", summary="内容检索需要 query", error_code="query_required")
        coverage: dict[str, Any] = {
            "mode": resolved_mode, "visible_count": len(candidate_ids),
            "unknown_published_count": unknown_published,
            "sort": sort, "scope_version": scope_version,
            "material_counts_for": "filtered_candidates",
            "require_transcript": require_transcript,
            "pre_material_candidate_count": pre_material_candidate_count,
        }
        if resolved_mode == "metadata":
            if query_variants:
                return ToolResult(call_id=call_id, status="invalid_arguments",
                                  summary="元数据分页只接受一条查询", error_code="variants_not_supported")
            if normalized_query:
                candidate_ids = self._metadata_matching_ids(candidate_ids, normalized_query)
            ordered = self._ordered_metadata_ids(candidate_ids, allowed_sources, sort,
                collected_from=collected_from, collected_to=collected_to)
            fingerprint = hashlib.sha256(json.dumps(
                {"ids": ordered, "query": normalized_query, "sources": sorted(allowed_sources),
                 "filters": [published_from, published_to, collected_from, collected_to, uploader,
                             require_transcript],
                 "sort": sort, "scope_version": scope_version},
                ensure_ascii=False, separators=(",", ":"),
            ).encode()).hexdigest()
            offset = 0
            if cursor:
                try:
                    if cursor.startswith("m1:"):
                        _, signature, raw_offset = cursor.split(":", 2)
                        if signature != fingerprint[:16]:
                            raise ValueError("stale cursor")
                        offset = int(raw_offset)
                    else:
                        # Legacy U-A cursors remain readable.
                        cursor_data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                        if cursor_data["v"] != 1 or cursor_data["fingerprint"] != fingerprint:
                            raise ValueError("stale cursor")
                        offset = int(cursor_data["offset"])
                    if offset < 0 or offset > len(ordered):
                        raise ValueError("invalid offset")
                except (ValueError, KeyError, TypeError, binascii.Error):
                    return ToolResult(call_id=call_id, status="invalid_arguments", summary="范围或排序已变化，请从第一页重新查询", error_code="cursor_scope_mismatch")
            cached = self._coverage_cache
            if cached is not None and cached[0] == fingerprint and time.monotonic() - cached[1] < 30:
                coverage.update(cached[2])
            else:
                material_coverage = self._material_coverage(candidate_ids)
                self._coverage_cache = (fingerprint, time.monotonic(), material_coverage)
                coverage.update(material_coverage)
            page = ordered[offset:offset + limit]
            items = [self._card(video_id, allowed_source_ids=allowed_sources) for video_id in page]
            next_offset = offset + len(page)
            next_cursor = f"m1:{fingerprint[:16]}:{next_offset}" if next_offset < len(ordered) else None
            coverage.update({"matched_count": len(ordered), "exhaustive": True,
                             "has_more": next_cursor is not None,
                             "sort_basis": "collected_desc" if sort == "relevance" else sort})
            return ToolResult(call_id=call_id, status="ok" if items else "empty",
                summary=f"元数据匹配 {len(ordered)} 项，本页 {len(items)} 项；{unknown_published} 个视频发布时间未知",
                items=items, source_refs=[str(item["source_ref"]) for item in items],
                next_cursor=next_cursor, coverage=coverage)
        if cursor:
            return ToolResult(call_id=call_id, status="invalid_arguments", summary="内容候选检索不支持分页游标", error_code="cursor_not_supported")
        coverage.update(self._material_coverage(candidate_ids))
        coverage_note = ""
        if self.product_search is not None:
            retrieval_limit = min(20, max(limit, 12)) if sort != "relevance" else limit
            ranked: dict[int, dict[str, Any]] = {}
            retrieval_details: list[dict[str, Any]] = []
            for variant in variants:
                results_for_query, raw = self._product_results(
                    query=variant, candidate_ids=candidate_ids,
                    result_limit=retrieval_limit,
                )
                retrieval_details.append({
                    "query": variant,
                    "executed_mode": getattr(raw, "executed_mode", "unknown"),
                    "fallback": bool(getattr(raw, "fallback", False)),
                    "fallback_reason": getattr(raw, "fallback_reason", None),
                    "raw_search_ms": getattr(getattr(raw, "timing", None), "total_ms", None),
                    "candidate_count": len(results_for_query),
                })
                for rank, result in enumerate(results_for_query, start=1):
                    video_id = int(result.video_id)
                    entry = ranked.setdefault(video_id, {
                        "result": result, "score": 0.0, "matches": [],
                    })
                    # Rank fusion avoids comparing scores from different retrieval paths.
                    entry["score"] += 1.0 / (20 + rank)
                    entry["matches"].append({"query": variant, "rank": rank})
            ranked_items = sorted(ranked.items(), key=lambda pair: (-pair[1]["score"], pair[0]))
            results = [entry["result"] for _, entry in ranked_items[:retrieval_limit]]
            if sort == "relevance":
                items = [
                    self._card(
                        int(result.video_id),
                        allowed_source_ids=allowed_sources,
                        excerpt=result.match_excerpt,
                    )
                    for result in results
                ][:limit]
                for item in items:
                    item["match_basis"] = ranked[int(item["video_id"])]["matches"]
            else:
                excerpts = {
                    int(result.video_id): result.match_excerpt
                    for result in results
                }
                items = self._metadata_cards(
                    list(excerpts),
                    allowed_source_ids=allowed_sources,
                    sort=sort,
                    limit=limit,
                    excerpts=excerpts,
                    collected_from=collected_from,
                    collected_to=collected_to,
                )
                label = "收藏时间" if sort == "collected_desc" else "发布时间"
                coverage_note = (
                    f"；先取得最多 {retrieval_limit} 个内容匹配候选，再按{label}排序，"
                    "不是对范围内全部关键词命中的穷尽排序"
                )
        else:
            return ToolResult(call_id=call_id, status="unavailable", summary="内容检索器不可用；可使用 mode=metadata 查找标题、作者和时间", error_code="content_search_unavailable", coverage=coverage)
        coverage.update({"candidate_limit": retrieval_limit, "exhaustive": False,
                         "sort_basis": "rank_fusion" if sort == "relevance" else f"candidate_{sort}",
                         "retrieval_requests": len(variants),
                         "retrieval_candidate_count": len(ranked),
                         "query_variants": variants,
                         "retrieval_details": retrieval_details,
                         "candidate_coverage": "top_k_not_exhaustive"})
        return ToolResult(
            call_id=call_id,
            status="ok" if items else "empty",
            summary=(
                f"返回 {len(items)} 个视频；范围内 {unknown_published} 个视频发布时间未知"
                f"{coverage_note}"
            ),
            items=items,
            source_refs=[str(item["source_ref"]) for item in items],
            coverage=coverage,
        )

    def _product_results(
        self, *, query: str, candidate_ids: list[int], result_limit: int
    ) -> tuple[list[Any], Any]:
        """Search an assistant scope without leaking the deep-search eight-video bound."""
        if self.product_search is None:
            return [], None
        raw, response = self.product_search.search_with_raw(
            ProductSearchRequest(
                query=query, result_limit=min(20, result_limit),
                max_windows_per_video=2, corpus_aware=False,
            ),
            scope_video_ids=tuple(candidate_ids), principal_id="local_operator",
        )
        return list(response.results), raw

    def _material_coverage(self, video_ids: list[int]) -> dict[str, int]:
        if not video_ids:
            return {"body_available_count": 0, "body_indexed_count": 0,
                    "indexed_video_count": 0}
        with self.db.connect() as connection:
            rows = connection.execute(
                f"SELECT id, source_id FROM videos WHERE id IN ({','.join('?' for _ in video_ids)})",
                video_ids,
            ).fetchall()
            indexed = []
            body_indexed = 0
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='retrieval_units'").fetchone():
                indexed = connection.execute(
                    f"SELECT unit_type, COUNT(DISTINCT video_id) AS n FROM retrieval_units WHERE removed_at IS NULL AND video_id IN ({','.join('?' for _ in video_ids)}) GROUP BY unit_type",
                    video_ids,
                ).fetchall()
                body_indexed = int(connection.execute(
                    f"SELECT COUNT(DISTINCT video_id) FROM retrieval_units WHERE removed_at IS NULL "
                    f"AND video_id IN ({','.join('?' for _ in video_ids)}) "
                    "AND (unit_type='transcript_chunk' OR instr(source_text, '[Summary')>0 "
                    "OR instr(source_text, '[Cleaned Transcript')>0)",
                    video_ids,
                ).fetchone()[0])
        counts = {str(row["unit_type"]): int(row["n"]) for row in indexed}
        available = 0
        for row in rows:
            directory = self.artifacts.videos_dir / str(row["source_id"])
            if (directory / "subtitle-raw.txt").is_file() or any(directory.glob("transcript*.md")) or any(directory.glob("summary*.md")):
                available += 1
        return {"body_available_count": available,
                "body_indexed_count": body_indexed,
                "indexed_video_count": counts.get("video", 0)}

    def _transcript_available_ids(self, video_ids: list[int]) -> list[int]:
        if not video_ids:
            return []
        with self.db.connect() as connection:
            rows = connection.execute(
                f"SELECT id,raw_subtitle_path,transcript_path FROM videos WHERE id IN ({','.join('?' for _ in video_ids)})",
                video_ids,
            ).fetchall()
        available = {int(row["id"]) for row in rows if any(
            self._managed_exists(value)
            for value in (row["raw_subtitle_path"], row["transcript_path"])
        )}
        return [value for value in video_ids if value in available]

    def _managed_exists(self, value: Any) -> bool:
        if not value:
            return False
        try:
            self.artifacts.managed_file(str(value))
            return True
        except (ValueError, FileNotFoundError, OSError):
            return False

    def _metadata_matching_ids(self, video_ids: list[int], query: str) -> list[int]:
        tokens = [token.casefold() for token in query.split() if token]
        with self.db.connect() as connection:
            rows = connection.execute(
                f"SELECT id, title, uploader FROM videos WHERE id IN ({','.join('?' for _ in video_ids)})",
                video_ids,
            ).fetchall()
        return [int(row["id"]) for row in rows if all(
            token in f"{row['title']} {row['uploader']}".casefold() for token in tokens
        )]

    def _ordered_metadata_ids(self, video_ids: list[int], allowed_source_ids: set[int], sort: str,
                              *, collected_from: int | None = None, collected_to: int | None = None) -> list[int]:
        if not video_ids:
            return []
        order = {
            "published_desc": "v.published_at IS NULL, v.published_at DESC, v.id DESC",
            "collected_desc": "MAX(m.favorite_time) IS NULL, MAX(m.favorite_time) DESC, v.id DESC",
            "relevance": "MAX(m.favorite_time) IS NULL, MAX(m.favorite_time) DESC, v.id DESC",
        }[sort]
        time_filter = ""
        time_params: list[int] = []
        if collected_from is not None:
            time_filter += " AND m.favorite_time>=?"
            time_params.append(collected_from)
        if collected_to is not None:
            time_filter += " AND m.favorite_time<=?"
            time_params.append(collected_to)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"SELECT v.id FROM videos v JOIN video_source_memberships m ON m.video_id=v.id AND m.removed_at IS NULL AND m.source_id IN ({','.join('?' for _ in allowed_source_ids)}){time_filter} WHERE v.id IN ({','.join('?' for _ in video_ids)}) GROUP BY v.id ORDER BY {order}",
                [*sorted(allowed_source_ids), *time_params, *video_ids],
            ).fetchall()
        return [int(row["id"]) for row in rows]

    def read(
        self,
        *,
        call_id: str,
        scope: SourceScope,
        source_ref: str,
        view: Literal["overview", "description", "summary", "notes", "transcript"] = "overview",
        revision: str | None = None,
        cursor: str | None = None,
        query: str | None = None,
        max_characters: int = 8000,
    ) -> ToolResult:
        try:
            video_id, ref_revision = _parse_source_ref(source_ref)
        except ValueError:
            return ToolResult(
                call_id=call_id, status="invalid_arguments", summary="source_ref 无效",
                error_code="invalid_source_ref",
            )
        if revision is not None and ref_revision is not None and revision != ref_revision:
            return ToolResult(
                call_id=call_id,
                status="invalid_arguments",
                summary="source_ref 中的版本与 revision 参数冲突",
                error_code="revision_conflict",
            )
        resolved_revision = ref_revision or revision
        if max_characters < 1 or max_characters > 12000:
            return ToolResult(call_id=call_id, status="invalid_arguments",
                              summary="单次读取限 1 至 12000 字符", error_code="read_budget_invalid")
        if query and cursor:
            return ToolResult(call_id=call_id, status="invalid_arguments",
                              summary="相关段落定位与顺序续读不能同时使用", error_code="query_cursor_conflict")
        offset = 0
        if cursor is not None:
            try:
                cursor_value = _decode_read_cursor(cursor)
            except ValueError:
                return ToolResult(
                    call_id=call_id,
                    status="invalid_arguments",
                    summary="cursor 无效",
                    error_code="invalid_cursor",
                )
            if cursor_value["video_id"] != video_id or cursor_value["view"] != view:
                return ToolResult(
                    call_id=call_id,
                    status="invalid_arguments",
                    summary="cursor 与来源或读取视图不匹配",
                    error_code="cursor_scope_mismatch",
                )
            if resolved_revision is not None and resolved_revision != cursor_value["revision"]:
                return ToolResult(
                    call_id=call_id,
                    status="invalid_arguments",
                    summary="cursor 与来源版本冲突",
                    error_code="revision_conflict",
                )
            resolved_revision = cursor_value["revision"]
            offset = cursor_value["offset"]
        allowed_sources = self._allowed_sources(scope, None)
        if not self._video_is_available(video_id, allowed_sources, scope=scope):
            return ToolResult(
                call_id=call_id, status="unavailable", summary="该来源不在当前 Space 范围内",
                error_code="source_out_of_scope",
            )
        try:
            captured = self._capture_or_load(video_id, resolved_revision)
        except KeyError:
            return ToolResult(
                call_id=call_id,
                status="unavailable",
                summary="指定的来源版本不存在或已不可用",
                error_code="source_revision_not_found",
            )
        view_model = self._source_view(
            captured,
            allowed_source_ids=allowed_sources,
            view=view,
            offset=offset,
            max_characters=max_characters,
            query=query,
        )
        position = view_model.provenance.get("content_position", {})
        end_offset = int(position.get("end") or 0)
        total_characters = int(position.get("total") or 0)
        truncated = end_offset < total_characters
        stable_ref = f"video:{video_id}:{captured.revision}"
        next_cursor = (
            _encode_read_cursor(
                video_id=video_id,
                revision=captured.revision,
                view=view,
                offset=end_offset,
            )
            if truncated
            else None
        )
        available_views = [
            "transcript" if material.kind == "raw_subtitle" else material.kind
            for material in view_model.materials if material.available
        ]
        available_views = sorted(set(available_views))
        requested_empty = view != "overview" and (view_model.content or "").strip() in {"", "-", "—"}
        if requested_empty:
            summary = f"本轮请求的 {view} 视图没有正文；可用视图：{', '.join(available_views) or '无'}。不能据此断言其他视图也为空"
        else:
            summary = f"已读取 {view}；覆盖范围为 {view_model.coverage}"
        return ToolResult(
            call_id=call_id,
            status="empty" if requested_empty else "ok",
            summary=summary,
            items=[view_model.model_dump(mode="json")],
            result_ref=f"assistant-object:{captured.snapshot_ref}",
            source_refs=[stable_ref],
            truncated=truncated,
            next_cursor=next_cursor,
            coverage={"requested_view": view, "requested_view_has_content": not requested_empty,
                      "available_views": available_views,
                      "body_coverage": view_model.coverage,
                      "read_position": position,
                      "read_complete": bool(total_characters == end_offset and not query),
                      "selection": "relevant_span" if query else "sequential",
                      "model_delivery": "pending_context_projection"},
        )

    def refresh_metadata(
        self, *, call_id: str, scope: SourceScope, source_ref: str
    ) -> ToolResult:
        try:
            video_id, ref_revision = _parse_source_ref(source_ref)
        except ValueError:
            return ToolResult(
                call_id=call_id, status="invalid_arguments", summary="source_ref 无效",
                error_code="invalid_source_ref",
            )
        if ref_revision is not None:
            return ToolResult(
                call_id=call_id,
                status="invalid_arguments",
                summary="版本化来源引用不可用于刷新；请使用 video:{id} 基础引用",
                error_code="versioned_ref_not_refreshable",
            )
        allowed_sources = self._allowed_sources(scope, None)
        if not self._video_is_available(video_id, allowed_sources, scope=scope):
            return ToolResult(
                call_id=call_id, status="unavailable", summary="该来源不在当前 Space 范围内",
                error_code="source_out_of_scope",
            )
        if self.metadata_adapter is None:
            return ToolResult(
                call_id=call_id, status="unavailable", summary="元数据刷新适配器未配置",
                error_code="metadata_refresh_unavailable",
            )
        video = self.db.get_video(video_id)
        if video is None:
            raise KeyError(video_id)
        bundle = self.metadata_adapter.fetch_video_metadata(str(video["source_id"]))
        self.artifacts.save_metadata(bundle)
        self.db.update_video(
            video_id,
            title=bundle.title,
            uploader=bundle.uploader,
            uploader_id=bundle.uploader_id,
            description=bundle.description,
            description_links_json=json.dumps(extract_urls(bundle.description), ensure_ascii=False),
            video_url=bundle.video_url,
            cover_url=bundle.cover_url,
            cid=bundle.cid,
            part_title=bundle.part_title,
            duration_seconds=bundle.duration_seconds,
            page_count=bundle.page_count,
            published_at=bundle.published_at,
            metadata_observed_at=bundle.metadata_observed_at,
        )
        captured = self.snapshots.capture(video_id)
        return ToolResult(
            call_id=call_id, status="ok", summary="视频元数据已轻量刷新；未读取字幕、未触发 ASR 或摘要",
            result_ref=f"assistant-object:{captured.snapshot_ref}",
            source_refs=[f"video:{video_id}:{captured.revision}"],
        )

    def _video_is_available(
        self,
        video_id: int,
        allowed_sources: set[int],
        *,
        scope: SourceScope | None = None,
    ) -> bool:
        if not allowed_sources or not self.db.video_has_active_source(
            video_id, allowed_source_ids=allowed_sources
        ):
            return False
        if scope is not None and scope.video_ids and video_id not in scope.video_ids:
            return False
        video = self.db.get_video(video_id)
        return bool(
            video is not None
            and not bool(video.get("is_ignored"))
            and video.get("archived_at") is None
        )

    def _allowed_sources(
        self, scope: SourceScope, requested_folder_ids: set[int] | None
    ) -> set[int]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT id, folder_id FROM favorite_sources WHERE status='active'"
            ).fetchall()
        active = {int(row["id"]): int(row["folder_id"]) for row in rows}
        allowed = set(active) if scope.all_active else set(scope.source_db_ids) & set(active)
        if requested_folder_ids is not None:
            allowed = {source_id for source_id in allowed if active[source_id] in requested_folder_ids}
        return allowed

    def _candidate_video_ids(
        self,
        source_ids: set[int],
        *,
        published_from: int | None,
        published_to: int | None,
        collected_from: int | None,
        collected_to: int | None,
        uploader: str | None,
        order: Literal["id", "collected_desc"] = "id",
        video_ids: frozenset[int] = frozenset(),
    ) -> tuple[list[int], int]:
        placeholders = ",".join("?" for _ in source_ids)
        conditions = [
            f"m.source_id IN ({placeholders})", "m.removed_at IS NULL", "s.status='active'",
            "v.is_ignored=0", "v.archived_at IS NULL",
        ]
        params: list[Any] = sorted(source_ids)
        if video_ids:
            conditions.append(f"v.id IN ({','.join('?' for _ in video_ids)})")
            params.extend(sorted(video_ids))
        if collected_from is not None:
            conditions.append("m.favorite_time>=?")
            params.append(collected_from)
        if collected_to is not None:
            conditions.append("m.favorite_time<=?")
            params.append(collected_to)
        if uploader:
            conditions.append("v.uploader LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(uploader)}%")
        base_where = " AND ".join(conditions)
        with self.db.connect() as connection:
            unknown = connection.execute(
                f"""
                SELECT COUNT(DISTINCT v.id)
                FROM videos v
                JOIN video_source_memberships m ON m.video_id=v.id
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE {base_where} AND v.published_at IS NULL
                """,
                params,
            ).fetchone()[0]
            published_conditions: list[str] = []
            published_params = list(params)
            if published_from is not None:
                published_conditions.append("v.published_at IS NOT NULL AND v.published_at>=?")
                published_params.append(published_from)
            if published_to is not None:
                published_conditions.append("v.published_at IS NOT NULL AND v.published_at<=?")
                published_params.append(published_to)
            extra = " AND " + " AND ".join(published_conditions) if published_conditions else ""
            order_sql = (
                "MAX(m.favorite_time) IS NULL, MAX(m.favorite_time) DESC, v.id DESC"
                if order == "collected_desc"
                else "v.id"
            )
            rows = connection.execute(
                f"""
                SELECT v.id
                FROM videos v
                JOIN video_source_memberships m ON m.video_id=v.id
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE {base_where}{extra}
                GROUP BY v.id
                ORDER BY {order_sql}
                """,
                published_params,
            ).fetchall()
        return [int(row["id"]) for row in rows], int(unknown)

    def _metadata_cards(
        self,
        video_ids: list[int],
        *,
        allowed_source_ids: set[int],
        sort: str,
        limit: int,
        excerpts: dict[int, str] | None = None,
        collected_from: int | None = None,
        collected_to: int | None = None,
    ) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in video_ids)
        source_placeholders = ",".join("?" for _ in allowed_source_ids)
        order = {
            "published_desc": "v.published_at IS NULL, v.published_at DESC, v.id DESC",
            "collected_desc": "MAX(m.favorite_time) IS NULL, MAX(m.favorite_time) DESC, v.id DESC",
            "relevance": "MAX(m.favorite_time) IS NULL, MAX(m.favorite_time) DESC, v.id DESC",
        }[sort]
        time_filter = ""
        time_params: list[int] = []
        if collected_from is not None:
            time_filter += " AND m.favorite_time>=?"
            time_params.append(collected_from)
        if collected_to is not None:
            time_filter += " AND m.favorite_time<=?"
            time_params.append(collected_to)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT v.id
                FROM videos v
                LEFT JOIN video_source_memberships m
                 ON m.video_id=v.id
                 AND m.removed_at IS NULL
                 AND m.source_id IN ({source_placeholders})
                 {time_filter}
                WHERE v.id IN ({placeholders})
                GROUP BY v.id
                ORDER BY {order}
                LIMIT ?
                """,
                [*sorted(allowed_source_ids), *time_params, *video_ids, limit],
            ).fetchall()
        return [
            self._card(
                int(row["id"]),
                allowed_source_ids=allowed_source_ids,
                excerpt=(excerpts or {}).get(int(row["id"]), ""),
            )
            for row in rows
        ]

    def _title_query_cards(
        self,
        video_ids: list[int],
        *,
        allowed_source_ids: set[int],
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        tokens = [token.casefold() for token in query.split() if token.strip()]
        if not tokens:
            return []
        placeholders = ",".join("?" for _ in video_ids)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"SELECT id, title, uploader FROM videos WHERE id IN ({placeholders})",
                video_ids,
            ).fetchall()
        ranked: list[tuple[int, int]] = []
        for row in rows:
            haystack = f"{row['title']} {row['uploader']}".casefold()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                ranked.append((score, int(row["id"])))
        ranked.sort(key=lambda item: (-item[0], -item[1]))
        return [
            self._card(video_id, allowed_source_ids=allowed_source_ids)
            for _score, video_id in ranked[:limit]
        ]

    def _card(
        self,
        video_id: int,
        *,
        allowed_source_ids: set[int],
        excerpt: str = "",
    ) -> dict[str, Any]:
        video = self.db.get_video(video_id)
        if video is None:
            raise KeyError(video_id)
        memberships = [
            item
            for item in self.db.video_sources(video_id)
            if item["removed_at"] is None and int(item["id"]) in allowed_source_ids
        ]
        available_views = [
            view for view, column in (
                ("transcript", "raw_subtitle_path"),
                ("transcript", "transcript_path"),
                ("summary", "summary_path"),
            ) if self._managed_exists(video.get(column))
        ]
        if str(video.get("description") or "").strip() not in {"", "-"}:
            available_views.append("description")
        available_views = list(dict.fromkeys(available_views))
        return {
            "source_ref": f"video:{video_id}",
            "video_id": video_id,
            "bvid": video["source_id"],
            "part": video["part"],
            "coverage": "p1_only" if int(video.get("page_count") or 1) > 1 else "single_part",
            "title": video["title"],
            "uploader": video["uploader"],
            "published_at": _epoch_iso(video.get("published_at")),
            "metadata_observed_at": video.get("metadata_observed_at"),
            "memberships": [
                {
                    "source_db_id": item["id"],
                    "source_account_name": item.get("account_name") or None,
                    "folder_id": item["folder_id"],
                    "folder_title": item["folder_title"],
                    "favorite_time": _epoch_iso(item.get("favorite_time")),
                }
                for item in memberships
            ],
            "matched_excerpt": excerpt,
            "available_views": available_views,
            "full_text_available": "transcript" in available_views,
        }

    def _capture_or_load(self, video_id: int, revision: str | None) -> CapturedSource:
        if revision is None:
            return self.snapshots.capture(video_id)
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT r.snapshot_ref FROM assistant_source_revisions r
                JOIN assistant_source_heads h ON h.id=r.head_id
                WHERE r.revision=? AND h.video_id=? AND h.principal_id='local_operator'
                """,
                (revision, video_id),
            ).fetchone()
        if row is None:
            raise KeyError(revision)
        relative = str(row["snapshot_ref"])
        path = self.snapshots.root / relative
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        return CapturedSource(revision=revision, snapshot_ref=relative, snapshot=snapshot)

    def _source_view(
        self,
        captured: CapturedSource,
        *,
        allowed_source_ids: set[int],
        view: str,
        offset: int,
        max_characters: int,
        query: str | None = None,
    ) -> SourceView:
        snapshot = captured.snapshot
        metadata = snapshot["metadata"]
        materials = snapshot["materials"]
        notes = snapshot["notes"]
        content: str | None = None
        if view == "description":
            content = str(metadata.get("description") or "")
        elif view == "summary":
            content = materials.get("summary", "")
        elif view == "notes":
            content = "\n\n".join(str(note["content"]) for note in notes)
        elif view == "transcript":
            content = materials.get("raw_subtitle") or materials.get("transcript", "")
        total_characters = len(content) if content is not None else 0
        if query and content:
            tokens = [value.casefold() for value in query.split() if value]
            matches = [content.casefold().find(value) for value in tokens]
            matches = [value for value in matches if value >= 0]
            if matches:
                offset = max(0, min(matches) - min(500, max_characters // 8))
        end_offset = min(total_characters, offset + max_characters)
        if content is not None:
            content = content[offset:end_offset]
        descriptors = [
            MaterialDescriptor(
                kind="description", available=str(metadata.get("description") or "").strip() not in {"", "-", "—"},
                content_hash=None,
            ),
            MaterialDescriptor(
                kind="raw_subtitle", available="raw_subtitle" in materials,
                subtitle_source=metadata.get("subtitle_source"),
                content_hash=snapshot["material_hashes"].get("raw_subtitle"),
            ),
            MaterialDescriptor(
                kind="transcript", available="transcript" in materials,
                revision=metadata.get("active_revision"),
                content_hash=snapshot["material_hashes"].get("transcript"),
            ),
            MaterialDescriptor(
                kind="summary", available="summary" in materials,
                revision=metadata.get("active_revision"),
                content_hash=snapshot["material_hashes"].get("summary"),
            ),
            MaterialDescriptor(kind="user_note", available=bool(notes)),
        ]
        return SourceView(
            source_ref=f"video:{metadata['id']}",
            revision=captured.revision,
            video={
                "video_id": metadata["id"], "bvid": metadata["source_id"],
                "part": metadata["part"], "cid": metadata.get("cid"),
                "page_count": metadata.get("page_count"),
                "part_title": metadata.get("part_title"), "title": metadata.get("title"),
                "uploader": metadata.get("uploader"), "uploader_id": metadata.get("uploader_id"),
                "description": metadata.get("description"),
                "description_links": json.loads(metadata.get("description_links_json") or "[]"),
                "duration_seconds": metadata.get("duration_seconds"),
                "coverage": "p1_only" if int(metadata.get("page_count") or 1) > 1 else "single_part",
            },
            time={
                "published_at": _epoch_iso(metadata.get("published_at")),
                "metadata_observed_at": metadata.get("metadata_observed_at"),
                "first_discovered_at": metadata.get("discovered_at"),
                "memberships": [
                    {
                        "source_db_id": row["source_id"],
                        "folder_id": row["folder_id"],
                        "folder_title": row["folder_title"],
                        "favorite_time": _epoch_iso(row.get("favorite_time")),
                        "first_observed_at": row["first_observed_at"],
                    }
                    for row in snapshot["memberships"]
                    if row["removed_at"] is None
                    and row["status"] == "active"
                    and int(row["source_id"]) in allowed_source_ids
                ],
            },
            materials=descriptors,
            coverage=snapshot["coverage"],
            content=content,
            provenance={
                "snapshot_ref": captured.snapshot_ref,
                "immutable": True,
                "content_position": {
                    "start": offset,
                    "end": end_offset,
                    "total": total_characters,
                },
            },
        )


def _parse_source_ref(source_ref: str) -> tuple[int, str | None]:
    parts = source_ref.split(":")
    if (
        len(parts) not in {2, 3}
        or parts[0] != "video"
        or not parts[1].isdigit()
        or int(parts[1]) <= 0
        or (len(parts) == 3 and not _is_revision(parts[2]))
    ):
        raise ValueError(source_ref)
    return int(parts[1]), parts[2] if len(parts) == 3 else None


def _is_revision(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _encode_read_cursor(*, video_id: int, revision: str, view: str, offset: int) -> str:
    payload = json.dumps(
        {"v": 1, "video_id": video_id, "revision": revision, "view": view, "offset": offset},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_read_cursor(cursor: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("v") != 1
            or not isinstance(value.get("video_id"), int)
            or value["video_id"] <= 0
            or not _is_revision(str(value.get("revision") or ""))
            or value.get("view") not in {"overview", "description", "summary", "notes", "transcript"}
            or not isinstance(value.get("offset"), int)
            or value["offset"] < 0
        ):
            raise ValueError(cursor)
        return value
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(cursor) from exc


def _epoch_iso(value: object) -> str | None:
    if value is None:
        return None
    try:
        epoch = int(value)
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(
        DISPLAY_TIMEZONE
    ).isoformat(timespec="seconds")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
