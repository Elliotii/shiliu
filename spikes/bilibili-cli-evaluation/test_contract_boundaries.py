"""Reproducible tests for bilibili-cli boundaries relevant to Shiliu."""

from __future__ import annotations

import pytest
from bilibili_api.exceptions import ResponseCodeException

from bili_cli import client
from bili_cli.exceptions import RateLimitError


class FakeVideo:
    def __init__(self) -> None:
        self.player_info_cids: list[int] = []

    async def get_pages(self):
        return [{"cid": 111, "part": "P1"}, {"cid": 222, "part": "P2"}]

    async def get_player_info(self, cid: int):
        self.player_info_cids.append(cid)
        return {
            "subtitle": {
                "subtitles": [
                    {"lan": "ja-JP", "subtitle_url": "https://example.test/ja"},
                    {"lan": "en-US", "subtitle_url": "https://example.test/en"},
                ]
            }
        }


class FakeResponse:
    def __init__(self, url: str) -> None:
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        return None

    async def json(self, content_type=None):
        language = "Japanese" if self.url.endswith("/ja") else "English"
        return {"body": [{"from": 0, "to": 1, "content": language}]}


class FakeSession:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return FakeResponse(url)


@pytest.mark.asyncio
async def test_v0_subtitle_implementation_reads_first_part_only(monkeypatch):
    fake_video = FakeVideo()
    monkeypatch.setattr(client.video, "Video", lambda **kwargs: fake_video)
    monkeypatch.setattr(client.aiohttp, "ClientSession", FakeSession)

    await client.get_video_subtitle("BV1ABcsztEcY")

    assert fake_video.player_info_cids == [111]


@pytest.mark.asyncio
async def test_current_fallback_chooses_first_arbitrary_track_not_english(monkeypatch):
    fake_video = FakeVideo()
    monkeypatch.setattr(client.video, "Video", lambda **kwargs: fake_video)
    monkeypatch.setattr(client.aiohttp, "ClientSession", FakeSession)

    text, _items = await client.get_video_subtitle("BV1ABcsztEcY")

    assert text == "Japanese"


def test_http_412_maps_to_rate_limit_error():
    mapped = client._map_api_error("test", ResponseCodeException(-412, "rate limited", {}))
    assert isinstance(mapped, RateLimitError)
