"""Provider registry and installation probes (feat_015 / task_071)."""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from typing import Literal

from cascade.agent.errors import ProviderConfigError

ProviderId = Literal["cursor", "claude", "codex", "fake"]
AuthSource = Literal["env", "user-store", "cli-session", "missing"]

ALL_PROVIDER_IDS: tuple[ProviderId, ...] = ("cursor", "claude", "codex")

_PROVIDER_DISPLAY_NAMES: dict[ProviderId, str] = {
    "cursor": "Cursor",
    "claude": "Claude Code",
    "codex": "Codex",
    "fake": "Fake",
}


@dataclass(frozen=True)
class ProviderStatus:
    id: ProviderId
    installed: bool
    authenticated: bool
    auth_source: AuthSource


def provider_display_name(provider_id: ProviderId) -> str:
    """Human-readable label owned by the provider integration registry."""

    return _PROVIDER_DISPLAY_NAMES.get(provider_id, provider_id)


def fake_provider_enabled() -> bool:
    return os.environ.get("CASCADE_ENABLE_FAKE_PROVIDER") == "1"


def _cursor_installed() -> bool:
    return importlib.util.find_spec("cursor_sdk") is not None


def _cli_installed(name: str) -> bool:
    return shutil.which(name) is not None


def probe_provider(provider_id: ProviderId) -> ProviderStatus:
    if provider_id == "fake" and not fake_provider_enabled():
        raise ProviderConfigError(f"unknown provider id: {provider_id!r}")
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
    if stripped == "fake":
        if fake_provider_enabled():
            return "fake"
        raise ProviderConfigError(f"unknown provider id: {stripped!r}")
    if stripped not in ALL_PROVIDER_IDS:
        raise ProviderConfigError(f"unknown provider id: {stripped!r}")
    return stripped  # type: ignore[return-value]
