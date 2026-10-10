from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from importlib.metadata import version

from pydantic import ValidationError

from shiliu.artifacts import ArtifactStore
from shiliu.app import Application
from shiliu.assistant.schema import initialize_assistant_foundation_schema
from shiliu.assistant.contracts import COLLECTION_TOOL_SCHEMAS, CollectionReadArgs
from shiliu.assistant.dependencies import AssistantProcessLock, CONTEXT7_TOOL_NAME_MAP
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.db import Database, SCHEMA_VERSION
from shiliu.domain import FavoriteItem, SubtitleSegment, VideoBundle
from shiliu.config import AppConfig, save_config
from shiliu.web import create_web_app


def _service(app_paths, *, product_search=None, adapter=None):
    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    snapshots = SourceSnapshotStore(db, artifacts, app_paths.assistant_content_dir)
    return db, artifacts, CollectionSourceService(
        db=db,
        artifacts=artifacts,
        snapshots=snapshots,
        product_search=product_search,
        metadata_adapter=adapter,
    )


def _add_source_video(
    db: Database,
    *,
    folder_id: int,
    bvid: str,
    favorite_time: int | None,
    title: str = "视频",
) -> tuple[int, int]:
    source_id = db.create_favorite_source(
        folder_id=folder_id, folder_title=f"收藏夹 {folder_id}", history_policy="all"
    )
    db.record_source_snapshot(
        source_id,
        [FavoriteItem(bvid=bvid, title=title, uploader="UP", favorite_time=favorite_time)],
        processing_profile="fast",
        authoritative=True,
        remote_total=1,
    )
    video = db.get_video_by_source(bvid)
    assert video is not None
    return source_id, int(video["id"])


def test_schema_v22_is_repeatable_and_contains_assistant_contract(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    db.initialize()

    with db.connect() as connection:
        version = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        video_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(videos)")
        }
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        initialize_assistant_foundation_schema(connection)

    assert int(version) == SCHEMA_VERSION == 24
    assert {"published_at", "metadata_observed_at", "cid", "part_title", "uploader_id"} <= video_columns
    assert {"assistant_spaces", "assistant_source_heads", "assistant_source_revisions"} <= tables


def test_feature_gated_foundation_initializes_without_starting_external_owners(app_paths) -> None:
    save_config(
        AppConfig(
            content_dir=str(app_paths.content_dir),
            bili_cli_root=str(app_paths.state_dir / "missing-bilibili-runtime"),
            assistant_enabled=True,
        ),
        app_paths,
    )
    application = Application(app_paths)
    web = create_web_app(application)

    assert application.config.assistant_enabled is True
    assert application.assistant_foundation.sources.db is application.db
    assert not app_paths.assistant_state_dir.exists()
    assert web.state.core is application


def test_empty_scope_never_calls_product_search(app_paths) -> None:
    class MustNotSearch:
        def search(self, *args, **kwargs):
            raise AssertionError("empty scope leaked into unbounded search")

    _db, _artifacts, service = _service(app_paths, product_search=MustNotSearch())
    result = service.search(
        call_id="call-empty",
        scope=SourceScope(source_db_ids=frozenset()),
        query="memory",
    )

    assert result.status == "empty"
    assert result.error_code == "empty_scope"


def test_native_tool_schemas_are_closed_and_do_not_accept_identity_or_scope() -> None:
    assert set(COLLECTION_TOOL_SCHEMAS) == {"collection_search", "collection_read"}
    for schema in COLLECTION_TOOL_SCHEMAS.values():
        assert schema["additionalProperties"] is False
        properties = schema["properties"]
        assert "principal_id" not in properties
        assert "source_db_ids" not in properties
        assert "space_id" not in properties
    try:
        CollectionReadArgs(source_ref="video:1", principal_id="attacker")
    except ValidationError:
        pass
    else:  # pragma: no cover - contract assertion
        raise AssertionError("model-supplied identity was accepted")
    revision = "a" * 64
    assert CollectionReadArgs(source_ref=f"video:1:{revision}").source_ref.endswith(revision)


