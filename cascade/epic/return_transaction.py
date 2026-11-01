"""Durable, replay-safe steps for returning an active Epic to backlog.

This module deliberately owns only the mutation journal.  Admission, locked
eligibility rechecks, recovery orchestration, and audit emission are separate
concerns.  Keeping the boundaries explicit makes a crash between any two
filesystem operations observable rather than guessing from the board layout.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class TransitionStep(str, Enum):
    """Ordered durable boundaries of an active-to-backlog transition."""

    INTENT = "intent"
    ARTIFACTS_PRESERVED = "artifacts_preserved"
    SOURCE_BRIEF_RESTORED = "source_brief_restored"
    ACTIVE_POINTER_REMOVED = "active_pointer_removed"
    STALE_RUN_INVALIDATED = "stale_run_invalidated"
    COMPLETE = "complete"


_STEPS = tuple(TransitionStep)


class TransitionUnsafe(RuntimeError):
    """The repository is not proven safe for a lifecycle mutation."""


@dataclass(frozen=True, slots=True)
class TransitionJournal:
    """The persisted identity and completed boundaries of one transition."""

    epic_id: str
    transition_id: str
    request_id: str
    completed_steps: tuple[TransitionStep, ...]

    @property
    def complete(self) -> bool:
        return TransitionStep.COMPLETE in self.completed_steps

    def has(self, step: TransitionStep) -> bool:
        return step in self.completed_steps


Mutation = Callable[[], None]
SafetyCheck = Callable[[], None]


class ActiveToBacklogTransaction:
    """Execute durable mutations once, recording each completed boundary.

    The journal is intentionally not deleted at completion: it is the stable
    idempotency record used by retry and the later recovery/audit layers.
    Mutation callables must themselves be idempotent, because a process can
    die after an external boundary but before its following journal write.
    """

    def __init__(self, *, root: Path, epic_id: str, request_id: str) -> None:
        if not epic_id or not request_id:
            raise ValueError("epic_id and request_id are required")
        self.root = Path(root).resolve()
        self.epic_id = epic_id
        self.request_id = request_id

    @property
    def journal_path(self) -> Path:
        # IDs are board-generated, but retain a hashed filename boundary so a
        # malformed externally supplied value can never escape this directory.
        key = hashlib.sha256(self.epic_id.encode("utf-8")).hexdigest()
        return self.root / ".cascade" / "epic-transitions" / f"{key}.json"

    def execute(
        self,
        *,
        assert_safe: SafetyCheck,
        preserve_artifacts: Mutation,
        restore_source_brief: Mutation,
        remove_active_pointer: Mutation,
        invalidate_stale_run: Mutation,
    ) -> TransitionJournal:
        """Run or resume the transaction, refusing before intent if unsafe."""

        journal = self.load()
        if journal is not None and journal.complete:
            return journal

        # Git safety must be established before writing even the intent marker:
        # an unsafe refusal is guaranteed to leave no lifecycle mutation.
        assert_safe()
        if journal is None:
            journal = TransitionJournal(
                epic_id=self.epic_id,
                transition_id=_transition_id(self.epic_id, self.request_id),
                request_id=self.request_id,
                completed_steps=(TransitionStep.INTENT,),
            )
            self._save(journal)

        for step, mutation in (
            (TransitionStep.ARTIFACTS_PRESERVED, preserve_artifacts),
            (TransitionStep.SOURCE_BRIEF_RESTORED, restore_source_brief),
            (TransitionStep.ACTIVE_POINTER_REMOVED, remove_active_pointer),
            (TransitionStep.STALE_RUN_INVALIDATED, invalidate_stale_run),
        ):
            if not journal.has(step):
                mutation()
                journal = self._mark(journal, step)

        if not journal.complete:
            journal = self._mark(journal, TransitionStep.COMPLETE)
        return journal

    def load(self) -> TransitionJournal | None:
        """Read a journal, rejecting corrupt or mismatched durable state."""

        if not self.journal_path.exists():
            return None
        try:
            raw = json.loads(self.journal_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("not an object")
            steps = tuple(TransitionStep(value) for value in raw["completed_steps"])
            journal = TransitionJournal(
                epic_id=str(raw["epic_id"]),
                transition_id=str(raw["transition_id"]),
                request_id=str(raw["request_id"]),
                completed_steps=steps,
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise TransitionUnsafe("transition journal is unreadable") from exc
        if journal.epic_id != self.epic_id:
            raise TransitionUnsafe("transition journal belongs to another Epic")
        _validate_steps(journal.completed_steps)
        if journal.request_id != self.request_id:
            # The first durable intent is the Epic's idempotency identity. A
            # racing/repeated command with another transport request ID must
            # converge on it, including after it has completed.
            return journal
        return journal

    def _mark(self, journal: TransitionJournal, step: TransitionStep) -> TransitionJournal:
        if step in journal.completed_steps:
            return journal
        marked = TransitionJournal(
            epic_id=journal.epic_id,
            transition_id=journal.transition_id,
            request_id=journal.request_id,
            completed_steps=(*journal.completed_steps, step),
        )
        self._save(marked)
        return marked

    def _save(self, journal: TransitionJournal) -> None:
        _validate_steps(journal.completed_steps)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            dir=self.journal_path.parent, prefix=f".{self.journal_path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        **asdict(journal),
                        "completed_steps": [step.value for step in journal.completed_steps],
                    },
                    handle,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.journal_path)
            # fsync the containing directory so the rename itself survives a
            # crash on filesystems where that distinction matters.
            directory_fd = os.open(self.journal_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _transition_id(epic_id: str, request_id: str) -> str:
    return hashlib.sha256(f"active-to-backlog:{epic_id}:{request_id}".encode("utf-8")).hexdigest()


def _validate_steps(steps: tuple[TransitionStep, ...]) -> None:
    if not steps or steps[0] is not TransitionStep.INTENT:
        raise TransitionUnsafe("transition journal has no intent marker")
    if len(set(steps)) != len(steps):
        raise TransitionUnsafe("transition journal repeats a step")
    expected = _STEPS[: len(steps)]
    if steps != expected:
        raise TransitionUnsafe("transition journal has unordered steps")


@dataclass(frozen=True, slots=True)
class ActiveToBacklogFiles:
    """Explicit owned paths for the concrete filesystem mutation.

    Callers must supply paths in an integration checkout, never a trunk path.
    Keeping these paths explicit avoids inferring deletion targets from mutable
    board metadata during a replay.
    """

    source_brief: Path
    backlog_brief: Path
    active_pointer: Path
    preserved_artifact: Path
    stale_run_marker: Path


def execute_file_transaction(
    *, root: Path, epic_id: str, request_id: str, files: ActiveToBacklogFiles
) -> TransitionJournal:
    """Perform the standard owned-file mutation in a safe integration checkout.

    This is the concrete capability intended for the command/recovery layers.
    It is deliberately not wired to the command yet: the next slice supplies
    authoritative path discovery and recovery/audit ownership.
    """

    repo = Path(root).resolve()
    owned = tuple(_owned_path(repo, path) for path in asdict(files).values())
    source, backlog, pointer, artifact, stale_marker = owned

    def preserve() -> None:
        source_bytes = _read_required(source, "source brief")
        if artifact.exists():
            if artifact.read_bytes() != source_bytes:
                raise TransitionUnsafe("preserved artifact conflicts with source brief")
            return
        _durable_write(artifact, source_bytes)

    def restore() -> None:
        source_bytes = _read_required(source, "source brief")
        if backlog.exists() and backlog.read_bytes() != source_bytes:
            raise TransitionUnsafe("backlog brief conflicts with source brief")
        if not backlog.exists():
            _durable_write(backlog, source_bytes)

    def remove_pointer() -> None:
        # The source and destination can be identical only in a malformed plan;
        # never allow that to turn a successful restoration into a deletion.
        if pointer == backlog:
            raise TransitionUnsafe("active pointer aliases restored backlog brief")
        pointer.unlink(missing_ok=True)

    def invalidate() -> None:
        _durable_write(stale_marker, b"invalidated\n")

    return ActiveToBacklogTransaction(root=repo, epic_id=epic_id, request_id=request_id).execute(
        assert_safe=lambda: _assert_safe_integration_checkout(repo),
        preserve_artifacts=preserve,
        restore_source_brief=restore,
        remove_active_pointer=remove_pointer,
        invalidate_stale_run=invalidate,
    )


def _owned_path(root: Path, path: object) -> Path:
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise TransitionUnsafe("transition path is outside the integration checkout") from exc
    return candidate


def _read_required(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise TransitionUnsafe(f"{label} is unreadable") from exc


def _durable_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _assert_safe_integration_checkout(root: Path) -> None:
    """Refuse dirty, non-Git, or operator-trunk mutation targets."""

    from cascade.workspace.integration_worktree import locate_trunk

    if root == locate_trunk(root).resolve():
        raise TransitionUnsafe("refusing to mutate operator trunk")
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise TransitionUnsafe("integration checkout is not a usable Git repository")
    if result.stdout.strip():
        raise TransitionUnsafe("integration checkout has uncommitted changes")
