from __future__ import annotations

from pathlib import Path

from shiliu.eval_v3_5.eval_v2.contracts import AnnotationPacketV2
from shiliu.eval_v3_5.eval_v2.providers import build_deepseek_secondary_request
from shiliu.eval_v3_5.eval_v2.stage2r_b_runtime import (
    RawInvocation,
    run_independent_preflight,
)
from shiliu.eval_v3_5.eval_v2.workspace import (
    PRIMARY_WORKSPACE_FILES,
    ProjectSensitivePaths,
    audit_denied_paths,
    export_primary_workspace,
    write_sandbox_profile,
)
from test_v3_5_eval_v2_reviewer_draft import valid_draft


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "research/v3_5/eval_v2/stage2r_a/fixtures/annotation_packet.synthetic.v2.json"


def packet() -> AnnotationPacketV2:
    return AnnotationPacketV2.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def invocation(body: object, model: str) -> RawInvocation:
    return RawInvocation(body, model, 1, 1, 1, 0, "stop", model, True, 1)


def test_primary_workspace_allowlist_and_project_sensitive_denial(tmp_path: Path) -> None:
    workspace = tmp_path / "outside" / "review"
    manifest = export_primary_workspace(
        packet=packet(), workspace=workspace, protocol="protocol", prompt="prompt"
    )
    assert set(manifest["inventory"]) == PRIMARY_WORKSPACE_FILES
    assert manifest["allowlist_passed"] is True
    assert manifest["project_sensitive_isolation"] == "required"
    assert manifest["universal_filesystem_isolation"] == "best_effort_not_proven"

    codex_home = tmp_path / "codex-home"
    attachment = codex_home / "attachments"
    project = tmp_path / "project"
    raw = tmp_path / "raw"
    state = tmp_path / "state"
    for path in (attachment, project, raw, state):
        path.mkdir(parents=True)
    sensitive = ProjectSensitivePaths(
        repository_root=project / "repo",
        project_parent=project,
        raw_source_root=raw,
        application_state_root=state,
        attachment_root=attachment,
        codex_home=codex_home,
        credential_paths=(),
    )
    profile = tmp_path / "profile.sb"
    write_sandbox_profile(workspace=workspace, profile_path=profile, sensitive=sensitive)
    audit = audit_denied_paths(profile, sensitive)
    assert audit["project_sensitive_isolation_passed"] is True
    assert audit["universal_filesystem_isolation"] == "best_effort_not_proven"


def test_deepseek_v4_pro_max_annotation_request() -> None:
    request = build_deepseek_secondary_request(packet(), "draft prompt")
    assert request.body["model"] == "deepseek-v4-pro"
    assert request.body["reasoning_effort"] == "max"
    assert request.provider_usage == "annotation_secondary_review"


def test_one_repair_and_independent_secondary_completion() -> None:
    calls = {"primary": 0, "primary_repair": 0, "secondary": 0, "secondary_repair": 0}
    invalid = {**valid_draft(), "supported_aspect_indices": [99]}

    def primary():
        calls["primary"] += 1
        return invocation(invalid, "gpt-5.4")

    def primary_repair(_raw: RawInvocation, _errors: tuple[str, ...]):
        calls["primary_repair"] += 1
        return invocation(invalid, "gpt-5.4")

    def secondary():
        calls["secondary"] += 1
        return invocation(valid_draft(), "deepseek-v4-pro")

    def secondary_repair(_raw: RawInvocation, _errors: tuple[str, ...]):
        calls["secondary_repair"] += 1
        return invocation(valid_draft(), "deepseek-v4-pro")

    result = run_independent_preflight(
        packet=packet(), primary_invoke=primary, primary_repair=primary_repair,
        secondary_invoke=secondary, secondary_repair=secondary_repair,
    )
    assert result.primary.status == "invalid_after_repair"
    assert result.primary.raw_call_count == 2
    assert result.secondary.status == "valid"
    assert calls == {"primary": 1, "primary_repair": 1, "secondary": 1, "secondary_repair": 0}


def test_valid_after_exactly_one_repair() -> None:
    invalid = {**valid_draft(), "missing_aspect_indices": [0]}
    repair_calls = 0

    def repair(_raw: RawInvocation, _errors: tuple[str, ...]):
        nonlocal repair_calls
        repair_calls += 1
        return invocation(valid_draft(), "gpt-5.4")

    result = run_independent_preflight(
        packet=packet(),
        primary_invoke=lambda: invocation(invalid, "gpt-5.4"),
        primary_repair=repair,
        secondary_invoke=lambda: invocation(valid_draft(), "deepseek-v4-pro"),
        secondary_repair=lambda _raw, _errors: invocation(valid_draft(), "deepseek-v4-pro"),
    )
    assert result.primary.status == "valid_after_repair"
    assert result.primary.raw_call_count == 2
    assert repair_calls == 1
