"""Inspect public page and subtitle-track metadata without downloading text."""

from __future__ import annotations

import asyncio
import json
import sys

from bilibili_api import video

from bili_cli.auth import get_credential


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: inspect_video_tracks.py <BVID>")

    credential = get_credential(mode="optional")
    resource = video.Video(bvid=sys.argv[1], credential=credential)
    pages = await resource.get_pages()
    result: list[dict[str, object]] = []
    for index, page in enumerate(pages, 1):
        cid = page.get("cid")
        player = await resource.get_player_info(cid=cid)
        tracks = player.get("subtitle", {}).get("subtitles", [])
        result.append(
            {
                "page": index,
                "cid": cid,
                "part": page.get("part", ""),
                "duration": page.get("duration", 0),
                "tracks": [
                    {
                        "id": track.get("id"),
                        "lan": track.get("lan", ""),
                        "lan_doc": track.get("lan_doc", ""),
                        "type": track.get("type"),
                    }
                    for track in tracks
                ],
            }
        )
    print(json.dumps({"bvid": sys.argv[1], "page_count": len(pages), "pages": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
