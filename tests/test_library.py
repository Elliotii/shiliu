from __future__ import annotations

import html
import re

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import Database, SCHEMA_VERSION, library_card_cursor
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
    assert SCHEMA_VERSION == 17
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


def test_keyset_pages_traverse_2055_cards_without_sync_drift(app_paths) -> None:
    application = Application(app_paths)
    source_id = application.db.create_favorite_source(
        folder_id=2055,
        folder_title="Large corpus",
    )
    items = [
        favorite(
            f"BV{index:010d}",
            f"视频 {index}",
            10_000 - (index // 3),
        )
        for index in range(2055)
    ]
    application.db.record_source_snapshot(
        source_id,
        items,
        processing_profile="formal",
    )
    expected = [
        (int(row["id"]), int(row["card_source_id"]))
        for row in application.db.list_video_cards(source_db_id=source_id)
    ]

    page = application.db.page_video_cards(
        source_db_id=source_id,
        page_size=40,
    )
    assert len(page.items) == 40
    assert page.has_previous is False
    assert page.has_next is True
    first_page = [
        (int(row["id"]), int(row["card_source_id"])) for row in page.items
    ]
    cursor = library_card_cursor(page.items[-1])

    # Continuous forward sync inserts a new favorite above the active cursor.
    application.db.record_source_snapshot(
        source_id,
        [favorite("BV9999999999", "同步后新收藏", 99_999), *items],
        processing_profile="formal",
    )

    traversed = list(first_page)
    while page.has_next:
        page = application.db.page_video_cards(
            source_db_id=source_id,
            page_size=40,
            after=cursor,
        )
        traversed.extend(
            (int(row["id"]), int(row["card_source_id"]))
            for row in page.items
        )
        if page.items:
            cursor = library_card_cursor(page.items[-1])

    assert traversed == expected
    assert len(traversed) == len(set(traversed)) == 2055
    new_first = application.db.page_video_cards(
        source_db_id=source_id,
        page_size=40,
    )
    assert new_first.items[0]["title"] == "同步后新收藏"

    second = application.db.page_video_cards(
        source_db_id=source_id,
        page_size=40,
        after=library_card_cursor(new_first.items[-1]),
    )
    previous = application.db.page_video_cards(
        source_db_id=source_id,
        page_size=40,
        before=library_card_cursor(second.items[0]),
    )
    assert [library_card_cursor(row) for row in previous.items] == [
        library_card_cursor(row) for row in new_first.items
    ]


def test_all_sources_cursor_snapshot_prevents_cross_folder_duplicates(app_paths) -> None:
    application = Application(app_paths)
    source_a = application.db.create_favorite_source(
        folder_id=301,
        folder_title="A folder",
    )
    source_b = application.db.create_favorite_source(
        folder_id=302,
        folder_title="B folder",
    )
    items_a = [
        favorite(f"BVA{index:09d}", f"A{index}", 100)
        for index in range(4)
    ]
    items_b = [
        favorite(f"BVB{index:09d}", f"B{index}", 100)
        for index in range(4)
    ]
    application.db.record_source_snapshot(
        source_a,
        items_a,
        processing_profile="formal",
    )
    application.db.record_source_snapshot(
        source_b,
        items_b,
        processing_profile="formal",
    )
    expected = [
        (int(row["id"]), int(row["card_source_id"]))
        for row in application.db.list_video_cards()
    ]

    page = application.db.page_video_cards(page_size=3)
    traversed = [
        (int(row["id"]), int(row["card_source_id"])) for row in page.items
    ]
    cursor = library_card_cursor(page.items[-1])

    application.db.record_source_snapshot(
        source_a,
        [favorite("BVNEW0000000", "new A0", 100), *items_a],
        processing_profile="formal",
    )

    while page.has_next:
        page = application.db.page_video_cards(page_size=3, after=cursor)
        traversed.extend(
            (int(row["id"]), int(row["card_source_id"])) for row in page.items
        )
        if page.items:
            cursor = library_card_cursor(page.items[-1])

    assert traversed == expected
    assert len(traversed) == len(set(traversed)) == 8
    assert application.db.page_video_cards(page_size=3).items[0]["title"] == "new A0"


def test_library_route_bounds_payload_and_preserves_view_source_cursors(
    app_paths,
) -> None:
    application = Application(app_paths)
    source_id = application.db.create_favorite_source(
        folder_id=41,
        folder_title="分页收藏夹",
    )
    application.db.record_source_snapshot(
        source_id,
        [
            favorite(f"BV{index:010d}", f"分页视频 {index}", 1000 - index)
            for index in range(41)
        ],
        processing_profile="formal",
    )
    client = TestClient(create_web_app(application))

    first = client.get(f"/?view=feed&source={source_id}")
    assert first.status_code == 200
    assert first.text.count('data-video-id="') == 40
    assert len(first.content) < 1_000_000
    match = re.search(r'href="([^"]*after=[^"]+)"', first.text)
    assert match is not None
    next_url = html.unescape(match.group(1))
    assert "view=feed" in next_url
    assert f"source={source_id}" in next_url

    second = client.get(next_url)
    assert second.status_code == 200
    assert second.text.count('data-video-id="') == 1
    assert "上一页" in second.text
    assert client.get("/?after=not-a-cursor").status_code == 400


def test_pagination_preserves_multi_folder_and_all_library_views(app_paths) -> None:
    application = Application(app_paths)
    first, video_id = source_with_video(application.db, 1)
    second = application.db.create_favorite_source(
        folder_id=2,
        folder_title="收藏夹 2",
    )
    application.db.record_source_snapshot(
        second,
        [favorite("BV1234567890", "测试视频", 999)],
        processing_profile="formal",
    )
    application.library.set_reading_state(video_id, "read")
    application.library.set_marked(video_id, True)
    application.library.add_note(video_id, "共同笔记")

    feed = application.db.page_video_cards(page_size=1)
    assert len(feed.items) == 1 and feed.has_next
    next_feed = application.db.page_video_cards(
        page_size=1,
        after=library_card_cursor(feed.items[-1]),
    )
    assert {feed.items[0]["card_source_id"], next_feed.items[0]["card_source_id"]} == {
        first,
        second,
    }
    assert len(application.db.page_video_cards(view="marked", page_size=40).items) == 2
    assert len(application.db.page_video_cards(view="noted", page_size=40).items) == 2
    assert len(
        application.db.page_video_cards(
            source_db_id=first,
            page_size=40,
        ).items
    ) == 1

    application.library.set_archived(video_id, True)
    assert application.db.page_video_cards(view="feed", page_size=40).items == []
    archived = application.db.page_video_cards(view="archived", page_size=40)
    assert len(archived.items) == 2
    application.library.set_archived(video_id, False)
    assert len(application.db.page_video_cards(view="feed", page_size=40).items) == 2


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
