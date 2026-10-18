"""validate_doc checks headings, parents, folders, skills, and cycles."""

from pathlib import Path

import pytest

from cascade.board import (
    BoardIndex,
    CycleError,
    SchemaError,
    StatusMismatch,
    parse_doc,
    validate_doc,
)

FIXTURES = Path(__file__).parent / "fixtures" / "docs"


def _load(rel: str):
    return parse_doc(FIXTURES / rel)


def test_happy_path() -> None:
    epic = _load("epics/1_backlog/epic_001_ok.md")
    feature = _load("features/1_backlog/feat_001_ok.md")
    task = _load("tasks/1_backlog/task_001_ok.md")
    board = BoardIndex(
        by_id={
            epic.meta.id: epic.meta,
            feature.meta.id: feature.meta,
            task.meta.id: task.meta,
        }
    )
    assert validate_doc(epic, board) is None
    assert validate_doc(feature, board) is None
    assert validate_doc(task, board) is None


def test_model_frontmatter_happy_path() -> None:
    epic = _load("epics/1_backlog/epic_003_model.md")
    feature = _load("features/1_backlog/feat_005_models.md")
    task = _load("tasks/1_backlog/task_010_model.md")
    board = BoardIndex(
        by_id={
            epic.meta.id: epic.meta,
            feature.meta.id: feature.meta,
            task.meta.id: task.meta,
            "epic_001": _load("epics/1_backlog/epic_001_ok.md").meta,
            "feat_001": _load("features/1_backlog/feat_001_ok.md").meta,
        }
    )
    assert validate_doc(epic, board) is None
    assert validate_doc(feature, board) is None
    assert validate_doc(task, board) is None


def test_provider_frontmatter_happy_path() -> None:
    epic = _load("epics/1_backlog/epic_001_ok.md")
    epic.meta.provider = "codex"
    board = BoardIndex(by_id={epic.meta.id: epic.meta})
    assert validate_doc(epic, board) is None


def test_unknown_provider_fails_validation() -> None:
    from cascade.agent.errors import ProviderConfigError

    epic = _load("epics/1_backlog/epic_001_ok.md")
    epic.meta.provider = "not-a-provider"  # type: ignore[assignment]
    board = BoardIndex(by_id={epic.meta.id: epic.meta})
    with pytest.raises(ProviderConfigError):
        validate_doc(epic, board)


def test_models_wrong_tier_key_fails_validation() -> None:
    epic = _load("epics/1_backlog/epic_001_ok.md")
    epic.meta.models = {"swe": "wrong-tier-model"}
    board = BoardIndex(by_id={epic.meta.id: epic.meta})
    with pytest.raises(SchemaError, match="swe"):
        validate_doc(epic, board)


def test_missing_parent() -> None:
    feature = _load("features/1_backlog/feat_002_no_parent.md")
    epic = _load("epics/1_backlog/epic_001_ok.md")
    board = BoardIndex(by_id={epic.meta.id: epic.meta, feature.meta.id: feature.meta})
    with pytest.raises(SchemaError, match="parent"):
        validate_doc(feature, board)


def test_missing_heading() -> None:
    epic = _load("epics/1_backlog/epic_002_no_intent.md")
    board = BoardIndex(by_id={epic.meta.id: epic.meta})
    with pytest.raises(SchemaError, match="Intent"):
        validate_doc(epic, board)


def test_blocked_in_backlog_is_status_mismatch() -> None:
    epic = _load("epics/1_backlog/epic_001_ok.md")
    feature = _load("features/1_backlog/feat_001_ok.md")
    task = _load("tasks/1_backlog/task_009_blocked.md")
    board = BoardIndex(
        by_id={
            epic.meta.id: epic.meta,
            feature.meta.id: feature.meta,
            task.meta.id: task.meta,
        }
    )
    with pytest.raises(StatusMismatch):
        validate_doc(task, board)


def test_depends_on_cycle() -> None:
    epic = _load("epics/1_backlog/epic_001_ok.md")
    left = _load("features/1_backlog/feat_003_cycle_a.md")
    right = _load("features/1_backlog/feat_004_cycle_b.md")
    board = BoardIndex(
        by_id={
            epic.meta.id: epic.meta,
            left.meta.id: left.meta,
            right.meta.id: right.meta,
        }
    )
    with pytest.raises(CycleError):
        validate_doc(left, board)


def test_parent_cycle() -> None:
    epic = _load("epics/1_backlog/epic_001_ok.md")
    feature = _load("features/1_backlog/feat_001_ok.md")
    epic.meta.parent = feature.meta.id
    board = BoardIndex(by_id={epic.meta.id: epic.meta, feature.meta.id: feature.meta})
    with pytest.raises(CycleError):
        validate_doc(feature, board)


def test_missing_dependency() -> None:
    epic = _load("epics/1_backlog/epic_001_ok.md")
    feature = _load("features/1_backlog/feat_001_ok.md")
    task = _load("tasks/1_backlog/task_001_ok.md")
    task.meta.depends_on = ["task_999"]
    board = BoardIndex(
        by_id={
            epic.meta.id: epic.meta,
            feature.meta.id: feature.meta,
            task.meta.id: task.meta,
        }
    )
    with pytest.raises(SchemaError, match="task_999"):
        validate_doc(task, board)


def test_skill_paths_must_stay_inside_repo() -> None:
    epic = _load("epics/1_backlog/epic_001_ok.md")
    feature = _load("features/1_backlog/feat_001_ok.md")
    task = _load("tasks/1_backlog/task_001_ok.md")
    board = BoardIndex(
        by_id={
            epic.meta.id: epic.meta,
            feature.meta.id: feature.meta,
            task.meta.id: task.meta,
        }
    )
    task.meta.skills = [Path("skills/ok.md")]
    assert validate_doc(task, board) is None

    task.meta.skills = [Path("../SKILL.md")]
    with pytest.raises(SchemaError):
        validate_doc(task, board)

    task.meta.skills = [Path("/tmp/SKILL.md")]
    with pytest.raises(SchemaError):
        validate_doc(task, board)
