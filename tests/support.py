"""Temporary git repos and valid work docs for board and watchdog tests."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from cascade.board.paths import column_dir, column_for_status, slugify
from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkDoc, WorkMeta, WorkStatus, WorkTier

_WORKSPACE = Path("/home/ubuntu/dev/CascadeCode").resolve()

EPIC_BODY = """\
# Title

## Intent

Why this exists.

## Macro-architecture

Module boundaries.

## Cross-module constraints

Local only.

## Core dependencies

Python 3.12.

## Feature breakdown

Children are listed in frontmatter.

## Open questions

None.

## Decision log

None yet.

## Amendment log

None.
"""

FEATURE_BODY = """\
# Title

## Parent Epic

Honor the parent constraints.

## Scope

In: this contract. Out: implementation.

## Data structures

Work documents.

## API contracts

Signatures live here.

## Logic flow

```mermaid
flowchart TD
  A --> B
```

## Task breakdown

Tasks are listed in frontmatter.

## Risks & upward questions

None.

## Decision log

None yet.
"""

TASK_BODY = """\
# Title

## Parent Feature

Parent feature and parent_rev.

## Depends on

See frontmatter.

## Acceptance criteria

Tests pass.

## Files likely touched

- cascade/

## Implementation notes

Notes for the implementer.

## Skills

_(none)_

## Test plan

pytest.

## Out of scope

UI and LangGraph.
"""

_BODIES = {"epic": EPIC_BODY, "feature": FEATURE_BODY, "task": TASK_BODY}


DEFAULT_MODELS_TOML = """
[models]
epic = "proj-epic"
feature = "proj-feature"
task = "proj-task"
""".strip()


def write_default_models(root: Path) -> None:
    path = root / "cascade.toml"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "[models]" in existing:
        return
    body = (existing.rstrip() + "\n\n" + DEFAULT_MODELS_TOML + "\n").lstrip("\n")
    path.write_text(body, encoding="utf-8")


_ROLE_SKILL_MARKERS = {
    "skills/roles/frugal_engineering/SKILL.md": "FIXTURE_FRUGAL_PHILOSOPHY",
    "skills/roles/product_manager/SKILL.md": "FIXTURE_PM_SCOPE_GUARD",
    "skills/roles/engineering_manager/SKILL.md": "FIXTURE_EM_PROCESS_FRUGALITY",
}

_ROLE_SKILL_EXTRA_FIXTURES = {
    "skills/roles/software_developer/SKILL.md": "FIXTURE_SW_DEV_SIMPLICITY",
    "skills/roles/code_reviewer/SKILL.md": "FIXTURE_CODE_REVIEW_SELF_CHECK",
}


def write_role_skill_fixtures(root: Path) -> None:
    """Materialize all RoleSkillDefaults playbooks under ``root`` for tests."""

    repo = Path(root).resolve()
    all_fixtures = {**_ROLE_SKILL_MARKERS, **_ROLE_SKILL_EXTRA_FIXTURES}
    for rel, marker in all_fixtures.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Fixture playbook\n{marker}\n", encoding="utf-8")


def commit_board(root: Path, message: str = "board") -> None:
    """Commit all docs on ``root`` when it is a git checkout (activation gates)."""

    if not (root / ".git").exists():
        return
    marker = root / "README.md"
    if not marker.is_file():
        marker.write_text("board\n", encoding="utf-8")
    _git(root, "add", "-A")
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "nothing to commit" not in (result.stdout + result.stderr):
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            result.stdout,
            result.stderr,
        )


def make_git_repo(tmp_path: Path) -> Path:
    """Empty git repo with no board layout or cascade.toml."""

    root = (tmp_path / "repo").resolve()
    if root == _WORKSPACE or _WORKSPACE in root.parents:
        raise RuntimeError("refusing to build a test repo inside the CascadeCode workspace")
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    return root


def make_repo(
    tmp_path: Path,
    *,
    git: bool = True,
    parallelism: int | None = None,
    models: bool = False,
    role_skills: bool = False,
) -> Path:
    """Create a throwaway repo. Never initializes the CascadeCode workspace."""

    root = (tmp_path / "repo").resolve()
    if root == _WORKSPACE or _WORKSPACE in root.parents:
        raise RuntimeError("refusing to build a test repo inside the CascadeCode workspace")
    for tier in ("epics", "features", "tasks"):
        for column in ("1_backlog", "2_active", "3_completed"):
            (root / "docs" / tier / column).mkdir(parents=True)
    toml_lines: list[str] = []
    if parallelism is not None:
        toml_lines.append(f"task_parallelism = {parallelism}")
    if models:
        toml_lines.append(DEFAULT_MODELS_TOML)
    if toml_lines:
        (root / "cascade.toml").write_text("\n".join(toml_lines) + "\n", encoding="utf-8")
    if git:
        _git(root, "init", "-b", "main")
        _git(root, "config", "user.email", "test@example.com")
        _git(root, "config", "user.name", "Test User")
    if role_skills:
        write_role_skill_fixtures(root)
    return root


def approve_board_feature(root: Path, feature_id: str) -> None:
    """Mark a feature approved through the same path production uses."""

    from cascade.approvals import approve_feature

    approve_feature(feature_id, root=root)


def add_doc(
    root: Path,
    *,
    id: str,
    title: str,
    tier: WorkTier,
    status: WorkStatus = "backlog",
    parent: str | None = None,
    depends_on: list[str] | None = None,
    skills: list[Path] | None = None,
    children: list[str] | None = None,
) -> WorkDoc:
    column = column_for_status(status)
    path = root / column_dir(tier, column) / f"{id}_{slugify(title)}.md"
    doc = WorkDoc(
        meta=WorkMeta(
            id=id,
            title=title,
            tier=tier,
            status=status,
            parent=parent,
            children=list(children or []),
            depends_on=list(depends_on or []),
            owners=["tester"],
            skills=list(skills or []),
            parent_rev=None,
            created=date(2026, 10, 9),
            updated=date(2026, 10, 9),
            path=path,
        ),
        body=_BODIES[tier],
        sha=None,
    )
    write_doc(doc, root=root)
    return read_doc(id, root=root)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


TEST_MODEL_ID = "test-model"


def write_swe_default_role_skills(root: Path) -> None:
    """Create SKILL.md files for SWE role-default paths (task boot tests)."""

    write_role_skill_fixtures(root)


def install_fake_planning_turns(monkeypatch) -> None:
    """Patch epic/feature graph nodes to use a deterministic fake adapter."""

    from cascade.agent.types import RoleResult

    async def fake_epic(
        role: str,
        model_id: str,
        prompt: str,
        *,
        provider: str,
        epic_id: str,
        root: object,
    ) -> RoleResult:
        assert model_id == TEST_MODEL_ID
        return RoleResult(text=f"{role}:{prompt}", status="finished")

    async def fake_feature(
        role: str,
        model_id: str,
        prompt: str,
        *,
        provider: str,
        feature_id: str,
        root: object,
    ) -> RoleResult:
        assert model_id == TEST_MODEL_ID
        return RoleResult(text=f"{role}:{prompt}", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", fake_epic)
    monkeypatch.setattr("cascade.agent.planning_turn.run_feature_planning_turn", fake_feature)
