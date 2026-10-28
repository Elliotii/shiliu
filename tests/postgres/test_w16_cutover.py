"""Normal production lifecycle is distinct from the earlier local-only trial."""

from shiliu.app import Application
from shiliu.ask.persistence import AskRunStore
from shiliu.config import AppConfig
from shiliu.w16_service import DisabledContext7
from test_application_pg import application_target  # noqa: F401
from test_collection_retrieval import FixedProvider


def test_normal_recovery_and_background_start_without_external_extension(
    application_target, app_paths, monkeypatch
):
    from shiliu.assistant.dependencies import Context7MCPClient

    def external_forbidden(*args, **kwargs):
        raise AssertionError("external Context7 or paid model was called")

    monkeypatch.setattr(Context7MCPClient, "connect", external_forbidden)
    core = Application(
        app_paths, postgres_config=application_target[0],
        config=AppConfig(content_dir=str(app_paths.content_dir), assistant_enabled=True),
        embedding_provider=FixedProvider(), adapter=object(),
        context7=DisabledContext7(), assistant_provider_factory=external_forbidden,
        extraction_provider_factory=external_forbidden,
    )
    store = AskRunStore(core.db)
    store.start(run_id="cutover-owner-loss", query="synthetic", mode="deep", filters={})
    try:
        core.start(background_tasks=True)
        assert store.get_run("cutover-owner-loss")["termination_reason"] == "interrupted"
        assert not core.assistant_runtime.local_projections_only
        caps = core.assistant_runtime.capabilities()
        assert caps["background_maintenance"] == "enabled"
        assert caps["context7"] == "unavailable"
        assert core.research_recovery._thread.is_alive()
        assert core._projection_thread.is_alive()
    finally:
        core.close()
    assert core.pg._pool.closed
    assert core.assistant_runtime._thread is None
    assert not core.research_recovery._thread.is_alive()


def test_scheduler_reinstall_keeps_fixed_runtime_and_explicit_pg_environment(
    monkeypatch, tmp_path, app_paths
):
    import plistlib
    from shiliu import launchd

    destination = tmp_path / "sync.plist"
    monkeypatch.setattr(launchd, "plist_path", lambda: destination)
    env = {
        "SHILIU_SERVICE_MODULE": "shiliu.w16_service",
        "SHILIU_DATABASE_URL": "host=/synthetic/socket dbname=synthetic user=synthetic",
        "SHILIU_ARTIFACT_ROOT": "/synthetic/artifacts",
        "SHILIU_ENV": "production", "SHILIU_STATE_DIR": "/synthetic/state",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-be-copied")
    launchd.install_launch_agent(app_paths, load=False)
    data = plistlib.loads(destination.read_bytes())
    assert data["ProgramArguments"][1:] == ["-I", "-m", "shiliu.w16_service", "sync", "--scheduled"]
    assert all(data["EnvironmentVariables"][key] == value for key, value in env.items())
    assert "UNRELATED_SECRET" not in data["EnvironmentVariables"]


def test_flash_research_uses_registered_conservative_price_and_existing_cap(
    application_target, app_paths, monkeypatch
):
    from decimal import Decimal
    import pytest
    import shiliu.app as app_module
    from shiliu.research.provider_wiring import ProviderPricePolicy
    from shiliu.research.errors import ResearchValidationError

    monkeypatch.setattr(app_module, "load_api_key", lambda _: "synthetic-not-a-key")
    core = Application(
        app_paths, postgres_config=application_target[0],
        config=AppConfig(content_dir=str(app_paths.content_dir),
                         interactive_model="deepseek-v4-flash",
                         llm_base_url="https://api.deepseek.com/v1"),
        embedding_provider=FixedProvider(), adapter=object(),
    )
    try:
        # This test isolates pricing/availability admission. The separate
        # production profile check exercises real local dense readiness.
        searches = []
        monkeypatch.setattr(core.dense_retrieval, "search", lambda *a, **kw: searches.append((a, kw)))
        assert core.provider_research_availability()["available"]
        assert len(searches) == 1
        policy = core.research_provider_receipts.price_policy
        assert policy.model == "deepseek-v4-flash"
        assert policy.absolute_max_cost_usd == Decimal("0.50")
        assert policy.actual_cost(input_tokens=1_000_000, cached_input_tokens=0,
                                  output_tokens=1_000_000, transport_attempts=1) == Decimal("1.5")
        assert policy.manifest()["pricing_basis"] == "published_peak_upper_bound_20261025"
        assert policy.expected_identity("grounded_answer")["thinking_enabled"] is False
        legacy = ProviderPricePolicy()
        assert ProviderPricePolicy.deployed(base_url=legacy.base_url, model=legacy.model) == legacy
        with pytest.raises(ResearchValidationError):
            ProviderPricePolicy.deployed(base_url=legacy.base_url, model="unregistered")
    finally:
        core.close()


def test_auto_sync_switch_and_explicit_manual_sync(monkeypatch, capsys):
    from types import SimpleNamespace
    import sys
    import shiliu.cli as cli
    import shiliu.w16_service as service

    class Core:
        config = SimpleNamespace(auto_sync_enabled=False)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    calls = []
    monkeypatch.setattr(service, "wait_for_database", lambda: None)
    monkeypatch.setattr(service, "production_application", Core)
    monkeypatch.setattr(cli, "_execute", lambda args, factory: calls.append(args.manual) or 0)
    monkeypatch.setattr(sys, "argv", ["shiliu", "sync", "--scheduled"])
    assert service.main() == 0 and calls == []
    assert "auto_sync_disabled" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["shiliu", "sync", "--manual"])
    assert service.main() == 0 and calls == [True]
    Core.config.auto_sync_enabled = True
    monkeypatch.setattr(sys, "argv", ["shiliu", "sync", "--scheduled"])
    assert service.main() == 0 and calls == [True, False]