def test_dependency_names_and_embedded_index_single_owner_contract(tmp_path: Path) -> None:
    assert version("mem0ai") == "2.1.0"
    assert version("mcp") == "2.2.0"
    assert CONTEXT7_TOOL_NAME_MAP == {
        "context7_resolve_library_id": "resolve-library-id",
        "context7_query_docs": "query-docs",
    }
    first = AssistantProcessLock(tmp_path / "assistant" / "owner.lock")
    second = AssistantProcessLock(tmp_path / "assistant" / "owner.lock")
    first.acquire()
    try:
        try:
            second.acquire()
        except RuntimeError as exc:
            assert str(exc) == "assistant_index_already_owned"
        else:  # pragma: no cover - safety contract
            raise AssertionError("second embedded index owner was accepted")
    finally:
        first.release()


def test_search_keeps_membership_times_separate_and_excludes_unknown_publication(app_paths) -> None:
    db, _artifacts, service = _service(app_paths)
    first_source, video_id = _add_source_video(
        db, folder_id=11, bvid="BV1234567890", favorite_time=2_000, title="已发布"
    )
    second_source = db.create_favorite_source(
        folder_id=12, folder_title="收藏夹 12", history_policy="all"
    )
    db.record_source_snapshot(
        second_source,
        [FavoriteItem(bvid="BV1234567890", title="已发布", uploader="UP", favorite_time=3_000)],
        processing_profile="fast",
        authoritative=True,
        remote_total=1,
    )
    _third_source, unknown_video_id = _add_source_video(
        db, folder_id=13, bvid="BV2234567890", favorite_time=4_000, title="发布时间未知"
    )
    db.update_video(
        video_id,
        published_at=1_500,
        metadata_observed_at="2026-09-21T00:00:00+00:00",
        cid=101,
        part_title="P1",
        page_count=2,
    )
    db.update_video(unknown_video_id, published_at=None)

    result = service.search(
        call_id="call-time",
        scope=SourceScope(all_active=True),
        published_from=1_000,
        published_to=2_000,
        sort="published_desc",
    )

    assert result.status == "ok"
    assert "1 个视频发布时间未知" in result.summary
    assert [item["video_id"] for item in result.items] == [video_id]
    times = {
        item["source_db_id"]: item["favorite_time"]
        for item in result.items[0]["memberships"]
    }
    assert set(times) == {first_source, second_source}
    assert times[first_source] != times[second_source]
    assert result.items[0]["coverage"] == "p1_only"


def test_favorite_snapshot_refreshes_materialized_title_without_new_video(app_paths) -> None:
    db, _artifacts, _service_instance = _service(app_paths)
    source_id, video_id = _add_source_video(
        db, folder_id=14, bvid="BV7234567890", favorite_time=4_100, title="旧标题"
    )

    created = db.record_source_snapshot(
        source_id,
        [FavoriteItem(
            bvid="BV7234567890", title="新标题", uploader="新作者",
            duration_seconds=321, favorite_time=4_100,
        )],
        processing_profile="fast",
        authoritative=True,
        remote_total=1,
    )
    video = db.get_video(video_id)

    assert created == []
    assert video is not None
    assert video["title"] == "新标题"
    assert video["uploader"] == "新作者"
    assert video["duration_seconds"] == 321


def test_query_search_passes_bounded_ids_and_disables_corpus_projection(app_paths) -> None:
    calls = []

    class SearchSpy:
        def search_with_raw(self, request, *, scope_video_ids=(), principal_id=None):
            calls.append((request, scope_video_ids, principal_id))
            return None, SimpleNamespace(results=[SimpleNamespace(video_id=scope_video_ids[0], match_excerpt="命中片段")])

    db, _artifacts, service = _service(app_paths, product_search=SearchSpy())
    source_id, video_id = _add_source_video(
        db, folder_id=21, bvid="BV3234567890", favorite_time=5_000
    )

    result = service.search(
        call_id="call-query",
        scope=SourceScope(source_db_ids=frozenset({source_id})),
        query="Agent memory",
    )

    assert result.status == "ok"
    request, video_ids, principal = calls[0]
    assert video_ids == (video_id,)
    assert request.corpus_aware is False
    assert principal == "local_operator"
    assert result.items[0]["matched_excerpt"] == "命中片段"


