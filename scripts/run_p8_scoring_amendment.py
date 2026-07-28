#!/usr/bin/env python3
"""Generate P8 Scoring Amendment v1 from immutable persisted artifacts."""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path


if __name__ == "__main__":
    repository_root = Path(__file__).resolve().parents[1]
    module_path = repository_root / "src/shiliu/eval_v3_5/p8_scoring_amendment.py"
    spec = importlib.util.spec_from_file_location("p8_scoring_amendment", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.generate(repository_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
