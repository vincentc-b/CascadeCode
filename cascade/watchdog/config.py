"""Read cascade.toml settings. Planning agents must not use this to self-start."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger(__name__)

_DEFAULT_WORKER_DRAIN_SECONDS = 120.0
_DEFAULT_CONVERGENCE_STALL_THRESHOLD_SECONDS = 600.0
_DEFAULT_TURN_PROGRESS_NO_PROGRESS_DEADLINE_SECONDS = 600.0
_DEFAULT_SUPERVISOR_HEALTH_SWEEP_SECONDS = 60.0

from cascade.agent.errors import ProviderConfigError
from cascade.agent.providers import (
    ALL_PROVIDER_IDS,
    ProviderId,
    fake_provider_enabled,
    parse_provider_id,
)

_TIER_KEYS = ("epic", "feature", "task", "boss")
_DEFAULT_COMPLETED_EPIC_DISPLAY_LIMIT = 10


class ConfigError(Exception):
    """cascade.toml is present but invalid or has a bad value."""


@dataclass(frozen=True)
class ModelsTable:
    """Project model defaults from cascade.toml [models]."""

    epic: str | None = None
    feature: str | None = None
    task: str | None = None
    boss: str | None = None
    roles: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProvidersConfig:
    """Per-provider model tables and project default provider."""

    default: ProviderId
    tables: dict[ProviderId, ModelsTable]


@dataclass(frozen=True)
class AutomationConfig:
    """Continuous workflow settings; new workspaces opt in through cascade.toml."""

    enabled: bool = True
    poll_seconds: float = 15.0
    remote: str = "origin"


def worker_drain_seconds(root: Path) -> float:
    """Turn drain window before SIGTERM cancellation. Invalid values default to 120s."""

    data = _load_cascade_toml(root)
    worker = data.get("worker")
    if not isinstance(worker, dict):
        return _DEFAULT_WORKER_DRAIN_SECONDS
    if "drain_seconds" not in worker:
        return _DEFAULT_WORKER_DRAIN_SECONDS
    value = worker["drain_seconds"]
    if isinstance(value, bool):
        _log.warning(
            "cascade.toml [worker].drain_seconds must be a positive number; using %.1f",
            _DEFAULT_WORKER_DRAIN_SECONDS,
        )
        return _DEFAULT_WORKER_DRAIN_SECONDS
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 0:
            return seconds
    _log.warning(
        "cascade.toml [worker].drain_seconds must be a positive number; using %.1f",
        _DEFAULT_WORKER_DRAIN_SECONDS,
    )
    return _DEFAULT_WORKER_DRAIN_SECONDS


def completed_epic_display_limit(root: Path) -> int:
    """War Room cap on completed epics shown. Missing or invalid values default to 10."""

    data = _load_cascade_toml(root)
    war_room = data.get("war_room")
    if not isinstance(war_room, dict):
        return _DEFAULT_COMPLETED_EPIC_DISPLAY_LIMIT
    if "completed_epic_display_limit" not in war_room:
        return _DEFAULT_COMPLETED_EPIC_DISPLAY_LIMIT
    value = war_room["completed_epic_display_limit"]
    if isinstance(value, bool):
        return _DEFAULT_COMPLETED_EPIC_DISPLAY_LIMIT
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value.is_integer() and int(value) > 0:
        return int(value)
    return _DEFAULT_COMPLETED_EPIC_DISPLAY_LIMIT


def turn_progress_no_progress_deadline_seconds(root: Path) -> float:
    """Monotonic seconds without useful turn progress before the watchdog may act."""

    data = _load_cascade_toml(root)
    turn_progress = data.get("turn_progress")
    if not isinstance(turn_progress, dict):
        return _DEFAULT_TURN_PROGRESS_NO_PROGRESS_DEADLINE_SECONDS
    if "no_progress_deadline_seconds" not in turn_progress:
        return _DEFAULT_TURN_PROGRESS_NO_PROGRESS_DEADLINE_SECONDS
    value = turn_progress["no_progress_deadline_seconds"]
    if isinstance(value, bool):
        return _DEFAULT_TURN_PROGRESS_NO_PROGRESS_DEADLINE_SECONDS
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 0:
            return seconds
    return _DEFAULT_TURN_PROGRESS_NO_PROGRESS_DEADLINE_SECONDS


def convergence_stall_threshold_seconds(root: Path) -> float:
    """Seconds without durable progress before a dispatchable item is stalled."""

    data = _load_cascade_toml(root)
    convergence = data.get("convergence")
    if not isinstance(convergence, dict):
        return _DEFAULT_CONVERGENCE_STALL_THRESHOLD_SECONDS
    if "stall_threshold_seconds" not in convergence:
        return _DEFAULT_CONVERGENCE_STALL_THRESHOLD_SECONDS
    value = convergence["stall_threshold_seconds"]
    if isinstance(value, bool):
        return _DEFAULT_CONVERGENCE_STALL_THRESHOLD_SECONDS
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 0:
            return seconds
    return _DEFAULT_CONVERGENCE_STALL_THRESHOLD_SECONDS


def supervisor_health_sweep_seconds(root: Path) -> float:
    """Seconds between direct-report health sweeps; invalid values use 60s."""

    data = _load_cascade_toml(root)
    health = data.get("supervisor_health")
    if not isinstance(health, dict):
        return _DEFAULT_SUPERVISOR_HEALTH_SWEEP_SECONDS
    value = health.get("sweep_seconds", _DEFAULT_SUPERVISOR_HEALTH_SWEEP_SECONDS)
    if isinstance(value, bool):
        return _DEFAULT_SUPERVISOR_HEALTH_SWEEP_SECONDS
    if isinstance(value, (int, float)) and float(value) > 0:
        return float(value)
    return _DEFAULT_SUPERVISOR_HEALTH_SWEEP_SECONDS


def task_parallelism(root: Path) -> int:
    """Return the cap. Missing file or missing key defaults to 4.

    A non-integer value raises ConfigError. It does not fall open to unlimited work.
    """

    path = Path(root) / "cascade.toml"
    if not path.exists():
        return 4
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid cascade.toml: {exc}") from exc
    if "task_parallelism" not in data:
        return 4
    value = data["task_parallelism"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"task_parallelism must be an integer >= 1, got {value!r}")
    return value


def read_automation_config(root: Path) -> AutomationConfig:
    data = _load_cascade_toml(root)
    if "automation" not in data:
        # Existing workspaces keep their manual lifecycle until the operator
        # opts into the new flow. `cascade init` writes the enabled table.
        return AutomationConfig(enabled=False)
    raw = data.get("automation", {})
    if not isinstance(raw, dict):
        raise ConfigError("[automation] must be a table")
    enabled = raw.get("enabled", True)
    poll_seconds = raw.get("poll_seconds", 15.0)
    remote = raw.get("remote", "origin")
    if not isinstance(enabled, bool):
        raise ConfigError("automation.enabled must be a boolean")
    if isinstance(poll_seconds, bool) or not isinstance(poll_seconds, (int, float)) or poll_seconds < 1:
        raise ConfigError("automation.poll_seconds must be a number >= 1")
    if not isinstance(remote, str) or not remote.strip():
        raise ConfigError("automation.remote must be a non-blank string")
    return AutomationConfig(enabled=enabled, poll_seconds=float(poll_seconds), remote=remote.strip())


def _require_non_blank_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-blank string, got {value!r}")
    return value.strip()


def _optional_tier_string(value: object, label: str) -> str | None:
    if not isinstance(value, str):
        raise ConfigError(f"{label} must be a string, got {value!r}")
    stripped = value.strip()
    return stripped if stripped else None


def _empty_provider_tables() -> dict[ProviderId, ModelsTable]:
    return {provider_id: ModelsTable() for provider_id in ALL_PROVIDER_IDS}


def _models_table_from_mapping(
    models: object,
    label: str,
    *,
    allow_blank_tiers: bool = False,
) -> ModelsTable:
    if not isinstance(models, dict):
        raise ConfigError(f"[{label}] must be a table, got {models!r}")

    tiers: dict[str, str | None] = {key: None for key in _TIER_KEYS}
    for key in _TIER_KEYS:
        if key in models:
            raw = models[key]
            if allow_blank_tiers:
                tiers[key] = _optional_tier_string(raw, f"{label}.{key}")
            else:
                tiers[key] = _require_non_blank_string(raw, f"{label}.{key}")

    roles: dict[str, str] = {}
    if "roles" in models:
        roles_raw = models["roles"]
        if not isinstance(roles_raw, dict):
            raise ConfigError(f"{label}.roles must be a table, got {roles_raw!r}")
        for role_id, model_id in roles_raw.items():
            roles[str(role_id)] = _require_non_blank_string(
                model_id, f"{label}.roles.{role_id}"
            )

    return ModelsTable(
        epic=tiers["epic"],
        feature=tiers["feature"],
        task=tiers["task"],
        boss=tiers["boss"],
        roles=roles,
    )


def _load_cascade_toml(root: Path) -> dict[str, object]:
    path = Path(root) / "cascade.toml"
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid cascade.toml: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("cascade.toml root must be a table")
    return data


def read_models_table(root: Path) -> ModelsTable:
    """Return [models] defaults. Missing file or missing table → empty ModelsTable."""

    data = _load_cascade_toml(root)
    if "models" not in data:
        return ModelsTable()
    return _models_table_from_mapping(data["models"], "models")


def read_providers_config(root: Path) -> ProvidersConfig:
    """Return per-provider tables and default provider."""

    data = _load_cascade_toml(root)
    has_providers = "providers" in data
    has_models = "models" in data
    if has_providers and has_models:
        raise ConfigError(
            "cascade.toml must not contain both [providers] and [models]"
        )

    if not has_providers:
        tables = _empty_provider_tables()
        tables["cursor"] = read_models_table(root)
        return ProvidersConfig(default="cursor", tables=tables)

    providers_raw = data["providers"]
    if not isinstance(providers_raw, dict):
        raise ConfigError(f"[providers] must be a table, got {providers_raw!r}")

    if "default" not in providers_raw:
        raise ConfigError("[providers].default is required")
    try:
        default = parse_provider_id(providers_raw["default"])
    except ProviderConfigError as exc:
        raise ConfigError(str(exc)) from exc

    tables = _empty_provider_tables()
    provider_ids: list[ProviderId] = list(ALL_PROVIDER_IDS)
    if fake_provider_enabled():
        tables["fake"] = ModelsTable()
        provider_ids.append("fake")
    for provider_id in provider_ids:
        if provider_id in providers_raw:
            tables[provider_id] = _models_table_from_mapping(
                providers_raw[provider_id],
                f"providers.{provider_id}",
                allow_blank_tiers=True,
            )

    return ProvidersConfig(default=default, tables=tables)
