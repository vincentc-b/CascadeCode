"""Pure model id resolution from document frontmatter and cascade.toml provider tables."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.agent.providers import ProviderId
from cascade.agent.types import RoleId
from cascade.board.types import WorkMeta
from cascade.watchdog.config import ModelsTable, read_providers_config

ModelSource = Literal[
    "document-role",
    "document",
    "project-role",
    "project-tier",
    "boss-falls-back-to-epic",
]

ProviderSource = Literal["document", "project-default"]


class ModelConfigError(Exception):
    """No configured model id for this role (fail closed)."""


@dataclass(frozen=True)
class ResolvedModel:
    role: RoleId
    model_id: str
    source: ModelSource


@dataclass(frozen=True)
class ResolvedBackend:
    provider: ProviderId
    provider_source: ProviderSource
    model: ResolvedModel


def _non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _tier_for_role(role: RoleId) -> Literal["epic", "feature", "task", "boss"]:
    if role in ("epic_manager", "epic_architect"):
        return "epic"
    if role in ("feature_lead", "feature_architect"):
        return "feature"
    if role == "swe":
        return "task"
    if role == "boss":
        return "boss"
    raise AssertionError(f"unknown role: {role!r}")


def _tier_model(table: ModelsTable, tier: Literal["epic", "feature", "task", "boss"]) -> str | None:
    return getattr(table, tier)


def resolve_model(
    role: RoleId,
    doc: WorkMeta | None,
    *,
    root: Path,
    provider: ProviderId,
) -> ResolvedModel:
    """Resolve model id for a role; document overrides beat project defaults."""

    if role != "boss":
        if doc is not None and doc.models is not None and role in doc.models:
            model_id = _non_blank(doc.models[role])
            if model_id is not None:
                return ResolvedModel(role=role, model_id=model_id, source="document-role")

        if doc is not None:
            model_id = _non_blank(doc.model)
            if model_id is not None:
                return ResolvedModel(role=role, model_id=model_id, source="document")

    providers_cfg = read_providers_config(root)
    table = providers_cfg.tables[provider]

    if role in table.roles:
        return ResolvedModel(
            role=role,
            model_id=table.roles[role],
            source="project-role",
        )

    tier = _tier_for_role(role)
    tier_model = _tier_model(table, tier)
    if tier_model is not None:
        return ResolvedModel(role=role, model_id=tier_model, source="project-tier")

    if role == "boss":
        epic_model = table.epic
        if epic_model is not None:
            return ResolvedModel(
                role=role,
                model_id=epic_model,
                source="boss-falls-back-to-epic",
            )

    raise ModelConfigError(f"no model configured for role {role!r}")


def resolve_project_provider(
    doc: WorkMeta | None,
    *,
    root: Path,
) -> tuple[ProviderId, ProviderSource]:
    """Resolve provider id from document frontmatter or project default."""

    if doc is not None and doc.provider is not None:
        return doc.provider, "document"
    providers_cfg = read_providers_config(root)
    return providers_cfg.default, "project-default"


def resolve_backend(
    role: RoleId,
    doc: WorkMeta | None,
    *,
    root: Path,
) -> ResolvedBackend:
    """Resolve provider and model for a role from document and project config."""

    provider, provider_source = resolve_project_provider(doc, root=root)
    model = resolve_model(role, doc, root=root, provider=provider)
    return ResolvedBackend(
        provider=provider,
        provider_source=provider_source,
        model=model,
    )
