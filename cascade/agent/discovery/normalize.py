"""Map provider-specific model payloads to normalized discovery types."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from cascade.agent.discovery.types import DiscoveredModel, ReasoningCapability

_REASONING_PARAM_IDS = frozenset(
    {"reasoning", "effort", "reasoningeffort", "thinking", "reasoning_level"}
)


def normalize_model_id(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def normalize_display_name(model_id: str, raw: object) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return model_id


def reasoning_from_cursor_parameters(
    *,
    parameters: Sequence[Any],
    variants: Sequence[Any],
) -> ReasoningCapability | None:
    param = None
    for candidate in parameters:
        param_id = getattr(candidate, "id", None)
        if isinstance(param_id, str) and param_id.casefold() in _REASONING_PARAM_IDS:
            param = candidate
            break
    if param is None:
        return None

    values = getattr(param, "values", ()) or ()
    levels: list[str] = []
    for item in values:
        value = getattr(item, "value", None)
        if isinstance(value, str) and value.strip():
            levels.append(value.strip())
    if not levels:
        return None

    default = levels[0]
    param_id = str(getattr(param, "id", ""))
    for variant in variants:
        if not getattr(variant, "is_default", False):
            continue
        for pv in getattr(variant, "params", ()) or ():
            if getattr(pv, "id", None) == param_id:
                chosen = getattr(pv, "value", None)
                if isinstance(chosen, str) and chosen.strip():
                    default = chosen.strip()
                break

    override_levels = tuple(levels)
    if len(override_levels) <= 1:
        return ReasoningCapability(default_level=default, override_levels=())
    return ReasoningCapability(default_level=default, override_levels=override_levels)


def reasoning_from_codex_record(record: Mapping[str, Any]) -> ReasoningCapability | None:
    default_raw = record.get("default_reasoning_level")
    default = default_raw.strip() if isinstance(default_raw, str) and default_raw.strip() else None

    levels_raw = record.get("supported_reasoning_levels")
    efforts: list[str] = []
    if isinstance(levels_raw, list):
        for item in levels_raw:
            if isinstance(item, Mapping):
                effort = item.get("effort")
                if isinstance(effort, str) and effort.strip():
                    efforts.append(effort.strip())

    if not default and efforts:
        default = efforts[0]
    if default is None:
        return None

    supports_updates = record.get("supports_reasoning_effort_updates")
    if supports_updates is False or len(efforts) <= 1:
        return ReasoningCapability(default_level=default, override_levels=())
    return ReasoningCapability(default_level=default, override_levels=tuple(efforts))


def discovered_model(
    *,
    model_id: str,
    display_name: str,
    reasoning: ReasoningCapability | None,
) -> DiscoveredModel:
    return DiscoveredModel(
        id=model_id,
        display_name=display_name,
        reasoning=reasoning,
    )


def sort_models(models: Sequence[DiscoveredModel]) -> tuple[DiscoveredModel, ...]:
    return tuple(sorted(models, key=lambda m: (m.display_name.casefold(), m.id)))


def sanitize_provider_error(exc: BaseException) -> str:
    """Public-safe error text; never include exception args that may hold secrets."""

    return type(exc).__name__
