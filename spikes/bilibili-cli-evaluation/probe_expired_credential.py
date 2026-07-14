"""Probe invalid-credential handling in an isolated temporary HOME."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BILI = ROOT / "references" / "upstreams" / "bilibili-cli" / ".venv" / "bin" / "bili"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="shiliu-bili-invalid-") as home:
        config = Path(home) / ".bilibili-cli"
        config.mkdir()
        credential_file = config / "credential.json"
        credential_file.write_text(
            json.dumps(
                {
                    "sessdata": "deliberately-invalid-test-value",
                    "bili_jct": "",
                    "saved_at": time.time(),
                }
            )
        )
        credential_file.chmod(0o600)

        env = dict(os.environ)
        env["HOME"] = home
        result = subprocess.run(
            [str(BILI), "status", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {"parse_error": True}

        evidence = {
            "exit_code": result.returncode,
            "stdout_is_json": "parse_error" not in payload,
            "ok": payload.get("ok"),
            "error_code": payload.get("error", {}).get("code"),
            "credential_cleared": not credential_file.exists(),
            "stderr_contains_fake_secret": "deliberately-invalid-test-value" in result.stderr,
        }
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0 if evidence["credential_cleared"] and evidence["error_code"] == "not_authenticated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
