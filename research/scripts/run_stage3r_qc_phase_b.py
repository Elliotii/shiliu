from __future__ import annotations

import argparse
import json
from pathlib import Path

from shiliu.eval_v3_5.stage3r_qc_phase_b import (
    PhaseBBlocked,
    run_phase_b,
    write_blocked_attempt,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Stage 3R-QC Phase B input gate")
    parser.add_argument("approved_query_file", type=Path)
    parser.add_argument(
        "--snapshot-db", type=Path,
        default=Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db"),
    )
    parser.add_argument(
        "--snapshot-artifacts", type=Path,
        default=Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts"),
    )
    parser.add_argument(
        "--artifact-manifest", type=Path,
        default=Path("research/v3_eval/artifact_manifest.jsonl"),
    )
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    try:
        artifact_manifest = (
            args.artifact_manifest
            if args.artifact_manifest.is_absolute()
            else repository_root / args.artifact_manifest
        )
        result = run_phase_b(
            repository_root=repository_root,
            approved_query_file=args.approved_query_file,
            snapshot_db=args.snapshot_db,
            snapshot_artifacts=args.snapshot_artifacts,
            artifact_manifest=artifact_manifest,
        )
    except PhaseBBlocked as exc:
        result = write_blocked_attempt(repository_root, exc, args.approved_query_file)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
