"""Durable, immutable architecture browsing snapshots.

Snapshots bind a known checkout to exact code, documentation, mapping, source
closure, and renderer identities.  Reads never inspect working-tree model
bytes and never admit renderer work; only explicit creation/refresh does so.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from cascade.task.lifecycle_lock import task_lifecycle_lock, task_lifecycle_read_lock
from cascade.workspace.architecture import ArchitectureArtifactRef
from cascade.workspace.architecture_browsing import (
    ArchitectureBrowsingError,
    ArchitectureContextSelection,
    resolve_architecture_code_context,
    resolve_architecture_context,
)
from cascade.workspace.c4_closure import materialize_c4_source_closure
from cascade.workspace.c4_render import C4RenderSettings
from cascade.workspace.c4_scheduler import (
    C4RenderAdmissionError,
    C4RenderScheduler,
    render_identity,
)
from cascade.workspace.c4_source import C4SourceError
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import ProjectContext, RepositoryContext

SnapshotState = Literal[
    "pending",
    "ready",
    "documentation_ref_required",
    "missing_commit",
    "missing_mapping",
    "missing_model",
    "invalid_model",
    "oversized_artifact",
    "render_failed",
    "render_unavailable",
]

_LEDGER_VERSION = 1
_MAPPING_PATH = Path("architecture/design-mappings.json")
_MAX_DESCRIPTOR_BLOB_BYTES = 1024 * 1024
_MAX_SOURCE_BYTES = 4 * 1024 * 1024
_MAX_RENDERED_ARTIFACT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ArchitectureBrowsingSnapshot:
    snapshot_id: str
    state: SnapshotState
    descriptor: dict[str, object]
    render_operation_id: str | None = None
    reason_code: str | None = None
    message: str | None = None
    view_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "snapshot_id": self.snapshot_id,
            "state": self.state,
            "reason_code": self.reason_code,
            "message": self.message,
            "descriptor": self.descriptor,
            "render_operation_id": self.render_operation_id,
            "view_keys": list(self.view_keys),
        }


class ArchitectureSnapshotStore:
    """Create and recover immutable branch-browsing descriptors."""

    def __init__(
        self,
        project: ProjectContext,
        session_target: Path,
        *,
        scheduler: C4RenderScheduler | None = None,
        ledger_path: Path | None = None,
    ) -> None:
        self.project = project
        self.session_target = Path(session_target).resolve()
        self.ledger_path = (ledger_path or (
            project.target.root / ".cascade" / "architecture-browsing-snapshots.json"
        )).resolve()
        self.scheduler = scheduler or C4RenderScheduler(project.target.root)
        self._owns_scheduler = scheduler is None

    def close(self) -> None:
        if self._owns_scheduler:
            self.scheduler.close()

    def __enter__(self) -> "ArchitectureSnapshotStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def create(
        self,
        context_id: str | None = None,
        *,
        documentation_ref_id: str | None = None,
        code_directory: str = ".",
        settings: C4RenderSettings | None = None,
    ) -> ArchitectureBrowsingSnapshot:
        """Pin one whole context and admit its exact render once."""

        selection = resolve_architecture_context(
            self.project,
            self.session_target,
            context_id,
            documentation_ref_id=documentation_ref_id,
        )
        base = self._selection_descriptor(selection, code_directory, documentation_ref_id)
        if selection.documentation_ref_required:
            return self._persist_failure(
                base,
                "documentation_ref_required",
                "documentation_ref_required",
                "select an exact known documentation revision before creating a snapshot",
            )

        assert selection.documentation_revision is not None
        code_revision = selection.context.revision
        documentation_revision = selection.documentation_revision
        if not _commit_exists(self.project.target, code_revision) or not _commit_exists(
            self.project.architecture_repository, documentation_revision
        ):
            return self._persist_failure(
                base, "missing_commit", "missing_commit",
                "a pinned code or documentation commit is unavailable",
            )

        try:
            mapping = _read_regular_blob(
                self.project.target, code_revision, _MAPPING_PATH,
                max_bytes=_MAX_DESCRIPTOR_BLOB_BYTES,
            )
        except _PinnedBlobError as exc:
            state: SnapshotState = (
                "oversized_artifact" if exc.code == "oversized_artifact" else "missing_mapping"
            )
            return self._persist_failure(base, state, exc.code, str(exc))

        mapping_digest = hashlib.sha256(mapping).hexdigest()
        base["mapping"] = {
            "repository_key": selection.mapping_repository_key,
            "revision": selection.mapping_revision,
            "path": _MAPPING_PATH.as_posix(),
            "sha256": mapping_digest,
        }
        try:
            owner_directory = _mapping_owner(mapping, code_directory, self.project.target_repository_key)
            references = _model_references(
                self.project,
                selection,
                code_directory=code_directory,
                owner_directory=owner_directory,
            )
            total = sum(
                _blob_size(
                    self.project.architecture_repository,
                    documentation_revision,
                    reference.repository_path,
                )
                for reference in references
            )
            if total > _MAX_SOURCE_BYTES:
                raise _PinnedBlobError(
                    "oversized_artifact", "pinned architecture source exceeds 4 MiB"
                )
            with tempfile.TemporaryDirectory(prefix="cascade-browsing-snapshot-") as directory:
                closure = materialize_c4_source_closure(
                    self.project, references[0], references[1:], Path(directory) / "source"
                )
                chosen_settings = settings or C4RenderSettings()
                identity = render_identity(closure.digest, chosen_settings)
                base.update({
                    "source_closure": {
                        "digest": closure.digest,
                        "revision": closure.revision,
                        "files": [
                            {
                                "path": item.repository_path.as_posix(),
                                "owner": item.owner,
                                "sha256": item.sha256,
                            }
                            for item in closure.files
                        ],
                    },
                    "render": {
                        "identity": identity,
                        "settings": chosen_settings.cache_payload(),
                    },
                })
                snapshot_id = _snapshot_id(base)
                existing = self._row(snapshot_id)
                if existing is not None:
                    return self.get(snapshot_id)
                operation = self.scheduler.admit(
                    closure,
                    chosen_settings,
                    owner="architecture_browsing",
                    snapshot_id=snapshot_id,
                )
        except _PinnedBlobError as exc:
            state = "oversized_artifact" if exc.code == "oversized_artifact" else "missing_model"
            return self._persist_failure(base, state, exc.code, str(exc))
        except (C4SourceError, WorkspaceError, ValueError, json.JSONDecodeError) as exc:
            return self._persist_failure(base, "invalid_model", "invalid_model", str(exc))
        except C4RenderAdmissionError as exc:
            return self._persist_failure(base, "render_unavailable", exc.code, str(exc))

        self._save({
            "snapshot_id": snapshot_id,
            "descriptor": base,
            "render_operation_id": operation.operation_id,
            "state": "pending",
            "reason_code": None,
            "message": "bounded architecture render is pending",
            "created_at": time.time(),
        })
        return self.get(snapshot_id)

    def get(self, snapshot_id: str) -> ArchitectureBrowsingSnapshot:
        row = self._row(snapshot_id)
        if row is None:
            raise KeyError(snapshot_id)
        descriptor = row["descriptor"]
        operation_id = row.get("render_operation_id")
        stored_state = row["state"]
        if operation_id is None:
            return ArchitectureBrowsingSnapshot(
                snapshot_id, stored_state, descriptor,
                reason_code=row.get("reason_code"), message=row.get("message"),
            )
        revisions = descriptor["revisions"]
        if not _commit_exists(self.project.target, revisions["code"]) or not _commit_exists(
            self.project.architecture_repository, revisions["documentation"]
        ):
            return ArchitectureBrowsingSnapshot(
                snapshot_id, "missing_commit", descriptor, operation_id,
                "missing_commit", "a pinned code or documentation commit is unavailable",
            )
        try:
            render = self.scheduler.get(operation_id)
        except KeyError:
            return ArchitectureBrowsingSnapshot(
                snapshot_id, "render_unavailable", descriptor, operation_id,
                "render_unavailable", "the durable render operation is unavailable",
            )
        if render.status in {"pending", "running"}:
            return ArchitectureBrowsingSnapshot(
                snapshot_id, "pending", descriptor, operation_id,
                message="bounded architecture render is pending",
            )
        if render.status == "ready" and render.artifact is not None:
            artifact_problem = _render_artifact_problem(render.artifact)
            if artifact_problem is not None:
                code, name = artifact_problem
                return ArchitectureBrowsingSnapshot(
                    snapshot_id,
                    "oversized_artifact" if code == "oversized_artifact" else "render_unavailable",
                    descriptor,
                    operation_id,
                    code,
                    (
                        f"rendered architecture artifact exceeds 4 MiB: {name}"
                        if code == "oversized_artifact"
                        else f"rendered architecture artifact is unavailable: {name}"
                    ),
                )
            return ArchitectureBrowsingSnapshot(
                snapshot_id, "ready", descriptor, operation_id,
                view_keys=render.artifact.view_keys,
            )
        failure = render.failure
        return ArchitectureBrowsingSnapshot(
            snapshot_id, "render_failed", descriptor, operation_id,
            failure.code if failure else "render_failed",
            failure.message if failure else f"architecture render ended as {render.status}",
        )

    def head_status(self, snapshot_id: str) -> dict[str, object]:
        snapshot = self.get(snapshot_id)
        context_id = str(snapshot.descriptor["context"]["context_id"])
        try:
            current = resolve_architecture_code_context(
                self.project, self.session_target, context_id
            )
        except ArchitectureBrowsingError as exc:
            return {
                "state": "context_unavailable",
                "changed": None,
                "pinned_revision": snapshot.descriptor["revisions"]["code"],
                "current_revision": None,
                "reason_code": exc.code,
            }
        pinned = snapshot.descriptor["revisions"]["code"]
        return {
            "state": "changed" if current.revision != pinned else "current",
            "changed": current.revision != pinned,
            "pinned_revision": pinned,
            "current_revision": current.revision,
        }

    def refresh(self, snapshot_id: str) -> ArchitectureBrowsingSnapshot:
        """Explicitly create a new whole snapshot from the context's current HEAD."""

        snapshot = self.get(snapshot_id)
        descriptor = snapshot.descriptor
        selected_ref = descriptor.get("selected_documentation_ref_id")
        return self.create(
            str(descriptor["context"]["context_id"]),
            documentation_ref_id=(str(selected_ref) if selected_ref else None),
            code_directory=str(descriptor["code_directory"]),
            settings=C4RenderSettings(**descriptor["render"]["settings"])
            if "render" in descriptor else None,
        )

    def view_state(self, snapshot_id: str, view_key: str) -> dict[str, str]:
        snapshot = self.get(snapshot_id)
        if snapshot.state != "ready":
            return {"state": snapshot.state, "view_key": view_key}
        return {
            "state": "ready" if view_key in snapshot.view_keys else "missing_view",
            "view_key": view_key,
        }

    def _selection_descriptor(
        self,
        selection: ArchitectureContextSelection,
        code_directory: str,
        documentation_ref_id: str | None,
    ) -> dict[str, object]:
        context = selection.context
        return {
            "context": context.to_dict(),
            "code_directory": _normalized_directory(code_directory),
            "architecture_destination": selection.architecture_destination,
            "revisions": {
                "code": context.revision,
                "documentation": selection.documentation_revision,
            },
            "repositories": {
                "code": context.repository_key,
                "documentation": selection.documentation_repository_key,
            },
            "association": {
                "provenance": selection.association_provenance,
                "evidence_id": selection.association_evidence_id,
            },
            "selected_documentation_ref_id": documentation_ref_id,
        }

    def _persist_failure(
        self,
        descriptor: dict[str, object],
        state: SnapshotState,
        reason_code: str,
        message: str,
    ) -> ArchitectureBrowsingSnapshot:
        snapshot_id = _snapshot_id({**descriptor, "failure": reason_code})
        if self._row(snapshot_id) is None:
            self._save({
                "snapshot_id": snapshot_id,
                "descriptor": descriptor,
                "render_operation_id": None,
                "state": state,
                "reason_code": reason_code,
                "message": message,
                "created_at": time.time(),
            })
        return self.get(snapshot_id)

    def _row(self, snapshot_id: str) -> dict[str, object] | None:
        if not snapshot_id.startswith("architecture-snapshot-") or len(snapshot_id) != 86:
            return None
        with task_lifecycle_read_lock(root=self.project.target.root):
            return self._read()["snapshots"].get(snapshot_id)

    def _save(self, row: dict[str, object]) -> None:
        with task_lifecycle_lock(root=self.project.target.root):
            ledger = self._read()
            ledger["snapshots"].setdefault(row["snapshot_id"], row)
            self._write(ledger)

    def _read(self) -> dict[str, object]:
        if not self.ledger_path.exists():
            return {"version": _LEDGER_VERSION, "snapshots": {}}
        try:
            value = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError("invalid architecture browsing snapshot ledger") from exc
        if (
            not isinstance(value, dict)
            or value.get("version") != _LEDGER_VERSION
            or not isinstance(value.get("snapshots"), dict)
        ):
            raise WorkspaceError("unsupported architecture browsing snapshot ledger")
        return value

    def _write(self, value: dict[str, object]) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.ledger_path.name}.", dir=self.ledger_path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.ledger_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class _PinnedBlobError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _model_references(
    project: ProjectContext,
    selection: ArchitectureContextSelection,
    *,
    code_directory: str,
    owner_directory: str,
) -> tuple[ArchitectureArtifactRef, ...]:
    revision = selection.documentation_revision
    assert revision is not None
    root = Path("architecture") / project.target_repository_key
    contract_path = root / "workspace.contract.json"
    try:
        contract_bytes = _read_regular_blob(
            project.architecture_repository, revision, contract_path,
            max_bytes=_MAX_DESCRIPTOR_BLOB_BYTES,
        )
    except _PinnedBlobError as exc:
        if exc.code == "missing_artifact":
            raise _PinnedBlobError("missing_model", str(exc)) from exc
        raise
    try:
        payload = json.loads(contract_bytes)
        workspace = payload["workspace"]
        source = _local_dsl(workspace["source"])
        workspace_owner = _nonblank(workspace["owner"])
        fragments = payload["fragments"]
        if not isinstance(fragments, list):
            raise ValueError("fragments must be a list")
        sources: list[tuple[Path, str]] = [(source, workspace_owner)]
        for row in fragments:
            if not isinstance(row, dict):
                raise ValueError("fragment must be an object")
            sources.append((_local_dsl(row["path"]), _nonblank(row["owner"])))
    except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise C4SourceError("invalid pinned C4 workspace contract") from exc

    destination = project.architecture_repository
    repository_key = (
        project.target_repository_key
        if selection.architecture_destination == "target"
        else selection.documentation_repository_key
    )
    common = dict(
        target_repository_key=project.target_repository_key,
        code_directory=Path(code_directory),
        design_owner_directory=Path(owner_directory),
        destination_repository_key=repository_key,
        destination_repository_role=selection.architecture_destination,
        revision=revision,
    )
    references = [
        ArchitectureArtifactRef(
            **common, owning_work=workspace_owner, repository_path=contract_path
        )
    ]
    references.extend(
        ArchitectureArtifactRef(
            **common, owning_work=owner, repository_path=root / path
        )
        for path, owner in sources
    )
    # Fail before materialization with a stable missing-model state.
    for reference in references:
        _blob_size(destination, revision, reference.repository_path)
    return tuple(references)


