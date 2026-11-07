"""Pure model id resolution from document frontmatter and cascade.toml provider tables."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Literal, Mapping

from cascade.agent.capability_contract import (
    EffectiveSelection,
    EffectiveSelectionBatch,
    REASON_MESSAGES,
    SELECTION_FINGERPRINT_SCHEMA,
    SelectionIssue,
    SelectionOrIssue,
    SelectionRole,
    SelectionSource,
    WorkTier,
    role_scope,
)
from cascade.agent.errors import ProviderConfigError
from cascade.agent.providers import ProviderId
from cascade.agent.types import RoleId
from cascade.board.gitutil import has_git, last_commit_touching
from cascade.board.types import WorkDoc, WorkMeta
from cascade.watchdog.config import ConfigError, ModelsTable, read_providers_config

ModelSource = Literal[
    "document-role",
    "document",
    "project-role",
    "project-tier",
    "boss-falls-back-to-epic",
]

ProviderSource = Literal["document", "project-default"]
ReasoningSource = Literal["document-role"]


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
    reasoning: str | None = None
    reasoning_source: ReasoningSource | None = None
    flex_mode: bool | None = None


ProviderReasoningDefaults = Mapping[tuple[str, str], str]


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


def resolve_reasoning(
    role: RoleId,
    doc: WorkMeta | None,
) -> tuple[str | None, ReasoningSource | None]:
    """Return a persisted per-role reasoning override, or None for provider default."""

    if doc is None or not doc.reasoning:
        return None, None
    level = _non_blank(doc.reasoning.get(role))
    if level is None:
        return None, None
    return level, "document-role"


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
    reasoning, reasoning_source = resolve_reasoning(role, doc)
    return ResolvedBackend(
        provider=provider,
        provider_source=provider_source,
        model=model,
        reasoning=reasoning,
        reasoning_source=reasoning_source,
        flex_mode=doc.flex_mode if doc is not None else None,
    )


def resolve_effective_selections(
    doc: WorkDoc | WorkMeta,
    *,
    root: Path,
    parent_doc: WorkDoc | WorkMeta | None = None,
    provider_reasoning_defaults: ProviderReasoningDefaults | None = None,
    effective_flex_mode: bool | None = None,
    document_revision: str | None = None,
) -> EffectiveSelectionBatch:
    """Resolve and fingerprint every role required by a work item's tier.

    This is the fail-closed selection boundary used by diagnostics.  Unlike the
    legacy one-role helpers above, it never drops a role or lets an explicitly
    present malformed value fall through to a project default.  Runtime Flex
    waivers affect only ``effective_flex_mode`` and therefore do not alter the
    reviewed-selection fingerprint.
    """

    repo = Path(root).resolve()
    meta = doc.meta if isinstance(doc, WorkDoc) else doc
    tier, roles = _selection_scope(meta)
    path = _relative_document_path(meta.path, repo)
    revision = _document_revision(
        doc,
        meta=meta,
        root=repo,
        explicit=document_revision,
    )
    config_path = repo / "cascade.toml"
    config_revision = _file_revision(config_path, root=repo)
    defaults = provider_reasoning_defaults or {}
    parent = _selection_parent(meta, supplied=parent_doc, root=repo)

    provisional: list[SelectionOrIssue] = []
    for role in roles:
        problem = _explicit_configuration_problem(meta, role)
        if tier != meta.tier:
            problem = "invalid_tier"
        if problem is not None:
            provisional.append(
                _selection_issue(
                    meta,
                    tier=tier,
                    role=role,
                    reason_code=problem,
                    path=path,
                    revision=revision,
                    root=repo,
                    config_revision=config_revision,
                )
            )
            continue
        try:
            backend, inherited_model_source = _resolve_effective_backend(
                role,
                meta,
                parent=parent,
                root=repo,
            )
            sources = _field_sources(
                backend,
                path=path,
                document_revision=revision,
                config_revision=config_revision,
                parent_revision=meta.parent_rev,
                model_source_override=inherited_model_source,
            )
            reasoning_effective = backend.reasoning
            if reasoning_effective is None:
                reasoning_effective = defaults.get(
                    (backend.provider, backend.model.model_id)
                )
            reviewed_flex = bool(meta.flex_mode) if meta.flex_mode is not None else False
            provisional.append(
                EffectiveSelection(
                    work_id=meta.id,
                    tier=tier,
                    role=role,
                    provider=backend.provider,
                    model_id=backend.model.model_id,
                    reasoning_level=backend.reasoning,
                    reasoning_effective=reasoning_effective,
                    reviewed_flex_mode=reviewed_flex,
                    effective_flex_mode=(
                        reviewed_flex
                        if effective_flex_mode is None
                        else effective_flex_mode
                    ),
                    field_sources=sources,
                    document_path=path,
                    document_revision=revision,
                    selection_fingerprint="",
                )
            )
        except ModelConfigError:
            provisional.append(
                _selection_issue(
                    meta,
                    tier=tier,
                    role=role,
                    reason_code="missing_configuration",
                    path=path,
                    revision=revision,
                    root=repo,
                    config_revision=config_revision,
                )
            )
        except (ConfigError, ProviderConfigError, KeyError, TypeError, ValueError):
            provisional.append(
                _selection_issue(
                    meta,
                    tier=tier,
                    role=role,
                    reason_code="malformed_configuration",
                    path=path,
                    revision=revision,
                    root=repo,
                    config_revision=config_revision,
                )
            )
        except Exception:
            # Diagnostics must remain safe and complete even when a resolver
            # implementation fails unexpectedly.  Raw exception text is never
            # carried into the result.
            provisional.append(
                _selection_issue(
                    meta,
                    tier=tier,
                    role=role,
                    reason_code="malformed_configuration",
                    path=path,
                    revision=revision,
                    root=repo,
                    config_revision=config_revision,
                )
            )

    fingerprint = selection_fingerprint(
        work_id=meta.id,
        tier=tier,
        roles=tuple(provisional),
        document_path=path,
        document_revision=revision,
    )
    completed = tuple(
        replace(item, selection_fingerprint=fingerprint)
        if isinstance(item, EffectiveSelection)
        else item
        for item in provisional
    )
    return EffectiveSelectionBatch(
        work_id=meta.id,
        tier=tier,
        roles=completed,
        selection_fingerprint=fingerprint,
    )


def selection_fingerprint(
    *,
    work_id: str,
    tier: WorkTier,
    roles: tuple[SelectionOrIssue, ...],
    document_path: str,
    document_revision: str,
) -> str:
    """Return the versioned canonical fingerprint for an ordered role scope."""

    canonical_roles: list[dict[str, object]] = []
    for item in roles:
        if isinstance(item, EffectiveSelection):
            canonical_roles.append(
                {
                    "role": item.role,
                    "provider": item.provider,
                    "model_id": item.model_id,
                    "reasoning_level": item.reasoning_level,
                    "reviewed_flex_mode": item.reviewed_flex_mode,
                    "field_sources": _canonical_sources(item.field_sources),
                    "document_path": item.document_path,
                    "document_revision": item.document_revision,
                }
            )
        else:
            canonical_roles.append(
                {
                    "role": item.role,
                    "issue": item.reason_code,
                    "provider": item.provider,
                    "model_id": item.model_id,
                    "reasoning_level": item.reasoning_level,
                    "reviewed_flex_mode": (
                        False
                        if item.reviewed_flex_mode is None
                        else item.reviewed_flex_mode
                    ),
                    "field_sources": _canonical_sources(item.field_sources or {}),
                    "document_path": item.document_path or document_path,
                    "document_revision": item.document_revision or document_revision,
                }
            )
    payload = {
        "schema": SELECTION_FINGERPRINT_SCHEMA,
        "work_id": work_id,
        "tier": tier,
        "roles": canonical_roles,
        "document_path": document_path,
        "document_revision": document_revision,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _selection_scope(meta: WorkMeta) -> tuple[WorkTier, tuple[SelectionRole, ...]]:
    if meta.tier in ("epic", "feature", "task"):
        return meta.tier, role_scope(meta.tier)
    inferred: WorkTier
    if meta.id.startswith("epic_"):
        inferred = "epic"
    elif meta.id.startswith("feat_"):
        inferred = "feature"
    else:
        inferred = "task"
    return inferred, role_scope(inferred)


def _explicit_configuration_problem(
    meta: WorkMeta,
    role: SelectionRole,
) -> Literal["malformed_configuration"] | None:
    if meta.provider is not None and (
        not isinstance(meta.provider, str) or not meta.provider.strip()
    ):
        return "malformed_configuration"
    if meta.models is not None:
        if not isinstance(meta.models, dict):
            return "malformed_configuration"
        if role in meta.models and _valid_non_blank(meta.models[role]) is None:
            return "malformed_configuration"
    role_model_present = isinstance(meta.models, dict) and role in meta.models
    if not role_model_present and meta.model is not None and _valid_non_blank(meta.model) is None:
        return "malformed_configuration"
    if meta.reasoning is not None:
        if not isinstance(meta.reasoning, dict):
            return "malformed_configuration"
        if role in meta.reasoning and _valid_non_blank(meta.reasoning[role]) is None:
            return "malformed_configuration"
    if meta.flex_mode is not None and not isinstance(meta.flex_mode, bool):
        return "malformed_configuration"
    return None


def _valid_non_blank(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _selection_issue(
    meta: WorkMeta,
    *,
    tier: WorkTier,
    role: SelectionRole,
    reason_code: Literal[
        "missing_configuration", "malformed_configuration", "invalid_tier"
    ],
    path: str,
    revision: str,
    root: Path,
    config_revision: str,
) -> SelectionIssue:
    provider = meta.provider if isinstance(meta.provider, str) and meta.provider.strip() else None
    provider_source: SelectionSource | None = None
    if provider is not None:
        provider_source = SelectionSource(
            kind="document",
            revision=revision,
            document_path=path,
            parent_revision=meta.parent_rev,
        )
    else:
        try:
            provider = read_providers_config(root).default
            provider_source = SelectionSource(
                kind="project-default",
                revision=config_revision,
                document_path="cascade.toml",
            )
        except Exception:
            provider = None
    model_id = None
    if isinstance(meta.models, dict) and role in meta.models:
        model_id = _valid_non_blank(meta.models[role])
    elif meta.model is not None:
        model_id = _valid_non_blank(meta.model)
    reasoning = None
    if isinstance(meta.reasoning, dict) and role in meta.reasoning:
        reasoning = _valid_non_blank(meta.reasoning[role])
    source = SelectionSource(
        kind="document",
        revision=revision,
        document_path=path,
        parent_revision=meta.parent_rev,
    )
    sources: dict[str, SelectionSource] = {"configuration": source}
    if provider_source is not None:
        sources["provider"] = provider_source
    return SelectionIssue(
        work_id=meta.id,
        tier=tier,
        role=role,
        reason_code=reason_code,
        message=REASON_MESSAGES[reason_code],
        provider=provider,
        model_id=model_id,
        reasoning_level=reasoning,
        reviewed_flex_mode=(meta.flex_mode if isinstance(meta.flex_mode, bool) else None),
        field_sources=sources,
        document_path=path,
        document_revision=revision,
    )


def _field_sources(
    backend: ResolvedBackend,
    *,
    path: str,
    document_revision: str,
    config_revision: str,
    parent_revision: str | None,
    model_source_override: SelectionSource | None = None,
) -> dict[str, SelectionSource]:
    def document_source(kind: Literal["document", "document-role"]) -> SelectionSource:
        return SelectionSource(
            kind=kind,
            revision=document_revision,
            document_path=path,
            parent_revision=parent_revision,
            stamping_rule="stamped-child" if parent_revision is not None else None,
        )

    def config_source(kind: Literal["project-default", "project-role", "project-tier"]) -> SelectionSource:
        return SelectionSource(
            kind=kind,
            revision=config_revision,
            document_path="cascade.toml",
        )

    provider_source = (
        document_source("document")
        if backend.provider_source == "document"
        else config_source("project-default")
    )
    if model_source_override is not None:
        model_source = model_source_override
    elif backend.model.source in ("document", "document-role"):
        model_source = document_source(backend.model.source)
    else:
        model_source = config_source(backend.model.source)  # type: ignore[arg-type]
    if backend.reasoning_source == "document-role":
        reasoning_source = document_source("document-role")
    else:
        # Provider-default capability evidence is intentionally not fingerprinted;
        # its source is anchored to the selected provider/model configuration.
        reasoning_source = SelectionSource(
            kind="provider-default",
            revision=model_source.revision,
            document_path=model_source.document_path,
            parent_revision=model_source.parent_revision,
            stamping_rule=model_source.stamping_rule,
        )
    return {
        "provider": provider_source,
        "model_id": model_source,
        "reasoning_level": reasoning_source,
        "reviewed_flex_mode": document_source("document"),
    }


def _resolve_effective_backend(
    role: SelectionRole,
    meta: WorkMeta,
    *,
    parent: WorkDoc | WorkMeta | None,
    root: Path,
) -> tuple[ResolvedBackend, SelectionSource | None]:
    """Apply the one resolve-time inheritance allowed by the stack contract."""

    if (
        meta.tier != "feature"
        or role != "swe"
        or _document_has_model(meta, role)
        or parent is None
    ):
        return resolve_backend(role, meta, root=root), None

    parent_meta = parent.meta if isinstance(parent, WorkDoc) else parent
    if not _document_has_model(parent_meta, role):
        return resolve_backend(role, meta, root=root), None
    if isinstance(parent_meta.models, dict) and role in parent_meta.models:
        if _valid_non_blank(parent_meta.models[role]) is None:
            raise ValueError("malformed inherited role model")
    elif parent_meta.model is not None and _valid_non_blank(parent_meta.model) is None:
        raise ValueError("malformed inherited legacy model")

    provider, provider_source = resolve_project_provider(meta, root=root)
    parent_model = resolve_model(role, parent_meta, root=root, provider=provider)
    reasoning, reasoning_source = resolve_reasoning(role, meta)
    parent_path = _relative_document_path(parent_meta.path, root)
    parent_revision = _document_revision(
        parent,
        meta=parent_meta,
        root=root,
        explicit=meta.parent_rev,
    )
    source = SelectionSource(
        kind=parent_model.source,  # type: ignore[arg-type]
        revision=parent_revision,
        document_path=parent_path,
        parent_revision=parent_meta.parent_rev,
        stamping_rule="feature_backend_from_epic",
    )
    return (
        ResolvedBackend(
            provider=provider,
            provider_source=provider_source,
            model=parent_model,
            reasoning=reasoning,
            reasoning_source=reasoning_source,
            flex_mode=meta.flex_mode,
        ),
        source,
    )


def _document_has_model(meta: WorkMeta, role: SelectionRole) -> bool:
    return bool(
        (isinstance(meta.models, dict) and role in meta.models)
        or meta.model is not None
    )


def _selection_parent(
    meta: WorkMeta,
    *,
    supplied: WorkDoc | WorkMeta | None,
    root: Path,
) -> WorkDoc | WorkMeta | None:
    if supplied is not None or meta.tier != "feature" or not meta.parent:
        return supplied
    try:
        from cascade.board.store import read_doc

        return read_doc(meta.parent, rev=meta.parent_rev, root=root)
    except Exception:
        return None


def _canonical_sources(sources: Mapping[str, SelectionSource]) -> dict[str, object]:
    return {
        key: {
            "kind": source.kind,
            "revision": source.revision,
            "document_path": source.document_path,
            "parent_revision": source.parent_revision,
            "stamping_rule": source.stamping_rule,
        }
        for key, source in sorted(sources.items())
    }


def _relative_document_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _document_revision(
    doc: WorkDoc | WorkMeta,
    *,
    meta: WorkMeta,
    root: Path,
    explicit: str | None,
) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    if isinstance(doc, WorkDoc) and doc.sha:
        return doc.sha
    return _file_revision(meta.path, root=root)


def _file_revision(path: Path, *, root: Path) -> str:
    try:
        if path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return f"sha256:{digest}"
    except OSError:
        return "unavailable"
    if has_git(root):
        try:
            rel = path.resolve().relative_to(root)
            revision = last_commit_touching(root, rel)
            if revision:
                return revision
        except (ValueError, OSError):
            pass
    return "absent"
