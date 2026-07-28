from __future__ import annotations

import argparse
import json
from pathlib import Path

from shiliu.eval_v3_5.stage3r import run_stage3r


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen Shiliu V3.5 Stage 3R evaluation.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("/tmp/shiliu-v3-5-stage2r-c4-review-v1/finalize_and_lock"),
    )
    parser.add_argument("--output-root", type=Path, default=Path("research/v3_5/stage3r"))
    parser.add_argument(
        "--snapshot-db",
        type=Path,
        default=Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db"),
    )
    parser.add_argument(
        "--snapshot-artifacts",
        type=Path,
        default=Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts"),
    )
    parser.add_argument("--artifact-manifest", type=Path, default=Path("research/v3_eval/artifact_manifest.jsonl"))
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    result = run_stage3r(
        repository_root=repository_root,
        source_root=args.source_root,
        output_root=(repository_root / args.output_root).resolve() if not args.output_root.is_absolute() else args.output_root,
        snapshot_db=args.snapshot_db,
        snapshot_artifacts=args.snapshot_artifacts,
        artifact_manifest=(
            (repository_root / args.artifact_manifest).resolve()
            if not args.artifact_manifest.is_absolute() else args.artifact_manifest
        ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print("Stage 3R Complete")
    print("Awaiting Main-session Review")


if __name__ == "__main__":
    main()
