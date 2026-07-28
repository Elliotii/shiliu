from __future__ import annotations

from shiliu.domain import FavoriteItem
from tests.test_product_search_api import chunk, make_client


def test_product_results_add_display_metadata_in_one_batch(app_paths, monkeypatch) -> None:
    web, core, _, _, _ = make_client(
        app_paths,
        lexical_results=[chunk("first", 1, 10, 20), chunk("second", 2, 30, 40)],
    )
    core.db.update_video(1, cover_url="//i.example/cover.jpg")
    source = core.db.create_favorite_source(folder_id=42, folder_title="检索资料")
    core.db.initialize_source_memberships(
        source,
        [FavoriteItem(bvid="BV0000000001", title="Canonical 1", favorite_time=100)],
    )
    core.db.set_reading_state(1, "read")
    core.db.set_marked(1, True)
    service = core.product_search
    original = service._display_metadata
    calls = []

    def observed(video_ids):
        calls.append(tuple(video_ids))
        return original(video_ids)

    monkeypatch.setattr(service, "_display_metadata", observed)
    body = web.post("/api/search", json={"query": "MCP"}).json()

    assert body["ok"] and calls == [(1, 2)]
    assert [item["video_id"] for item in body["results"]] == [1, 2]
    first = body["results"][0]
    assert first["cover_url"] == "https://i.example/cover.jpg"
    assert first["detail_url"] == "/videos/1/transcript"
    assert first["reading_state"] == "read" and first["marked"] is True
    assert first["folder_names"] == ["检索资料"]
    assert first["match_excerpt"]
    assert first["windows"][0]["jump_url"].endswith("?t=10")


def test_display_metadata_fallback_and_video_scope_preserve_order(app_paths) -> None:
    web, _, _, _, _ = make_client(app_paths)
    body = web.post(
        "/api/search", json={"query": "MCP", "scope": "video"}
    ).json()
    result = body["results"][0]
    assert result["cover_url"] is None
    assert result["detail_url"] == "/videos/1/transcript"
    assert result["reading_state"] == "unread"
    assert result["marked"] is False and result["folder_names"] == []
    assert result["windows"] == []


def test_metadata_extension_does_not_change_window_order(app_paths) -> None:
    web, _, _, _, _ = make_client(
        app_paths,
        lexical_results=[
            chunk("later", 1, 100, 105, score=1.0),
            chunk("earlier-rank", 1, 10, 15, score=2.0),
        ],
    )
    windows = web.post(
        "/api/search", json={"query": "MCP", "max_windows_per_video": 5}
    ).json()["results"][0]["windows"]
    assert [window["window_start"] for window in windows] == [100, 10]
