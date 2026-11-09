"""Stable architecture identities, mappings, and pinned artifact references.

``architecture/design-mappings.json`` is a version-1 JSON index stored in the
target repository.  It owns the opaque target key and directory-to-design-owner
mappings regardless of the configured documentation destination.  The JSON
object contains ``version``, ``target_repository_key``, and a ``designs`` map
keyed by normalized code directory.  Each row records ``code_directory``,
``design_owner_directory``, and the stable ``artifact_id``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import ProjectContext, RepositoryContext

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DesignOwnership:
    """A target directory and the target directory whose design owns it."""

    target_repository_key: str
    code_directory: Path
    design_owner_directory: Path
    artifact_id: str
    design_path: Path


@dataclass(frozen=True)
class ArchitectureArtifactRef:
    """A design location fixed to one repository revision at creation time."""

    target_repository_key: str
    code_directory: Path
    design_owner_directory: Path
    owning_work: str
    destination_repository_key: str
    destination_repository_role: Literal["target", "tracking"]
    repository_path: Path
    revision: str

    def __post_init__(self) -> None:
        if not self.target_repository_key.startswith("target-"):
            raise WorkspaceError("invalid architecture artifact target repository key")
        if not self.owning_work.strip():
            raise WorkspaceError("architecture artifact owning work must be non-blank")
        if not self.destination_repository_key.strip():
            raise WorkspaceError("invalid architecture artifact destination repository key")
        if self.destination_repository_role not in {"target", "tracking"}:
            raise WorkspaceError("invalid architecture artifact destination role")
        _validate_stored_path(self.code_directory, allow_root=True)
        _validate_stored_path(self.design_owner_directory, allow_root=True)
        _validate_stored_path(self.repository_path)
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.revision) is None:
            raise WorkspaceError("invalid architecture artifact revision")

    def to_dict(self) -> dict[str, str]:
        return {
            "target_repository_key": self.target_repository_key,
            "code_directory": _portable_directory(self.code_directory),
            "design_owner_directory": _portable_directory(
                self.design_owner_directory
            ),
            "owning_work": self.owning_work,
            "destination_repository_key": self.destination_repository_key,
            "destination_repository_role": self.destination_repository_role,
            "repository_path": self.repository_path.as_posix(),
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ArchitectureArtifactRef":
        if not isinstance(payload, dict):
            raise WorkspaceError("architecture artifact reference must be a mapping")
        required = {
            "target_repository_key",
            "code_directory",
            "design_owner_directory",
            "owning_work",
            "destination_repository_key",
            "destination_repository_role",
            "repository_path",
            "revision",
        }
        if set(payload) != required or not all(
            isinstance(payload[field], str) for field in required
        ):
            raise WorkspaceError("invalid architecture artifact reference")
        role = payload["destination_repository_role"]
        if role not in {"target", "tracking"}:
            raise WorkspaceError("invalid architecture artifact destination role")
        code = _stored_relative(payload["code_directory"], allow_root=True)
        owner = _stored_relative(payload["design_owner_directory"], allow_root=True)
        repository_path = _stored_relative(payload["repository_path"])
        return cls(
            target_repository_key=payload["target_repository_key"],
            code_directory=code,
            design_owner_directory=owner,
            owning_work=payload["owning_work"],
            destination_repository_key=payload["destination_repository_key"],
            destination_repository_role=role,
            repository_path=repository_path,
            revision=payload["revision"],
        )


def resolve_design_ownership(
    project: ProjectContext,
    code_directory: Path | str = ".",
    *,
    design_owner_directory: Path | str | None = None,
    persist: bool = True,
) -> DesignOwnership:
    """Resolve and optionally persist the directory-to-design ownership row."""

    relative_code = _target_relative(project, code_directory)
    relative_owner = _target_relative(
        project,
        relative_code if design_owner_directory is None else design_owner_directory,
    )
    design_path = project.design_path(relative_owner)
    artifact_id = _design_artifact_id(project.target_repository_key, relative_owner)
    ownership = DesignOwnership(
        target_repository_key=project.target_repository_key,
        code_directory=relative_code,
        design_owner_directory=relative_owner,
        artifact_id=artifact_id,
        design_path=design_path,
    )
    if persist:
        _, rows = _read_index(project)
        key = _portable_directory(relative_code)
        existing = rows.get(key)
        projected = {
            "code_directory": key,
            "design_owner_directory": _portable_directory(relative_owner),
            "artifact_id": artifact_id,
        }
        if existing is not None and existing != projected:
            raise WorkspaceError(
                f"design ownership for target directory {key!r} is already fixed at "
                f"{existing!r}; ownership changes require an explicit migration"
            )
        if existing is None:
            rows[key] = projected
            _write_index(project, rows)
    return ownership


def load_design_ownerships(project: ProjectContext) -> tuple[DesignOwnership, ...]:
    """Load persisted rows without guessing repository identity from a path name."""

    _, rows = _read_index(project)
    return tuple(
        DesignOwnership(
            target_repository_key=project.target_repository_key,
            code_directory=_stored_relative(row["code_directory"], allow_root=True),
            design_owner_directory=_stored_relative(
                row["design_owner_directory"], allow_root=True
            ),
            artifact_id=row["artifact_id"],
            design_path=project.design_path(
                _stored_relative(row["design_owner_directory"], allow_root=True)
            ),
        )
        for _, row in sorted(rows.items())
    )


def ensure_target_repository_key(project: ProjectContext) -> str:
    """Load the recorded key or calculate the candidate for a new index."""

    key, _ = _read_index(project)
    return key


def create_architecture_artifact_ref(
    project: ProjectContext,
    code_directory: Path | str,
    *,
    owning_work: str,
    design_owner_directory: Path | str | None = None,
) -> ArchitectureArtifactRef:
    """Resolve today's destination once and return a serializable pinned ref."""

    if not owning_work.strip():
        raise WorkspaceError("architecture artifact owning work must be non-blank")
    if design_owner_directory is not None:
        ownership = resolve_design_ownership(
            project,
            code_directory,
            design_owner_directory=design_owner_directory,
        )
    else:
        ownership = require_design_ownership(project, code_directory)
    repository = project.architecture_repository
    assert repository.repository_key is not None
    try:
        relative_path = ownership.design_path.relative_to(repository.root)
    except ValueError as exc:  # pragma: no cover - ProjectContext invariant
        raise WorkspaceError("architecture artifact path escapes its repository") from exc
    reference = ArchitectureArtifactRef(
        target_repository_key=ownership.target_repository_key,
        code_directory=ownership.code_directory,
        design_owner_directory=ownership.design_owner_directory,
        owning_work=owning_work,
        destination_repository_key=(
            project.target_repository_key
            if project.architecture_destination == "target"
            else repository.repository_key
        ),
        destination_repository_role=project.architecture_destination,
        repository_path=relative_path,
        revision=_head_revision(repository.root),
    )
    _require_committed_artifact(repository.root, reference)
    return reference


