"""Epic brief template and MR-backed brief creation."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
    get_provider_inventory,
)
from cascade.agent.discovery.normalize import sanitize_provider_error
from cascade.agent.providers import parse_provider_id
from cascade.board.errors import GitError
from cascade.board.gitutil import _run
from cascade.board.parse import render_doc
from cascade.board.errors import SchemaError
from cascade.board.store import list_board, read_doc
from cascade.board.work_ids import format_hierarchical_epic_id, parse_work_id_parts
from cascade.board.types import WorkDoc, WorkMeta
from cascade.brief_stack import (
    BRIEF_STACK_ROLES,
    brief_selection_from_meta,
    normalize_reasoning_overrides,
    parse_brief_models,
    parse_brief_reasoning,
    role_models_for_provider,
    validate_models_against_inventory,
)
from cascade.tracking import MergeRequest, create_merge_request, forge_ready, push_branch
from cascade.watchdog.config import read_providers_config
from cascade.workspace.trunk import resolve_product_trunk


@dataclass(frozen=True)
class BriefRequest:
    title: str
    intent: str
    success_criteria: str
    constraints: str
    provider: str
    models: dict[str, str]
    reasoning: dict[str, str]
    flex_mode: bool

    @property
    def manager_model(self) -> str:
        return self.models["epic_manager"]

    @property
    def architect_model(self) -> str:
        return self.models["epic_architect"]


def fetch_brief_provider_inventory(
    root: Path,
    *,
    force_refresh: bool = False,
) -> dict[str, object]:
    """Return normalized provider/model inventory for brief UI consumers."""

    from cascade.war_room.serialize import brief_provider_inventory_to_dict

    config = read_providers_config(root)
    try:
        result = get_provider_inventory(force_refresh=force_refresh)
    except Exception as exc:
        empty = ProviderInventoryResult(
            providers=(),
            failures=(),
            freshness=InventoryFreshness(
                from_cache=False,
                fetched_at=0.0,
                expires_at=0.0,
                ttl_seconds=0.0,
            ),
        )
        return brief_provider_inventory_to_dict(
            empty,
            default_provider=config.default,
            force_refresh=force_refresh,
            refresh_failed=True,
            refresh_error=sanitize_provider_error(exc),
        )
    return brief_provider_inventory_to_dict(
        result,
        default_provider=config.default,
        force_refresh=force_refresh,
    )


def _resolve_template_provider(
    config_default: str,
    inventory: ProviderInventoryResult,
) -> str:
    available = [item.provider_id for item in inventory.providers]
    if config_default in available:
        return config_default
    if available:
        return available[0]
    return config_default


def brief_template(
    root: Path,
    *,
    epic_id: str | None = None,
    request_path: str | None = None,
) -> dict[str, object]:
    config = read_providers_config(root)
    inventory = get_provider_inventory()
    provider = _resolve_template_provider(config.default, inventory)
    table = config.tables[provider]  # type: ignore[index]
    role_models = role_models_for_provider(table)
    available_providers = [item.provider_id for item in inventory.providers]
    provider_models = {
        provider_id: role_models_for_provider(config.tables[provider_id])
        for provider_id in available_providers
    }
    payload: dict[str, object] = {
        "provider": provider,
        "providers": available_providers,
        "roles": list(BRIEF_STACK_ROLES),
        "models": dict(role_models),
        "reasoning": {},
        "provider_models": provider_models,
        "manager_model": role_models["epic_manager"],
        "architect_model": role_models["epic_architect"],
        "suggestions": {
            "epic_manager": "Use a strong reasoning model for scope, sequencing, and acceptance criteria.",
            "epic_architect": "Use a strong coding/reasoning model for boundaries and cross-feature constraints.",
            "feature_lead": "Use a strong planning model for feature breakdown and acceptance criteria.",
            "feature_architect": "Use a strong coding model for feature-level design constraints.",
            "swe": "Use a fast implementation model for scoped task delivery.",
        },
        "inventory_available": bool(inventory.providers),
        "tracking_ready": forge_ready(root),
    }
    if epic_id:
        try:
            doc = read_doc(epic_id, root=root)
        except (SchemaError, OSError, ValueError):
            doc = None
        if doc is not None and doc.meta.tier == "epic":
            payload["saved"] = brief_selection_from_meta(doc.meta)
    elif request_path:
        query = parse_qs(urlparse(request_path).query)
        epic_from_query = (query.get("epic_id") or [None])[0]
        if isinstance(epic_from_query, str) and epic_from_query.strip():
            return brief_template(root, epic_id=epic_from_query.strip())
    return payload


def _clean(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def validate_brief(raw: dict[str, object], *, root: Path) -> BriefRequest:
    config = read_providers_config(root)
    provider = parse_provider_id(_clean(str(raw.get("provider") or ""), "provider"))
    table = config.tables[provider]
    models = parse_brief_models(raw, table=table)
    reasoning_input = parse_brief_reasoning(raw)
    inventory = get_provider_inventory()
    provider_item = validate_models_against_inventory(provider, models, inventory)
    flex_mode = normalize_flex_mode(raw.get("flex_mode"), provider_item)
    reasoning = normalize_reasoning_overrides(
        models,
        reasoning_input,
        provider_item=provider_item,
    )
    return BriefRequest(
        title=_clean(str(raw.get("title") or ""), "title"),
        intent=_clean(str(raw.get("intent") or ""), "intent"),
        success_criteria=_clean(str(raw.get("success_criteria") or ""), "success criteria"),
        constraints=str(raw.get("constraints") or "").strip(),
        provider=provider,
        models=models,
        reasoning=reasoning,
        flex_mode=flex_mode,
    )


def normalize_flex_mode(raw: object, provider_item: ProviderInventoryItem) -> bool:
    """Default from capability and prevent unsupported providers enabling flex."""

    if raw is None:
        return provider_item.supports_flex_mode
    if not isinstance(raw, bool):
        raise ValueError("flex_mode must be a boolean")
    return raw and provider_item.supports_flex_mode


def _next_epic_id(root: Path) -> str:
    numbers: set[int] = set()
    for meta in list_board(root).by_id.values():
        if meta.tier != "epic":
            continue
        try:
            numbers.add(parse_work_id_parts(meta.id).segments[0])
        except SchemaError:
            continue
    branches = _run(["branch", "-a", "--format=%(refname:short)"], root, check=False)
    for match in re.finditer(r"cascade/brief/epic_(\d{3})", branches.stdout):
        numbers.add(int(match.group(1)))
    return format_hierarchical_epic_id(max(numbers, default=0) + 1)


def _slug(title: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return value[:60] or "brief"


def build_brief_doc(request: BriefRequest, epic_id: str, path: Path) -> WorkDoc:
    today = date.today()
    constraints = request.constraints or "To be refined by the Epic Team during planning."
    body = f"""# {request.title}

