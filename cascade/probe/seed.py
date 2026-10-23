"""Minimal board seeding inside a disposable probe workspace."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from cascade.approvals import approve_feature
from cascade.board.paths import column_dir, column_for_status, slugify
from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkDoc, WorkMeta, WorkStatus, WorkTier

_EPIC_BODY = """\
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

_FEATURE_BODY = """\
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

_TASK_BODY = """\
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

_TIER_BODY = {"epic": _EPIC_BODY, "feature": _FEATURE_BODY, "task": _TASK_BODY}


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def commit_probe_board(root: Path, message: str = "probe seed") -> None:
    """Commit board changes so activation and dispatch gates succeed."""

    if not (root / ".git").is_dir():
        return
    readme = root / "README.md"
    if not readme.is_file():
        readme.write_text("cascade lifecycle probe workspace\n", encoding="utf-8")
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


def write_probe_doc(
    root: Path,
    *,
    work_id: str,
    title: str,
    tier: WorkTier,
    status: WorkStatus = "backlog",
    parent: str | None = None,
) -> WorkDoc:
    column = column_for_status(status)
    path = root / column_dir(tier, column) / f"{work_id}_{slugify(title)}.md"
    doc = WorkDoc(
        meta=WorkMeta(
            id=work_id,
            title=title,
            tier=tier,
            status=status,
            parent=parent,
            children=[],
            depends_on=[],
            owners=["probe"],
            skills=[],
            parent_rev=None,
            created=date(2026, 10, 23),
            updated=date(2026, 10, 23),
            path=path,
        ),
        body=_TIER_BODY[tier],
        sha=None,
    )
    write_doc(doc, root=root)
    return read_doc(work_id, root=root)


def seed_lifecycle_chain(root: Path) -> dict[str, str]:
    """Epic → feature → task backlog chain ready for dispatch."""

    write_probe_doc(root, work_id="epic_901", title="Probe epic", tier="epic")
    write_probe_doc(
        root,
        work_id="feat_901_001",
        title="Probe feature",
        tier="feature",
        parent="epic_901",
    )
    write_probe_doc(
        root,
        work_id="task_901_001_001",
        title="Probe task",
        tier="task",
        parent="feat_901_001",
    )
    commit_probe_board(root, message="probe lifecycle chain seed")
    approve_feature("feat_901_001", root=root)
    commit_probe_board(root, message="probe feature approved")
    return {"epic": "epic_901", "feature": "feat_901_001", "task": "task_901_001_001"}


def seed_dispatchable_feature(
    root: Path,
    *,
    epic_id: str,
    feature_id: str,
    stall_threshold_seconds: float,
) -> None:
    """Approved backlog feature observed by convergence detection."""

    write_probe_doc(root, work_id=epic_id, title=f"{epic_id} epic", tier="epic")
    write_probe_doc(
        root,
        work_id=feature_id,
        title=f"{feature_id} feature",
        tier="feature",
        parent=epic_id,
    )
    commit_probe_board(root, message=f"probe convergence seed {feature_id}")
    approve_feature(feature_id, root=root)
    commit_probe_board(root, message=f"probe approve {feature_id}")
    config = root / "cascade.toml"
    existing = config.read_text(encoding="utf-8") if config.is_file() else ""
    threshold_line = f"stall_threshold_seconds = {int(stall_threshold_seconds)}"
    if "[convergence]" in existing:
        lines = []
        for line in existing.splitlines():
            if line.strip().startswith("stall_threshold_seconds"):
                lines.append(threshold_line)
            else:
                lines.append(line)
        config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        block = f"[convergence]\n{threshold_line}\n"
        config.write_text((existing.rstrip() + "\n\n" + block).lstrip("\n"), encoding="utf-8")
    commit_probe_board(root, message="probe convergence threshold")
