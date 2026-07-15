from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


PRIVATE_DIR = Path(__file__).resolve().parent / "private_reference"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_taxonomy(path: Path, version: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != version:
        raise ValueError("reference taxonomy version does not match --version")
    if not isinstance(payload.get("content_types"), list) or not isinstance(payload.get("domains"), list):
        raise ValueError("reference taxonomy must contain content_types and domains arrays")
    if not payload["content_types"] and not payload["domains"]:
        raise ValueError("empty reference taxonomy cannot be frozen")


def validate_gold(path: Path) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 40:
        raise ValueError("Gold Set must contain exactly 40 non-empty JSONL rows")
    keys = [row.get("content_key") for row in rows]
    if any(row.get("review_status") != "human_confirmed" for row in rows):
        raise ValueError("every Gold Set row must be human_confirmed")
    if len(set(keys)) != len(keys) or any(not key for key in keys):
        raise ValueError("Gold Set content_key values must be non-empty and unique")


def freeze(taxonomy: Path, gold: Path, version: str) -> dict[str, object]:
    if not version.startswith("v") or not version[1:].isdigit():
        raise ValueError("version must look like v1, v2, ...")
    taxonomy = taxonomy.expanduser().resolve()
    gold = gold.expanduser().resolve()
    validate_taxonomy(taxonomy, version)
    validate_gold(gold)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    taxonomy_target = PRIVATE_DIR / f"reference_taxonomy_{version}.yaml"
    gold_target = PRIVATE_DIR / (
        "gold_eval_set_40.jsonl" if version == "v1" else f"gold_eval_set_40_{version}.jsonl"
    )
    manifest_target = PRIVATE_DIR / f"reference_manifest_{version}.json"
    targets = [taxonomy_target, gold_target, manifest_target]
    if any(path.exists() for path in targets):
        raise FileExistsError(f"reference version {version} already exists and cannot be overwritten")
    shutil.copyfile(taxonomy, taxonomy_target)
    shutil.copyfile(gold, gold_target)
    manifest = {
        "version": version,
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "human_confirmed": True,
        "reference_taxonomy": {"path": taxonomy_target.name, "sha256": sha256(taxonomy_target)},
        "gold_eval_set": {"path": gold_target.name, "sha256": sha256(gold_target), "row_count": 40},
    }
    temporary = manifest_target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_target)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze a human-authored V3 reference version")
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.taxonomy, args.gold, args.version), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
