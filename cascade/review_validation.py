"""Bounded repository checks for review publication, without shell evaluation."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Iterator, Literal, Mapping

from cascade.board.types import BoardIndex
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
class ReviewValidationProfile:
    """Repository-owner-approved, finite validator policy."""

    profile_id: str
    command: tuple[str, ...]
    coverage_class: str
    policy_owner: str
    approval_version: str
    timeout_seconds: float
    attempt_budget: int = 1

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.profile_id,
                self.coverage_class,
                self.policy_owner,
                self.approval_version,
            )
        ):
            raise ValueError("validation profile identity and approval are required")
        if self.command and (
            not isinstance(self.command[0], str)
            or not self.command[0].strip()
            or not all(isinstance(value, str) for value in self.command)
        ):
            raise ValueError("validation profile command must be an argv tuple")
        if (
            isinstance(self.timeout_seconds, bool)
            or not 1 <= self.timeout_seconds <= 3600
            or isinstance(self.attempt_budget, bool)
            or self.attempt_budget != 1
        ):
            raise ValueError("validation profile requires one finite bounded attempt")


@dataclass(frozen=True, slots=True)
class ReviewValidationOperation:
    """Canonical identities and the durable permit for one validator process."""

    incident_id: str
    claim_id: str
    operation_id: str
    root: Path
    permit: IncidentOperationPermit
    environment_revision: dict[str, str]
    profile: ReviewValidationProfile
    material: dict[str, object]


@dataclass(frozen=True, slots=True)
class ExactValidationMaterial:
    """JSON-safe identity consumed by admission, execution and publication."""

    identity: dict[str, object]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ExactMaterialInspection:
    """Pre-spawn feasibility and physical-board result for one candidate."""

    material: ExactValidationMaterial | None = None
    refusal: MergeCandidateRefusal | None = None
    history_refusal: TerminalHistoryRefusal | None = None
    reason: str | None = None
    owner_action: str = ""


ReceiptMatch = Literal[
    "matching_green", "same_material_fenced", "admission_required", "unavailable"
]


@dataclass(frozen=True, slots=True)
class MergeCandidateRefusal:
    """Typed fail-closed result when an exact merge candidate cannot exist."""

    kind: Literal["missing", "unknown", "conflict"]
    source_sha: str | None
    target_sha: str | None
    message: str
    owner_action: str
    conflicted_paths: tuple[str, ...] = ()
    diagnostics: str = ""


@dataclass(frozen=True, slots=True)
class ExactMergeCandidate:
    """Identity and private checkout for one exact source/target merge result."""

    source_sha: str
    target_sha: str
    result_commit: str
    result_tree: str
    checkout: Path


@dataclass(frozen=True, slots=True)
class TerminalHistoryRefusal:
    """Actionable refusal for one exact candidate/history comparison."""

    kind: Literal[
        "malformed",
        "duplicate",
        "hierarchy",
        "history",
        "evidence_unavailable",
        "target_changed",
    ]
    affected_ids: tuple[str, ...]
    paths: tuple[str, ...]
    source_revision: str
    target_revision: str
    result_revision: str
    accepted_revision: str
    canonical_owners: tuple[tuple[str, str], ...]
    reason: str
    owner_action: str


@dataclass(frozen=True, slots=True)
class AcceptedTerminalHistoryProof:
    """Fresh proof that a candidate retains one pinned accepted board history."""

    source_revision: str
    target_revision: str
    result_revision: str
    result_tree: str
    accepted_revision: str
    retained_ids: tuple[str, ...]
    terminal_ids: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ExactCandidateValidation:
    """Bounded validation evidence tied to exact candidate and runtime bytes."""

    outcome: Literal[
        "passed", "product_assertion", "fixture_environment", "timeout", "unavailable"
    ]
    stage: Literal["materialization", "board", "process", "checks"]
    candidate: ExactMergeCandidate | None
    refusal: MergeCandidateRefusal | None
    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    dependency_revision: str | None
    environment_revision: Mapping[str, str]
    owner_action: str
    reason: str | None = None


def review_validation_environment() -> dict[str, str]:
    """Return material local runtime identity; excludes clocks and reports."""

    executable = Path(sys.executable).resolve()
    try:
        executable_digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    except OSError:
        executable_digest = "unavailable"
    return {
        "implementation": platform.python_implementation(),
        "python": platform.python_version(),
        "executable": str(executable),
        "executable_sha256": executable_digest,
    }


def exact_material_fingerprint(identity: Mapping[str, object]) -> str:
    """Hash only canonical material fields; clocks and diagnostics are excluded."""

    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def exact_review_identity(
    action_id: str,
    review_id: str,
    source_ref: str,
    target_ref: str,
    source_sha: str,
    target_sha: str,
    request: Mapping[str, object],
) -> dict[str, object] | None:
    """Canonicalize the durable review route and observed generation."""

    review_url = request.get("review_url")
    values = (action_id, review_id, review_url, source_ref, target_ref, source_sha, target_sha)
    if not all(isinstance(value, str) and value for value in values):
        return None
    generation = exact_material_fingerprint(
        {
            "review_id": review_id,
            "review_url": review_url,
            "source_ref": source_ref,
            "target_ref": target_ref,
            "observed_source_sha": source_sha,
            "observed_target_sha": target_sha,
        }
    )
    return {
        "action_id": action_id,
        "review_id": review_id,
        "review_url": review_url,
        "source_ref": source_ref,
        "target_ref": target_ref,
        "generation": generation,
    }


def match_review_validation_receipt(
    incident_id: str, material: ExactValidationMaterial, *, root: Path
) -> tuple[ReceiptMatch, dict[str, object] | None]:
    """Read the existing incident operations and compare complete material."""

    budget = read_incident_budget(incident_id, root=root)
    if budget is None:
        return "unavailable", None
    operations = budget.get("operations")
    if not isinstance(operations, Mapping):
        return "unavailable", None
    saw_legacy = False
    for value in operations.values():
        if not isinstance(value, Mapping) or value.get("kind") != "review_validator":
            continue
        exact = value.get("exact_validation_material")
        fingerprint = value.get("material_fingerprint")
        if not isinstance(exact, Mapping) or not isinstance(fingerprint, str):
            saw_legacy = True
            continue
        if fingerprint != material.fingerprint or exact != material.identity:
            continue
        if value.get("state") != "settled":
            return "unavailable", dict(value)
        observation = value.get("observation")
        if not isinstance(observation, Mapping):
            return "unavailable", dict(value)
        if (
            observation.get("outcome") == "success"
            and observation.get("validation_status") == "passed"
        ):
            return "matching_green", dict(value)
        if observation.get("failure_class") == "deterministic":
            return "same_material_fenced", dict(value)
    return ("unavailable", None) if saw_legacy else ("admission_required", None)


def reserve_review_validation(
    incident_id: str,
    claim_id: str,
    operation_id: str,
    *,
    root: Path,
    timeout: float,
    environment_revision: dict[str, str],
    parent_operation_id: str | None = None,
    profile: ReviewValidationProfile | None = None,
    material: ExactValidationMaterial | None = None,
) -> tuple[IncidentOperationDecision, ReviewValidationOperation | None]:
    """Reserve the validator's worst-case runtime before any process spawn."""

    selected = profile or replace(
        approved_review_validation_profile(root), command=(), timeout_seconds=timeout
    )
    if timeout != selected.timeout_seconds:
        raise ReviewValidationAdmissionError(
            "validator timeout does not match its approved profile"
        )
    material_identity = dict(material.identity) if material is not None else {}
    decision = reserve_incident_operation(
        incident_id,
        operation_id,
        "review_validator",
        {
            "tool_attempts": selected.attempt_budget,
            "process_seconds": max(1, int(timeout + 0.999999)),
        },
        claim_id,
        POLICY_VERSION,
        root=root,
        attributes={
            "parent_operation_id": parent_operation_id,
            "validation_profile": {
                "id": selected.profile_id,
                "coverage_class": selected.coverage_class,
                "policy_owner": selected.policy_owner,
                "approval_version": selected.approval_version,
                "command": list(selected.command),
                "timeout_seconds": selected.timeout_seconds,
                "attempt_budget": selected.attempt_budget,
            },
            **(
                {
                    "exact_validation_material": material_identity,
                    "material_fingerprint": material.fingerprint,
                }
                if material is not None
                else {}
            ),
        },
    )
    operation = (
        ReviewValidationOperation(
            incident_id,
            claim_id,
            operation_id,
            root,
            decision.permit,
            dict(environment_revision),
            selected,
            material_identity,
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
        {
            "outcome": "success",
            "validation_status": "unused",
            "quality": "known",
            "usage": {},
        },
        root=operation.root,
    )


def settle_interrupted_review_validation(operation: ReviewValidationOperation) -> None:
    """Retain the full reservation when execution began but settlement is unknown."""

    settle_incident_operation(
        operation.incident_id,
        operation.operation_id,
        {
            "outcome": "interrupted",
            "validation_status": "unknown",
            "quality": "unavailable",
            "usage": {},
        },
        root=operation.root,
    )


def review_validation_command(root: Path) -> tuple[str, ...]:
    """Use the repository's review gate, preserving the task/full-suite default."""
    from cascade.validation_command import validation_command

    path = root / "cascade.toml"
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    command = config.get("validation", {}).get("review_command")
    if command is None:
        return validation_command(root)
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(arg, str) and arg.strip() for arg in command)
    ):
        raise ValueError("validation.review_command must be a nonempty argv array")
    return tuple(command)


