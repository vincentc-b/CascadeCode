"""Filesystem board. move_doc does not enforce dispatch law."""

from importlib import import_module

from cascade.board.errors import (
    BoardError,
    CycleError,
    GitError,
    NotFound,
    SchemaError,
    StatusMismatch,
)
from cascade.board.parse import parse_doc
from cascade.board.paths import (
    column_dir,
    column_for_status,
    format_work_id,
    legal_folder,
    parse_work_id,
    status_for_column,
)
from cascade.board.id_reservations import reset_id_reservations
from cascade.board.store import (
    allocate_id,
    list_board,
    move_doc,
    pin_parent,
    read_doc,
    write_doc,
)
from cascade.board.work_ids import allocate_hierarchical_id
from cascade.board.types import (
    BoardIndex,
    Column,
    WorkDoc,
    WorkId,
    WorkMeta,
    WorkStatus,
    WorkTier,
)
from cascade.board.validate import validate_doc

_MIGRATION_EXPORTS = {
    "BacklogMigrationApplyError",
    "BacklogMigrationPlan",
    "BacklogMigrationValidationError",
    "apply_backlog_migration",
    "build_backlog_migration_plan",
}


def __getattr__(name: str):
    if name not in _MIGRATION_EXPORTS:
        raise AttributeError(name)
    return getattr(import_module("cascade.board.backlog_migration"), name)

__all__ = [
    "BoardError",
    "BoardIndex",
    "Column",
    "CycleError",
    "GitError",
    "NotFound",
    "SchemaError",
    "StatusMismatch",
    "WorkDoc",
    "WorkId",
    "WorkMeta",
    "WorkStatus",
    "WorkTier",
    "BacklogMigrationApplyError",
    "BacklogMigrationPlan",
    "BacklogMigrationValidationError",
    "allocate_hierarchical_id",
    "apply_backlog_migration",
    "build_backlog_migration_plan",
    "allocate_id",
    "column_dir",
    "column_for_status",
    "format_work_id",
    "legal_folder",
    "list_board",
    "move_doc",
    "parse_doc",
    "parse_work_id",
    "pin_parent",
    "read_doc",
    "reset_id_reservations",
    "status_for_column",
    "validate_doc",
    "write_doc",
]
