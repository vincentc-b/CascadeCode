"""Provider registry and installation probes (feat_015 / task_071)."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from typing import Literal

from cascade.agent.errors import ProviderConfigError

ProviderId = Literal["cursor", "claude", "codex", "fake"]
AuthSource = Literal["env", "user-store", "cli-session", "missing"]

ALL_PROVIDER_IDS: tuple[ProviderId, ...] = ("cursor", "claude", "codex", "fake")


@dataclass(frozen=True)
class ProviderStatus:
    id: ProviderId
    installed: bool
    authenticated: bool
    auth_source: AuthSource


def _cursor_installed() -> bool:
    return importlib.util.find_spec("cursor_sdk") is not None


def _cli_installed(name: str) -> bool:
    return shutil.which(name) is not None


def probe_provider(provider_id: ProviderId) -> ProviderStatus:
    if provider_id == "cursor":
        installed = _cursor_installed()
    elif provider_id == "claude":
        installed = _cli_installed("claude")
    elif provider_id == "codex":
        installed = _cli_installed("codex")
    elif provider_id == "fake":
        installed = True
    else:
        raise ProviderConfigError(f"unknown provider id: {provider_id!r}")

    from cascade.agent.credentials import credential_auth_source

    if provider_id == "fake":
        auth_source = "env"
        authenticated = True
    else:
        auth_source = credential_auth_source(provider_id)
        authenticated = auth_source != "missing"
    return ProviderStatus(
        id=provider_id,
        installed=installed,
        authenticated=authenticated,
        auth_source=auth_source,
    )


def probe_providers() -> list[ProviderStatus]:
    return [probe_provider(pid) for pid in ALL_PROVIDER_IDS]


def parse_provider_id(value: object) -> ProviderId:
    if not isinstance(value, str):
        raise ProviderConfigError(
            f"provider id must be a string, got {type(value).__name__}"
        )
    stripped = value.strip()
    if not stripped:
        raise ProviderConfigError("provider id must not be blank")
    if stripped not in ALL_PROVIDER_IDS:
        raise ProviderConfigError(f"unknown provider id: {stripped!r}")
    return stripped  # type: ignore[return-value]
