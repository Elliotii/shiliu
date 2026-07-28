from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shiliu.config import AppPaths, load_config

from .contracts import AnnotationPacketV2
from .reviewer_draft import ReviewerDraft


PRIMARY_WORKSPACE_FILES = frozenset(
    {
        "annotation_protocol_excerpt.md",
        "primary_reviewer.draft.v1.md",
        "reviewer_draft.v1.schema.json",
        "current_case.packet.json",
        "output",
        "workspace_manifest.json",
    }
)


@dataclass(frozen=True)
class ProjectSensitivePaths:
    repository_root: Path
    project_parent: Path
    raw_source_root: Path
    application_state_root: Path
    attachment_root: Path
    codex_home: Path
    credential_paths: tuple[Path, ...]

    @classmethod
    def defaults(cls, repository_root: Path) -> "ProjectSensitivePaths":
        repository_root = repository_root.resolve()
        app_paths = AppPaths.defaults()
        config = load_config(app_paths)
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).resolve()
        return cls(
            repository_root=repository_root,
            project_parent=repository_root.parent.resolve(),
            raw_source_root=Path(config.content_dir).expanduser().resolve(),
            application_state_root=app_paths.state_dir.resolve(),
            attachment_root=(codex_home / "attachments").resolve(),
            codex_home=codex_home,
            credential_paths=(
                codex_home / "auth.json",
                codex_home / "auth.json.bak",
                codex_home / ".cockpit_codex_auth.json",
                Path.home() / ".env",
                Path.home() / ".ssh",
                Path.home() / ".aws",
                Path.home() / ".config" / "gcloud",
            ),
        )

    def denied_paths(self) -> tuple[Path, ...]:
        return (
            self.project_parent,
            self.raw_source_root,
            self.application_state_root,
            self.attachment_root,
            *self.credential_paths,
        )


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def strict_output_schema(value: object) -> object:
    if isinstance(value, dict):
        result = {key: strict_output_schema(item) for key, item in value.items()}
        properties = result.get("properties")
        if result.get("type") == "object" and isinstance(properties, dict):
            result["required"] = list(properties)
            result["additionalProperties"] = False
        return result
    if isinstance(value, list):
        return [strict_output_schema(item) for item in value]
    return value


def export_primary_workspace(
    *, packet: AnnotationPacketV2, workspace: Path, protocol: str, prompt: str
) -> dict[str, object]:
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    (workspace / "output").mkdir()
    (workspace / "annotation_protocol_excerpt.md").write_text(protocol, encoding="utf-8")
    (workspace / "primary_reviewer.draft.v1.md").write_text(prompt, encoding="utf-8")
    (workspace / "reviewer_draft.v1.schema.json").write_text(
        canonical_json(strict_output_schema(ReviewerDraft.model_json_schema())), encoding="utf-8"
    )
    (workspace / "current_case.packet.json").write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    inventory = sorted([path.name for path in workspace.iterdir()] + ["workspace_manifest.json"])
    manifest = {
        "workspace_version": "v3.5-primary-reviewer-draft-workspace-v1",
        "absolute_path": str(workspace),
        "case_id": packet.case_id,
        "case_input_sha256": packet.case_input_sha256,
        "inventory": inventory,
        "allowlist_passed": set(inventory) == PRIMARY_WORKSPACE_FILES,
        "repository_external": not workspace.is_relative_to(Path.cwd().resolve()),
        "repository_copy_present": (workspace / ".git").exists(),
        "secret_files_present": any(path.name == ".env" for path in workspace.rglob("*")),
        "project_sensitive_isolation": "required",
        "universal_filesystem_isolation": "best_effort_not_proven",
    }
    (workspace / "workspace_manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    return manifest


def write_sandbox_profile(
    *, workspace: Path, profile_path: Path, sensitive: ProjectSensitivePaths
) -> None:
    workspace = workspace.resolve()
    escaped = lambda path: str(path).replace('"', '\\"')
    denies = [
        f'(deny file-read* (subpath "{escaped(path.resolve())}"))'
        for path in sensitive.denied_paths()
    ]
    profile_path.write_text(
        "\n".join(
            [
                "(version 1)",
                "(deny default)",
                "(allow process*)",
                "(allow network*)",
                "(allow sysctl-read)",
                "(allow mach-lookup)",
                "(allow file-read* (subpath \"/System\") (subpath \"/usr\") (subpath \"/bin\") (subpath \"/sbin\") (subpath \"/Library\") (subpath \"/Applications/ChatGPT.app\") (subpath \"/private/etc\") (subpath \"/dev\"))",
                f'(allow file-read* (subpath "{escaped(sensitive.codex_home)}"))',
                f'(allow file-read* file-write* (subpath "{escaped(workspace)}"))',
                "(allow file-read* file-write* (subpath \"/private/var/folders\"))",
                *denies,
            ]
        ),
        encoding="utf-8",
    )


def audit_denied_paths(profile_path: Path, sensitive: ProjectSensitivePaths) -> dict[str, object]:
    probes: list[dict[str, object]] = []
    for path in sensitive.denied_paths():
        if not path.exists():
            probes.append({"path": str(path), "exists": False, "read_denied": True})
            continue
        result = subprocess.run(
            ["/usr/bin/sandbox-exec", "-f", str(profile_path), "/usr/bin/test", "-r", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        probes.append({"path": str(path), "exists": True, "read_denied": result.returncode != 0})
    passed = all(bool(probe["read_denied"]) for probe in probes)
    return {
        "project_sensitive_isolation": "required",
        "project_sensitive_isolation_passed": passed,
        "universal_filesystem_isolation": "best_effort_not_proven",
        "probes": probes,
    }