def create_architecture_model_ref(
    project: ProjectContext,
    code_directory: Path | str,
    model_path: Path | str,
    *,
    owning_work: str,
) -> ArchitectureArtifactRef:
    """Pin an editable model or owned fragment to today's destination once.

    ``model_path`` is relative to ``architecture/<target-key>/``.  The code
    directory still has to have a persisted design owner, preserving target
    provenance and authorization context for model fragments.
    """

    if not owning_work.strip():
        raise WorkspaceError("architecture artifact owning work must be non-blank")
    ownership = require_design_ownership(project, code_directory)
    relative_model_path = _relative_artifact_path(model_path)
    repository = project.architecture_repository
    assert repository.repository_key is not None
    destination_path = project.editable_architecture_root / relative_model_path
    try:
        repository_path = destination_path.relative_to(repository.root)
    except ValueError as exc:  # pragma: no cover - ProjectContext invariant
        raise WorkspaceError("architecture model path escapes its repository") from exc
    reference = ArchitectureArtifactRef(
        target_repository_key=ownership.target_repository_key,
        code_directory=ownership.code_directory,
        design_owner_directory=ownership.design_owner_directory,
        owning_work=owning_work,
        destination_repository_key=(
            project.target_repository_key
            if project.architecture_destination == "target"
            else repository.repository_key
        ),
        destination_repository_role=project.architecture_destination,
        repository_path=repository_path,
        revision=_head_revision(repository.root),
    )
    _require_committed_artifact(repository.root, reference)
    return reference


def resolve_artifact_ref_path(
    project: ProjectContext, reference: ArchitectureArtifactRef
) -> Path:
    """Route a proposed edit using the reference's recorded destination."""

    repository = _repository_for_artifact_ref(project, reference)
    path = (repository.root / reference.repository_path).resolve()
    try:
        path.relative_to(repository.root)
    except ValueError as exc:
        raise WorkspaceError("architecture artifact reference escapes its repository") from exc
    return path


