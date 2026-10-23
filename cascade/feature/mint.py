"""Feature Team tools: mint backlog tasks."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from cascade.board.errors import NotFound, SchemaError
from cascade.board.id_reservations import release_work_id
from cascade.board.paths import slugify
from cascade.board.store import allocate_id, list_board, read_doc, write_doc
from cascade.board.types import WorkDoc, WorkId, WorkMeta
from cascade.feature.checkout import feature_checkout_root
from cascade.feature.guard import FeatureToolDenied, tool_guard
from cascade.feature.registry import register_feature_tool
from cascade.feature.scoped_docs import feature_read_doc, feature_write_doc
from cascade.watchdog import append_event
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import merged_board

def mint_task(
    title: str,
    depends_on: list[str] | None = None,
    skills: list[str] | None = None,
    body_stub: str = "",
    *,
    feature_id: str,
    root: Path,
) -> WorkId:
    """Create a backlog task under this feature; does not dispatch or move columns."""

    trunk = Path(root).resolve()
    checkout = feature_checkout_root(feature_id, trunk=trunk)
    feature = _require_feature(feature_id, trunk)
    _refuse_blocked_feature(feature)
    from cascade.comments.gate import refusal_if_blocked

    if blocked := refusal_if_blocked(feature_id, root=trunk):
        raise FeatureToolDenied(blocked)

    deps = list(depends_on or [])
    skill_paths = _validate_skills(list(skills or []), trunk)

    board = list_board(checkout)
    for dep_id in deps:
        if dep_id not in board.by_id:
            raise FeatureToolDenied(f"depends_on {dep_id} is not on the board")
        dep = board.by_id[dep_id]
        if dep.tier != "task":
            raise FeatureToolDenied(f"depends_on {dep_id} must be a task")
        if dep.parent != feature_id:
            raise FeatureToolDenied(f"depends_on {dep_id} is not owned by {feature_id}")

    today = date.today()
    parent_rev = feature.sha
    task_id: WorkId | None = None
    for _attempt in range(8):
        candidate = allocate_id("task", merged_board(trunk), parent_id=feature_id)
        path = checkout / "docs" / "tasks" / "1_backlog" / f"{candidate}_{slugify(title)}.md"
        if not tool_guard(path, "write", feature_id=feature_id, root=trunk):
            release_work_id(candidate)
            raise FeatureToolDenied(f"write denied for {path}")

        doc = WorkDoc(
            meta=WorkMeta(
                id=candidate,
                title=title,
                tier="task",
                status="backlog",
                parent=feature_id,
                children=[],
                depends_on=deps,
                owners=["swe"],
                skills=skill_paths,
                parent_rev=parent_rev,
                created=today,
                updated=today,
                path=path,
            ),
            body=_task_body(
                title=title,
                feature_id=feature_id,
                depends_on=deps,
                skills=skill_paths,
                body_stub=body_stub,
            ),
            sha=None,
        )
        try:
            write_doc(doc, root=checkout)
            task_id = candidate
            break
        except SchemaError as exc:
            release_work_id(candidate)
            if "id collision" not in str(exc):
                raise
    if task_id is None:
        raise SchemaError("failed to allocate task id after persistence retries")

    feature = feature_read_doc(feature_id, feature_id=feature_id, root=trunk)
    if task_id not in feature.meta.children:
        feature.meta.children.append(task_id)
    feature.meta.updated = today
    feature.body = _append_task_breakdown(feature.body, task_id)
    feature_write_doc(feature, feature_id=feature_id, root=trunk)

    append_event(
        feature_id,
        Event(
            type="TasksMinted",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": feature_id, "task_ids": [task_id]},
            dest=feature_id,
        ),
        root=trunk,
    )
    return task_id


def _require_feature(feature_id: str, root: Path) -> WorkDoc:
    try:
        checkout = feature_checkout_root(feature_id, trunk=root)
        feature = read_doc(feature_id, root=checkout)
    except NotFound:
        raise FeatureToolDenied(f"unknown work id {feature_id}") from None
    if feature.meta.tier != "feature":
        raise FeatureToolDenied(f"{feature_id} is not a feature")
    if not tool_guard(feature.meta.path, "read", feature_id=feature_id, root=root):
        raise FeatureToolDenied(f"read denied for feature {feature_id}")
    return feature


def _refuse_blocked_feature(feature: WorkDoc) -> None:
    if feature.meta.status == "blocked":
        raise FeatureToolDenied(
            f"mint_task refused: feature {feature.meta.id} is blocked awaiting amendment resolution"
        )


def _validate_skills(skills: list[str], root: Path) -> list[Path]:
    repo = root.resolve()
    validated: list[Path] = []
    for skill in skills:
        path = Path(skill)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise FeatureToolDenied(f"skill path is not inside the repo: {skill}")
        if not path.parts or any(part in {"", "."} for part in path.parts):
            raise FeatureToolDenied(f"skill path is not inside the repo: {skill}")
        resolved = (repo / path).resolve()
        try:
            inside = resolved.is_relative_to(repo)
        except AttributeError:
            inside = str(resolved).startswith(str(repo))
        if not inside:
            raise FeatureToolDenied(f"skill path is not inside the repo: {skill}")
        validated.append(path)
    return validated


def _task_body(
    *,
    title: str,
    feature_id: str,
    depends_on: list[str],
    skills: list[Path],
    body_stub: str,
) -> str:
    deps_section = _depends_on_section(depends_on)
    skills_section = _skills_section(skills)
    notes = body_stub.strip() if body_stub else "TBD."
    return f"""\
# {title}

## Parent Feature

[{feature_id}](../../features/2_active/{feature_id}.md)

{deps_section}

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

{notes}

{skills_section}

## Test plan

TBD.

## Out of scope

TBD.
"""


def _depends_on_section(depends_on: list[str]) -> str:
    lines = ["## Depends on", ""]
    if not depends_on:
        lines.append("None.")
    else:
        for dep_id in depends_on:
            lines.append(f"- {dep_id}")
    return "\n".join(lines)


def _skills_section(skills: list[Path]) -> str:
    lines = ["## Skills", ""]
    if not skills:
        lines.append("_(none)_")
    else:
        for skill in skills:
            lines.append(f"- {skill.as_posix()}")
    return "\n".join(lines)


def _append_task_breakdown(body: str, task_id: str) -> str:
    bullet = f"- {task_id}"
    if any(line.strip() == bullet for line in body.splitlines()):
        return body
    marker = "## Task breakdown"
    idx = body.find(marker)
    if idx < 0:
        return body.rstrip() + f"\n\n{marker}\n\n{bullet}\n"
    line_end = body.find("\n", idx)
    if line_end < 0:
        return body + f"\n{bullet}\n"
    return body[: line_end + 1] + bullet + "\n" + body[line_end + 1 :]


register_feature_tool("mint_task", mint_task)
