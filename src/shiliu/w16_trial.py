"""W16's local Web handoff; external generation remains explicitly paused."""

from __future__ import annotations

import re

from shiliu.domain import PipelineError


def trial_request_allowed(
    method: str, path: str, *, manual_models: bool = False
) -> bool:
    # Setup GETs include credential status, remote folder discovery and login.
    if path == "/api/setup" or path.startswith("/api/setup/"):
        return False
    if method in {"GET", "HEAD", "OPTIONS"}:
        return True
    if (
        manual_models
        and method == "POST"
        and any(
            re.fullmatch(pattern, path)
            for pattern in (
                r"/api/ask(?:/stream|/runs)?",
                r"/api/ask/runs/[^/]+/abort",
                r"/api/assistant/threads/[^/]+/runs",
                r"/api/assistant/runs/[^/]+/(?:cancel|resume|finish)",
            )
        )
    ):
        return True
    if path == "/api/assistant/wiki/organize":
        return False
    # Keep this list small: no Research execution can invoke its global recovery
    # coordinator, and no settings request can touch Keychain/launchd/old config.
    return any(
        re.fullmatch(pattern, path)
        for pattern in (
            r"/api/search(?:/raw)?",
            r"/api/evidence-sufficiency",
            r"/api/videos/[^/]+/(?:ignore|restore|reading-state|mark|archive|notes)",
            r"/api/notes/[^/]+",
            r"/api/assistant/spaces(?:/[^/]+)?",
            r"/api/assistant/threads",
            r"/api/assistant/memory-settings",
            r"/api/assistant/memories(?:/[^/]+(?:/undo-created)?)?",
            r"/api/assistant/wiki/[^/]+(?:/(?:notes|revert|lifecycle))?",
        )
    )


def paused_provider(*_args, **_kwargs):
    # Defense in depth: fail before consulting Keychain or constructing a client.
    raise PipelineError(
        "迁移体验尚未开放模型调用。", code="trial_model_paused", retryable=False
    )


def provider_availability():
    return {"available": False, "reason": "迁移体验仅开放本地功能，模型调用待授权。"}


class PausedIngestionAdapter:
    def __getattr__(self, name):
        raise PipelineError(
            "体验期间采集和元数据刷新保持暂停。",
            code="trial_ingestion_paused",
            retryable=False,
        )


def main():
    import os
    import uvicorn
    from psycopg.conninfo import make_conninfo
    from shiliu.app import Application
    from shiliu.config import AppConfig, AppPaths, PostgresConfig, load_config
    from shiliu.migration import deployment as d
    from shiliu.web import create_web_app

    os.umask(0o077)
    root = d.binding()
    pg = PostgresConfig(
        make_conninfo(
            host=str(root / "socket"), port=55484, dbname="shiliu_w16", user=d.RUNTIME
        ),
        root / "artifacts",
        "production",
    )
    d.guard(pg)
    for name in ("state", "config", "content", "logs"):
        d.private(root / name)
    paths = AppPaths(
        root / "state",
        root / "content",
        root / "state/unused.sqlite3",
        root / "config/trial.toml",
        root / "logs",
        root / "content/videos",
        root / "state/sync.lock",
    )
    manual_model_since = None
    manual = root / "config/manual-models.json"
    config = AppConfig(
        content_dir=str(root / "content"),
        assistant_enabled=True,
        baseline_confirmed=True,
        api_key_ref="",
        asr_api_key_ref="",
    )
    if manual.exists():
        import json
        from datetime import datetime

        d.private(manual, directory=False)
        approval = json.loads(manual.read_text())
        if (
            approval["task"] != d.TASK
            or approval["scope"] != "user-triggered-fast-deep-assistant"
            or approval["enabled"] is not True
        ):
            raise ValueError("Refusing unknown manual-model authorization")
        manual_model_since = approval["authorized_at"]
        if datetime.fromisoformat(manual_model_since).tzinfo is None:
            raise ValueError("Manual-model authorization requires UTC identity")
        d.private(paths.config, directory=False)
        config = load_config(paths)
        if (
            config.llm_base_url != "https://api.deepseek.com/v1"
            or config.content_dir != str(root / "content")
            or config.auto_sync_enabled
            or config.asr_api_key_ref
            or not config.api_key_ref
        ):
            raise ValueError("Refusing unsafe manual trial configuration")
    core = Application(
        paths,
        postgres_config=pg,
        config=config,
        provider_factory=None if manual_model_since else paused_provider,
        assistant_provider_factory=None if manual_model_since else paused_provider,
        extraction_provider_factory=paused_provider,
        provider_availability=provider_availability,
        adapter=PausedIngestionAdapter(),
    )
    web = create_web_app(
        core,
        background_tasks=False,
        local_projections_only=True,
        manual_model_since=manual_model_since,
    )

    @web.middleware("http")
    async def record_first_mutation(request, call_next):
        response = await call_next(request)
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and 200 <= response.status_code < 300
        ):
            from datetime import datetime, timezone
            import json

            # A conservative boundary: the first successful mutation request
            # may have committed data. Never infer safe rollback from later GETs.
            try:
                with (
                    root / "execution/trial-first-successful-mutation-private.json"
                ).open("x") as f:
                    json.dump(
                        {
                            "at": datetime.now(timezone.utc).isoformat(),
                            "method": request.method,
                            "path": request.url.path,
                            "status": response.status_code,
                            "keep_new_system_data": True,
                        },
                        f,
                    )
            except FileExistsError:
                pass
        return response

    uvicorn.run(web, host="127.0.0.1", port=18525, access_log=False)


if __name__ == "__main__":
    main()