def read_architecture_artifact(
    project: ProjectContext, reference: ArchitectureArtifactRef
) -> str:
    """Read the exact reviewed source from the reference's pinned Git commit."""

    repository = _repository_for_artifact_ref(project, reference)
    object_name = f"{reference.revision}:{reference.repository_path.as_posix()}"
    result = subprocess.run(
        ["git", "show", object_name],
        cwd=repository.root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise WorkspaceError(
            "cannot read pinned architecture artifact "
            f"{reference.repository_path.as_posix()} at {reference.revision}"
        )
    return result.stdout


def replay_architecture_artifact(
    project: ProjectContext, reference: ArchitectureArtifactRef
) -> str:
    """Replay an architecture source from the same fixed read used by review."""

    return read_architecture_artifact(project, reference)


def architecture_artifact_link(reference: ArchitectureArtifactRef) -> str:
    """Return a stable source link containing only recorded reference fields."""

    return (
        f"architecture:{reference.destination_repository_key}"
        f"@{reference.revision}:{reference.repository_path.as_posix()}"
    )


def require_design_ownership(
    project: ProjectContext, code_directory: Path | str
) -> DesignOwnership:
    """Return an existing mapping, rejecting writes/reviews with no owner."""

    relative_code = _target_relative(project, code_directory)
    key = _portable_directory(relative_code)
    _, rows = _read_index(project)
    row = rows.get(key)
    if row is None:
        raise WorkspaceError(
            f"target directory {key!r} has no persisted design ownership mapping"
        )
    owner = _stored_relative(row["design_owner_directory"], allow_root=True)
    return DesignOwnership(
        target_repository_key=project.target_repository_key,
        code_directory=relative_code,
        design_owner_directory=owner,
        artifact_id=row["artifact_id"],
        design_path=project.design_path(owner),
    )


def _target_relative(project: ProjectContext, code_directory: Path | str) -> Path:
    candidate = Path(code_directory)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(project.target.root)
        except ValueError as exc:
            raise WorkspaceError(
                "design ownership code directory must be inside the target repository"
            ) from exc
    if any(part == ".." for part in candidate.parts):
        raise WorkspaceError(
            "design ownership code directory must not escape the target repository"
        )
    parts = [part for part in candidate.parts if part not in {"", "."}]
    return Path(*parts) if parts else Path(".")


def _relative_artifact_path(path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise WorkspaceError("architecture model path must be repository-relative")
    return candidate


def _validate_stored_path(path: Path, *, allow_root: bool = False) -> None:
    if path == Path(".") and allow_root:
        return
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise WorkspaceError(f"invalid repository-relative architecture path: {path!s}")


def _repository_for_artifact_ref(
    project: ProjectContext, reference: ArchitectureArtifactRef
) -> RepositoryContext:
    if reference.target_repository_key != project.target_repository_key:
        raise WorkspaceError("architecture artifact reference belongs to another target")
    repository = (
        project.target
        if reference.destination_repository_role == "target"
        else project.tracking
    )
    expected_repository_key = (
        project.target_repository_key
        if reference.destination_repository_role == "target"
        else repository.repository_key
    )
    if expected_repository_key != reference.destination_repository_key:
        raise WorkspaceError("architecture artifact destination repository has changed")
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{reference.revision}^{{commit}}"],
        cwd=repository.root,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise WorkspaceError(
            "architecture artifact pinned revision is unavailable in its "
            "recorded destination repository"
        )
    return repository


def _portable_directory(path: Path) -> str:
    return "." if path == Path(".") else path.as_posix()


def _read_index(project: ProjectContext) -> tuple[str, dict[str, dict[str, str]]]:
    path = project.design_ownership_path
    if not path.exists():
        committed_key = _committed_index_key(project)
        if committed_key is not None:
            raise WorkspaceError(
                f"target architecture mapping index is missing from the checkout: {path}"
            )
        return _initial_target_key(project), {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"invalid design ownership index: {path}") from exc
    if not isinstance(payload, dict) or payload.get("version") != _SCHEMA_VERSION:
        raise WorkspaceError(f"unsupported design ownership index: {path}")
    target_key = payload.get("target_repository_key")
    if not isinstance(target_key, str) or not target_key.startswith("target-"):
        raise WorkspaceError(f"invalid target repository key in mapping index: {path}")
    committed_key = _committed_index_key(project)
    if committed_key is not None and committed_key != target_key:
        raise WorkspaceError(
            "target repository key differs from the committed architecture mapping index"
        )
    rows = payload.get("designs")
    if not isinstance(rows, dict) or not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in rows.items()
    ):
        raise WorkspaceError(f"invalid design ownership mappings: {path}")
    validated: dict[str, dict[str, str]] = {}
    artifact_owners: dict[str, str] = {}
    for key, row in rows.items():
        expected_fields = {
            "code_directory",
            "design_owner_directory",
            "artifact_id",
        }
        if set(row) != expected_fields or not all(
            isinstance(row[field], str) for field in expected_fields
        ):
            raise WorkspaceError(f"invalid design ownership mapping for {key!r}: {path}")
        code = _stored_relative(row["code_directory"], allow_root=True)
        owner = _stored_relative(row["design_owner_directory"], allow_root=True)
        normalized_code = _portable_directory(code)
        normalized_owner = _portable_directory(owner)
        expected_artifact = _design_artifact_id(target_key, owner)
        if key != normalized_code or row["artifact_id"] != expected_artifact:
            raise WorkspaceError(f"conflicting design ownership mapping for {key!r}: {path}")
        prior_owner = artifact_owners.setdefault(expected_artifact, normalized_owner)
        if prior_owner != normalized_owner:
            raise WorkspaceError(f"ambiguous design artifact ownership in index: {path}")
        validated[key] = {
            "code_directory": normalized_code,
            "design_owner_directory": normalized_owner,
            "artifact_id": expected_artifact,
        }
    return target_key, validated


def _write_index(project: ProjectContext, rows: dict[str, dict[str, str]]) -> None:
    path = project.design_ownership_path
    key, _ = _read_index(project)
    _write_index_payload(path, key, rows)


def _write_index_payload(
    path: Path, key: str, rows: dict[str, dict[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _SCHEMA_VERSION,
        "target_repository_key": key,
        "designs": dict(sorted(rows.items())),
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _stored_relative(value: str, *, allow_root: bool = False) -> Path:
    if value == "." and allow_root:
        return Path(".")
    candidate = Path(value)
    if (
        not value
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise WorkspaceError(f"invalid repository-relative architecture path: {value!r}")
    return candidate


def _design_artifact_id(target_key: str, owner: Path) -> str:
    return f"design:{target_key}:{_portable_directory(owner)}"


def _head_revision(repository: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=repository,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    revision = result.stdout.strip()
    if result.returncode != 0 or not revision:
        raise WorkspaceError(
            f"cannot pin architecture artifact: repository has no readable HEAD: {repository}"
        )
    return revision


def _require_committed_artifact(
    repository: Path, reference: ArchitectureArtifactRef
) -> None:
    object_name = f"{reference.revision}:{reference.repository_path.as_posix()}"
    result = subprocess.run(
        ["git", "show", object_name],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise WorkspaceError(
            "cannot pin architecture artifact: reviewed bytes are not committed at "
            f"{reference.repository_path.as_posix()} in {reference.revision}"
        )
    artifact_path = repository / reference.repository_path
    try:
        reviewed_bytes = artifact_path.read_bytes()
    except OSError as exc:
        raise WorkspaceError(
            "cannot pin architecture artifact: reviewed artifact is not readable at "
            f"{reference.repository_path.as_posix()}"
        ) from exc
    if reviewed_bytes != result.stdout:
        raise WorkspaceError(
            "cannot pin architecture artifact: reviewed working bytes differ from "
            f"{reference.repository_path.as_posix()} in {reference.revision}"
        )


def _committed_index_key(project: ProjectContext) -> str | None:
    relative = project.design_ownership_path.relative_to(project.target.root).as_posix()
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=project.target.root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkspaceError(
            "committed target architecture mapping index is invalid"
        ) from exc
    key = payload.get("target_repository_key") if isinstance(payload, dict) else None
    if not isinstance(key, str):
        raise WorkspaceError("committed target architecture mapping key is invalid")
    return key


def _initial_target_key(project: ProjectContext) -> str:
    """Return an opaque seed stable across clones until the index is committed."""

    result = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "--reverse", "HEAD"],
        cwd=project.target.root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    roots = result.stdout.splitlines() if result.returncode == 0 else []
    identity = f"git-root:{roots[0]}" if roots else project.target.root.as_uri()
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    return f"target-{digest}"
