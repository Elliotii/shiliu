"""Small subprocess bridge executed by the vendored bilibili-cli virtualenv.

This module deliberately uses only the standard library plus dependencies that
already belong to the evaluated upstream CLI. The main Shiliu process never
imports bilibili-api-python directly.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from bilibili_api import video
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents

from bili_cli import client, payloads
from bili_cli.auth import get_credential, save_credential


def _language_kind(track: dict[str, Any]) -> str | None:
    value = " ".join(
        str(track.get(key, "")) for key in ("lan", "lan_doc")
    ).lower()
    if any(token in value for token in ("zh", "中文", "chinese", "汉语", "漢語")):
        return "zh"
    if any(token in value for token in ("en", "英文", "english")):
        return "en"
    return None


def _choose_track(tracks: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    for wanted in ("zh", "en"):
        for track in tracks:
            if _language_kind(track) == wanted:
                return track, wanted
    return None, None


def _source_from_type(value: object) -> str:
    if value == 0:
        return "human"
    if value == 1:
        return "ai"
    return "unknown"


async def fetch_video(bvid: str) -> dict[str, Any]:
    credential = get_credential(mode="optional")
    resource = video.Video(bvid=bvid, credential=credential)
    info = await resource.get_info()
    pages = await resource.get_pages()
    if not pages:
        raise RuntimeError("视频没有可用分P")

    page = pages[0]
    cid = page.get("cid")
    if not cid:
        raise RuntimeError("P1 缺少 cid")
    player = await resource.get_player_info(cid=cid)
    tracks = player.get("subtitle", {}).get("subtitles", []) or []
    track, language = _choose_track(tracks)
    segments: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    if track and language:
        subtitle_url = str(track.get("subtitle_url", ""))
        if subtitle_url.startswith("//"):
            subtitle_url = "https:" + subtitle_url
        if subtitle_url:
            request = urllib.request.Request(
                subtitle_url,
                headers={"User-Agent": "Mozilla/5.0 Shiliu/0.1"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                subtitle_payload = json.loads(response.read().decode("utf-8"))
            segments = subtitle_payload.get("body", []) or []
        upstream_type = track.get("type")
        selected = {
            "language": language,
            "source": _source_from_type(upstream_type),
            "upstream_type": upstream_type if isinstance(upstream_type, int) else None,
            "upstream_language": str(track.get("lan", "")),
            "upstream_language_label": str(track.get("lan_doc", "")),
        }

    owner = info.get("owner", {}) or {}
    return {
        "bvid": bvid,
        "title": str(info.get("title", "")),
        "uploader": str(owner.get("name", "")),
        "description": str(info.get("desc", "")),
        "video_url": f"https://www.bilibili.com/video/{bvid}",
        "cover_url": info.get("pic"),
        "cid": cid,
        "part_title": str(page.get("part", "")),
        "duration_seconds": int(page.get("duration", info.get("duration", 0)) or 0),
        "page_count": len(pages),
        "subtitle_track": selected,
        "subtitle_segments": segments,
    }


async def fetch_favorite_folders() -> list[dict[str, Any]]:
    credential = get_credential(mode="optional")
    if credential is None:
        raise RuntimeError("authentication_required: 没有已保存的 B 站登录凭据")
    folders = await client.get_favorite_list(credential)
    return [payloads.normalize_favorite_folder(item) for item in folders]


async def fetch_favorites_page(folder_id: int, page: int) -> dict[str, Any]:
    credential = get_credential(mode="optional")
    if credential is None:
        raise RuntimeError("authentication_required: 没有已保存的 B 站登录凭据")
    data = await client.get_favorite_videos(folder_id, credential, page=page)
    info = data.get("info") or {}
    return {
        "folder_id": folder_id,
        "page": page,
        "has_more": bool(data.get("has_more", False)),
        "remote_total": (
            int(info["media_count"])
            if page == 1 and info.get("media_count") is not None
            else None
        ),
        "items": [_normalize_favorite_media(item) for item in (data.get("medias") or [])],
    }


async def fetch_favorite_scan(folder_id: int) -> dict[str, Any]:
    """Fetch an authoritative lightweight snapshot in one bridge process."""
    credential = get_credential(mode="optional")
    if credential is None:
        raise RuntimeError("authentication_required: 没有已保存的 B 站登录凭据")
    items: list[dict[str, Any]] = []
    remote_total: int | None = None
    page = 1
    while True:
        data = await client.get_favorite_videos(folder_id, credential, page=page)
        info = data.get("info") or {}
        if page == 1 and info.get("media_count") is not None:
            remote_total = max(0, int(info["media_count"]))
        items.extend(
            _normalize_favorite_media(item) for item in (data.get("medias") or [])
        )
        if not bool(data.get("has_more", False)):
            break
        page += 1
        if page > 500:
            raise RuntimeError("pagination_limit: 收藏夹分页超过安全上限")
        # Reusing one authenticated process removes the old per-page startup
        # delay. Keep a small deterministic pause so a large folder does not
        # become a burst of 100+ API calls and trigger Bilibili 412 controls.
        await asyncio.sleep(2)
    return {
        "folder_id": folder_id,
        "remote_total": remote_total,
        "pages_fetched": page,
        "raw_item_count": len(items),
        "items": items,
    }


def _normalize_favorite_media(item: dict[str, Any]) -> dict[str, Any]:
    normalized = payloads.normalize_favorite_media(item)
    normalized["fav_time"] = item.get("fav_time")
    normalized["ctime"] = item.get("ctime")
    normalized["pubtime"] = item.get("pubtime")
    return normalized


async def fetch_favorite_preview(folder_id: int) -> dict[str, Any]:
    credential = get_credential(mode="optional")
    if credential is None:
        raise RuntimeError("authentication_required: 没有已保存的 B 站登录凭据")
    data = await client.get_favorite_videos(folder_id, credential, page=1)
    info = data.get("info") or {}
    upper = info.get("upper") or {}
    return {
        "folder_id": int(info.get("id") or folder_id),
        "folder_title": str(info.get("title") or ""),
        "media_count": int(info.get("media_count") or 0),
        "account_id": int(info.get("mid") or upper.get("mid") or 0),
        "account_name": str(upper.get("name") or ""),
    }


async def qr_login_file(path: Path) -> None:
    login = QrCodeLogin()
    await login.generate_qrcode()
    path.parent.mkdir(parents=True, exist_ok=True)
    login.get_qrcode_picture().to_file(str(path))
    print(json.dumps({"event": "ready", "path": str(path)}, ensure_ascii=False), flush=True)
    while True:
        state = await login.check_state()
        if state == QrCodeLoginEvents.DONE:
            save_credential(login.get_credential())
            print(json.dumps({"event": "done"}), flush=True)
            return
        if state == QrCodeLoginEvents.TIMEOUT:
            raise RuntimeError("二维码已过期")
        await asyncio.sleep(2)


async def download_audio(bvid: str, path: Path) -> dict[str, Any]:
    credential = get_credential(mode="optional")
    audio_url = await client.get_audio_url(bvid, credential)
    size = await client.download_audio(audio_url, str(path))
    return {"path": str(path), "bytes": size}


async def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    valid = {
        "fetch-video": 3,
        "qr-login-file": 3,
        "favorite-folders": 2,
        "favorites-page": 4,
        "favorites-scan": 3,
        "favorite-preview": 3,
        "download-audio": 4,
    }
    if command not in valid or len(sys.argv) != valid[command]:
        print(json.dumps({"ok": False, "error": {"code": "usage", "message": "invalid bridge command"}}))
        return 2
    try:
        if command == "qr-login-file":
            await qr_login_file(Path(sys.argv[2]))
            return 0
        if command == "download-audio":
            data = await download_audio(sys.argv[2], Path(sys.argv[3]))
        if command == "favorite-folders":
            data = await fetch_favorite_folders()
        elif command == "favorites-page":
            data = await fetch_favorites_page(int(sys.argv[2]), int(sys.argv[3]))
        elif command == "favorites-scan":
            data = await fetch_favorite_scan(int(sys.argv[2]))
        elif command == "favorite-preview":
            data = await fetch_favorite_preview(int(sys.argv[2]))
        elif command != "download-audio":
            data = await fetch_video(sys.argv[2])
    except Exception as exc:
        name = type(exc).__name__
        lowered = f"{name} {exc}".lower()
        if any(token in lowered for token in ("authentication_required", "credential", "sessdata", "csrf", "-101", "未登录")):
            code = "authentication_required"
        elif any(token in lowered for token in ("412", "rate", "network", "timeout", "urlerror")):
            code = "upstream_retryable"
        else:
            code = "upstream_error"
        print(
            json.dumps(
                {"ok": False, "error": {"code": code, "message": f"{name}: {exc}"}},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"ok": True, "data": data}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
