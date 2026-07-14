"""Capture one newly discovered video's normalized metadata and raw P1 subtitles.

This helper is intentionally read-only with respect to Bilibili and the saved
favorite baseline. It writes only local spike artifacts for inspection.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BILI = ROOT / "references" / "upstreams" / "bilibili-cli" / ".venv" / "bin" / "bili"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def format_seconds(value: float) -> str:
    milliseconds = round(value * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: capture_video_fixture.py <BVID>")

    bvid = sys.argv[1]
    result = subprocess.run(
        [str(BILI), "video", bvid, "--subtitle-timeline", "--json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"bili exited {result.returncode}")

    payload = json.loads(result.stdout)
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("error")))

    data = payload["data"]
    video = data["video"]
    subtitle = data["subtitle"]
    items = subtitle.get("items") or []

    destination = ARTIFACTS / bvid
    destination.mkdir(parents=True, exist_ok=True)
    metadata_path = destination / "metadata.json"
    subtitle_json_path = destination / "subtitle-raw.json"
    subtitle_text_path = destination / "subtitle-raw.txt"

    metadata_path.write_text(
        json.dumps(video, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subtitle_json_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subtitle_text_path.write_text(
        "\n".join(
            f"[{format_seconds(float(item['from']))} --> {format_seconds(float(item['to']))}] {item['content']}"
            for item in items
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "bvid": bvid,
                "title": video.get("title"),
                "subtitle_items": len(items),
                "metadata_path": str(metadata_path),
                "subtitle_json_path": str(subtitle_json_path),
                "subtitle_text_path": str(subtitle_text_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