## Intent

{request.intent}

### Success criteria

{request.success_criteria}

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

{constraints}

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- {today.isoformat()} · Human · Brief approved through merge request review.

## Amendment log

_(none)_
"""
    meta = WorkMeta(
        id=epic_id,
        title=request.title,
        tier="epic",
        status="backlog",
        parent=None,
        children=[],
        depends_on=[],
        owners=["epic_manager", "epic_architect"],
        skills=[],
        parent_rev=None,
        created=today,
        updated=today,
        path=path,
        provider=request.provider,  # type: ignore[arg-type]
        models=dict(request.models),
        reasoning=dict(request.reasoning) if request.reasoning else None,
        flex_mode=request.flex_mode,
    )
    return WorkDoc(meta=meta, body=body)


def _fetch_remote_trunk(repo: Path, trunk: str, *, remote: str = "origin") -> str:
    """Fetch and return the remote-tracking ref used as a clean brief base."""

    fetch = subprocess.run(
        ["git", "fetch", remote, trunk],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        raise GitError((fetch.stderr or fetch.stdout).strip() or f"could not fetch {remote}/{trunk}")
    base = f"{remote}/{trunk}"
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        raise GitError((verify.stderr or verify.stdout).strip() or f"remote trunk {base} is unavailable")
    return base


def create_brief(root: Path, raw: dict[str, object]) -> tuple[str, MergeRequest]:
    """Create an isolated brief branch, push it, and open its approval MR."""

    repo = Path(root).resolve()
    if not forge_ready(repo):
        raise GitError(
            "brief creation requires an authenticated gh or glab CLI matching the origin remote"
        )
    request = validate_brief(raw, root=repo)
    epic_id = _next_epic_id(repo)
    branch = f"cascade/brief/{epic_id}"
    trunk = resolve_product_trunk(repo)
    base = _fetch_remote_trunk(repo, trunk)
    with tempfile.TemporaryDirectory(prefix=f"cascade-{epic_id}-") as temp:
        worktree = Path(temp) / "worktree"
        add = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(worktree), base],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if add.returncode != 0:
            raise GitError((add.stderr or add.stdout).strip() or "brief worktree creation failed")
        try:
            path = worktree / "docs" / "epics" / "1_backlog" / f"{epic_id}_{_slug(request.title)}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_doc(build_brief_doc(request, epic_id, path)), encoding="utf-8")
            commit = subprocess.run(
                ["git", "add", "--", str(path.relative_to(worktree))],
                cwd=worktree, capture_output=True, text=True,
            )
            if commit.returncode == 0:
                commit = subprocess.run(
                    [
                        "git", "-c", "commit.gpgsign=false", "commit", "--only",
                        "-m", f"brief: {epic_id} {request.title}",
                        "--", str(path.relative_to(worktree)),
                    ],
                    cwd=worktree, capture_output=True, text=True,
                )
            if commit.returncode != 0:
                raise GitError((commit.stderr or commit.stdout).strip() or "brief commit failed")
            push_branch(worktree, branch)
            mr = create_merge_request(
                worktree,
                title=f"Brief: {request.title}",
                body=(
                    f"Creates `{epic_id}` for review. Merge this brief to make it available "
                    "in the War Room backlog. Activation starts the Epic Team automatically."
                ),
                source_branch=branch,
                target_branch=trunk,
            )
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo, capture_output=True)
    return epic_id, mr
