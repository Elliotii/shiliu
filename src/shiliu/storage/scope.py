from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceContext:
    """An ownership value, not authentication or proof of authorization.

    Entrypoints must inject this from trusted process configuration, never from
    request user_id. W01 supports only SPEC's personal installation identity.
    """

    workspace_id: str
    user_id: str


def personal_context() -> ResourceContext:
    """Trusted single-user configuration source until authentication is added."""
    return ResourceContext("personal:local_operator", "local_operator")
