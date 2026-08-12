from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib  # type: ignore[no-redef]


APP_NAME = "Shiliu"
KEYCHAIN_SERVICE = "app.shiliu.llm"
KEYCHAIN_ACCOUNT = "default"
ASR_KEYCHAIN_SERVICE = "app.shiliu.asr"
ASR_KEYCHAIN_ACCOUNT = "paraformer"


@dataclass(frozen=True)
class AppPaths:
    state_dir: Path
    content_dir: Path
    database: Path
    config: Path
    logs_dir: Path
    videos_dir: Path
    sync_lock: Path

    @classmethod
    def defaults(cls) -> "AppPaths":
        state_dir = Path(
            os.environ.get(
                "SHILIU_STATE_DIR",
                Path.home() / "Library" / "Application Support" / APP_NAME,
            )
        ).expanduser()
        content_dir = Path(
            os.environ.get("SHILIU_CONTENT_DIR", Path.home() / "Documents" / APP_NAME)
        ).expanduser()
        return cls(
            state_dir=state_dir,
            content_dir=content_dir,
            database=state_dir / "shiliu.db",
            config=state_dir / "config.toml",
            logs_dir=state_dir / "logs",
            videos_dir=content_dir / "videos",
            sync_lock=state_dir / "sync.lock",
        )

    def with_content_dir(self, content_dir: Path) -> "AppPaths":
        content_dir = content_dir.expanduser().resolve()
        return replace(self, content_dir=content_dir, videos_dir=content_dir / "videos")

    def ensure(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppConfig:
    content_dir: str
    favorite_id: int | None = None
    favorite_title: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    ingestion_model: str = ""
    interactive_model: str = ""
    taxonomy_model: str = ""
    fast_transcript_model: str = ""
    formal_transcript_model: str = ""
    formal_summary_model: str = ""
    formal_reasoning_effort: str = "high"
    api_key_ref: str = f"{KEYCHAIN_SERVICE}:{KEYCHAIN_ACCOUNT}"
    asr_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    asr_model: str = "paraformer-v2"
    asr_api_key_ref: str = f"{ASR_KEYCHAIN_SERVICE}:{ASR_KEYCHAIN_ACCOUNT}"
    process_all_parts: bool = False
    baseline_confirmed: bool = False
    auto_sync_enabled: bool = False
    bili_cli_root: str = ""

    def model_for(self, role: str) -> str:
        if role in {"fast_transcript", "formal_transcript"}:
            legacy = self.fast_transcript_model or self.formal_transcript_model
            return self.ingestion_model or legacy or self.llm_model
        if role == "formal_summary":
            return self.ingestion_model or self.formal_summary_model or self.llm_model
        if role.startswith("taxonomy_"):
            return self.taxonomy_model or self.llm_model
        if role in {
            "query_analysis",
            "agent_action",
            "grounded_answer",
            "grounded_answer_recovery",
        }:
            return self.interactive_model or self.llm_model
        return self.llm_model

    @classmethod
    def default(cls, paths: AppPaths | None = None) -> "AppConfig":
        resolved = paths or AppPaths.defaults()
        cli_root = Path(__file__).resolve().parents[2] / "references" / "upstreams" / "bilibili-cli"
        return cls(content_dir=str(resolved.content_dir), bili_cli_root=str(cli_root))


def load_config(paths: AppPaths | None = None) -> AppConfig:
    resolved = paths or AppPaths.defaults()
    if not resolved.config.exists():
        return AppConfig.default(resolved)
    data = tomllib.loads(resolved.config.read_text(encoding="utf-8"))
    app = data.get("app", {})
    llm = data.get("llm", {})
    asr = data.get("asr", {})
    bili = data.get("bilibili", {})
    legacy_model = str(llm.get("model", ""))
    # V2.1 deliberately routes every thinking-enabled video stage through
    # high. Legacy max/xhigh values remain readable but no longer control the
    # runtime, which prevents an old local config from restoring max effort.
    effort = "high"
    return AppConfig(
        content_dir=str(app.get("content_dir", resolved.content_dir)),
        favorite_id=_optional_int(bili.get("favorite_id")),
        favorite_title=str(bili.get("favorite_title", "")),
        llm_base_url=str(llm.get("base_url", "https://api.openai.com/v1")),
        llm_model=legacy_model,
        ingestion_model=str(llm.get("ingestion_model", "")),
        interactive_model=str(llm.get("interactive_model", "")),
        taxonomy_model=str(llm.get("taxonomy_model", "")),
        fast_transcript_model=str(
            llm.get(
                "fast_transcript_model",
                "deepseek-v4-flash" if legacy_model == "deepseek-v4-pro" else legacy_model,
            )
        ),
        formal_transcript_model=str(llm.get("formal_transcript_model", legacy_model)),
        formal_summary_model=str(llm.get("formal_summary_model", legacy_model)),
        formal_reasoning_effort=effort,
        api_key_ref=str(llm.get("api_key_ref", f"{KEYCHAIN_SERVICE}:{KEYCHAIN_ACCOUNT}")),
        asr_base_url=str(asr.get("base_url", "https://dashscope.aliyuncs.com/api/v1")),
        asr_model=str(asr.get("model", "paraformer-v2")),
        asr_api_key_ref=str(
            asr.get("api_key_ref", f"{ASR_KEYCHAIN_SERVICE}:{ASR_KEYCHAIN_ACCOUNT}")
        ),
        process_all_parts=bool(app.get("process_all_parts", False)),
        baseline_confirmed=bool(app.get("baseline_confirmed", False)),
        auto_sync_enabled=bool(app.get("auto_sync_enabled", False)),
        bili_cli_root=str(bili.get("cli_root", AppConfig.default(resolved).bili_cli_root)),
    )


def save_config(config: AppConfig, paths: AppPaths | None = None) -> AppPaths:
    resolved = (paths or AppPaths.defaults()).with_content_dir(Path(config.content_dir))
    resolved.ensure()
    lines = [
        "[app]",
        f"content_dir = {_toml_string(config.content_dir)}",
        f"process_all_parts = {_toml_bool(config.process_all_parts)}",
        f"baseline_confirmed = {_toml_bool(config.baseline_confirmed)}",
        f"auto_sync_enabled = {_toml_bool(config.auto_sync_enabled)}",
        "",
        "[bilibili]",
        f"favorite_id = {config.favorite_id if config.favorite_id is not None else 0}",
        f"favorite_title = {_toml_string(config.favorite_title)}",
        f"cli_root = {_toml_string(config.bili_cli_root)}",
        "",
        "[llm]",
        f"base_url = {_toml_string(config.llm_base_url.rstrip('/'))}",
        f"model = {_toml_string(config.model_for('grounded_answer'))}",
        f"ingestion_model = {_toml_string(config.ingestion_model)}",
        f"interactive_model = {_toml_string(config.interactive_model)}",
        f"taxonomy_model = {_toml_string(config.taxonomy_model)}",
        f"fast_transcript_model = {_toml_string(config.model_for('fast_transcript'))}",
        f"formal_transcript_model = {_toml_string(config.model_for('formal_transcript'))}",
        f"formal_summary_model = {_toml_string(config.model_for('formal_summary'))}",
        f"formal_reasoning_effort = {_toml_string('high')}",
        f"api_key_ref = {_toml_string(config.api_key_ref)}",
        "",
        "[asr]",
        f"base_url = {_toml_string(config.asr_base_url.rstrip('/'))}",
        f"model = {_toml_string(config.asr_model)}",
        f"api_key_ref = {_toml_string(config.asr_api_key_ref)}",
        "",
    ]
    temporary = resolved.config.with_suffix(".toml.tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(resolved.config)
    return resolved


def store_api_key(api_key: str, *, service: str = KEYCHAIN_SERVICE, account: str = KEYCHAIN_ACCOUNT) -> None:
    if not api_key.strip():
        raise ValueError("API Key 不能为空")
    import keyring

    keyring.set_password(service, account, api_key.strip())


def load_api_key(reference: str) -> str:
    import keyring

    service, separator, account = reference.partition(":")
    if not separator or not service or not account:
        raise RuntimeError("API Key 引用格式无效")
    value = keyring.get_password(service, account)
    if not value:
        raise RuntimeError("macOS Keychain 中没有找到模型 API Key")
    return value


def public_config(config: AppConfig) -> dict[str, Any]:
    return {
        "content_dir": config.content_dir,
        "favorite_id": config.favorite_id,
        "favorite_title": config.favorite_title,
        "llm_base_url": config.llm_base_url,
        "llm_model": config.llm_model,
        "ingestion_model": config.model_for("formal_summary"),
        "interactive_model": config.model_for("grounded_answer"),
        "taxonomy_model": config.model_for("taxonomy_global"),
        "fast_transcript_model": config.model_for("fast_transcript"),
        "formal_transcript_model": config.model_for("formal_transcript"),
        "formal_summary_model": config.model_for("formal_summary"),
        "formal_reasoning_effort": "high",
        "has_api_key_reference": bool(config.api_key_ref),
        "asr_base_url": config.asr_base_url,
        "asr_model": config.asr_model,
        "has_asr_api_key_reference": bool(config.asr_api_key_ref),
        "process_all_parts": config.process_all_parts,
        "baseline_confirmed": config.baseline_confirmed,
        "auto_sync_enabled": config.auto_sync_enabled,
    }


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _optional_int(value: object) -> int | None:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None
