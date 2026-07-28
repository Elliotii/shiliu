from __future__ import annotations

import argparse
import json
from pathlib import Path

from shiliu.eval_v3_5.stage3r_s1 import run_stage3r_s1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair Stage 3R segment identity scoring and rescore frozen predictions."
    )
    parser.add_argument("--stage3r-root", type=Path, default=Path("research/v3_5/stage3r"))
    parser.add_argument("--output-root", type=Path, default=Path("research/v3_5/stage3r_s1"))
    parser.add_argument(
        "--artifact-manifest", type=Path,
        default=Path("research/v3_eval/artifact_manifest.jsonl"),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    resolve = lambda value: value if value.is_absolute() else (root / value).resolve()
    result = run_stage3r_s1(
        repository_root=root, stage3r_root=resolve(args.stage3r_root),
        output_root=resolve(args.output_root),
        artifact_manifest=resolve(args.artifact_manifest),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print("Stage 3R-S1 Complete")
    print("Awaiting Main-session Review")


if __name__ == "__main__":
    main()
