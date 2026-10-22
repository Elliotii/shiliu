from shiliu.bilibili import _duration_seconds


def test_normalized_duration_seconds_and_display_duration_are_supported() -> None:
    assert _duration_seconds(867) == 867
    assert _duration_seconds("14:27") == 867
    assert _duration_seconds("01:14:27") == 4467
    assert _duration_seconds("unknown") == 0



def test_favorite_scan_preserves_cover_url(tmp_path, monkeypatch):
    from shiliu.bilibili import BilibiliAdapter
    adapter = BilibiliAdapter(tmp_path)
    monkeypatch.setattr(adapter, "_run_bridge", lambda *a, **k: {
        "items": [{"bvid": "BV1cover", "title": "新收藏", "cover_url": "https://i.example/cover.jpg"}],
        "remote_total": 1, "pagination_complete": True,
    })
    assert adapter.list_favorite_scan(42).items[0].cover_url == "https://i.example/cover.jpg"


def test_video_unavailable_is_terminal_but_auth_rate_and_network_are_not_reclassified(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import pytest
    from shiliu.bilibili import BilibiliAdapter, unavailable_video_error
    from shiliu.domain import PipelineError
    adapter = BilibiliAdapter(tmp_path)
    monkeypatch.setattr(adapter, "_ensure_runtime", lambda: None)
    for message, code, expected, retryable in [
        ("接口返回错误代码：62002，稿件不可见", "upstream_error", "video_unavailable", False),
        ("{'code': -404, 'message': '啥都木有'}", "upstream_error", "video_unavailable", False),
        ("HTTP 404 on gateway", "upstream_error", "upstream_error", True),
        ("timeout", "upstream_timeout", "upstream_timeout", True),
        ("412 rate limited", "upstream_retryable", "upstream_retryable", True),
        ("未登录", "authentication_required", "authentication_required", False),
    ]:
        monkeypatch.setattr("shiliu.bilibili.subprocess.run", lambda *a, **k: SimpleNamespace(
            returncode=1, stdout=json.dumps({"ok": False, "error": {"code": code, "message": message}}), stderr=""))
        with pytest.raises(PipelineError) as caught:
            adapter.fetch_video_bundle("BV1test")
        assert caught.value.code == expected
        assert caught.value.retryable is retryable
    assert not unavailable_video_error("code: 620020")
