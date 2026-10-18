"""Path pairing and work-id format."""

from pathlib import Path

import pytest

from cascade.board import (
    BoardError,
    CycleError,
    GitError,
    NotFound,
    SchemaError,
    StatusMismatch,
    column_dir,
    format_work_id,
    legal_folder,
    parse_work_id,
    status_for_column,
)


def test_status_folder_pairing() -> None:
    assert legal_folder("backlog") == "1_backlog"
    assert legal_folder("ready_to_plan") == "1_backlog"
    assert legal_folder("active") == "2_active"
    assert legal_folder("blocked") == "2_active"
    assert legal_folder("completed") == "3_completed"
    assert status_for_column("backlog") == "backlog"
    assert status_for_column("active") == "active"
    assert status_for_column("completed") == "completed"
    assert column_dir("epic", "backlog") == Path("docs/epics/1_backlog")
    assert column_dir("feature", "active") == Path("docs/features/2_active")
    assert column_dir("task", "completed") == Path("docs/tasks/3_completed")


def test_work_id_format() -> None:
    assert parse_work_id("epic_001") == ("epic", 1)
    assert parse_work_id("feat_012") == ("feature", 12)
    assert parse_work_id("task_003") == ("task", 3)
    assert format_work_id("epic", 1) == "epic_001"
    assert format_work_id("feature", 12) == "feat_012"
    assert format_work_id("task", 3) == "task_003"
    assert parse_work_id(format_work_id("task", 42)) == ("task", 42)
    with pytest.raises(SchemaError):
        parse_work_id("feature_001")
    with pytest.raises(SchemaError):
        parse_work_id("task_0")


def test_exceptions_inherit_board_error() -> None:
    for error in (SchemaError, NotFound, CycleError, StatusMismatch, GitError):
        assert issubclass(error, BoardError)
