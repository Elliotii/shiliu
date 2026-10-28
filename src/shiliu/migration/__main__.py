"""Explicit W04 CLI; no implicit source, DSN, Artifact root or application startup."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

import psycopg

from shiliu.config import PostgresConfig
from shiliu.migration.safety import guard, guard_input_target
from shiliu.migration.snapshot import inspect_snapshot, plan_snapshot
from shiliu.migration.etl import import_snapshot, validate_snapshot, _connect
from shiliu.migration.values import MigrationRejected
from shiliu.migration.rebuild import rebuild_snapshot
from shiliu.retrieval.qwen import LocalModelNotReadyError


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "invalid_migration_arguments\n")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["inspect", "plan", "import", "validate", "rebuild", "report"],
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--source-content-root", type=Path)
    parser.add_argument("--owner-map", type=Path)
    parser.add_argument("--embedding", choices=["none", "qwen"], default="none")
    parser.add_argument("--model-path", type=Path)
    args = parser.parse_args(argv)
    try:
        for selected, expected in [
            (args.source_manifest, args.source.parent / "artifacts.json"),
            (args.source_content_root, args.source.parent / "files"),
            (args.owner_map, args.source.parent / "ownership.json"),
        ]:
            if selected is not None and selected.resolve() != expected.resolve():
                raise MigrationRejected("explicit_source_package_member_mismatch")
        config = PostgresConfig(args.database_url, args.artifact_root, args.environment)
        guard(config, etl=True)
        guard_input_target(args.source, config)
        if args.command in {"inspect", "plan"}:
            identity, rows = (
                inspect_snapshot if args.command == "inspect" else plan_snapshot
            )(args.source)
            result = {
                "run_id": args.run_id,
                "source_manifest_hash": identity["manifest_hash"],
                "mapping_version": identity["mapping_version"],
                "synthetic_only": identity["provenance"]["synthetic_only"],
                "planned_counts": {k: len(v) for k, v in rows.items()},
                "target_modified": False,
            }
        elif args.command == "import":
            result = import_snapshot(args.source, config, args.run_id)
        elif args.command == "validate":
            result = validate_snapshot(args.source, config, args.run_id)
        elif args.command == "rebuild":
            provider = None
            if args.embedding == "qwen":
                from shiliu.retrieval.qwen import (
                    QwenEmbeddingProvider,
                    verify_qwen_snapshot,
                )

                provider = QwenEmbeddingProvider(
                    **({"model_path": args.model_path} if args.model_path else {})
                )
                verify_qwen_snapshot(provider.model_path)
            result = rebuild_snapshot(
                args.source, config, args.run_id, provider=provider
            )
        else:
            identity, _ = inspect_snapshot(args.source)
            with _connect(config) as conn:
                conn.read_only = True
                row = conn.execute(
                    "SELECT run_id,status,source_manifest_hash,mapping_version FROM shiliu.migration_runs WHERE run_id=%s",
                    (args.run_id,),
                ).fetchone()
                if row is None:
                    raise MigrationRejected("migration_run_missing")
                if row["source_manifest_hash"] != identity["manifest_hash"]:
                    raise MigrationRejected("migration_input_identity_conflict")
                result = dict(row)
                from shiliu.migration.projection_state import receipt

                state = receipt(conn, args.run_id)
                result["rebuild_status"] = state["status"] if state else "not_requested"
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (
        MigrationRejected,
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        OSError,
        psycopg.Error,
        LocalModelNotReadyError,
    ) as error:
        category = (
            str(error)
            if isinstance(error, MigrationRejected)
            else "offline_embedding_unavailable"
            if isinstance(error, LocalModelNotReadyError)
            else "migration_configuration_or_database_failure"
        )
        print(json.dumps({"error": category}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
