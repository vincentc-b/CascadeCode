"""Authenticated tool adapters for bounded architecture history reads."""

from pathlib import Path
from typing import Sequence

from cascade.board.context import get_project_context
from cascade.workspace.architecture_context import read_historical_replay
from cascade.workspace.types import ProjectContext


def _project(root: Path) -> ProjectContext:
    return get_project_context() or ProjectContext.colocated(root)


def read_epic_historical_evidence(
    work_id: str,
    evidence_scope: Sequence[str],
    *,
    epic_id: str,
    root: Path,
) -> dict[str, object]:
    return read_historical_replay(
        _project(root), epic_id, work_id, evidence_scope
    ).to_dict()


def read_feature_historical_evidence(
    work_id: str,
    evidence_scope: Sequence[str],
    *,
    feature_id: str,
    root: Path,
) -> dict[str, object]:
    return read_historical_replay(
        _project(root), feature_id, work_id, evidence_scope
    ).to_dict()


def read_task_historical_evidence(
    work_id: str,
    evidence_scope: Sequence[str],
    *,
    task_id: str,
    root: Path,
) -> dict[str, object]:
    return read_historical_replay(
        _project(root), task_id, work_id, evidence_scope
    ).to_dict()

