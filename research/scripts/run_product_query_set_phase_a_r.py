from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.product_query_set_phase_a_r import build_phase_a_r


if __name__ == "__main__":
    print(json.dumps(build_phase_a_r(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2, sort_keys=True))
