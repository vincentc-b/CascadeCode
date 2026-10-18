"""Board exceptions. Every board failure inherits BoardError."""


class BoardError(Exception):
    """Base error for parse, validate, and git plan-store failures."""


class SchemaError(BoardError):
    """Frontmatter, heading, path, or id contract violation."""


class NotFound(BoardError):
    """No work doc with this id is on the board."""

    def __init__(self, work_id: str) -> None:
        self.work_id = work_id
        super().__init__(f"not found: {work_id}")


class CycleError(BoardError):
    """depends_on or parent links form a cycle."""


class StatusMismatch(BoardError):
    """status is not legal in the file's column folder."""


class GitError(BoardError):
    """A git command failed after the file was written, or a revision could not be read."""
