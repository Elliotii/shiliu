from shiliu.db import Database, library_card_cursor
from shiliu.domain import FavoriteItem
from shiliu.library import LibraryService
from types import SimpleNamespace


def favorite(bvid: str, title: str, favorite_time: int | None) -> FavoriteItem:
    return FavoriteItem(
        bvid=bvid, title=title, uploader="UP", favorite_time=favorite_time
    )


def source_with_video(
    db: Database, folder_id: int, bvid: str = "BV1234567890"
) -> tuple[int, int]:
    source_id = db.create_favorite_source(
        folder_id=folder_id,
        folder_title=f"收藏夹 {folder_id}",
        account_name=f"账号 {folder_id}",
    )
    created = db.record_source_snapshot(
        source_id,
        [favorite(bvid, "测试视频", folder_id * 100)],
        processing_profile="formal",
    )
    video = db.get_video_by_source(bvid)
    assert video is not None
    assert created == [video["id"]] or created == []
    return source_id, int(video["id"])


def test_all_sources_cursor_snapshot_prevents_cross_folder_duplicates(
    collection_db,
) -> None:
    application = SimpleNamespace(
        db=collection_db, library=LibraryService(collection_db)
    )
    source_a = application.db.create_favorite_source(
        folder_id=301,
        folder_title="A folder",
    )
    source_b = application.db.create_favorite_source(
        folder_id=302,
        folder_title="B folder",
    )
    items_a = [favorite(f"BVA{index:09d}", f"A{index}", 100) for index in range(4)]
    items_b = [favorite(f"BVB{index:09d}", f"B{index}", 100) for index in range(4)]
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
    traversed = [(int(row["id"]), int(row["card_source_id"])) for row in page.items]
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


def test_pagination_preserves_multi_folder_and_all_library_views(collection_db) -> None:
    application = SimpleNamespace(
        db=collection_db, library=LibraryService(collection_db)
    )
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
    assert (
        len(
            application.db.page_video_cards(
                source_db_id=first,
                page_size=40,
            ).items
        )
        == 1
    )

    application.library.set_archived(video_id, True)
    assert application.db.page_video_cards(view="feed", page_size=40).items == []
    archived = application.db.page_video_cards(view="archived", page_size=40)
    assert len(archived.items) == 2
    application.library.set_archived(video_id, False)
    assert len(application.db.page_video_cards(view="feed", page_size=40).items) == 2


def test_archive_and_reentry_reset_only_the_required_state(collection_db) -> None:
    application = SimpleNamespace(
        db=collection_db, library=LibraryService(collection_db)
    )
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
    assert (
        application.db.record_source_snapshot(
            second,
            [favorite("BV1234567890", "测试视频", 999)],
            processing_profile="formal",
        )
        == []
    )
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
    assert (
        application.db.record_source_snapshot(
            first,
            [favorite("BV1234567890", "测试视频", None)],
            processing_profile="formal",
        )
        == []
    )
    assert application.db.get_video(video_id)["reading_state"] == "unread"


def test_importing_a_new_source_reenters_an_archived_existing_video(
    collection_db,
) -> None:
    application = SimpleNamespace(
        db=collection_db, library=LibraryService(collection_db)
    )
    _, video_id = source_with_video(application.db, 1)
    application.library.set_reading_state(video_id, "read")
    application.library.set_marked(video_id, True)
    application.library.set_archived(video_id, True)
    new_source = application.db.create_favorite_source(
        folder_id=2, folder_title="新导入"
    )

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


def test_scope_notes_and_atomic_intent(collection_db):
    import pytest
    from shiliu.storage.scope import ResourceContext

    db = collection_db
    sid, vid = source_with_video(db, 91)
    foreign = Database(db.pg, ResourceContext("personal:someone_else", "someone_else"))
    assert foreign.get_video(vid) is None
    assert foreign.list_videos() == [] and foreign.list_sources() == []
    note = db.create_note(vid, "私有合成笔记")
    assert foreign.get_note(note["id"]) is None
    assert foreign.list_notes(vid) == []
    with db.pg.read() as c:
        before = c.execute(
            "SELECT requested_generation FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND resource_key=%s",
            (db.workspace_id, str(vid)),
        ).fetchone()
    with pytest.raises(RuntimeError):
        with db.connect(guard=True) as c:
            db.update_video(vid, title="回滚标题", conn=c)
            raise RuntimeError("injected")
    assert db.get_video(vid)["title"] == "测试视频"
    with db.pg.read() as c:
        assert (
            before
            == c.execute(
                "SELECT requested_generation FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND resource_key=%s",
                (db.workspace_id, str(vid)),
            ).fetchone()
        )
    db.set_ignored(vid, True)
    with db.pg.read() as c:
        assert (
            c.execute(
                "SELECT requested_generation FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND resource_key=%s",
                (db.workspace_id, str(vid)),
            ).fetchone()["requested_generation"]
            == before["requested_generation"] + 1
        )


def test_c06_uncommitted_publication_blocks_first_page_and_excludes_later_members(
    collection_db,
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import time

    db = collection_db
    sid = db.create_favorite_source(folder_id=301, folder_title="C06")
    items = [favorite(f"BVC06{i}", f"旧{i}", 100) for i in range(6)]
    db.record_source_snapshot(sid, items, processing_profile="formal")
    inserted = Event()
    commit = Event()
    paging = Event()

    def publish():
        with db.connect(guard=True) as c:
            pid = c.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            db.record_source_snapshot(
                sid,
                [favorite("BVC06new", "先发布", 100), *items],
                processing_profile="formal",
                conn=c,
            )
            inserted.set()
            assert commit.wait(5)
            return pid

    def page():
        paging.set()
        return db.page_video_cards(page_size=3)

    with ThreadPoolExecutor(2) as executor:
        a = executor.submit(publish)
        assert inserted.wait(5)
        b = executor.submit(page)
        assert paging.wait(5)
        deadline = time.monotonic() + 3
        waiting = False
        while time.monotonic() < deadline:
            with db.pg.read() as c:
                waiting = c.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE 'SELECT %%workspace_guards%%') AS n"
                ).fetchone()["n"]
            if waiting:
                break
            time.sleep(0.01)
        assert waiting and not b.done()
        commit.set()
        a.result(5)
        first = b.result(5)
    assert first.snapshot_rowid == 7 and first.items[0]["title"] == "先发布"
    expected = [r["id"] for r in db.list_video_cards()]
    db.record_source_snapshot(
        sid,
        [
            favorite("BVC06later", "后提交", 100),
            favorite("BVC06new", "先发布", 100),
            *items,
        ],
        processing_profile="formal",
    )
    traversed = [r["id"] for r in first.items]
    current = first
    while current.has_next:
        current = db.page_video_cards(
            page_size=3, after=library_card_cursor(current.items[-1])
        )
        traversed += [r["id"] for r in current.items]
    assert traversed == expected and len(set(traversed)) == 7
    second = db.page_video_cards(
        page_size=3, after=library_card_cursor(first.items[-1])
    )
    previous = db.page_video_cards(
        page_size=3, before=library_card_cursor(second.items[0])
    )
    assert [r["id"] for r in previous.items] == [r["id"] for r in first.items]
    # A removed anchor retains its snapshot position; old cursor remains usable.
    db.record_source_snapshot(
        sid,
        [
            favorite("BVC06later", "后提交", 100),
            favorite("BVC06new", "先发布", 100),
            *items[1:],
        ],
        processing_profile="formal",
        authoritative=True,
    )
    tail = db.page_video_cards(page_size=20, after=library_card_cursor(first.items[-1]))
    assert all(r["title"] != "后提交" for r in tail.items)
