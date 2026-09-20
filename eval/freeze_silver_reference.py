from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIVATE_DIR = Path(__file__).resolve().parent / "private_reference"
ALLOWED_BUCKETS = {
    "high_evidence_clear",
    "high_evidence_cross_domain",
    "evidence_c",
    "boundary_or_confusing",
    "evidence_d_or_unavailable",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate_taxonomy(path: Path, version: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != version or payload.get("reference_kind") != "silver":
        raise ValueError("Silver taxonomy version or reference_kind is invalid")
    if not isinstance(payload.get("content_types"), list) or not isinstance(payload.get("domains"), list):
        raise ValueError("Silver taxonomy must contain content_types and domains arrays")
    if not payload["content_types"] and not payload["domains"]:
        raise ValueError("Empty Silver taxonomy cannot be frozen")


def validate_eval_set(path: Path) -> tuple[int, dict[str, int]]:
    rows = _jsonl(path)
    if not 35 <= len(rows) <= 45:
        raise ValueError("Silver Eval Set must contain approximately 40 rows (35-45)")
    keys = [row.get("content_key") for row in rows]
    if len(set(keys)) != len(keys) or any(not key for key in keys):
        raise ValueError("Silver Eval content_key values must be non-empty and unique")
    buckets = Counter(str(row.get("selection_bucket") or "") for row in rows)
    if set(buckets) - ALLOWED_BUCKETS or any(not row.get("selection_reason") for row in rows):
        raise ValueError("Every Silver Eval row needs a valid bucket and selection reason")
    if any(row.get("silver_agreement") not in {"agreed", "adjudicated"} for row in rows):
        raise ValueError("Every Silver Eval row needs a Silver agreement status")
    return len(rows), dict(sorted(buckets.items()))


def validate_calls(path: Path) -> int:
    rows = _jsonl(path)
    roles = {str(row.get("evaluator_role")) for row in rows if row.get("status") == "completed"}
    if not {"evaluator_a", "evaluator_b", "evaluator_c"}.issubset(roles):
        raise ValueError("Completed independent calls for Evaluator A, B, and C are required")
    required = {"model", "prompt_version", "parameters", "input_hash", "output_hash", "output_path"}
    if any(not required.issubset(row) for row in rows):
        raise ValueError("Silver call audit is missing required metadata")
    return len(rows)


def freeze(
    *,
    taxonomy: Path,
    eval_set: Path,
    disagreements: Path,
    calls: Path,
    version: str,
    snapshot_id: int,
    snapshot_hash: str,
) -> dict[str, Any]:
    if not version.startswith("v") or not version[1:].isdigit():
        raise ValueError("version must look like v1, v2, ...")
    if len(snapshot_hash) != 64:
        raise ValueError("snapshot_hash must be SHA-256")
    taxonomy, eval_set, disagreements, calls = [
        path.expanduser().resolve() for path in (taxonomy, eval_set, disagreements, calls)
    ]
    validate_taxonomy(taxonomy, version)
    row_count, bucket_counts = validate_eval_set(eval_set)
    disagreement_count = len(_jsonl(disagreements))
    call_count = validate_calls(calls)

    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if version == "v1" else f"_{version}"
    targets = {
        "silver_reference_taxonomy": PRIVATE_DIR / f"silver_reference_taxonomy_{version}.yaml",
        "silver_eval_set": PRIVATE_DIR / f"silver_eval_set_40{suffix}.jsonl",
        "silver_disagreements": PRIVATE_DIR / f"silver_disagreements_{version}.jsonl",
        "silver_calls": PRIVATE_DIR / f"silver_calls_{version}.jsonl",
    }
    manifest_target = PRIVATE_DIR / f"silver_reference_manifest_{version}.json"
    if manifest_target.exists() or any(path.exists() for path in targets.values()):
        raise FileExistsError(f"Silver Reference {version} already exists and cannot be overwritten")
    sources = {
        "silver_reference_taxonomy": taxonomy,
        "silver_eval_set": eval_set,
        "silver_disagreements": disagreements,
        "silver_calls": calls,
    }
    for name, target in targets.items():
        shutil.copyfile(sources[name], target)
    manifest: dict[str, Any] = {
        "version": version,
        "reference_kind": "silver",
        "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash,
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifacts": {
            name: {"path": path.name, "sha256": sha256(path)}
            for name, path in targets.items()
        },
        "counts": {
            "eval_rows": row_count,
            "selection_buckets": bucket_counts,
            "disagreements": disagreement_count,
            "evaluator_calls": call_count,
        },
        "evaluation_semantics": {
            "true_accuracy": "not_claimed",
            "human_satisfaction": "not_evaluated",
            "human_modification_rate": "not_evaluated",
        },
    }
    temporary = manifest_target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_target)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze an independently generated Silver Reference")
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--eval-set", type=Path, required=True)
    parser.add_argument("--disagreements", type=Path, required=True)
    parser.add_argument("--calls", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--snapshot-id", type=int, required=True)
    parser.add_argument("--snapshot-hash", required=True)
    args = parser.parse_args()
    manifest = freeze(
        taxonomy=args.taxonomy,
        eval_set=args.eval_set,
        disagreements=args.disagreements,
        calls=args.calls,
        version=args.version,
        snapshot_id=args.snapshot_id,
        snapshot_hash=args.snapshot_hash,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
