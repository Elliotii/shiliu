from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.product_query_set_phase_a import build_phase_a


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(build_phase_a(root), ensure_ascii=False, indent=2, sort_keys=True))
