"""Propagate brief-saved provider, models, and reasoning onto minted work (feat_006_002)."""

from __future__ import annotations

from cascade.agent.types import RoleId
from cascade.board.types import WorkMeta
_EPIC_TO_FEATURE: tuple[tuple[RoleId, RoleId], ...] = (
    ("epic_manager", "feature_lead"),
    ("epic_architect", "feature_architect"),
)


def _non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def feature_backend_from_epic(
    epic: WorkMeta,
) -> tuple[str | None, dict[str, str] | None, str | None, dict[str, str] | None]:
    """Copy parent epic defaults onto a new feature (explicit stamp, not resolve-time inherit)."""

    provider = epic.provider
    models: dict[str, str] | None = None
    model: str | None = None

    if epic.models:
        mapped: dict[str, str] = {}
        for epic_role, feature_role in _EPIC_TO_FEATURE:
            if epic_role in epic.models:
                mapped[feature_role] = epic.models[epic_role]
        for key, value in epic.models.items():
            if key in ("feature_lead", "feature_architect"):
                mapped[key] = value
        if mapped:
            models = mapped
    elif epic.model:
        model = epic.model

    reasoning = reasoning_for_feature_from_epic(epic)
    return provider, models, model, reasoning


def reasoning_for_feature_from_epic(epic: WorkMeta) -> dict[str, str] | None:
    if not epic.reasoning:
        return None
    mapped: dict[str, str] = {}
    for epic_role, feature_role in _EPIC_TO_FEATURE:
        level = _non_blank(epic.reasoning.get(epic_role))
        if level is not None:
            mapped[feature_role] = level
    for role in ("feature_lead", "feature_architect"):
        level = _non_blank(epic.reasoning.get(role))
        if level is not None:
            mapped[role] = level
    return mapped or None


def task_backend_from_feature(
    feature: WorkMeta,
    *,
    epic: WorkMeta | None,
) -> tuple[str | None, dict[str, str] | None, dict[str, str] | None]:
    """Stamp task-tier provider, SWE model, and optional reasoning from feature/epic defaults."""

    provider = _non_blank(feature.provider)
    if provider is None and epic is not None:
        provider = _non_blank(epic.provider)
    models: dict[str, str] | None = None
    swe_model = _swe_model_from_stack(feature, epic=epic)
    if swe_model is not None:
        models = {"swe": swe_model}

    reasoning = reasoning_for_task_from_feature(feature, epic=epic)
    return provider, models, reasoning


def reasoning_for_task_from_feature(
    feature: WorkMeta,
    *,
    epic: WorkMeta | None,
) -> dict[str, str] | None:
    for source in (feature, epic):
        if source is None or not source.reasoning:
            continue
        level = _non_blank(source.reasoning.get("swe"))
        if level is not None:
            return {"swe": level}
    return None


def _swe_model_from_stack(feature: WorkMeta, *, epic: WorkMeta | None) -> str | None:
    for source in (feature, epic):
        if source is None or not source.models:
            continue
        model_id = _non_blank(source.models.get("swe"))
        if model_id is not None:
            return model_id
    return None
