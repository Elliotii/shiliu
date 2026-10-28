"""Small operator entry point for the existing marker-bound paired backup."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

import psycopg
from shiliu.config import LIBPQ_DISABLED_PASSFILE, load_postgres_config
from shiliu.migration.backup import create_runtime_pair, restore_pair, runtime_report, verify_pair
from shiliu.migration.safety import guard
from shiliu.migration.values import MigrationRejected


def require_quiescent(config):
    """Stopped writers must disconnect; do not stop services on the user's behalf."""
    guard(config, etl=True)
    with psycopg.connect(config.database_url, passfile=LIBPQ_DISABLED_PASSFILE,
                         connect_timeout=2, options="-c statement_timeout=3000") as conn:
        conn.read_only = True
        if config.environment == "production":
            from shiliu.migration.deployment import check_server
            check_server(conn)
        if conn.execute(
            "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid<>pg_backend_pid() LIMIT 1"
        ).fetchone():
            raise MigrationRejected("backup_requires_disconnected_writers")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('create', 'verify', 'restore'))
    parser.add_argument('directory', type=Path)
    parser.add_argument('--writers-stopped', action='store_true',
                        help='Operator confirms all Web/Worker/sync writers stopped and disconnected')
    parser.add_argument('--admin-url', help='Restore only: exact bound admin connection, no password URL')
    args = parser.parse_args(argv)
    if args.command != 'verify' and not args.writers_stopped:
        parser.error('create/restore require --writers-stopped; this command never stops services')
    if args.command == 'verify':
        manifest = verify_pair(args.directory)
    else:
        config = load_postgres_config()
        require_quiescent(config)
        if args.command == 'create':
            manifest = create_runtime_pair(config, args.directory.name, args.directory)
        else:
            if not args.admin_url:
                parser.error('restore requires --admin-url for an independent empty target')
            admin = replace(config, database_url=args.admin_url)
            guard(admin, admin=True)
            manifest = restore_pair(args.directory, admin, config)
            if runtime_report(config) != manifest['validation']:
                raise MigrationRejected('restored_runtime_validation_mismatch')
    print(json.dumps({'status': 'verified', 'command': args.command,
                      'revision': manifest['validation'].get('revision'),
                      'dump_sha256': manifest['dump_sha256'],
                      'artifact_count': len(manifest['artifacts'])}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
