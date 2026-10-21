"""Epic brief template and MR-backed brief creation."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cascade.agent.providers import parse_provider_id
from cascade.board.errors import GitError
from cascade.board.gitutil import _run
from cascade.board.parse import render_doc
from cascade.board.store import list_board
from cascade.board.types import WorkDoc, WorkMeta
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
    manager_model: str
    architect_model: str


def brief_template(root: Path) -> dict[str, object]:
    config = read_providers_config(root)
    provider = config.default
    table = config.tables[provider]
    provider_models = {}
    for provider_id, provider_table in config.tables.items():
        provider_models[provider_id] = {
            "manager_model": provider_table.roles.get("epic_manager") or provider_table.epic or "",
            "architect_model": provider_table.roles.get("epic_architect") or provider_table.epic or "",
        }
    return {
        "provider": provider,
        "providers": ["cursor", "claude", "codex"],
        "manager_model": table.roles.get("epic_manager") or table.epic or "",
        "architect_model": table.roles.get("epic_architect") or table.epic or "",
        "provider_models": provider_models,
        "suggestions": {
            "epic_manager": "Use a strong reasoning model for scope, sequencing, and acceptance criteria.",
            "epic_architect": "Use a strong coding/reasoning model for boundaries and cross-feature constraints.",
        },
        "tracking_ready": forge_ready(root),
    }


def _clean(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def validate_brief(raw: dict[str, object]) -> BriefRequest:
    provider = parse_provider_id(_clean(str(raw.get("provider") or ""), "provider"))
    return BriefRequest(
        title=_clean(str(raw.get("title") or ""), "title"),
        intent=_clean(str(raw.get("intent") or ""), "intent"),
        success_criteria=_clean(str(raw.get("success_criteria") or ""), "success criteria"),
        constraints=str(raw.get("constraints") or "").strip(),
        provider=provider,
        manager_model=_clean(str(raw.get("manager_model") or ""), "manager model"),
        architect_model=_clean(str(raw.get("architect_model") or ""), "architect model"),
    )


def _next_epic_id(root: Path) -> str:
    numbers = [int(meta.id.split("_", 1)[1]) for meta in list_board(root).by_id.values() if meta.tier == "epic"]
    branches = _run(["branch", "-a", "--format=%(refname:short)"], root, check=False)
    for match in re.finditer(r"cascade/brief/epic_(\d+)", branches.stdout):
        numbers.append(int(match.group(1)))
    return f"epic_{(max(numbers, default=0) + 1):03d}"


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
        models={
            "epic_manager": request.manager_model,
            "epic_architect": request.architect_model,
        },
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
    request = validate_brief(raw)
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
