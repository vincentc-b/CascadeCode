"""Workspace CLI and init failures."""

from cascade.board.errors import NotFound


class WorkspaceError(Exception):
    """init/up preconditions failed; no agents were started."""


class MutationOwnerError(WorkspaceError, NotFound):
    """A lifecycle write could not prove one exact document owner."""

    def __init__(self, work_id: str, reason: str, action: str) -> None:
        self.work_id = work_id
        self.reason = reason
        self.action = action
        super().__init__(f"cannot mutate {work_id}: {reason}; {action}")
