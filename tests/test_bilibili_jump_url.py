from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from shiliu.retrieval.product_search import build_bilibili_jump_url


@pytest.mark.parametrize(
    ("video_url", "bvid", "jump_time", "expected_path", "expected_time"),
    [
        (None, "BV1234567890", 12, "/video/BV1234567890", "12"),
        ("https://www.bilibili.com/video/BV1234567890", None, 0, "/video/BV1234567890", "0"),
        ("https://www.bilibili.com/video/BV1234567890", None, 12.99, "/video/BV1234567890", "12"),
        ("https://www.bilibili.com/video/BV1234567890", None, 999999.8, "/video/BV1234567890", "999999"),
    ],
)
def test_bilibili_jump_url_identity_and_integer_seconds(
    video_url, bvid, jump_time, expected_path, expected_time
) -> None:
    value = build_bilibili_jump_url(video_url, bvid, jump_time)
    parsed = urlsplit(value)
    assert parsed.scheme == "https" and parsed.netloc == "www.bilibili.com"
    assert parsed.path == expected_path
    assert parse_qs(parsed.query)["t"] == [expected_time]


def test_bilibili_jump_url_preserves_and_encodes_existing_query() -> None:
    value = build_bilibili_jump_url(
        "https://www.bilibili.com/video/BV1234567890?p=2&label=a%20b&t=4",
        "BVOTHER",
        65.8,
    )
    parsed = urlsplit(value)
    assert parsed.path == "/video/BV1234567890"
    assert parse_qs(parsed.query) == {"p": ["2"], "label": ["a b"], "t": ["65"]}


def test_bilibili_jump_url_handles_missing_or_invalid_identity() -> None:
    assert build_bilibili_jump_url(None, None, 10) is None
    assert build_bilibili_jump_url("not-a-url", None, 10) is None


def test_bilibili_jump_url_normalizes_protocol_relative_url() -> None:
    assert build_bilibili_jump_url(
        "//www.bilibili.com/video/BV1234567890", None, -4
    ) == "https://www.bilibili.com/video/BV1234567890?t=0"
