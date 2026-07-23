from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from shiliu.eval_v3_5.stage3r_qc_phase_b_r import (
    PhaseBRBlocked,
    run_phase_b_r,
    write_blocked_attempt,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Stage 3R-QC Phase B-R mode-corrected diagnostic"
    )
    parser.add_argument(
        "--snapshot-db",
        type=Path,
        default=Path(
            "/Users/elliot/Documents/Shiliu/eval/v3_stage6/"
            "20260720T094346Z_c7663365/shiliu_eval.db"
        ),
    )
    parser.add_argument(
        "--snapshot-artifacts",
        type=Path,
        default=Path(
            "/Users/elliot/Documents/Shiliu/eval/v3_stage6/"
            "20260720T094346Z_c7663365/artifacts"
        ),
    )
    parser.add_argument(
        "--artifact-manifest",
        type=Path,
        default=Path("research/v3_eval/artifact_manifest.jsonl"),
    )
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    artifact_manifest = (
        args.artifact_manifest
        if args.artifact_manifest.is_absolute()
        else repository_root / args.artifact_manifest
    )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        result = run_phase_b_r(
            repository_root=repository_root,
            snapshot_db=args.snapshot_db,
            snapshot_artifacts=args.snapshot_artifacts,
            artifact_manifest=artifact_manifest,
        )
    except PhaseBRBlocked as exc:
        result = write_blocked_attempt(repository_root, exc)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
