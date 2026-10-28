"""Fixed W16 production entrypoint; normal domain recovery, explicit resources."""

from __future__ import annotations

from contextlib import ExitStack
import json
import os
import time

from shiliu.app import Application
from shiliu.config import AppPaths, load_config, load_postgres_config
from shiliu.migration import deployment


class DisabledContext7:
    """The cutover does not authorize connecting an unrelated external tool."""

    async def connect(self):
        raise RuntimeError("context7_disabled_by_deployment")


def production_application():
    root = deployment.binding()
    pg = load_postgres_config()
    deployment.guard(pg)
    paths = AppPaths.defaults()
    if paths.state_dir != root / "state" or paths.content_dir != root / "content":
        raise ValueError("Refusing non-bound production application paths")
    deployment.private(paths.config, directory=False)
    config = load_config(paths)
    if (config.content_dir != str(root / "content")
            or config.llm_base_url != "https://api.deepseek.com/v1"
            or config.model_for("grounded_answer_deep") != "deepseek-v4-flash"
            or config.model_for("assistant") != "deepseek-v4-flash"):
        raise ValueError("Refusing unexpected production model or content binding")
    return Application(paths, postgres_config=pg, config=config, context7=DisabledContext7())


def wait_for_database(*, timeout=30):
    """launchd has no ordering dependency; wait boundedly for this exact server."""
    import psycopg
    from shiliu.config import LIBPQ_DISABLED_PASSFILE

    config = load_postgres_config()
    deployment.guard(config)
    deadline = time.monotonic() + timeout
    while True:
        try:
            with psycopg.connect(config.database_url, passfile=LIBPQ_DISABLED_PASSFILE,
                                 connect_timeout=2) as conn:
                # The operator verifies pgdata with the ETL settings privilege.
                # Runtime needs no broad pg_read_all_settings grant: its socket,
                # role and database are already bound by the private marker.
                if conn.info.server_version != 180006:
                    raise ValueError("Unexpected production PostgreSQL version")
            return
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                raise RuntimeError("production_database_start_timeout") from None
            time.sleep(.5)


def main():
    import uvicorn
    from shiliu.cli import build_parser, _execute
    from shiliu.web import create_web_app

    os.umask(0o077)
    arguments = build_parser().parse_args()
    wait_for_database()
    if arguments.command == "serve":
        if arguments.port not in {18520, 18525}:
            raise ValueError("W16 production Web is bound to port 18525")
        core = production_application()
        web = create_web_app(core, background_tasks=not arguments.no_background)
        uvicorn.run(web, host="127.0.0.1", port=18525, access_log=False)
        return 0
    with ExitStack() as stack:
        def factory():
            return stack.enter_context(production_application())

        if arguments.command == "sync":
            core = factory()
            if not core.config.auto_sync_enabled and not arguments.manual:
                # Respect the user's switch; the extra deployment budget hold
                # was withdrawn by the approved final closeout contract.
                print(json.dumps({"status": "paused", "reason": "auto_sync_disabled"}))
                return 0
            return _execute(arguments, lambda: core)
        return _execute(arguments, factory)


if __name__ == "__main__":
    raise SystemExit(main())
