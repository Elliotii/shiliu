from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from shiliu.eval_v3_5.p8_product_initial_baseline import P8Blocked, run_blind, score_frozen


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the P8 Product Initial Baseline.")
    parser.add_argument("phase", choices=("blind", "score"))
    parser.add_argument("--snapshot-db", type=Path, default=Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db"))
    parser.add_argument("--snapshot-artifacts", type=Path, default=Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        if args.phase == "blind":
            result = run_blind(repository_root=root, snapshot_db=args.snapshot_db, snapshot_artifacts=args.snapshot_artifacts)
        else:
            result = score_frozen(repository_root=root, snapshot_db=args.snapshot_db)
    except P8Blocked as exc:
        print(json.dumps({"status": "blocked", "category": exc.category, "message": str(exc), "details": exc.details}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
