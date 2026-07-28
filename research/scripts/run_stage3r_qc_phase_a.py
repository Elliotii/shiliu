from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.stage3r_qc_phase_a import build_phase_a


if __name__ == "__main__":
    repository_root = Path(__file__).resolve().parents[1]
    print(json.dumps(build_phase_a(repository_root), ensure_ascii=False, indent=2, sort_keys=True))
