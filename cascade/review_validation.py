"""Bounded repository checks for review publication, without shell evaluation."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import tomllib
import time
from dataclasses import dataclass

from cascade.task.incident_budget import (
    IncidentOperationDecision,
    IncidentOperationPermit,
    POLICY_VERSION,
    read_incident_budget,
    reserve_incident_operation,
    settle_incident_operation,
)


class ReviewValidationAdmissionError(RuntimeError):
    """The cumulative incident gate did not authorize a validator spawn."""


@dataclass(frozen=True, slots=True)
class ReviewValidationOperation:
    """Canonical identities and the durable permit for one validator process."""

    incident_id: str
    claim_id: str
    operation_id: str
    root: Path
    permit: IncidentOperationPermit
    environment_revision: dict[str, str]


def review_validation_environment() -> dict[str, str]:
    """Return material local runtime identity; excludes clocks and reports."""

    return {
        "implementation": platform.python_implementation(),
        "python": platform.python_version(),
        "executable": os.path.realpath(sys.executable),
    }


def reserve_review_validation(
    incident_id: str,
    claim_id: str,
    operation_id: str,
    *,
    root: Path,
    timeout: float,
    environment_revision: dict[str, str],
) -> tuple[IncidentOperationDecision, ReviewValidationOperation | None]:
    """Reserve the validator's worst-case runtime before any process spawn."""

    decision = reserve_incident_operation(
        incident_id,
        operation_id,
        "review_validator",
        {"tool_attempts": 1, "process_seconds": max(1, int(timeout + 0.999999))},
        claim_id,
        POLICY_VERSION,
        root=root,
    )
    operation = (
        ReviewValidationOperation(
            incident_id,
            claim_id,
            operation_id,
            root,
            decision.permit,
            dict(environment_revision),
        )
        if decision.admitted and decision.permit is not None
        else None
    )
    return decision, operation


def settle_unused_review_validation(operation: ReviewValidationOperation) -> None:
    """Release a reservation when a later local precondition prevents spawn."""

    settle_incident_operation(
        operation.incident_id,
        operation.operation_id,
        {"outcome": "success", "quality": "known", "usage": {}},
        root=operation.root,
    )


def review_validation_command(root: Path) -> tuple[str, ...]:
    """Use the repository's review gate, preserving the task/full-suite default."""
    from cascade.validation_command import validation_command

    path = root / 'cascade.toml'
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    command = config.get('validation', {}).get('review_command')
    if command is None:
        return validation_command(root)
    if not isinstance(command, list) or not command or not all(
        isinstance(arg, str) and arg.strip() for arg in command
    ):
        raise ValueError('validation.review_command must be a nonempty argv array')
    return tuple(command)


def review_validation_timeout(root: Path) -> float:
    path = root / 'cascade.toml'
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    value = config.get('validation', {}).get('review_timeout_seconds', 300)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 3600:
        raise ValueError('validation.review_timeout_seconds must be between 1 and 3600')
    return float(value)


def run_review_validation(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout: float,
    operation: ReviewValidationOperation | None = None,
) -> subprocess.CompletedProcess:
    # Files avoid unbounded in-memory capture; report only bounded diagnostic tails.
    def tail(handle):
        handle.seek(max(0, handle.tell() - 65536))
        return handle.read(65536).decode('utf-8', errors='replace')

    if operation is not None:
        budget = read_incident_budget(operation.incident_id, root=operation.root)
        receipt = (budget or {}).get("operations", {}).get(operation.operation_id)
        if (
            not isinstance(receipt, dict)
            or receipt.get("state") != "reserved"
            or receipt.get("receipt_id") != operation.permit.receipt_id
            or receipt.get("claim_id") != operation.claim_id
            or (budget or {}).get("policy", {}).get("version")
            != operation.permit.policy_version
            or review_validation_environment() != operation.environment_revision
        ):
            raise ReviewValidationAdmissionError(
                "validator operation has no live cumulative-budget permit"
            )

    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        except BaseException:
            if operation is not None:
                settle_incident_operation(
                    operation.incident_id,
                    operation.operation_id,
                    {
                        "outcome": "error",
                        "quality": "known",
                        "usage": {"tool_attempts": 1},
                    },
                    root=operation.root,
                )
            raise
        try:
            process.wait(timeout=timeout)
        except BaseException as error:
            # Kill the whole check group, including children that outlive the
            # initial command. Never leave validators mutating a preserved checkout.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if isinstance(error, subprocess.TimeoutExpired):
                error.output, error.stderr = tail(stdout), tail(stderr)
            if operation is not None:
                elapsed = max(0, int(time.monotonic() - started + 0.999999))
                settle_incident_operation(
                    operation.incident_id,
                    operation.operation_id,
                    {
                        "outcome": (
                            "timeout"
                            if isinstance(error, subprocess.TimeoutExpired)
                            else "interrupted"
                        ),
                        "failure_class": (
                            "transient"
                            if isinstance(error, subprocess.TimeoutExpired)
                            else None
                        ),
                        "quality": (
                            "known"
                            if isinstance(error, subprocess.TimeoutExpired)
                            else "unavailable"
                        ),
                        "usage": {"tool_attempts": 1, "process_seconds": elapsed},
                    },
                    root=operation.root,
                )
            raise
        result = subprocess.CompletedProcess(
            command, process.returncode, tail(stdout), tail(stderr)
        )
        if operation is not None:
            elapsed = max(0, int(time.monotonic() - started + 0.999999))
            environment_changed = (
                review_validation_environment() != operation.environment_revision
            )
            settle_incident_operation(
                operation.incident_id,
                operation.operation_id,
                {
                    "outcome": (
                        "success"
                        if process.returncode == 0 and not environment_changed
                        else "error"
                    ),
                    "failure_class": (
                        None
                        if process.returncode == 0 and not environment_changed
                        else "deterministic"
                    ),
                    "quality": "known",
                    "usage": {"tool_attempts": 1, "process_seconds": elapsed},
                },
                root=operation.root,
            )
            if environment_changed:
                raise ReviewValidationAdmissionError(
                    "validator environment changed during repository checks"
                )
        return result


def validate_publication_board(worktree: Path) -> None:
    """Validate physical documents being published, without split-root redirection.

    Normal board scans intentionally skip malformed drafts; publication must
    reject those and duplicate IDs rather than hide them from the live board.
    """
    from cascade.board.parse import parse_doc
    from cascade.board.errors import SchemaError
    seen = {}
    for tier in ('epics', 'features', 'tasks'):
        for column in ('1_backlog', '2_active', '3_completed', '4_cancelled'):
            for path in sorted((worktree / 'docs' / tier / column).glob('*.md')):
                if path.is_symlink():
                    raise SchemaError(f'publication board symlink: {path}')
                doc = parse_doc(path)
                if doc.meta.id in seen:
                    raise SchemaError(f'duplicate id {doc.meta.id} at {path} and {seen[doc.meta.id]}')
                seen[doc.meta.id] = path
