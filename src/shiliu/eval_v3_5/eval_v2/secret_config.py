from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class MissingSecretError(RuntimeError):
    pass


@dataclass(frozen=True, repr=False)
class LoadedSecret:
    value: str
    source: str

    def __repr__(self) -> str:
        return f"LoadedSecret(value=[REDACTED], source={self.source!r})"


@dataclass(frozen=True, repr=False)
class OpenAIReviewerLocalConfig:
    api_key: str
    key_source: str
    base_url: str
    model: str
    reasoning_effort: str

    def __repr__(self) -> str:
        return (
            "OpenAIReviewerLocalConfig(api_key=[REDACTED], "
            f"key_source={self.key_source!r}, base_url=[REDACTED], "
            f"model={self.model!r}, reasoning_effort={self.reasoning_effort!r})"
        )


def default_dotenv_path() -> Path:
    return Path(__file__).resolve().parents[4] / ".env.local"


def load_required_secret(
    env_name: str,
    *,
    dotenv_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> LoadedSecret:
    values = os.environ if environ is None else environ
    direct = values.get(env_name, "").strip()
    if direct:
        return LoadedSecret(direct, "env")

    path = (dotenv_path or default_dotenv_path()).resolve()
    dotenv = _read_dotenv(path)
    local = dotenv.get(env_name, "").strip()
    if local:
        return LoadedSecret(local, "dotenv")
    raise MissingSecretError(f"missing required secret: {env_name}")


def load_openai_reviewer_local_config(
    *,
    dotenv_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> OpenAIReviewerLocalConfig:
    path = (dotenv_path or default_dotenv_path()).resolve()
    values = os.environ if environ is None else environ
    dotenv = _read_dotenv(path)
    secret = load_required_secret(
        "OPENAI_API_KEY", dotenv_path=path, environ=values
    )
    model = (values.get("OPENAI_MODEL") or dotenv.get("model") or "").strip()
    reasoning = (
        values.get("OPENAI_REASONING_EFFORT")
        or dotenv.get("model_reasoning_effort")
        or ""
    ).strip()
    base_url = (values.get("OPENAI_BASE_URL") or dotenv.get("base_url") or "").strip()
    if model != "gpt-5.6-terra":
        raise RuntimeError("OpenAI reviewer model does not match frozen Registry")
    if reasoning != "high":
        raise RuntimeError("OpenAI reviewer reasoning effort does not match frozen Registry")
    if not base_url:
        raise RuntimeError("OpenAI reviewer base_url is not configured")
    return OpenAIReviewerLocalConfig(
        api_key=secret.value,
        key_source=secret.source,
        base_url=base_url,
        model=model,
        reasoning_effort=reasoning,
    )


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name.startswith("export "):
            name = name[7:].strip()
        if not name or not all(char.isalnum() or char == "_" for char in name):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        result[name] = value
    return result
