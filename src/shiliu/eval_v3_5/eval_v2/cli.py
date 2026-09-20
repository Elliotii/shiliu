from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts import AnnotationPacketV2
from .hashing import canonical_bytes, stable_sha256
from .providers import build_deepseek_secondary_request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 2R-A local-only dry-run tools")
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    packet = AnnotationPacketV2.model_validate_json(args.packet.read_text())
    request = build_deepseek_secondary_request(packet, "SECONDARY_PROMPT_V2")
    result = {"dry_run": True, "real_provider_calls": 0, "case_input_sha256": packet.case_input_sha256,
              "request_body_sha256": stable_sha256(request.body), "provider_usage": request.provider_usage}
    encoded = canonical_bytes(result) + b"\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    else: print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
