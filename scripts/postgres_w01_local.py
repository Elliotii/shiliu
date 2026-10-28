"""Task-owned W01 PostgreSQL bootstrap/lifecycle. No system service or TCP port.

Build the pinned binaries first (tests/postgres/README.md). Commands deliberately
have no arbitrary paths/DSNs. Only this private task root may be initialized.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/tmp/shiliu-w01-20261023').resolve()
IDENTITY = {'task': 'shiliu-w01-20261023', 'port': 55483}


def check_root() -> None:
    if ROOT.stat().st_uid != os.getuid() or ROOT.stat().st_mode & 0o077:
        raise SystemExit('Refusing non-private task root')
    if any((ROOT / name).is_symlink() for name in ('data', 'socket', 'pg', 'artifacts', 'instance.json')):
        raise SystemExit('Refusing symlink task resource')


def run(binary: str, *args: str, **kwargs):
    return subprocess.run([str(ROOT / 'pg' / 'bin' / binary), *args], check=True, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'start', 'stop', 'status'))
    command = parser.parse_args().command
    check_root()
    marker = ROOT / 'instance.json'
    if command == 'init':
        if marker.exists() or (ROOT / 'data').exists():
            raise SystemExit('Refusing to overwrite existing task instance')
        for name in ('socket', 'artifacts'):
            (ROOT / name).mkdir(mode=0o700, exist_ok=True)
            (ROOT / name).chmod(0o700)
        run('initdb', '-D', str(ROOT / 'data'), '--username=shiliu_w01_admin',
            '--auth-local=trust', '--auth-host=reject', '--no-locale', '--encoding=UTF8')
        # Bootstrap without opening any database socket or connecting to an
        # unprefixed default database. Only this freshly initialized data dir.
        run('postgres', '--single', '-D', str(ROOT / 'data'), 'template1',
            input='CREATE DATABASE shiliu_w01_test_control;\n'
                  'CREATE ROLE shiliu_w01_runtime LOGIN NOSUPERUSER NOCREATEDB '
                  'NOCREATEROLE NOREPLICATION NOBYPASSRLS;\n', text=True)
        marker.write_text(json.dumps(IDENTITY))
        marker.chmod(0o600)
        return
    if not marker.is_file() or json.loads(marker.read_text()) != IDENTITY:
        raise SystemExit('Refusing unknown instance')
    if command == 'start':
        run('pg_ctl', '-D', str(ROOT / 'data'), '-l', str(ROOT / 'server.log'),
            '-o', f"-k {ROOT / 'socket'} -p 55483 -c listen_addresses=''", '-w', '-t', '10', 'start')
    elif command == 'stop':
        run('pg_ctl', '-D', str(ROOT / 'data'), '-m', 'fast', '-w', '-t', '10', 'stop')
    else:
        try:
            run('pg_ctl', '-D', str(ROOT / 'data'), 'status')
        except subprocess.CalledProcessError as error:
            # pg_ctl uses exit 3 for the expected stopped state.
            raise SystemExit(error.returncode) from None


if __name__ == '__main__':
    main()