def test_search_and_read_do_not_project_memberships_outside_space(app_paths) -> None:
    db, _artifacts, service = _service(app_paths)
    first_source, video_id = _add_source_video(
        db, folder_id=22, bvid="BV6234567890", favorite_time=5_100
    )
    other_source = db.create_favorite_source(
        folder_id=23, folder_title="范围外收藏夹", history_policy="all"
    )
    db.record_source_snapshot(
        other_source,
        [FavoriteItem(bvid="BV6234567890", title="视频", uploader="UP", favorite_time=9_900)],
        processing_profile="fast",
        authoritative=True,
        remote_total=1,
    )
    second_source, second_video_id = _add_source_video(
        db, folder_id=24, bvid="BV8234567890", favorite_time=5_200
    )
    scope = SourceScope(source_db_ids=frozenset({first_source, second_source}))

    searched = service.search(
        call_id="scope-search", scope=scope, sort="collected_desc"
    )
    read = service.read(
        call_id="scope-read", scope=scope, source_ref=f"video:{video_id}"
    )

    assert [item["video_id"] for item in searched.items] == [second_video_id, video_id]
    first_card = next(item for item in searched.items if item["video_id"] == video_id)
    assert [item["source_db_id"] for item in first_card["memberships"]] == [first_source]
    assert [item["source_db_id"] for item in read.items[0]["time"]["memberships"]] == [first_source]


def test_read_captures_immutable_material_and_old_revision_stays_readable(app_paths) -> None:
    db, artifacts, service = _service(app_paths)
    source_id, video_id = _add_source_video(
        db, folder_id=31, bvid="BV4234567890", favorite_time=6_000
    )
    _raw_json, raw_text = artifacts.save_raw_subtitle(
        "BV4234567890",
        [SubtitleSegment.model_validate({"from": 1.0, "to": 2.5, "content": "第一版字幕"})],
    )
    db.update_video(
        video_id,
        raw_subtitle_path=str(raw_text),
        subtitle_source="ai",
        page_count=3,
        cid=404,
        part_title="第一讲",
        metadata_observed_at="2026-09-21T00:00:00+00:00",
    )
    scope = SourceScope(source_db_ids=frozenset({source_id}))

    first = service.read(
        call_id="read-1", scope=scope, source_ref=f"video:{video_id}", view="transcript"
    )
    first_view = first.items[0]
    first_revision = first_view["revision"]
    stable_ref = first.source_refs[0]
    round_trip_args = CollectionReadArgs(source_ref=stable_ref, view="transcript")
    assert first_view["coverage"] == "full_available_transcript"
    assert first_view["video"]["coverage"] == "p1_only"
    assert "第一版字幕" in first_view["content"]

    artifacts.save_raw_subtitle(
        "BV4234567890",
        [SubtitleSegment.model_validate({"from": 1.0, "to": 2.5, "content": "第二版字幕"})],
    )
    db.update_video(video_id, raw_subtitle_path=str(raw_text))
    second = service.read(
        call_id="read-2", scope=scope, source_ref=f"video:{video_id}", view="transcript"
    )
    old = service.read(
        call_id="read-old",
        scope=scope,
        source_ref=round_trip_args.source_ref,
        view="transcript",
    )
    conflict = service.read(
        call_id="read-conflict",
        scope=scope,
        source_ref=stable_ref,
        revision=second.items[0]["revision"],
        view="transcript",
    )
    missing = service.read(
        call_id="read-missing",
        scope=scope,
        source_ref=f"video:{video_id}:{'f' * 64}",
        view="transcript",
    )

    assert second.items[0]["revision"] != first_revision
    assert "第二版字幕" in second.items[0]["content"]
    assert "第一版字幕" in old.items[0]["content"]
    assert conflict.status == "invalid_arguments"
    assert conflict.error_code == "revision_conflict"
    assert missing.status == "unavailable"
    assert missing.error_code == "source_revision_not_found"
    assert Path(app_paths.assistant_content_dir / first.items[0]["provenance"]["snapshot_ref"]).is_file()


