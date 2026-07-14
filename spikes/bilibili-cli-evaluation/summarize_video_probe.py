"""Run one read-only video probe and print compact, non-content evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BILI = ROOT / "references" / "upstreams" / "bilibili-cli" / ".venv" / "bin" / "bili"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: summarize_video_probe.py <BVID>")

    result = subprocess.run(
        [str(BILI), "video", sys.argv[1], "--subtitle-timeline", "--json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    evidence: dict[str, object] = {
        "exit_code": result.returncode,
        "stdout_is_json": False,
        "stderr_empty": not bool(result.stderr),
    }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        evidence["stdout_prefix"] = result.stdout[:200]
        evidence["stderr_prefix"] = result.stderr[:200]
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return result.returncode or 1

    evidence["stdout_is_json"] = True
    evidence["ok"] = payload.get("ok")
    evidence["schema_version"] = payload.get("schema_version")
    if payload.get("ok"):
        data = payload.get("data", {})
        video = data.get("video", {})
        subtitle = data.get("subtitle", {})
        items = subtitle.get("items", [])
        transcript_text = subtitle.get("text", "")
        evidence.update(
            {
                "video_fields": sorted(video.keys()),
                "subtitle_fields": sorted(subtitle.keys()),
                "subtitle_available": subtitle.get("available"),
                "subtitle_item_count": len(items),
                "subtitle_first_from": items[0].get("from") if items else None,
                "subtitle_last_to": items[-1].get("to") if items else None,
                "transcript_sha256": hashlib.sha256(transcript_text.encode()).hexdigest(),
                "warnings": data.get("warnings", []),
            }
        )
    else:
        evidence["error"] = payload.get("error")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
