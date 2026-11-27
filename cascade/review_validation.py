"""Bounded repository checks for review publication, without shell evaluation."""

from __future__ import annotations

import hashlib
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
    parent_operation_id: str | None = None,
    profile: ReviewValidationProfile | None = None,
) -> tuple[IncidentOperationDecision, ReviewValidationOperation | None]:
    """Reserve the validator's worst-case runtime before any process spawn."""

    selected = profile or replace(
        approved_review_validation_profile(root), command=(), timeout_seconds=timeout
    )
    if timeout != selected.timeout_seconds:
        raise ReviewValidationAdmissionError(
            "validator timeout does not match its approved profile"
        )
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


@contextmanager
def materialize_exact_merge_candidate(
    repository: Path,
    source_sha: str | None,
    target_sha: str | None,
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

    with materialize_exact_merge_candidate(repository, source_sha, target_sha) as materialized:
        if isinstance(materialized, MergeCandidateRefusal):
            return ExactCandidateValidation(
                "unavailable", "materialization", None, materialized, command, None, "",
                materialized.diagnostics, None, review_validation_environment(),
                materialized.owner_action,
            )
        candidate = materialized
        dependency_revision = _candidate_dependency_revision(candidate.checkout)
        runtime = {
            **review_validation_environment(),
            "dependency_revision": dependency_revision,
            "source_tree": candidate.result_tree,
        }
        from cascade.board.errors import BoardError

        try:
            validate_publication_board(candidate.checkout)
        except (BoardError, OSError, ValueError) as exc:
            return ExactCandidateValidation(
                "fixture_environment", "board", candidate, None, command, None, "", "",
                dependency_revision, runtime,
                f"Repair the candidate lifecycle documents ({type(exc).__name__}) before validation.",
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
                    operation=operation, env=env,
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
        current_head = _candidate_git(
            candidate.checkout, "rev-parse", "--verify", "HEAD^{commit}"
        ).stdout.strip()
        if current_head != candidate.result_commit:
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


def validate_publication_board(worktree: Path) -> None:
    """Validate physical documents being published, without split-root redirection.

    Normal board scans intentionally skip malformed drafts; publication must
    reject those and duplicate IDs rather than hide them from the live board.
    """
    from cascade.board.parse import parse_doc
    from cascade.board.errors import SchemaError

    seen = {}
    for tier in ("epics", "features", "tasks"):
        for column in ("1_backlog", "2_active", "3_completed", "4_cancelled"):
            for path in sorted((worktree / "docs" / tier / column).glob("*.md")):
                if path.is_symlink():
                    raise SchemaError(f"publication board symlink: {path}")
                doc = parse_doc(path)
                if doc.meta.id in seen:
                    raise SchemaError(
                        f"duplicate id {doc.meta.id} at {path} and {seen[doc.meta.id]}"
                    )
                seen[doc.meta.id] = path