def test_ignored_or_archived_video_cannot_be_read_or_refreshed(app_paths) -> None:
    calls: list[str] = []

    class MustNotRefresh:
        def fetch_video_metadata(self, bvid: str) -> VideoBundle:
            calls.append(bvid)
            raise AssertionError("unavailable video reached external adapter")

    db, _artifacts, service = _service(app_paths, adapter=MustNotRefresh())
    source_id, video_id = _add_source_video(
        db, folder_id=32, bvid="BV9234567890", favorite_time=6_100
    )
    scope = SourceScope(source_db_ids=frozenset({source_id}))

    with db.connect() as connection:
        connection.execute("UPDATE videos SET is_ignored=1 WHERE id=?", (video_id,))
    ignored_read = service.read(
        call_id="ignored-read", scope=scope, source_ref=f"video:{video_id}"
    )
    ignored_refresh = service.refresh_metadata(
        call_id="ignored-refresh", scope=scope, source_ref=f"video:{video_id}"
    )

    with db.connect() as connection:
        connection.execute(
            "UPDATE videos SET is_ignored=0, archived_at=? WHERE id=?",
            ("2026-09-21T00:00:00+00:00", video_id),
        )
    archived_read = service.read(
        call_id="archived-read", scope=scope, source_ref=f"video:{video_id}"
    )
    archived_refresh = service.refresh_metadata(
        call_id="archived-refresh", scope=scope, source_ref=f"video:{video_id}"
    )

    assert ignored_read.status == ignored_refresh.status == "unavailable"
    assert archived_read.status == archived_refresh.status == "unavailable"
    assert calls == []


def test_metadata_refresh_is_lightweight_and_persists_pubdate(app_paths) -> None:
    calls: list[str] = []

    class MetadataOnlyAdapter:
        def fetch_video_metadata(self, bvid: str) -> VideoBundle:
            calls.append(bvid)
            return VideoBundle(
                bvid=bvid,
                title="刷新标题",
                uploader="刷新作者",
                uploader_id=88,
                description="说明 https://example.com",
                video_url=f"https://www.bilibili.com/video/{bvid}",
                cid=909,
                part_title="P1",
                duration_seconds=123,
                page_count=2,
                published_at=1_234_567,
                metadata_observed_at="2026-09-21T01:00:00+00:00",
            )

    db, _artifacts, service = _service(app_paths, adapter=MetadataOnlyAdapter())
    source_id, video_id = _add_source_video(
        db, folder_id=41, bvid="BV5234567890", favorite_time=7_000
    )

    result = service.refresh_metadata(
        call_id="refresh-1",
        scope=SourceScope(source_db_ids=frozenset({source_id})),
        source_ref=f"video:{video_id}",
    )
    video = db.get_video(video_id)

    assert result.status == "ok"
    assert calls == ["BV5234567890"]
    assert video is not None
    assert video["published_at"] == 1_234_567
    assert video["cid"] == 909
    assert video["page_count"] == 2
    assert video["subtitle_check_count"] == 0


def test_existing_v17_upgrades_with_backup_and_preserves_rows(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO seen_items(platform,source_id,part,is_baseline,first_seen_at,last_seen_at) "
            "VALUES('test','v17-stage-a-sentinel',1,0,'2026-01-01','2026-01-01')"
        )
        connection.execute(
            "UPDATE schema_meta SET value='17' WHERE key='schema_version'"
        )

    db.initialize()
    backup = app_paths.database.with_name("shiliu.pre-v23.backup.db")

    assert backup.is_file()
    with db.connect() as connection:
        assert connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "24"
        assert connection.execute(
            "SELECT COUNT(*) FROM seen_items WHERE source_id='v17-stage-a-sentinel'"
        ).fetchone()[0] == 1
