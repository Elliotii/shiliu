"""Compare the target folder with the saved first-scan baseline.

This is a read-only spike helper. It does not update the baseline or fetch video
metadata/subtitles; it only reports source-id set differences.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BILI = ROOT / "references" / "upstreams" / "bilibili-cli" / ".venv" / "bin" / "bili"
BASELINE = HERE / "artifacts" / "llm-baseline.json"


def fetch_page(folder_id: int, page: int) -> dict:
    result = subprocess.run(
        [str(BILI), "favorites", str(folder_id), "--page", str(page), "--json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"favorites page {page} failed with exit code {result.returncode}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    if not payload.get("ok"):
        raise RuntimeError(f"favorites page {page} returned an error envelope: {payload.get('error')}")
    return payload["data"]


def main() -> None:
    baseline = json.loads(BASELINE.read_text())
    folder_id = int(baseline["folder_id"])
    seen = set(baseline["seen_source_ids"])

    current: set[str] = set()
    page = 1
    while True:
        data = fetch_page(folder_id, page)
        current.update(item["bvid"] for item in data.get("items", []) if item.get("bvid"))
        if not data.get("has_more"):
            break
        page += 1

    print(
        json.dumps(
            {
                "folder_name": baseline["folder_name"],
                "pages_scanned": page,
                "baseline_count": len(seen),
                "current_count": len(current),
                "new_source_ids": sorted(current - seen),
                "removed_source_ids": sorted(seen - current),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