def _mapping_owner(content: bytes, code_directory: str, target_key: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise WorkspaceError("pinned architecture mapping is invalid JSON") from exc
    normalized = _normalized_directory(code_directory)
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or payload.get("target_repository_key") != target_key
        or not isinstance(payload.get("designs"), dict)
    ):
        raise WorkspaceError("pinned architecture mapping has an invalid identity")
    row = payload["designs"].get(normalized)
    if not isinstance(row, dict) or row.get("code_directory") != normalized:
        raise WorkspaceError(f"no pinned architecture mapping for {normalized!r}")
    owner = row.get("design_owner_directory")
    if not isinstance(owner, str):
        raise WorkspaceError("pinned architecture mapping has an invalid owner")
    return _normalized_directory(owner)


def _read_regular_blob(
    repository: RepositoryContext,
    revision: str,
    path: Path,
    *,
    max_bytes: int,
) -> bytes:
    size = _blob_size(repository, revision, path)
    if size > max_bytes:
        raise _PinnedBlobError("oversized_artifact", f"pinned artifact is too large: {path}")
    result = subprocess.run(
        ["git", "show", f"{revision}:{path.as_posix()}"],
        cwd=repository.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise _PinnedBlobError("missing_artifact", f"pinned artifact is unavailable: {path}")
    return result.stdout


def _blob_size(repository: RepositoryContext, revision: str, path: Path) -> int:
    tree = subprocess.run(
        ["git", "ls-tree", "-z", revision, "--", path.as_posix()],
        cwd=repository.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if tree.returncode != 0 or not tree.stdout:
        raise _PinnedBlobError("missing_artifact", f"pinned artifact is unavailable: {path}")
    header, separator, returned = tree.stdout.partition(b"\t")
    fields = header.split()
    if (
        separator != b"\t"
        or returned.rstrip(b"\0").decode("utf-8", "strict") != path.as_posix()
        or len(fields) != 3
        or fields[0] != b"100644"
        or fields[1] != b"blob"
    ):
        raise _PinnedBlobError("missing_artifact", f"pinned artifact is not a regular file: {path}")
    size = subprocess.run(
        ["git", "cat-file", "-s", fields[2].decode()],
        cwd=repository.root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if size.returncode != 0:
        raise _PinnedBlobError("missing_artifact", f"pinned artifact is unavailable: {path}")
    return int(size.stdout.strip())


def _commit_exists(repository: RepositoryContext, revision: object) -> bool:
    if not isinstance(revision, str) or not revision:
        return False
    return subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=repository.root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def _render_artifact_problem(artifact: object) -> tuple[str, str] | None:
    paths = (
        getattr(artifact, "semantic_workspace", None),
        getattr(artifact, "embedded_workspace", None),
        getattr(artifact, "binding_manifest", None),
        *getattr(artifact, "svg_files", ()),
    )
    for path in paths:
        if path is None:
            continue
        try:
            if Path(path).stat().st_size > _MAX_RENDERED_ARTIFACT_BYTES:
                return "oversized_artifact", Path(path).name
        except OSError:
            return "artifact_unavailable", Path(path).name
    return None


def _normalized_directory(value: str) -> str:
    if value == ".":
        return value
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("code directory must be a normalized repository-relative path")
    return candidate.as_posix()


def _local_dsl(value: object) -> Path:
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("model source must be a local DSL path")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or candidate.suffix.lower() != ".dsl"
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError("model source must be a local DSL path")
    return Path(*candidate.parts)


def _nonblank(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("model owner must be non-blank")
    return value


def _snapshot_id(descriptor: dict[str, object]) -> str:
    encoded = json.dumps(
        descriptor, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return f"architecture-snapshot-{hashlib.sha256(encoded).hexdigest()}"