def review_validation_timeout(root: Path) -> float:
    path = root / "cascade.toml"
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    value = config.get("validation", {}).get("review_timeout_seconds", 300)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 1 <= value <= 3600
    ):
        raise ValueError("validation.review_timeout_seconds must be between 1 and 3600")
    return float(value)


def approved_review_validation_profile(
    root: Path, *, command: tuple[str, ...] | None = None
) -> ReviewValidationProfile:
    """Resolve the one repository-approved review profile without executing it."""

    path = root / "cascade.toml"
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    validation = config.get("validation", {})
    identity = validation.get("review_profile_id", "cascade.review-publication")
    owner = validation.get("review_policy_owner", "repository_operator")
    approval = validation.get("review_approval_version", "1")
    coverage = validation.get("review_coverage_class", "review_publication")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (identity, owner, approval, coverage)
    ):
        raise ValueError("review validation profile identity and approval are required")
    return ReviewValidationProfile(
        identity,
        command if command is not None else review_validation_command(root),
        coverage,
        owner,
        approval,
        review_validation_timeout(root),
    )


def preflight_review_validation(
    profile: ReviewValidationProfile,
    *,
    cwd: Path,
    command: tuple[str, ...] | None = None,
) -> None:
    """Refuse an infeasible profile before consuming a validator process."""

    if not cwd.is_dir():
        raise ReviewValidationAdmissionError(
            "validator working directory is unavailable"
        )
    selected_command = profile.command or command
    if not selected_command:
        raise ReviewValidationAdmissionError("validator command is unavailable")
    executable = selected_command[0]
    resolved = (
        Path(executable).is_file()
        if os.sep in executable
        else shutil.which(executable) is not None
    )
    if not resolved:
        raise ReviewValidationAdmissionError(
            "approved validator executable is unavailable"
        )


