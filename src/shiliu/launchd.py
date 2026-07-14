from __future__ import annotations

import html
import shutil
import subprocess
import sys
from pathlib import Path

from shiliu.config import AppPaths


LABEL = "app.shiliu.sync"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install_launch_agent(paths: AppPaths, *, load: bool = True) -> Path:
    executable = shutil.which("shiliu")
    if executable:
        arguments = [executable, "sync", "--scheduled"]
    else:
        arguments = [sys.executable, "-m", "shiliu", "sync", "--scheduled"]
    destination = plist_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    arguments_xml = "\n".join(f"      <string>{html.escape(item)}</string>" for item in arguments)
    document = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{arguments_xml}
  </array>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>{html.escape(str(paths.logs_dir / 'launchd.out.log'))}</string>
  <key>StandardErrorPath</key>
  <string>{html.escape(str(paths.logs_dir / 'launchd.err.log'))}</string>
</dict>
</plist>
"""
    temporary = destination.with_suffix(".plist.tmp")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(destination)
    if load:
        domain = f"gui/{_uid()}"
        subprocess.run(["launchctl", "bootout", domain, str(destination)], check=False, capture_output=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(destination)], check=True)
    return destination


def _uid() -> int:
    import os

    return os.getuid()

