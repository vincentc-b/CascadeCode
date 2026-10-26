"""Full-stack brief role defaults and inventory-backed validation (feat_006_002)."""

from __future__ import annotations

from cascade.agent.discovery.inventory import ProviderInventoryItem, ProviderInventoryResult
from cascade.agent.discovery.types import ReasoningCapability
from cascade.agent.providers import ProviderId
from cascade.agent.types import RoleId
from cascade.board.types import WorkMeta
from cascade.watchdog.config import ModelsTable

BRIEF_STACK_ROLES: tuple[RoleId, ...] = (
    "epic_manager",
    "epic_architect",
    "feature_lead",
    "feature_architect",
    "swe",
)

_LEGACY_MODEL_FIELDS: dict[str, RoleId] = {
    "manager_model": "epic_manager",
    "architect_model": "epic_architect",
    "feature_lead_model": "feature_lead",
    "feature_architect_model": "feature_architect",
    "swe_model": "swe",
}


def default_model_for_role(table: ModelsTable, role: RoleId) -> str:
    if role in table.roles:
        return table.roles[role]
    if role in ("epic_manager", "epic_architect"):
        return table.epic or ""
    if role in ("feature_lead", "feature_architect"):
        return table.feature or ""
    if role == "swe":
        return table.task or ""
    return ""


def role_models_for_provider(table: ModelsTable) -> dict[str, str]:
    return {role: default_model_for_role(table, role) for role in BRIEF_STACK_ROLES}


def parse_brief_models(
    raw: dict[str, object],
    *,
    table: ModelsTable,
) -> dict[str, str]:
    """Parse per-role models from request payload with legacy field aliases."""

    models: dict[str, str] = {}
    models_raw = raw.get("models")
    if models_raw is not None:
        if not isinstance(models_raw, dict):
            raise ValueError("models must be a mapping")
        for role in BRIEF_STACK_ROLES:
            if role in models_raw:
                models[role] = _require_non_blank(str(models_raw[role]), f"{role} model")

    for legacy_field, role in _LEGACY_MODEL_FIELDS.items():
        if legacy_field in raw and role not in models:
            models[role] = _require_non_blank(str(raw[legacy_field]), f"{role} model")

    for role in BRIEF_STACK_ROLES:
        if role not in models:
            fallback = default_model_for_role(table, role)
            if not fallback.strip():
                raise ValueError(f"{role} model is required")
            models[role] = fallback.strip()
    return models


def parse_brief_reasoning(raw: dict[str, object]) -> dict[str, str]:
    """Parse optional per-role reasoning overrides (empty means provider default)."""

    reasoning_raw = raw.get("reasoning")
    if reasoning_raw is None:
        return {}
    if not isinstance(reasoning_raw, dict):
        raise ValueError("reasoning must be a mapping")
    result: dict[str, str] = {}
    for key, value in reasoning_raw.items():
        if not isinstance(key, str) or key not in BRIEF_STACK_ROLES:
            raise ValueError(f"unsupported reasoning role: {key!r}")
        if value is None:
            continue
        level = str(value).strip()
        if level:
            result[key] = level
    return result


def normalize_reasoning_overrides(
    models: dict[str, str],
    reasoning: dict[str, str],
    *,
    provider_item: ProviderInventoryItem,
) -> dict[str, str]:
    """Validate explicit effort choices; an omitted choice keeps provider behavior."""

    model_by_id = {model.id: model for model in provider_item.models}
    persisted: dict[str, str] = {}
    for role in BRIEF_STACK_ROLES:
        override = reasoning.get(role)
        if not override:
            continue
        model = model_by_id.get(models[role])
        if model is None:
            raise ValueError(f"{role} model is not offered by {provider_item.provider_id}")
        capability = model.reasoning
        _validate_reasoning_override(role, override, capability, model.id)
        persisted[role] = override
    return persisted


def validate_models_against_inventory(
    provider: ProviderId,
    models: dict[str, str],
    inventory: ProviderInventoryResult,
) -> ProviderInventoryItem:
    if not inventory.providers:
        raise ValueError("no usable provider is available in the model inventory")

    provider_item = next(
        (item for item in inventory.providers if item.provider_id == provider),
        None,
    )
    if provider_item is None:
        raise ValueError(f"provider {provider!r} is not available")

    model_ids = {model.id for model in provider_item.models}
    for role in BRIEF_STACK_ROLES:
        model_id = models.get(role, "").strip()
        if not model_id:
            raise ValueError(f"{role} model is required")
        if model_id not in model_ids:
            raise ValueError(f"{role} model is not offered by {provider}")
    return provider_item


def brief_selection_from_meta(meta: WorkMeta) -> dict[str, object]:
    """Serialize saved brief defaults for reload/continue consumers."""

    models = dict(meta.models or {})
    payload: dict[str, object] = {
        "provider": meta.provider,
        "models": {role: models.get(role, "") for role in BRIEF_STACK_ROLES},
        "reasoning": dict(meta.reasoning or {}),
        "flex_mode": meta.flex_mode,
        "manager_model": models.get("epic_manager", ""),
        "architect_model": models.get("epic_architect", ""),
    }
    return payload


def _validate_reasoning_override(
    role: RoleId,
    override: str,
    capability: ReasoningCapability | None,
    model_id: str,
) -> None:
    if capability is None or not capability.supports_overrides:
        raise ValueError(
            f"{role} does not support reasoning overrides for model {model_id}"
        )
    allowed = {capability.default_level, *capability.override_levels}
    if override not in allowed:
        raise ValueError(f"{role} reasoning override is not supported for model {model_id}")


def legal_model_keys_for_tier(tier: str) -> frozenset[str]:
    if tier == "epic":
        return frozenset(BRIEF_STACK_ROLES)
    if tier == "feature":
        return frozenset({"feature_lead", "feature_architect"})
    if tier == "task":
        return frozenset({"swe"})
    raise ValueError(f"unknown tier: {tier!r}")


def legal_reasoning_keys_for_tier(tier: str) -> frozenset[str]:
    return legal_model_keys_for_tier(tier)


def _require_non_blank(value: str, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} is required")
    return stripped