def run_review_validation(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout: float,
    operation: ReviewValidationOperation | None = None,
    env: Mapping[str, str] | None = None,
    defer_settlement: bool = False,
) -> subprocess.CompletedProcess:
    # Files avoid unbounded in-memory capture; report only bounded diagnostic tails.
    def tail(handle):
        handle.seek(max(0, handle.tell() - 65536))
        return handle.read(65536).decode("utf-8", errors="replace")

    if operation is not None:
        if (
            operation.profile.command and command != operation.profile.command
        ) or timeout != operation.profile.timeout_seconds:
            raise ReviewValidationAdmissionError(
                "validator command or timeout differs from its approved profile"
            )
        preflight_review_validation(operation.profile, cwd=cwd, command=command)
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
            or (
                operation.material
                and (
                    receipt.get("attributes", {}).get("exact_validation_material")
                    != operation.material
                    or receipt.get("material_fingerprint")
                    != exact_material_fingerprint(operation.material)
                )
            )
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
                env=None if env is None else dict(env),
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
        if operation is not None and not defer_settlement:
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


@contextmanager
def materialize_exact_merge_candidate(
    repository: Path,
    source_sha: str | None,
    target_sha: str | None,
    *,
    prefer_source_paths: tuple[str, ...] = (),
) -> Iterator[ExactMergeCandidate | MergeCandidateRefusal]:
    """Create an owned checkout and resolve an exact pair with Git's merge path.

    The source repository is only read.  The private clone, index, refs and
    object store are removed together when the caller leaves the context.
    """

    source = source_sha.strip() if isinstance(source_sha, str) else ""
    target = target_sha.strip() if isinstance(target_sha, str) else ""
    if not source or not target:
        yield MergeCandidateRefusal(
            "missing", source or None, target or None,
            "Both freshly observed source and target SHAs are required.",
            "Refresh both review heads before requesting validation.",
        )
        return
    if not all(re.fullmatch(r"[0-9a-fA-F]{40,64}", value) for value in (source, target)):
        yield MergeCandidateRefusal(
            "unknown", source, target,
            "Source and target must be full observed commit SHAs, not symbolic or abbreviated revisions.",
            "Refresh both review heads and retain their complete commit identities.",
        )
        return

    repository = Path(repository).resolve()
    with tempfile.TemporaryDirectory(prefix="cascade-merge-candidate-") as owned:
        checkout = Path(owned) / "checkout"
        clone = _candidate_git(
            None, "clone", "--quiet", "--no-checkout", "--no-local",
            str(repository), str(checkout),
        )
        if clone.returncode:
            yield MergeCandidateRefusal(
                "unknown", source, target,
                "The repository could not provide an isolated candidate checkout.",
                "Restore local Git object access, then refresh the exact review heads.",
                diagnostics=_sanitized_tail(clone.stderr, repository, checkout),
            )
            return

        resolved: list[str] = []
        for label, revision in (("source", source), ("target", target)):
            probe = _candidate_git(checkout, "rev-parse", "--verify", f"{revision}^{{commit}}")
            value = probe.stdout.strip()
            if probe.returncode or not re.fullmatch(r"[0-9a-f]{40,64}", value):
                yield MergeCandidateRefusal(
                    "unknown", source, target,
                    f"The observed {label} SHA is not an available commit.",
                    f"Fetch and re-observe the {label} head before validation.",
                    diagnostics=_sanitized_tail(probe.stderr, repository, checkout),
                )
                return
            resolved.append(value)
        exact_source, exact_target = resolved

        checkout_result = _candidate_git(checkout, "checkout", "--quiet", "--detach", exact_target)
        if checkout_result.returncode:
            yield MergeCandidateRefusal(
                "unknown", exact_source, exact_target,
                "Git could not check out the observed target commit.",
                "Repair local Git object access and retry the same exact pair.",
                diagnostics=_sanitized_tail(checkout_result.stderr, repository, checkout),
            )
            return

        merge = _candidate_git(checkout, "merge", "--no-commit", "--no-ff", exact_source)
        if merge.returncode:
            conflicts = tuple(
                line for line in _candidate_git(
                    checkout, "diff", "--name-only", "--diff-filter=U"
                ).stdout.splitlines() if line
            )
            safe_preference = bool(prefer_source_paths) and all(
                path
                and not Path(path).is_absolute()
                and ".." not in Path(path).parts
                for path in prefer_source_paths
            )
            if safe_preference and set(conflicts) == set(prefer_source_paths):
                resolved_conflict = _candidate_git(
                    checkout, "checkout", exact_source, "--", *prefer_source_paths
                )
                remaining = tuple(
                    line for line in _candidate_git(
                        checkout, "diff", "--name-only", "--diff-filter=U"
                    ).stdout.splitlines() if line
                )
                if resolved_conflict.returncode == 0 and not remaining:
                    merge = resolved_conflict
            if merge.returncode == 0:
                conflicts = ()
            else:
                yield MergeCandidateRefusal(
                    "conflict" if conflicts else "unknown", exact_source, exact_target,
                    (
                        "The exact source/target pair has merge conflicts."
                        if conflicts else "Git could not resolve the exact source/target pair."
                    ),
                    (
                        "Resolve the listed product conflicts on the source branch and refresh both heads."
                        if conflicts else "Inspect the bounded Git diagnostic and restore a mergeable exact pair."
                    ),
                    conflicts,
                    _sanitized_tail(f"{merge.stdout}\n{merge.stderr}", repository, checkout),
                )
                return

        merge_head = checkout / ".git" / "MERGE_HEAD"
        if merge_head.is_file():
            tree = _candidate_git(checkout, "write-tree").stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{40,64}", tree):
                yield MergeCandidateRefusal(
                    "unknown", exact_source, exact_target,
                    "Git resolved the pair but did not produce a valid tree identity.",
                    "Inspect local Git integrity before retrying the exact pair.",
                )
                return
            commit_env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Cascade candidate",
                "GIT_AUTHOR_EMAIL": "candidate@cascade.invalid",
                "GIT_AUTHOR_DATE": "@0 +0000",
                "GIT_COMMITTER_NAME": "Cascade candidate",
                "GIT_COMMITTER_EMAIL": "candidate@cascade.invalid",
                "GIT_COMMITTER_DATE": "@0 +0000",
            }
            commit = _candidate_git(
                checkout, "commit-tree", tree, "-p", exact_target, "-p", exact_source,
                input_text="Cascade exact merge candidate\n", env=commit_env,
            )
            result_commit = commit.stdout.strip()
            if commit.returncode or not result_commit:
                yield MergeCandidateRefusal(
                    "unknown", exact_source, exact_target,
                    "Git resolved the tree but could not identify its prospective commit.",
                    "Inspect local Git integrity before retrying the exact pair.",
                    diagnostics=_sanitized_tail(commit.stderr, repository, checkout),
                )
                return
            reset = _candidate_git(checkout, "reset", "--quiet", "--hard", result_commit)
            if reset.returncode:
                yield MergeCandidateRefusal(
                    "unknown", exact_source, exact_target,
                    "The prospective result could not be checked out for validation.",
                    "Inspect local Git integrity before retrying the exact pair.",
                    diagnostics=_sanitized_tail(reset.stderr, repository, checkout),
                )
                return
        else:
            # Source already contributes no new tree content to the target.
            result_commit = exact_target
            tree = _candidate_git(checkout, "rev-parse", f"{result_commit}^{{tree}}").stdout.strip()

        effective_policy = repository / "cascade.toml"
        if effective_policy.is_file() and not effective_policy.is_symlink():
            candidate_policy = checkout / "cascade.toml"
            if candidate_policy.is_symlink():
                candidate_policy.unlink()
            shutil.copyfile(effective_policy, candidate_policy)

        yield ExactMergeCandidate(
            exact_source, exact_target, result_commit, tree, checkout
        )


