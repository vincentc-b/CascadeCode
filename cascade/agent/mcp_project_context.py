"""Carry trusted repository roles across the local MCP subprocess boundary."""

from pathlib import Path

from cascade.board.context import get_project_context, set_project_context
from cascade.workspace.types import ProjectContext


def project_context_payload() -> dict[str, str] | None:
    project = get_project_context()
    if project is None:
        return None
    return {
        "target_root": str(project.target.root.resolve()),
        "tracking_root": str(project.tracking.root.resolve()),
    }


def restore_project_context(
    payload: object,
    *,
    architecture_destination: object = None,
) -> None:
    """Restore launcher configuration, never caller-supplied tool arguments."""
    if payload is None:
        set_project_context(None)
        return
    if not isinstance(payload, dict) or set(payload) != {
        "target_root",
        "tracking_root",
    }:
        raise ValueError("invalid MCP project repository context")
    if not all(
        isinstance(value, str) and value and Path(value).is_absolute()
        for value in payload.values()
    ):
        raise ValueError("MCP project roots must be absolute paths")
    if architecture_destination is None:
        architecture_destination = "target"
    if architecture_destination not in {"target", "tracking"}:
        raise ValueError("invalid MCP architecture destination")
    set_project_context(
        ProjectContext.split(
            Path(payload["target_root"]),
            Path(payload["tracking_root"]),
            architecture_destination=architecture_destination,
        )
    )
