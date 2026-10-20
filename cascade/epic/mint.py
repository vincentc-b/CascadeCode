"""Epic Team tools: mint backlog features and list child features."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.paths import slugify
from cascade.board.store import allocate_id, list_board, read_doc
from cascade.board.types import WorkDoc, WorkMeta
from cascade.epic.guard import EpicToolDenied, tool_guard
from cascade.epic.registry import register_epic_tool
from cascade.epic.scoped_docs import epic_read_doc, epic_write_doc
from cascade.watchdog import append_event
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import merged_board


def mint_feature(
    title: str,
    depends_on: list[str] | None = None,
    body_stub: str = "",
    *,
    epic_id: str,
    root: Path,
) -> str:
    """Create a backlog feature under this epic; does not dispatch or move columns."""

    repo = Path(root).resolve()
    _require_epic(epic_id, repo)

    deps = list(depends_on or [])
    board = merged_board(repo)
    for dep_id in deps:
        if dep_id not in board.by_id:
            raise EpicToolDenied(f"depends_on {dep_id} is not on the board")
        if board.by_id[dep_id].tier != "feature":
            raise EpicToolDenied(f"depends_on {dep_id} must be a feature")

    feature_id = allocate_id("feature", board)
    today = date.today()
    path = repo / "docs" / "features" / "1_backlog" / f"{feature_id}_{slugify(title)}.md"
    if not tool_guard(path, "write", epic_id=epic_id, root=repo):
        raise EpicToolDenied(f"write denied for {path}")

    epic_doc = epic_read_doc(epic_id, epic_id=epic_id, root=repo)
    provider, models, model = _feature_backend_from_epic(epic_doc)

    doc = WorkDoc(
        meta=WorkMeta(
            id=feature_id,
            title=title,
            tier="feature",
            status="backlog",
            parent=epic_id,
            children=[],
            depends_on=deps,
            owners=["feature_lead", "feature_architect"],
            skills=[],
            parent_rev=None,
            created=today,
            updated=today,
            path=path,
            model=model,
            models=models,
            provider=provider,
        ),
        body=_feature_body(title=title, epic_id=epic_id, body_stub=body_stub),
        sha=None,
    )
    epic_write_doc(doc, epic_id=epic_id, root=repo)

    epic = epic_read_doc(epic_id, epic_id=epic_id, root=repo)
    if feature_id not in epic.meta.children:
        epic.meta.children.append(feature_id)
    epic.meta.updated = today
    epic.body = _append_feature_breakdown(epic.body, feature_id)
    epic_write_doc(epic, epic_id=epic_id, root=repo)

    append_event(
        epic_id,
        Event(
            type="FeatureMinted",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": feature_id, "epic_id": epic_id},
            dest=epic_id,
        ),
        root=repo,
    )
    return feature_id


def list_children(*, epic_id: str, root: Path) -> list[WorkMeta]:
    """Return feature-tier children of this epic in epic.children order."""

    repo = Path(root).resolve()
    epic = _require_epic(epic_id, repo)
    board = list_board(repo)
    result: list[WorkMeta] = []
    for child_id in epic.meta.children:
        meta = board.by_id.get(child_id)
        if meta is None or meta.tier != "feature":
            continue
        result.append(meta)
    return result


def _require_epic(epic_id: str, root: Path) -> WorkDoc:
    try:
        epic = read_doc(epic_id, root=root)
    except NotFound:
        raise EpicToolDenied(f"unknown work id {epic_id}") from None
    if epic.meta.tier != "epic":
        raise EpicToolDenied(f"{epic_id} is not an epic")
    if not tool_guard(epic.meta.path, "read", epic_id=epic_id, root=root):
        raise EpicToolDenied(f"read denied for epic {epic_id}")
    return epic


def _feature_backend_from_epic(epic: WorkDoc) -> tuple[str | None, dict[str, str] | None, str | None]:
    """Copy parent epic provider/model defaults onto a new feature (explicit stamp, not resolve-time inherit)."""

    provider = epic.meta.provider
    models: dict[str, str] | None = None
    model: str | None = None

    if epic.meta.models:
        mapped: dict[str, str] = {}
        for epic_role, feature_role in (
            ("epic_manager", "feature_lead"),
            ("epic_architect", "feature_architect"),
        ):
            if epic_role in epic.meta.models:
                mapped[feature_role] = epic.meta.models[epic_role]
        for key, value in epic.meta.models.items():
            if key in ("feature_lead", "feature_architect"):
                mapped[key] = value
        if mapped:
            models = mapped
    elif epic.meta.model:
        model = epic.meta.model

    return provider, models, model


def _feature_body(*, title: str, epic_id: str, body_stub: str) -> str:
    scope = body_stub.strip() if body_stub else "TBD."
    return f"""\
# {title}

## Parent Epic

{epic_id}

## Scope

{scope}

## Data structures

TBD.

## API contracts

TBD.

## Logic flow

```mermaid
flowchart TD
  A[Start] --> B[End]
```

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
"""


def _append_feature_breakdown(body: str, feature_id: str) -> str:
    bullet = f"- {feature_id}"
    if any(line.strip() == bullet for line in body.splitlines()):
        return body
    marker = "## Feature breakdown"
    idx = body.find(marker)
    if idx < 0:
        return body.rstrip() + f"\n\n{marker}\n\n{bullet}\n"
    line_end = body.find("\n", idx)
    if line_end < 0:
        return body + f"\n{bullet}\n"
    return body[: line_end + 1] + bullet + "\n" + body[line_end + 1 :]


register_epic_tool("mint_feature", mint_feature)
register_epic_tool("list_children", list_children)