def _candidate_runtime_identity(candidate: ExactMergeCandidate) -> dict[str, object]:
    dependency_revision = _candidate_dependency_revision(candidate.checkout)
    return {
        **review_validation_environment(),
        "dependency_revision": dependency_revision,
        "import_roots": ["."],
        "source_tree": candidate.result_tree,
    }


def inspect_exact_validation_material(
    repository: Path,
    source_sha: str | None,
    target_sha: str | None,
    *,
    profile: ReviewValidationProfile,
    review_identity: Mapping[str, object],
    policy_version: int = POLICY_VERSION,
) -> ExactMaterialInspection:
    """Resolve feasibility, candidate bytes and board before budget reservation."""

    try:
        preflight_review_validation(profile, cwd=repository)
    except (OSError, ValueError, ReviewValidationAdmissionError) as exc:
        return ExactMaterialInspection(
            reason="validation_profile_infeasible",
            owner_action=f"Restore the approved validation profile ({type(exc).__name__}).",
        )
    with materialize_exact_merge_candidate(repository, source_sha, target_sha) as result:
        if isinstance(result, MergeCandidateRefusal):
            return ExactMaterialInspection(
                refusal=result,
                reason=f"candidate_{result.kind}",
                owner_action=result.owner_action,
            )
        from cascade.board.errors import BoardError

        try:
            validate_publication_board(result.checkout)
        except (BoardError, OSError, ValueError) as exc:
            return ExactMaterialInspection(
                reason="board_validation_failed",
                owner_action=(
                    f"Repair the candidate lifecycle documents ({type(exc).__name__}) "
                    "before requesting admission."
                ),
            )
        history = prove_accepted_terminal_history(
            repository, result, result.target_sha
        )
        if isinstance(history, TerminalHistoryRefusal):
            return ExactMaterialInspection(
                history_refusal=history,
                reason=f"board_history_{history.kind}",
                owner_action=history.owner_action,
            )
        unconfined = _unconfined_candidate_source(result.checkout)
        if unconfined is not None:
            return ExactMaterialInspection(
                reason="candidate_source_unconfined",
                owner_action=(
                    f"Replace candidate source/dependency symlink {unconfined} "
                    "with repository bytes before requesting admission."
                ),
            )
        identity: dict[str, object] = {
            "candidate": {
                "source_sha": result.source_sha,
                "target_sha": result.target_sha,
                "result_commit": result.result_commit,
                "result_tree": result.result_tree,
            },
            "review": dict(review_identity),
            "profile": {
                "id": profile.profile_id,
                "argv": list(profile.command),
                "coverage_class": profile.coverage_class,
                "policy_owner": profile.policy_owner,
                "approval_revision": profile.approval_version,
                "timeout_seconds": profile.timeout_seconds,
                "attempt_budget": profile.attempt_budget,
            },
            "incident_policy_version": policy_version,
            "board_history": {
                "accepted_revision": history.accepted_revision,
                "retained_ids": list(history.retained_ids),
                "terminal_ids": list(history.terminal_ids),
                "fingerprint": history.fingerprint,
            },
            "runtime": _candidate_runtime_identity(result),
        }
        try:
            json.dumps(identity, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return ExactMaterialInspection(
                reason="candidate_identity_unavailable",
                owner_action="Restore JSON-safe review and validation identity evidence.",
            )
        return ExactMaterialInspection(
            material=ExactValidationMaterial(identity, exact_material_fingerprint(identity))
        )


def validate_exact_merge_candidate(
    repository: Path,
    source_sha: str | None,
    target_sha: str | None,
    *,
    command: tuple[str, ...],
    timeout: float,
    operation: ReviewValidationOperation | None = None,
) -> ExactCandidateValidation:
    """Materialize, board-scan and freshly validate one exact merge result."""

    if (
        not command
        or not isinstance(command[0], str)
        or not command[0]
        or not all(isinstance(arg, str) for arg in command)
        or isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 0 < timeout <= 3600
    ):
        return ExactCandidateValidation(
            "unavailable", "process", None, None, command, None, "", "", None,
            review_validation_environment(),
            "Restore one nonempty approved argv and a positive finite timeout of at most 3600 seconds.",
            "validation_profile_invalid",
        )

    validation_started = time.monotonic()

    def settle_completed(outcome: str, failure_class: str | None = None) -> None:
        if operation is None:
            return
        settle_incident_operation(
            operation.incident_id,
            operation.operation_id,
            {
                "outcome": outcome,
                "failure_class": failure_class,
                "validation_status": "passed" if outcome == "success" else "failed",
                "quality": "known",
                "usage": {
                    "tool_attempts": 1,
                    "process_seconds": max(
                        0, int(time.monotonic() - validation_started + 0.999999)
                    ),
                },
            },
            root=operation.root,
        )

    with materialize_exact_merge_candidate(repository, source_sha, target_sha) as materialized:
        if isinstance(materialized, MergeCandidateRefusal):
            return ExactCandidateValidation(
                "unavailable", "materialization", None, materialized, command, None, "",
                materialized.diagnostics, None, review_validation_environment(),
                materialized.owner_action,
            )
        candidate = materialized
        dependency_revision = _candidate_dependency_revision(candidate.checkout)
        runtime = _candidate_runtime_identity(candidate)
        from cascade.board.errors import BoardError

        try:
            validate_publication_board(candidate.checkout)
        except (BoardError, OSError, ValueError) as exc:
            return ExactCandidateValidation(
                "fixture_environment", "board", candidate, None, command, None, "", "",
                dependency_revision, runtime,
                f"Repair the candidate lifecycle documents ({type(exc).__name__}) before validation.",
            )

        history = prove_accepted_terminal_history(
            repository, candidate, candidate.target_sha
        )
        if isinstance(history, TerminalHistoryRefusal):
            return ExactCandidateValidation(
                "fixture_environment", "board", candidate, None, command, None, "", "",
                dependency_revision, runtime, history.owner_action,
                f"board_history_{history.kind}: {history.reason}",
            )

        unconfined = _unconfined_candidate_source(candidate.checkout)
        if unconfined is not None:
            return ExactCandidateValidation(
                "fixture_environment", "board", candidate, None, command, None, "", "",
                dependency_revision, runtime,
                f"Replace candidate source/dependency symlink {unconfined} with repository bytes before validation.",
            )

        _remove_candidate_bytecode(candidate.checkout)
        policy_revision = _optional_file_revision(candidate.checkout / "cascade.toml")
        if operation is not None:
            admitted_candidate = operation.material.get("candidate")
            admitted_runtime = operation.material.get("runtime")
            observed_candidate = {
                "source_sha": candidate.source_sha,
                "target_sha": candidate.target_sha,
                "result_commit": candidate.result_commit,
                "result_tree": candidate.result_tree,
            }
            if admitted_candidate != observed_candidate or admitted_runtime != runtime:
                return ExactCandidateValidation(
                    "unavailable", "checks", candidate, None, command, None, "", "",
                    dependency_revision, runtime,
                    "Refresh the changed exact candidate/runtime identity and seek bounded admission.",
                    "validation_material_changed",
                )
        with tempfile.TemporaryDirectory(prefix="cascade-candidate-pycache-") as pycache:
            env = {
                **os.environ,
                "PYTHONPATH": str(candidate.checkout),
                "PYTHONPYCACHEPREFIX": pycache,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONSAFEPATH": "1",
                "CASCADE_CANDIDATE_COMMIT": candidate.result_commit,
                "CASCADE_CANDIDATE_TREE": candidate.result_tree,
                "CASCADE_CANDIDATE_DEPENDENCY_SHA256": dependency_revision,
            }
            env.pop("PYTHONHOME", None)
            env.pop("PYTHONSTARTUP", None)
            env.pop("PYTHONINSPECT", None)
            try:
                result = run_review_validation(
                    command, cwd=candidate.checkout, timeout=timeout,
                    operation=operation, env=env, defer_settlement=True,
                )
            except subprocess.TimeoutExpired as exc:
                return ExactCandidateValidation(
                    "timeout", "process", candidate, None, command, 124,
                    _sanitized_tail(str(exc.output or ""), repository, candidate.checkout),
                    _sanitized_tail(str(exc.stderr or ""), repository, candidate.checkout),
                    dependency_revision, runtime,
                    "Inspect the bounded timeout diagnostic; narrow or repair the approved check before retrying.",
                )
            except (OSError, ValueError, ReviewValidationAdmissionError) as exc:
                return ExactCandidateValidation(
                    "unavailable", "process", candidate, None, command, None, "",
                    type(exc).__name__, dependency_revision, runtime,
                    "Restore the approved validation environment without weakening its argv or coverage.",
                )

        stdout = _sanitized_tail(result.stdout, repository, candidate.checkout)
        stderr = _sanitized_tail(result.stderr, repository, candidate.checkout)
        if (
            operation is not None
            and review_validation_environment() != operation.environment_revision
        ):
            settle_completed("error", "deterministic")
            return ExactCandidateValidation(
                "unavailable", "checks", candidate, None, command, result.returncode,
                stdout, stderr, dependency_revision, runtime,
                "Refresh the changed runtime identity and seek bounded admission.",
                "validation_material_changed",
            )
        current_head = _candidate_git(
            candidate.checkout, "rev-parse", "--verify", "HEAD^{commit}"
        ).stdout.strip()
        if current_head != candidate.result_commit:
            settle_completed("error", "deterministic")
            return ExactCandidateValidation(
                "fixture_environment", "checks", candidate, None, command,
                result.returncode, stdout, stderr, dependency_revision, runtime,
                "Discard the validator-created commit and rerun the unchanged exact pair.",
                "source_head_changed",
            )
        if (
            _optional_file_revision(candidate.checkout / "cascade.toml") != policy_revision
            or _candidate_dependency_revision(candidate.checkout) != dependency_revision
        ):
            settle_completed("error", "deterministic")
            return ExactCandidateValidation(
                "fixture_environment", "checks", candidate, None, command,
                result.returncode, stdout, stderr, dependency_revision, runtime,
                "Restore the approved profile/dependency bytes and rerun the exact pair.",
                "validation_policy_changed",
            )

        if result.returncode == 0:
            outcome = "passed"
            action = "Candidate evidence is complete for this exact pair."
        elif _is_product_assertion(f"{stdout}\n{stderr}"):
            outcome = "product_assertion"
            action = "Correct the product incompatibility; keep the approved assertion and coverage intact."
        else:
            outcome = "fixture_environment"
            action = "Repair the fixture or environment, then rerun the unchanged approved assertion coverage."
        settle_completed(
            "success" if outcome == "passed" else "error",
            "deterministic" if outcome != "passed" else None,
        )
        return ExactCandidateValidation(
            outcome, "checks", candidate, None, command, result.returncode, stdout, stderr,
            dependency_revision, runtime, action,
        )


def _candidate_git(
    cwd: Path | None,
    *args: str,
    input_text: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    try:
        return subprocess.run(
            command, cwd=cwd, input=input_text, capture_output=True, text=True,
            encoding="utf-8", timeout=30,
            env=None if env is None else dict(env),
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command, 124, str(exc.output or ""), str(exc.stderr or "Git operation timed out")
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, "", type(exc).__name__)


def _candidate_dependency_revision(checkout: Path) -> str:
    names = ["pyproject.toml", "poetry.lock", "uv.lock", "Pipfile.lock", "pdm.lock"]
    paths = [checkout / name for name in names]
    paths.extend(sorted(checkout.glob("requirements*.txt")))
    digest = hashlib.sha256()
    for path in paths:
        if path.is_file() and not path.is_symlink():
            digest.update(path.relative_to(checkout).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _optional_file_revision(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remove_candidate_bytecode(checkout: Path) -> None:
    for path in sorted(checkout.rglob("*.py[co]")):
        path.unlink(missing_ok=True)
    for path in sorted(checkout.rglob("__pycache__"), reverse=True):
        if path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)


def _unconfined_candidate_source(checkout: Path) -> str | None:
    manifests = {"pyproject.toml", "poetry.lock", "uv.lock", "Pipfile.lock", "pdm.lock"}
    for directory, directories, files in os.walk(checkout, followlinks=False):
        root = Path(directory)
        if root == checkout / ".git" or (checkout / ".git") in root.parents:
            directories[:] = []
            continue
        for name in directories:
            path = root / name
            if path.is_symlink():
                return path.relative_to(checkout).as_posix()
        for name in files:
            path = root / name
            if path.is_symlink() and (
                name.endswith(".py") or name in manifests or name.startswith("requirements")
            ):
                return path.relative_to(checkout).as_posix()
    return None


def _sanitized_tail(value: str, *private_roots: Path) -> str:
    text = value[-65536:]
    for root in private_roots:
        text = text.replace(str(Path(root).resolve()), "<checkout>")
    return "".join(char if char in "\n\t" or ord(char) >= 32 else "?" for char in text)


def _is_product_assertion(diagnostic: str) -> bool:
    return bool(re.search(r"AssertionError|(^|\n)\s*assert\s|(^|\n)FAILED\s", diagnostic))


def validate_publication_board(worktree: Path) -> BoardIndex:
    """Validate the exact physical checkout without split-root redirection."""

    from cascade.board.store import scan_physical_board

    return scan_physical_board(worktree)


def _history_path(label: str, revision: str, path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = str(path.resolve())
    return f"{label}@{revision}:{relative}"


def _feedback_identity(meta: object) -> tuple[tuple[object, ...], ...]:
    feedback = getattr(meta, "cancellation_feedback", ())
    return tuple(
        (
            item.child_id,
            item.child_tier,
            item.parent_id,
            item.reason,
            item.cancelled_at.isoformat(),
            tuple(item.available_dispositions),
            item.disposition,
            item.resolved_at.isoformat() if item.resolved_at is not None else None,
        )
        for item in feedback
    )


def _physical_refusal_details(error: Exception) -> tuple[str, tuple[str, ...]]:
    """Classify Board's path-rich aggregate without discarding its evidence."""

    message = str(error)
    if "duplicate id" in message:
        kind = "duplicate"
    elif "identity " in message or " parent " in message:
        kind = "hierarchy"
    else:
        kind = "malformed"
    affected = tuple(
        sorted(set(re.findall(r"\b(?:epic|feat|task)(?:_[0-9]+)+\b", message)))
    )
    return kind, affected


def _history_repair_previews(
    work_ids: tuple[str, ...], owner_root: Path
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...], tuple[str, ...]]:
    """Return established owners, prerequisites, and unavailable owner facts."""

    from cascade.board.errors import BoardError
    from cascade.workspace.errors import MutationOwnerError
    from cascade.workspace.integration_worktree import preview_terminal_history_repair

    owners: list[tuple[str, str]] = []
    prerequisites: list[str] = []
    unavailable: list[str] = []
    for work_id in work_ids:
        try:
            preview = preview_terminal_history_repair((work_id,), trunk=owner_root)[0]
        except MutationOwnerError as exc:
            unavailable.append(f"{work_id}: {exc.reason}")
            prerequisites.append(f"{work_id}: {exc.action}")
        except (BoardError, OSError) as exc:
            unavailable.append(f"{work_id}: canonical owner evidence is unreadable: {exc}")
            prerequisites.append(
                f"{work_id}: repair the canonical physical board before retrying"
            )
        else:
            owners.append((work_id, str(preview.owner)))
            prerequisites.append(preview.prerequisite)
    return tuple(owners), tuple(prerequisites), tuple(unavailable)


@contextmanager
def _materialize_pinned_revision(
    repository: Path, revision: str
) -> Iterator[tuple[Path, str] | MergeCandidateRefusal]:
    """Check out one full pinned commit without reading a moving worktree."""

    value = revision.strip() if isinstance(revision, str) else ""
    if not value or re.fullmatch(r"[0-9a-fA-F]{40,64}", value) is None:
        yield MergeCandidateRefusal(
            "missing" if not value else "unknown",
            None,
            value or None,
            "A full pinned accepted revision is required for history comparison.",
            "Refresh and retain the exact accepted target revision before retrying.",
        )
        return
    repository = Path(repository).resolve()
    with tempfile.TemporaryDirectory(prefix="cascade-accepted-history-") as owned:
        checkout = Path(owned) / "checkout"
        clone = _candidate_git(
            None,
            "clone",
            "--quiet",
            "--no-checkout",
            "--no-local",
            str(repository),
            str(checkout),
        )
        if clone.returncode:
            yield MergeCandidateRefusal(
                "unknown",
                None,
                value,
                "The pinned accepted repository is unavailable.",
                "Restore the accepted repository and its exact Git object before retrying.",
                diagnostics=_sanitized_tail(clone.stderr, repository, checkout),
            )
            return
        probe = _candidate_git(checkout, "rev-parse", "--verify", f"{value}^{{commit}}")
        exact = probe.stdout.strip()
        if probe.returncode or re.fullmatch(r"[0-9a-f]{40,64}", exact) is None:
            yield MergeCandidateRefusal(
                "unknown",
                None,
                value,
                "The pinned accepted revision is not available as a commit.",
                "Fetch the accepted target object and retry with the same full revision.",
                diagnostics=_sanitized_tail(probe.stderr, repository, checkout),
            )
            return
        result = _candidate_git(checkout, "checkout", "--quiet", "--detach", exact)
        if result.returncode:
            yield MergeCandidateRefusal(
                "unknown",
                None,
                exact,
                "The pinned accepted revision could not be checked out.",
                "Repair accepted-repository Git object access before retrying.",
                diagnostics=_sanitized_tail(result.stderr, repository, checkout),
            )
            return
        yield checkout, exact


def prove_accepted_terminal_history(
    repository: Path,
    candidate: ExactMergeCandidate,
    accepted_revision: str,
    *,
    accepted_repository: Path | None = None,
    candidate_board_root: Path | None = None,
    owner_root: Path | None = None,
    target_ref: str | None = None,
) -> AcceptedTerminalHistoryProof | TerminalHistoryRefusal:
    """Compare a fresh physical candidate with one pinned accepted board.

    Paths and document bytes may change through valid lifecycle transitions.
    Identity, retained records, terminal state, cancellation cleanup, and parent
    feedback may not regress.  No result is cached: repaired candidates and a
    moved target are independently scanned on every call.
    """

    repository = Path(repository).resolve()
    accepted_repository = Path(accepted_repository or repository).resolve()
    candidate_root = Path(candidate_board_root or candidate.checkout).resolve()
    owner_root = Path(owner_root or repository).resolve()

    from cascade.board.context import get_project_context
    from cascade.board.errors import BoardError

    project = get_project_context()
    if (
        project is not None
        and project.target.root.resolve() != project.tracking.root.resolve()
        and candidate_board_root is None
    ):
        return TerminalHistoryRefusal(
            "evidence_unavailable",
            (),
            (str(candidate.checkout), str(project.tracking.root.resolve())),
            candidate.source_sha,
            candidate.target_sha,
            candidate.result_commit,
            accepted_revision,
            (),
            "split-root candidate history evidence was not supplied",
            "materialize the exact tracking-root candidate and pass its physical root",
        )

    observed_target: str | None = None
    if target_ref is not None:
        before = _candidate_git(repository, "rev-parse", "--verify", f"{target_ref}^{{commit}}")
        observed_target = before.stdout.strip()
        if before.returncode or observed_target != candidate.target_sha:
            return TerminalHistoryRefusal(
                "target_changed",
                (),
                (),
                candidate.source_sha,
                candidate.target_sha,
                candidate.result_commit,
                accepted_revision,
                (),
                f"target {target_ref} no longer names candidate target {candidate.target_sha}",
                "refresh the target, materialize a new candidate, and prove history again",
            )

    try:
        candidate_board = validate_publication_board(candidate_root)
    except BoardError as exc:
        kind, affected_ids = _physical_refusal_details(exc)
        owners, prerequisites, unavailable = _history_repair_previews(
            affected_ids, owner_root
        )
        return TerminalHistoryRefusal(
            "evidence_unavailable" if unavailable else kind,
            affected_ids,
            (str(candidate_root),),
            candidate.source_sha,
            candidate.target_sha,
            candidate.result_commit,
            accepted_revision,
            owners,
            "; ".join(
                [f"candidate physical inventory is invalid: {exc}", *unavailable]
            ),
            "; ".join(prerequisites)
            or "restore identifiable records, then validate a new exact candidate",
        )
    except (OSError, ValueError) as exc:
        return TerminalHistoryRefusal(
            "evidence_unavailable",
            (),
            (str(candidate_root),),
            candidate.source_sha,
            candidate.target_sha,
            candidate.result_commit,
            accepted_revision,
            (),
            f"candidate physical inventory is unavailable: {exc}",
            "restore the exact candidate inventory and retry without reusing prior proof",
        )

    with _materialize_pinned_revision(accepted_repository, accepted_revision) as pinned:
        if isinstance(pinned, MergeCandidateRefusal):
            return TerminalHistoryRefusal(
                "evidence_unavailable",
                (),
                (str(accepted_repository),),
                candidate.source_sha,
                candidate.target_sha,
                candidate.result_commit,
                accepted_revision,
                (),
                pinned.message,
                pinned.owner_action,
            )
        accepted_root, exact_accepted = pinned
        try:
            accepted_board = validate_publication_board(accepted_root)
        except BoardError as exc:
            kind, affected_ids = _physical_refusal_details(exc)
            owners, prerequisites, unavailable = _history_repair_previews(
                affected_ids, owner_root
            )
            return TerminalHistoryRefusal(
                "evidence_unavailable" if unavailable else kind,
                affected_ids,
                (str(accepted_repository),),
                candidate.source_sha,
                candidate.target_sha,
                candidate.result_commit,
                exact_accepted,
                owners,
                "; ".join(
                    [f"accepted physical inventory is invalid: {exc}", *unavailable]
                ),
                "; ".join(prerequisites)
                or "restore identifiable pinned records through their canonical owners",
            )
        except (OSError, ValueError) as exc:
            return TerminalHistoryRefusal(
                "evidence_unavailable",
                (),
                (str(accepted_repository),),
                candidate.source_sha,
                candidate.target_sha,
                candidate.result_commit,
                exact_accepted,
                (),
                f"accepted physical inventory is unavailable: {exc}",
                "restore the pinned accepted inventory before retrying",
            )

        issues: list[str] = []
        affected: set[str] = set()
        paths: list[str] = []
        terminal_ids: list[str] = []
        for work_id, accepted in sorted(accepted_board.by_id.items()):
            current = candidate_board.by_id.get(work_id)
            accepted_path = _history_path(
                "accepted", exact_accepted, accepted.path, accepted_root
            )
            paths.append(accepted_path)
            if current is None:
                affected.add(work_id)
                issues.append(f"{work_id} retained specification is missing")
                continue
            current_path = _history_path(
                "candidate", candidate.result_commit, current.path, candidate_root
            )
            paths.append(current_path)
            if current.tier != accepted.tier or current.parent != accepted.parent:
                affected.add(work_id)
                issues.append(f"{work_id} tier or parent lineage changed")
            missing_children = sorted(set(accepted.children) - set(current.children))
            if missing_children:
                affected.update((work_id, *missing_children))
                issues.append(
                    f"{work_id} dropped accepted children {', '.join(missing_children)}"
                )
            if accepted.status in {"completed", "cancelled"}:
                terminal_ids.append(work_id)
                if current.status != accepted.status:
                    affected.add(work_id)
                    issues.append(
                        f"{work_id} terminal status reopened from {accepted.status} "
                        f"to {current.status}"
                    )
            accepted_cancel = (
                accepted.cancellation_reason,
                accepted.cancelled_at.isoformat() if accepted.cancelled_at else None,
                accepted.cancellation_step,
                accepted.cancellation_error,
            )
            current_cancel = (
                current.cancellation_reason,
                current.cancelled_at.isoformat() if current.cancelled_at else None,
                current.cancellation_step,
                current.cancellation_error,
            )
            if current_cancel != accepted_cancel:
                affected.add(work_id)
                issues.append(f"{work_id} cancellation reason/timestamp/cleanup outcome changed")
            if _feedback_identity(current) != _feedback_identity(accepted):
                affected.add(work_id)
                issues.append(f"{work_id} accepted parent feedback/disposition changed")

        if issues:
            owners, prerequisites, unavailable = _history_repair_previews(
                tuple(sorted(affected)), owner_root
            )
            return TerminalHistoryRefusal(
                "evidence_unavailable" if unavailable else "history",
                tuple(sorted(affected)),
                tuple(dict.fromkeys(paths)),
                candidate.source_sha,
                candidate.target_sha,
                candidate.result_commit,
                exact_accepted,
                owners,
                "; ".join([*issues, *unavailable]),
                "; ".join(prerequisites),
            )

    if target_ref is not None:
        after = _candidate_git(repository, "rev-parse", "--verify", f"{target_ref}^{{commit}}")
        if after.returncode or after.stdout.strip() != observed_target:
            return TerminalHistoryRefusal(
                "target_changed",
                (),
                (),
                candidate.source_sha,
                candidate.target_sha,
                candidate.result_commit,
                accepted_revision,
                (),
                f"target {target_ref} moved while terminal history was being proved",
                "refresh the target, materialize a new candidate, and prove history again",
            )

    identity = {
        "candidate": {
            "source": candidate.source_sha,
            "target": candidate.target_sha,
            "result": candidate.result_commit,
            "tree": candidate.result_tree,
        },
        "accepted_revision": exact_accepted,
        "retained_ids": sorted(accepted_board.by_id),
        "terminal_ids": sorted(terminal_ids),
    }
    return AcceptedTerminalHistoryProof(
        candidate.source_sha,
        candidate.target_sha,
        candidate.result_commit,
        candidate.result_tree,
        exact_accepted,
        tuple(sorted(accepted_board.by_id)),
        tuple(sorted(terminal_ids)),
        exact_material_fingerprint(identity),
    )
