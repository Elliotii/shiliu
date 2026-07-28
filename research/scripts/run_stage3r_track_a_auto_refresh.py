from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from shiliu.eval_v3_5.stage3r_track_a_auto_refresh import (
    TrackAAutoRefreshBlocked,
    run_stage3r_track_a_auto_refresh,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen omitted-mode Product Auto Stage 3R Track A refresh.")
    parser.add_argument("--snapshot-db", type=Path, default=Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db"))
    parser.add_argument("--snapshot-artifacts", type=Path, default=Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts"))
    parser.add_argument("--artifact-manifest", type=Path, default=Path("research/v3_eval/artifact_manifest.jsonl"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        result = run_stage3r_track_a_auto_refresh(repository_root=root, snapshot_db=args.snapshot_db, snapshot_artifacts=args.snapshot_artifacts, artifact_manifest=(root / args.artifact_manifest if not args.artifact_manifest.is_absolute() else args.artifact_manifest))
    except TrackAAutoRefreshBlocked as exc:
        print(json.dumps({"status": "blocked", "code": exc.code, "message": str(exc), "details": exc.details}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print("Stage 3R-QC-R Complete")
    print("Awaiting Human Review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
