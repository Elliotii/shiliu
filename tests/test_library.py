from __future__ import annotations

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import Database, SCHEMA_VERSION
from shiliu.domain import FavoriteItem
from shiliu.web import create_web_app


def favorite(bvid: str, title: str, favorite_time: int | None) -> FavoriteItem:
    return FavoriteItem(bvid=bvid, title=title, uploader="UP", favorite_time=favorite_time)


def source_with_video(db: Database, folder_id: int, bvid: str = "BV1234567890") -> tuple[int, int]:
    source_id = db.create_favorite_source(
        folder_id=folder_id,
        folder_title=f"收藏夹 {folder_id}",
        account_name=f"账号 {folder_id}",
    )
    created = db.record_source_snapshot(
        source_id, [favorite(bvid, "测试视频", folder_id * 100)], processing_profile="formal"
    )
    video = db.get_video_by_source(bvid)
    assert video is not None
    assert created == [video["id"]] or created == []
    return source_id, int(video["id"])


def test_schema_upgrade_adds_library_defaults_without_changing_ignore(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    video_id = db.create_video("BV1234567890", "旧视频")
    db.set_ignored(video_id, True)
    with db.connect() as connection:
        connection.execute("PRAGMA user_version=4")

    db.initialize()
    video = db.get_video(video_id)
    assert SCHEMA_VERSION == 16
    assert video["reading_state"] == "unread"
    assert video["is_marked"] == 0
    assert video["archived_at"] is None
    assert video["is_ignored"] == 1


def test_library_state_and_note_api_are_independent_and_safe(app_paths) -> None:
    application = Application(app_paths)
    _, video_id = source_with_video(application.db, 1)
    client = TestClient(create_web_app(application))

    assert client.patch(
        f"/api/videos/{video_id}/reading-state", json={"reading_state": "in_progress"}
    ).status_code == 200
    assert client.patch(
        f"/api/videos/{video_id}/reading-state", json={"reading_state": "unknown"}
    ).status_code == 400
    assert client.post(f"/api/videos/{video_id}/mark").status_code == 200
    created = client.post(
        f"/api/videos/{video_id}/notes",
        json={"content": "13 : 20 **值得再看** <script>alert(1)</script> [坏链接](javascript:alert(1))"},
    )
    assert created.status_code == 201
    note = created.json()["note"]
    assert "13 : 20" in note["content"]
    assert "<strong>值得再看</strong>" in note["rendered_html"]
    assert "<script>" not in note["rendered_html"]
    assert "javascript:" not in note["rendered_html"]
    assert len(note["display_updated_at"]) == 16
    assert note["display_updated_at"][4] == "-"
    assert note["display_updated_at"][13] == ":"

    video = application.db.get_video(video_id)
    assert video["reading_state"] == "in_progress"
    assert video["is_marked"] == 1
    assert video["archived_at"] is None

    updated = client.patch(
        f"/api/notes/{note['id']}", json={"content": "修改后"}
    )
    assert updated.json()["note"]["content"] == "修改后"
    assert client.delete(f"/api/notes/{note['id']}").status_code == 200
    assert application.db.list_notes(video_id) == []


def test_membership_cards_duplicate_but_share_filters_and_state(app_paths) -> None:
    application = Application(app_paths)
    first, video_id = source_with_video(application.db, 1)
    second = application.db.create_favorite_source(
        folder_id=2, folder_title="收藏夹 2", account_name="账号 2"
    )
    application.db.record_source_snapshot(
        second, [favorite("BV1234567890", "测试视频", 999)], processing_profile="formal"
    )
    application.library.set_reading_state(video_id, "read")
    application.library.set_marked(video_id, True)
    application.library.add_note(video_id, "共同笔记")

    cards = application.db.list_video_cards()
    assert len(cards) == 2
    assert [card["card_source_id"] for card in cards] == [second, first]
    assert {card["reading_state"] for card in cards} == {"read"}
    assert {card["note_count"] for card in cards} == {1}
    assert len(application.db.list_video_cards(view="marked")) == 2
    assert len(application.db.list_video_cards(view="noted")) == 2
    assert len(application.db.list_video_cards(source_db_id=first)) == 1

    page = TestClient(create_web_app(application)).get("/")
    assert page.text.count('data-video-id="%s"' % video_id) == 2
    assert page.text.count("is-read") >= 2
    assert "收藏夹 1" in page.text and "收藏夹 2" in page.text
    assert "深度笔记" not in page.text


def test_archive_and_reentry_reset_only_the_required_state(app_paths) -> None:
    application = Application(app_paths)
    first, video_id = source_with_video(application.db, 1)
    application.library.set_reading_state(video_id, "read")
    application.library.set_marked(video_id, True)
    application.db.set_ignored(video_id, True)
    note = application.library.add_note(video_id, "保留我")
    application.library.set_archived(video_id, True)

    # Stable scans do not unarchive a video.
    application.db.record_source_snapshot(
        first, [favorite("BV1234567890", "测试视频", 100)], processing_profile="formal"
    )
    assert application.db.get_video(video_id)["archived_at"] is not None
    assert application.db.list_video_cards() == []
    assert len(application.db.list_video_cards(view="archived")) == 1

    # A genuinely new membership re-enters without creating a new processing entity.
    second = application.db.create_favorite_source(folder_id=2, folder_title="收藏夹 2")
    assert application.db.record_source_snapshot(
        second, [favorite("BV1234567890", "测试视频", 999)], processing_profile="formal"
    ) == []
    video = application.db.get_video(video_id)
    assert video["archived_at"] is None
    assert video["reading_state"] == "unread"
    assert video["is_ignored"] == 0
    assert video["is_marked"] == 1
    assert application.db.get_note(note["id"])["content"] == "保留我"

    # Removing every relationship hides all views; reactivating resets again.
    application.library.set_reading_state(video_id, "in_progress")
    application.db.record_source_snapshot(
        first, [], processing_profile="formal", authoritative=True
    )
    application.db.record_source_snapshot(
        second, [], processing_profile="formal", authoritative=True
    )
    assert application.db.list_video_cards() == []
    assert application.db.list_video_cards(view="marked") == []
    assert application.db.list_video_cards(view="noted") == []
    assert application.db.list_video_cards(view="archived") == []
    assert application.db.record_source_snapshot(
        first, [favorite("BV1234567890", "测试视频", None)], processing_profile="formal"
    ) == []
    assert application.db.get_video(video_id)["reading_state"] == "unread"


def test_manual_unarchive_preserves_all_other_state(app_paths) -> None:
    application = Application(app_paths)
    _, video_id = source_with_video(application.db, 1)
    application.library.set_reading_state(video_id, "read")
    application.library.set_marked(video_id, True)
    application.db.set_ignored(video_id, True)
    application.library.add_note(video_id, "笔记")
    application.library.set_archived(video_id, True)
    client = TestClient(create_web_app(application))

    assert client.get("/?view=archived").text.count(f'data-video-id="{video_id}"') == 1
    assert client.delete(f"/api/videos/{video_id}/archive").status_code == 200
    video = application.db.get_video(video_id)
    assert video["reading_state"] == "read"
    assert video["is_marked"] == 1
    assert video["is_ignored"] == 1
    assert len(application.db.list_notes(video_id)) == 1


def test_importing_a_new_source_reenters_an_archived_existing_video(app_paths) -> None:
    application = Application(app_paths)
    _, video_id = source_with_video(application.db, 1)
    application.library.set_reading_state(video_id, "read")
    application.library.set_marked(video_id, True)
    application.library.set_archived(video_id, True)
    new_source = application.db.create_favorite_source(folder_id=2, folder_title="新导入")

    application.db.initialize_source_memberships(
        new_source,
        [favorite("BV1234567890", "测试视频", None)],
        authoritative=True,
    )

    video = application.db.get_video(video_id)
    assert video["archived_at"] is None
    assert video["reading_state"] == "unread"
    assert video["is_marked"] == 1
    assert len(application.db.list_video_cards(source_db_id=new_source)) == 1
