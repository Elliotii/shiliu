from __future__ import annotations

import json

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.retrieval import (
    ChunkingConfig,
    RetrievalFilters,
    RetrievalService,
    build_raw_subtitle_chunks,
)


def segment(start: float, end: float, content: str) -> SubtitleSegment:
    return SubtitleSegment.model_validate({"from": start, "to": end, "content": content})


def make_service(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    return db, artifacts, RetrievalService(db=db, artifacts=artifacts)


def add_video(
    db: Database,
    artifacts: ArtifactStore,
    *,
    bvid: str,
    title: str,
    uploader: str = "Creator",
    folder_id: int = 101,
    folder_title: str = "技术收藏",
    favorite_time: int = 1_700_000_000,
    subtitle_source: str | None = None,
    segments: list[SubtitleSegment] | None = None,
) -> tuple[int, int]:
    source = db.get_source_by_folder(folder_id)
    source_db_id = (
        int(source["id"])
        if source
        else db.create_favorite_source(
            folder_id=folder_id,
            folder_title=folder_title,
            account_name="Account",
        )
    )
    db.record_source_snapshot(
        source_db_id,
        [
            FavoriteItem(
                bvid=bvid,
                title=title,
                uploader=uploader,
                favorite_time=favorite_time,
            )
        ],
        processing_profile="formal",
    )
    video = db.get_video_by_source(bvid)
    assert video is not None
    video_id = int(video["id"])
    db.update_video(
        video_id,
        title=title,
        uploader=uploader,
        description=f"{title} 的本地说明",
        status="completed",
    )
    if segments is not None:
        _, raw_text = artifacts.save_raw_subtitle(bvid, segments)
        db.update_video(
            video_id,
            raw_subtitle_path=str(raw_text),
            subtitle_source=subtitle_source or "ai",
            subtitle_language="zh",
        )
    return source_db_id, video_id


def test_chunking_is_deterministic_preserves_segments_and_overlap() -> None:
    values = [
        segment(0.0, 2.0, "AAAAA"),
        segment(2.0, 4.0, "BBBBB"),
        segment(4.0, 6.0, "CCCCC"),
        segment(6.0, 7.0, "   "),
    ]
    config = ChunkingConfig(
        target_characters=10,
        maximum_characters=15,
        maximum_duration_seconds=10,
    )
    first = build_raw_subtitle_chunks(
        platform="bilibili",
        source_id="BV1234567890",
        part=1,
        source_type="human",
        segments=values,
        config=config,
    )
    second = build_raw_subtitle_chunks(
        platform="bilibili",
        source_id="BV1234567890",
        part=1,
        source_type="human",
        segments=values,
        config=config,
    )

    assert first == second
    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
    assert [item.text for item in first] == ["AAAAA BBBBB", "BBBBB CCCCC"]
    assert first[0].start_time == 0.0
    assert first[0].end_time == 4.0
    assert first[1].start_time == 2.0
    assert first[1].end_time == 6.0
    assert all("AAAA" not in item.text or "AAAAA" in item.text for item in first)


def test_chunking_honors_duration_and_keeps_oversized_whole_segment() -> None:
    values = [
        segment(0, 3, "first"),
        segment(3, 7, "second"),
        segment(7, 8, "X" * 30),
    ]
    chunks = build_raw_subtitle_chunks(
        platform="bilibili",
        source_id="BV1234567890",
        part=1,
        source_type="asr",
        segments=values,
        config=ChunkingConfig(10, 15, 5),
    )

    assert chunks[0].text == "first"
    assert chunks[0].start_time == 0
    assert chunks[0].end_time == 3
    assert chunks[-1].text == "X" * 30
    assert chunks[-1].segment_count == 1


def test_schema_initialization_and_unchanged_rebuild_are_idempotent(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    add_video(
        db,
        artifacts,
        bvid="BV1234567890",
        title="LangGraph 工作流",
        subtitle_source="ai",
        segments=[segment(0, 2, "LangGraph 状态图"), segment(2, 5, "持久化 checkpoint")],
    )

    retrieval.initialize_schema()
    retrieval.initialize_schema()
    first = retrieval.rebuild().as_dict()
    first_stats = retrieval.statistics()
    second = retrieval.rebuild().as_dict()
    second_stats = retrieval.statistics()

    assert first["video_unit_count"] == second["video_unit_count"] == 1
    assert first["chunk_unit_count"] == second["chunk_unit_count"] == 1
    assert first_stats["current"]["metadata_count"] == 2
    assert second_stats["current"]["metadata_count"] == 2
    assert second_stats["current"]["metadata_count"] == second_stats["current"]["fts_count"]
    assert second_stats["current"]["duplicate_count"] == 0
    assert second_stats["current"]["consistent"] is True
    assert second_stats["index"]["metadata_semantics"] == "current_index_state"
    assert second_stats["index"]["eligible_video_count"] == 1
    assert second_stats["index"]["video_unit_count"] == 1
    assert second_stats["index"]["chunk_unit_count"] == 1
    assert second_stats["index"]["total_unit_count"] == 2
    assert second_stats["last_full_rebuild"]["completed_at"]


def test_malformed_optional_assets_degrade_and_video_without_subtitle_is_indexed(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    _, video_id = add_video(
        db,
        artifacts,
        bvid="BV1234567890",
        title="No Subtitle Entity",
    )
    directory = artifacts.video_dir("BV1234567890")
    bad_summary = directory / "summary.json"
    bad_transcript = directory / "transcript.json"
    bad_summary.write_text("{bad", encoding="utf-8")
    bad_transcript.write_text("[]", encoding="utf-8")
    db.update_video(
        video_id,
        summary_path=str(directory / "summary.md"),
        transcript_path=str(directory / "transcript.md"),
    )

    rebuilt = retrieval.rebuild()
    results = retrieval.search("No Subtitle Entity", level="video")

    assert rebuilt.video_unit_count == 1
    assert rebuilt.chunk_unit_count == 0
    assert rebuilt.malformed_summary_json == 1
    assert rebuilt.malformed_transcript_json == 1
    assert results[0].video_id == video_id


def test_replace_removes_stale_units_and_delete_removes_fts_rows(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    _, video_id = add_video(
        db,
        artifacts,
        bvid="BV1234567890",
        title="Replace Target",
        subtitle_source="asr",
        segments=[segment(0, 2, "old alpha"), segment(2, 4, "old beta")],
    )
    retrieval.rebuild()
    after_rebuild = retrieval.statistics()
    rebuild_completed_at = after_rebuild["last_full_rebuild"]["completed_at"]
    assert after_rebuild["index"]["total_unit_count"] == 2
    with db.connect() as connection:
        old_ids = {
            row[0]
            for row in connection.execute(
                "SELECT unit_id FROM retrieval_units WHERE video_id=?", (video_id,)
            )
        }

    _, raw_text = artifacts.save_raw_subtitle(
        "BV1234567890",
        [
            segment(10, 12, "replacement-a-" + "x" * 900),
            segment(12, 14, "replacement-b-" + "y" * 900),
            segment(14, 16, "replacement-c-" + "z" * 900),
        ],
    )
    db.update_video(video_id, raw_subtitle_path=str(raw_text))
    replaced = retrieval.replace_video(video_id)
    with db.connect() as connection:
        new_ids = {
            row[0]
            for row in connection.execute(
                "SELECT unit_id FROM retrieval_units WHERE video_id=?", (video_id,)
            )
        }
    assert replaced == {"video_id": video_id, "video_units": 1, "chunk_units": 3}
    assert len(old_ids - new_ids) == 1
    assert not retrieval.search("old alpha")
    assert retrieval.search("replacement", level="transcript_chunk")

    after_replace = retrieval.statistics()
    assert after_replace["current"]["metadata_count"] == 4
    assert after_replace["current"]["fts_count"] == 4
    assert after_replace["current"]["distinct_unit_count"] == 4
    assert after_replace["current"]["video_unit_count"] == 1
    assert after_replace["current"]["chunk_unit_count"] == 3
    assert after_replace["index"]["eligible_video_count"] == 1
    assert after_replace["index"]["video_unit_count"] == 1
    assert after_replace["index"]["chunk_unit_count"] == 3
    assert after_replace["index"]["total_unit_count"] == 4
    assert after_replace["index"]["index_version"] == "v3-stage1-lexical-v1"
    assert after_replace["last_full_rebuild"]["completed_at"] == rebuild_completed_at
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_unit_folders"
        ).fetchone()[0] == 4

    assert retrieval.delete_video(video_id) == 4
    stats = retrieval.statistics()
    assert stats["current"]["metadata_count"] == stats["current"]["fts_count"] == 0
    assert stats["current"]["distinct_unit_count"] == 0
    assert stats["index"]["eligible_video_count"] == 0
    assert stats["index"]["video_unit_count"] == 0
    assert stats["index"]["chunk_unit_count"] == 0
    assert stats["index"]["total_unit_count"] == 0
    assert stats["index"]["index_version"] == "v3-stage1-lexical-v1"
    assert stats["last_full_rebuild"]["completed_at"] == rebuild_completed_at
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_unit_folders"
        ).fetchone()[0] == 0


def test_full_rebuild_removes_video_without_active_membership(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    source_id, video_id = add_video(
        db,
        artifacts,
        bvid="BV1234567890",
        title="Stale Retrieval Unit",
    )
    retrieval.rebuild()
    assert retrieval.search("Stale Retrieval Unit")

    db.record_source_snapshot(
        source_id, [], processing_profile="formal", authoritative=True
    )
    rebuilt = retrieval.rebuild()

    assert rebuilt.eligible_video_count == 0
    assert not retrieval.search("Stale Retrieval Unit")
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_units WHERE video_id=?", (video_id,)
        ).fetchone()[0] == 0


def test_lexical_search_levels_top_k_and_chunk_provenance(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    _, video_id = add_video(
        db,
        artifacts,
        bvid="BV1234567890",
        title="Model Context Protocol Guide",
        subtitle_source="human",
        segments=[
            segment(1.25, 4.5, "Model Context Protocol transports"),
            segment(4.5, 8.75, "MCP tool schema details"),
        ],
    )
    retrieval.rebuild()

    all_results = retrieval.search("Model Context Protocol", top_k=1)
    video_results = retrieval.search("Model Context Protocol", level="video")
    chunk_results = retrieval.search("Model Context Protocol", level="transcript_chunk")

    assert len(all_results) == 1
    assert video_results[0].unit_type == "video"
    chunk = chunk_results[0]
    assert chunk.video_id == video_id
    assert chunk.source_id == "BV1234567890"
    assert chunk.chunk_id and chunk.unit_id.endswith(chunk.chunk_id)
    assert chunk.source_type == "human"
    assert chunk.start_time == 1.25
    assert chunk.end_time == 8.75
    assert "Model Context Protocol" in chunk.matched_excerpt
    assert chunk.retrieval_method == "lexical"
    assert isinstance(chunk.lexical_score, float)
    assert chunk.index_version == "v3-stage1-lexical-v1"


def test_metadata_visibility_and_folder_filters(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    first_source, first_id = add_video(
        db,
        artifacts,
        bvid="BV1234567890",
        title="Shared Search Entity Alpha",
        uploader="Alice Creator",
        folder_id=101,
        folder_title="Alpha Folder",
    )
    _, second_id = add_video(
        db,
        artifacts,
        bvid="BV2234567890",
        title="Shared Search Entity Beta",
        uploader="Bob",
        folder_id=202,
        folder_title="Beta Folder",
    )
    db.set_reading_state(first_id, "read")
    db.set_marked(first_id, True)
    db.set_archived(first_id, True)
    db.set_ignored(second_id, True)
    retrieval.rebuild()

    default = retrieval.search("Shared Search Entity", level="video")
    included = retrieval.search(
        "Shared Search Entity", level="video", include_ignored=True
    )
    filtered = retrieval.search(
        "Shared Search Entity",
        level="video",
        include_ignored=True,
        filters=RetrievalFilters(
            source_db_id=first_source,
            folder_id=101,
            reading_state="read",
            is_marked=True,
            uploader_contains="LiCe cRe",
            archived=True,
        ),
    )

    assert [item.video_id for item in default] == [first_id]
    assert {item.video_id for item in included} == {first_id, second_id}
    assert [item.video_id for item in filtered] == [first_id]
    assert filtered[0].archived is True
    assert filtered[0].folders[0].folder_title == "Alpha Folder"


def test_short_query_uses_documented_fallback(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    first_source, first_id = add_video(
        db,
        artifacts,
        bvid="BV6000000001",
        title="AI Alpha",
        uploader="Alice",
        folder_id=101,
    )
    _, ignored_id = add_video(
        db,
        artifacts,
        bvid="BV6000000002",
        title="AI Ignored",
        uploader="Bob",
        folder_id=202,
    )
    removed_source, removed_id = add_video(
        db,
        artifacts,
        bvid="BV6000000003",
        title="AI Removed",
        uploader="Alice",
        folder_id=303,
    )
    _, fourth_id = add_video(
        db,
        artifacts,
        bvid="BV6000000004",
        title="AI Delta",
        uploader="Alice",
        folder_id=404,
    )
    db.set_reading_state(first_id, "read")
    db.set_reading_state(fourth_id, "read")
    db.set_archived(first_id, True)
    db.set_ignored(ignored_id, True)
    db.record_source_snapshot(
        removed_source, [], processing_profile="formal", authoritative=True
    )
    retrieval.rebuild()

    first = retrieval.search("AI", level="video", top_k=1)
    second = retrieval.search("AI", level="video", top_k=1)
    assert [item.unit_id for item in first] == [item.unit_id for item in second]
    assert [item.video_id for item in first] == [first_id]
    assert first[0].archived is True
    assert first[0].retrieval_method == "lexical_substring_fallback"
    assert first[0].lexical_score == 0.0

    filtered = retrieval.search(
        "AI",
        level="video",
        filters=RetrievalFilters(uploader="Alice", reading_state="read"),
    )
    assert {item.video_id for item in filtered} == {first_id, fourth_id}
    folder = retrieval.search(
        "AI",
        level="video",
        filters=RetrievalFilters(source_db_id=first_source, folder_id=101),
    )
    assert [item.video_id for item in folder] == [first_id]
    default_ids = {
        item.video_id for item in retrieval.search("AI", level="video")
    }
    included_ids = {
        item.video_id
        for item in retrieval.search("AI", level="video", include_ignored=True)
    }
    assert removed_id not in default_ids
    assert ignored_id not in default_ids
    assert ignored_id in included_ids


def test_uploader_exact_and_contains_contracts_are_independent(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    _, exact_id = add_video(
        db,
        artifacts,
        bvid="BV7000000001",
        title="Shared Filter Term One",
        uploader="Alice Studio",
        folder_id=701,
    )
    _, extended_id = add_video(
        db,
        artifacts,
        bvid="BV7000000002",
        title="Shared Filter Term Two",
        uploader="Alice Studio Extra",
        folder_id=702,
    )
    add_video(
        db,
        artifacts,
        bvid="BV7000000003",
        title="Shared Filter Term Three",
        uploader="Bob Channel",
        folder_id=703,
    )
    retrieval.rebuild()

    def result_ids(filters: RetrievalFilters) -> set[int]:
        return {
            item.video_id
            for item in retrieval.search(
                "Shared Filter Term",
                level="video",
                top_k=10,
                filters=filters,
            )
        }

    assert result_ids(RetrievalFilters(uploader="aLiCe StUdIo")) == {exact_id}
    assert result_ids(RetrievalFilters(uploader="Alice")) == set()
    assert result_ids(RetrievalFilters(uploader_contains="ALICE ST")) == {
        exact_id,
        extended_id,
    }
    assert result_ids(RetrievalFilters(uploader_contains="Alice Studio")) == {
        exact_id,
        extended_id,
    }
    assert result_ids(RetrievalFilters(uploader_contains="unrelated")) == set()


def test_raw_subtitle_source_is_retained_for_ai_human_and_asr(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    for index, source in enumerate(("ai", "human", "asr"), start=1):
        add_video(
            db,
            artifacts,
            bvid=f"BV{index:010d}",
            title=f"Source {source}",
            folder_id=100 + index,
            subtitle_source=source,
            segments=[segment(0, 1, f"source-retention-{source}")],
        )
    retrieval.rebuild()

    with db.connect() as connection:
        rows = connection.execute(
            """
            SELECT source_type, COUNT(*) FROM retrieval_units
            WHERE unit_type='transcript_chunk' GROUP BY source_type
            """
        ).fetchall()
    assert {row[0]: row[1] for row in rows} == {"ai": 1, "asr": 1, "human": 1}


def test_favorite_time_range_is_inclusive_and_combines_with_folder_filter(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    _, first_id = add_video(
        db,
        artifacts,
        bvid="BV2000000001",
        title="Range Entity First",
        folder_id=101,
        favorite_time=100,
    )
    second_source, second_id = add_video(
        db,
        artifacts,
        bvid="BV2000000002",
        title="Range Entity Second",
        folder_id=202,
        favorite_time=200,
    )
    _, third_id = add_video(
        db,
        artifacts,
        bvid="BV2000000003",
        title="Range Entity Third",
        folder_id=303,
        favorite_time=300,
    )
    retrieval.rebuild()

    def ids(filters: RetrievalFilters) -> set[int]:
        return {
            item.video_id
            for item in retrieval.search(
                "Range Entity", level="video", filters=filters
            )
        }

    assert ids(RetrievalFilters(favorite_time_from=200)) == {second_id, third_id}
    assert ids(RetrievalFilters(favorite_time_to=200)) == {first_id, second_id}
    assert ids(
        RetrievalFilters(favorite_time_from=200, favorite_time_to=200)
    ) == {second_id}
    assert ids(
        RetrievalFilters(
            source_db_id=second_source,
            folder_id=202,
            favorite_time_from=200,
            favorite_time_to=200,
        )
    ) == {second_id}


def test_mixed_active_removed_memberships_only_index_active_folder_provenance(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    removed_source, video_id = add_video(
        db,
        artifacts,
        bvid="BV3000000001",
        title="Mixed Membership Entity",
        folder_id=101,
        folder_title="Removed Folder",
    )
    active_source, same_video_id = add_video(
        db,
        artifacts,
        bvid="BV3000000001",
        title="Mixed Membership Entity",
        folder_id=202,
        folder_title="Active Folder",
    )
    assert same_video_id == video_id
    db.record_source_snapshot(
        removed_source, [], processing_profile="formal", authoritative=True
    )

    rebuilt = retrieval.rebuild()
    assert rebuilt.eligible_video_count == 1
    active = retrieval.search(
        "Mixed Membership Entity",
        level="video",
        filters=RetrievalFilters(source_db_id=active_source, folder_id=202),
    )
    removed = retrieval.search(
        "Mixed Membership Entity",
        level="video",
        filters=RetrievalFilters(source_db_id=removed_source, folder_id=101),
    )
    assert [item.video_id for item in active] == [video_id]
    assert [folder.folder_title for folder in active[0].folders] == ["Active Folder"]
    assert removed == []
    with db.connect() as connection:
        folder_rows = connection.execute(
            """
            SELECT source_db_id, folder_id FROM retrieval_unit_folders
            WHERE unit_id=(SELECT unit_id FROM retrieval_units
                           WHERE video_id=? AND unit_type='video')
            """,
            (video_id,),
        ).fetchall()
    assert [tuple(row) for row in folder_rows] == [(active_source, 202)]

    db.record_source_snapshot(
        active_source, [], processing_profile="formal", authoritative=True
    )
    replaced = retrieval.replace_video(video_id)
    assert replaced == {"video_id": video_id, "video_units": 0, "chunk_units": 0}
    assert not retrieval.search("Mixed Membership Entity", level="video")
    stats = retrieval.statistics()
    assert stats["current"]["metadata_count"] == 0
    assert stats["current"]["fts_count"] == 0
    assert stats["index"]["eligible_video_count"] == 0
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_unit_folders"
        ).fetchone()[0] == 0


def test_fts_special_characters_do_not_raise_and_preserve_filter_and_top_k(app_paths) -> None:
    db, artifacts, retrieval = make_service(app_paths)
    first_source, first_id = add_video(
        db,
        artifacts,
        bvid="BV4000000001",
        title="GPT-4o Alpha",
        uploader="Alice",
        folder_id=401,
    )
    add_video(
        db,
        artifacts,
        bvid="BV4000000002",
        title="GPT-4o Beta",
        uploader="Bob",
        folder_id=402,
    )
    values = (
        ("BV4000000003", "C++ toolchain", 403),
        ("BV4000000004", 'quoted " term example', 404),
        ("BV4000000005", "Using (MCP) protocol", 405),
    )
    for bvid, title, folder_id in values:
        add_video(
            db,
            artifacts,
            bvid=bvid,
            title=title,
            uploader="Alice",
            folder_id=folder_id,
        )
    retrieval.rebuild()

    for query in ("GPT-4o", "C++", 'quoted " term', "(MCP)"):
        results = retrieval.search(
            query,
            level="video",
            top_k=1,
            filters=RetrievalFilters(uploader="Alice"),
        )
        assert len(results) == 1
        assert results[0].retrieval_method == "lexical"
    filtered = retrieval.search(
        "GPT-4o",
        level="video",
        top_k=1,
        filters=RetrievalFilters(source_db_id=first_source, folder_id=401),
    )
    assert [item.video_id for item in filtered] == [first_id]
