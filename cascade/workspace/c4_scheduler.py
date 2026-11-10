"""Project-scoped, durable scheduling for C4 artifact renders."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from cascade.task.lifecycle_lock import task_lifecycle_lock, task_lifecycle_read_lock
from cascade.workspace.c4_closure import C4SourceClosure, C4SourceFile
from cascade.workspace.c4_render import (
    STRUCTURIZR_IMAGE_DIGEST,
    C4ArtifactRenderer,
    C4RenderArtifact,
    C4RenderFailure,
    C4RenderSettings,
    _ARTIFACT_VERSION,
    _BINDING_ADAPTER,
    _snapshot_verified_closure,
)
from cascade.workspace.c4_source import C4SourceError, validate_c4_workspace


ScheduledStatus = Literal["pending", "running", "ready", "empty", "failed", "cancelled"]
_LEDGER_VERSION = 1
_ADAPTER_FORMAT = 1


class C4RenderAdmissionError(RuntimeError):
    """A stable scheduler admission failure suitable for an HTTP adapter."""

    def __init__(self, code: str, message: str, *, retry_after_seconds: int | None = None) -> None:
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class C4ScheduledRender:
    operation_id: str
    render_identity: str
    status: ScheduledStatus
    owner: str
    snapshot_id: str
    attempts: int
    recovery_attempts: int
    created_at: float
    updated_at: float
    failure: C4RenderFailure | None = None
    artifact: C4RenderArtifact | None = None


class C4ScheduledRenderOperation:
    """A durable operation handle; reads never start rendering."""

    def __init__(self, scheduler: "C4RenderScheduler", operation_id: str) -> None:
        self._scheduler = scheduler
        self.operation_id = operation_id

    def snapshot(self) -> C4ScheduledRender:
        return self._scheduler.get(self.operation_id)

    def wait(self, timeout: float | None = None) -> C4ScheduledRender:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            result = self.snapshot()
            if result.status not in {"pending", "running"}:
                return result
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("C4 scheduled render is still running")
            time.sleep(0.02)

    def cancel(self) -> bool:
        return self._scheduler.cancel(self.operation_id)


class C4RenderScheduler:
    """Admit and run a bounded number of renders for one project.

    The ledger and source snapshots are operational metadata.  Review and
    acceptance authority remains in :class:`ArchitectureReviewStore`.
    """

    def __init__(
        self,
        project_root: Path | str,
        *,
        renderer: C4ArtifactRenderer | None = None,
        max_active: int = 1,
        max_pending: int = 32,
        ledger_path: Path | str | None = None,
        start_worker: bool = True,
    ) -> None:
        if max_active < 1 or max_pending < 0:
            raise ValueError("render scheduler bounds must be non-negative with an active worker")
        self.project_root = Path(project_root).resolve()
        self.renderer = renderer or C4ArtifactRenderer(
            self.project_root / ".cascade" / "c4-render-cache"
        )
        self.max_active = max_active
        self.max_pending = max_pending
        self.ledger_path = Path(ledger_path).resolve() if ledger_path else (
            self.project_root / ".cascade" / "c4-render-operations.json"
        )
        self.source_directory = self.ledger_path.parent / "c4-render-sources"
        self._worker_id = f"{os.getpid()}:{uuid.uuid4().hex}"
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.reconcile()
        if start_worker:
            for index in range(max_active):
                thread = threading.Thread(
                    target=self._worker,
                    name=f"c4-render-scheduler-{index}",
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)
            self._wake.set()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=1)

    def __enter__(self) -> "C4RenderScheduler":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def admit(
        self,
        closure: C4SourceClosure,
        settings: C4RenderSettings | None = None,
        *,
        owner: str,
        snapshot_id: str,
    ) -> C4ScheduledRenderOperation:
        if not owner.strip() or not snapshot_id.strip():
            raise ValueError("render owner and snapshot ID must be non-blank")
        chosen = settings or C4RenderSettings()
        identity = render_identity(closure.digest, chosen)
        operation_id = f"c4-render-{identity}"
        now = time.time()
        with task_lifecycle_lock(root=self.project_root):
            ledger = self._read()
            existing = ledger["operations"].get(operation_id)
            if existing is not None:
                if existing["owner"] != owner or existing["snapshot_id"] != snapshot_id:
                    associations = existing.setdefault("associations", [])
                    association = {"owner": owner, "snapshot_id": snapshot_id}
                    if association not in associations:
                        associations.append(association)
                        existing["updated_at"] = now
                        self._write(ledger)
                return C4ScheduledRenderOperation(self, operation_id)
            pending = sum(
                row["status"] == "pending" for row in ledger["operations"].values()
            )
            running = sum(
                row["status"] == "running" for row in ledger["operations"].values()
            )
            # One admission may become active immediately; the pending bound is
            # deliberately independent of the active bound.
            if pending + running >= self.max_pending + self.max_active:
                raise C4RenderAdmissionError(
                    "queue_full",
                    "the project render queue is full; retry after an active render completes",
                    retry_after_seconds=2,
                )
            source = self.source_directory / operation_id
            self._snapshot_source(closure, source)
            ledger["operations"][operation_id] = {
                "operation_id": operation_id,
                "render_identity": identity,
                "status": "pending",
                "owner": owner,
                "snapshot_id": snapshot_id,
                "associations": [],
                "closure": _closure_to_dict(closure),
                "settings": chosen.cache_payload(),
                "source_directory": source.relative_to(self.ledger_path.parent).as_posix(),
                "attempts": 0,
                "recovery_attempts": 0,
                "explicit_retries": 0,
                "created_at": now,
                "updated_at": now,
                "lease": None,
                "failure": None,
                "artifact": None,
            }
            self._write(ledger)
        self._wake.set()
        return C4ScheduledRenderOperation(self, operation_id)

    def get(self, operation_id: str) -> C4ScheduledRender:
        with task_lifecycle_read_lock(root=self.project_root):
            row = self._read()["operations"].get(operation_id)
        if row is None:
            raise KeyError(operation_id)
        return _scheduled_from_row(row)

    def retry(self, operation_id: str) -> C4ScheduledRenderOperation:
        with task_lifecycle_lock(root=self.project_root):
            ledger = self._read()
            row = ledger["operations"].get(operation_id)
            if row is None:
                raise KeyError(operation_id)
            if row["status"] not in {"failed", "cancelled"}:
                raise C4RenderAdmissionError("retry_not_allowed", "only failed renders may be retried")
            if not self._source_path(row).is_dir():
                raise C4RenderAdmissionError("source_unavailable", "the exact render source is unavailable")
            admitted = sum(
                candidate["status"] in {"pending", "running"}
                for candidate in ledger["operations"].values()
            )
            if admitted >= self.max_pending + self.max_active:
                raise C4RenderAdmissionError(
                    "queue_full",
                    "the project render queue is full; retry after an active render completes",
                    retry_after_seconds=2,
                )
            row.update(
                status="pending", lease=None, failure=None, artifact=None,
                explicit_retries=row["explicit_retries"] + 1, updated_at=time.time(),
            )
            self._write(ledger)
        self._wake.set()
        return C4ScheduledRenderOperation(self, operation_id)

    def cancel(self, operation_id: str) -> bool:
        with task_lifecycle_lock(root=self.project_root):
            ledger = self._read()
            row = ledger["operations"].get(operation_id)
            if row is None:
                raise KeyError(operation_id)
            if row["status"] != "pending":
                return False
            row.update(status="cancelled", updated_at=time.time())
            self._write(ledger)
            return True

    def reconcile(self) -> None:
        """Recover interrupted work once without rendering on the caller thread."""

        changed = False
        with task_lifecycle_lock(root=self.project_root):
            ledger = self._read()
            for row in ledger["operations"].values():
                if row["status"] != "running" or _lease_is_live(row.get("lease")):
                    continue
                row["lease"] = None
                row["updated_at"] = time.time()
                if row["recovery_attempts"] < 1:
                    row["recovery_attempts"] += 1
                    row["status"] = "pending"
                else:
                    row["status"] = "failed"
                    row["failure"] = {
                        "code": "internal_error",
                        "stage": "scheduler",
                        "message": "render worker was interrupted after its automatic recovery attempt",
                    }
                changed = True
            if changed:
                self._write(ledger)
        if changed:
            self._wake.set()

    def _worker(self) -> None:
        while not self._stop.is_set():
            row = self._claim()
            if row is None:
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            operation_id = row["operation_id"]
            try:
                closure = _closure_from_row(row, self._source_path(row))
                settings = C4RenderSettings(**row["settings"])
                result = self.renderer.submit(closure, settings).wait(
                    timeout=settings.timeout_seconds + 5
                )
            except (C4SourceError, OSError, ValueError) as exc:
                result = C4RenderArtifact(
                    status="render_error",
                    closure_digest=row["closure"]["digest"],
                    failure=C4RenderFailure("invalid_artifact", "source", str(exc)),
                )
            except Exception as exc:
                result = C4RenderArtifact(
                    status="render_error",
                    closure_digest=row["closure"]["digest"],
                    failure=C4RenderFailure("internal_error", "scheduler", str(exc)),
                )
            self._finish(operation_id, result)

    def _claim(self) -> dict[str, object] | None:
        with task_lifecycle_lock(root=self.project_root):
            ledger = self._read()
            active = sum(row["status"] == "running" for row in ledger["operations"].values())
            if active >= self.max_active:
                return None
            rows = sorted(
                (row for row in ledger["operations"].values() if row["status"] == "pending"),
                key=lambda row: (row["created_at"], row["operation_id"]),
            )
            if not rows:
                return None
            row = rows[0]
            settings = C4RenderSettings(**row["settings"])
            row["status"] = "running"
            row["attempts"] += 1
            row["updated_at"] = time.time()
            row["lease"] = {
                "worker_id": self._worker_id,
                "pid": os.getpid(),
                "expires_at": time.time() + settings.timeout_seconds + 10,
            }
            self._write(ledger)
            return json.loads(json.dumps(row))

    def _finish(self, operation_id: str, result: C4RenderArtifact) -> None:
        with task_lifecycle_lock(root=self.project_root):
            ledger = self._read()
            row = ledger["operations"].get(operation_id)
            if row is None or row["status"] != "running":
                return
            lease = row.get("lease") or {}
            if lease.get("worker_id") != self._worker_id:
                return
            status: ScheduledStatus
            if result.status in {"ready", "empty"}:
                status = result.status
                row["artifact"] = _artifact_to_dict(result)
                row["failure"] = None
            elif result.status == "cancelled":
                status = "cancelled"
                row["failure"] = _failure_to_dict(result.failure)
            else:
                status = "failed"
                row["failure"] = _failure_to_dict(result.failure) or {
                    "code": "internal_error", "stage": "scheduler",
                    "message": f"renderer ended in {result.status}",
                }
            row.update(status=status, lease=None, updated_at=time.time())
            self._write(ledger)
        self._wake.set()

    def _snapshot_source(self, closure: C4SourceClosure, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
        try:
            _snapshot_verified_closure(closure, temporary)
            # A crash after snapshotting but before the atomic ledger write can
            # leave only this operation-owned directory behind.
            if destination.exists():
                shutil.rmtree(destination)
            os.replace(temporary, destination)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def _source_path(self, row: dict[str, object]) -> Path:
        relative = Path(str(row["source_directory"]))
        path = (self.ledger_path.parent / relative).resolve()
        if self.ledger_path.parent.resolve() not in path.parents:
            raise ValueError("render source path escapes operational metadata")
        return path

    def _read(self) -> dict[str, object]:
        if not self.ledger_path.exists():
            return {"version": _LEDGER_VERSION, "operations": {}}
        try:
            value = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"invalid C4 render ledger: {self.ledger_path}") from exc
        if (
            not isinstance(value, dict) or value.get("version") != _LEDGER_VERSION
            or set(value) != {"version", "operations"}
            or not isinstance(value["operations"], dict)
        ):
            raise RuntimeError(f"unsupported C4 render ledger: {self.ledger_path}")
        return value

    def _write(self, ledger: dict[str, object]) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{self.ledger_path.name}.", dir=self.ledger_path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(ledger, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.ledger_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def render_identity(closure_digest: str, settings: C4RenderSettings) -> str:
    """Versioned identity for every byte-affecting renderer input."""

    payload = {
        "closure_digest": closure_digest,
        "image_digest": STRUCTURIZR_IMAGE_DIGEST,
        "artifact_version": _ARTIFACT_VERSION,
        "adapter_format": _ADAPTER_FORMAT,
        "adapter_sha256": hashlib.sha256(_BINDING_ADAPTER.read_bytes()).hexdigest(),
        "settings": settings.cache_payload(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _closure_to_dict(closure: C4SourceClosure) -> dict[str, object]:
    return {
        "target_repository_key": closure.target_repository_key,
        "destination_repository_key": closure.destination_repository_key,
        "destination_repository_role": closure.destination_repository_role,
        "code_directory": closure.code_directory.as_posix(),
        "design_owner_directory": closure.design_owner_directory.as_posix(),
        "revision": closure.revision,
        "architecture_root": closure.architecture_root.as_posix(),
        "source": closure.source.as_posix(),
        "digest": closure.digest,
        "files": [
            {**asdict(item), "path": item.path.as_posix(),
             "repository_path": item.repository_path.as_posix()}
            for item in closure.files
        ],
    }


def _closure_from_row(row: dict[str, object], source_directory: Path) -> C4SourceClosure:
    value = row["closure"]
    files = tuple(
        C4SourceFile(
            path=Path(item["path"]), repository_path=Path(item["repository_path"]),
            owner=item["owner"], revision=item["revision"], sha256=item["sha256"],
        )
        for item in value["files"]
    )
    closure = C4SourceClosure(
        target_repository_key=value["target_repository_key"],
        destination_repository_key=value["destination_repository_key"],
        destination_repository_role=value["destination_repository_role"],
        code_directory=Path(value["code_directory"]),
        design_owner_directory=Path(value["design_owner_directory"]),
        revision=value["revision"], architecture_root=Path(value["architecture_root"]),
        source=Path(value["source"]), files=files, digest=value["digest"],
        input_directory=source_directory, contract=validate_c4_workspace(source_directory),
    )
    if closure.computed_digest() != closure.digest:
        raise ValueError("durable C4 closure identity is invalid")
    return closure


def _artifact_to_dict(artifact: C4RenderArtifact) -> dict[str, object]:
    return {
        "status": artifact.status,
        "closure_digest": artifact.closure_digest,
        "image_digest": artifact.image_digest,
        "cache_key": artifact.cache_key,
        "cache_hit": artifact.cache_hit,
        "artifact_directory": str(artifact.artifact_directory) if artifact.artifact_directory else None,
        "semantic_workspace": str(artifact.semantic_workspace) if artifact.semantic_workspace else None,
        "semantic_workspace_sha256": artifact.semantic_workspace_sha256,
        "embedded_workspace": str(artifact.embedded_workspace) if artifact.embedded_workspace else None,
        "static_directory": str(artifact.static_directory) if artifact.static_directory else None,
        "svg_files": [str(path) for path in artifact.svg_files],
        "binding_manifest": str(artifact.binding_manifest) if artifact.binding_manifest else None,
        "interactive": artifact.interactive,
        "source_diff_reference": artifact.source_diff_reference,
        "view_keys": list(artifact.view_keys),
        "revision": artifact.revision,
        "source_files": list(artifact.source_files),
    }


def _artifact_from_dict(value: dict[str, object] | None) -> C4RenderArtifact | None:
    if value is None:
        return None
    artifact_directory = Path(value["artifact_directory"]) if value["artifact_directory"] else None
    semantic_workspace = Path(value["semantic_workspace"]) if value["semantic_workspace"] else None
    embedded_workspace = Path(value["embedded_workspace"]) if value["embedded_workspace"] else None
    static_directory = Path(value["static_directory"]) if value["static_directory"] else None
    binding_manifest = Path(value["binding_manifest"]) if value["binding_manifest"] else None
    return C4RenderArtifact(
        status=value["status"], closure_digest=value["closure_digest"],
        image_digest=value["image_digest"], cache_key=value["cache_key"],
        cache_hit=value["cache_hit"],
        artifact_directory=artifact_directory, semantic_workspace=semantic_workspace,
        semantic_workspace_sha256=value["semantic_workspace_sha256"],
        embedded_workspace=embedded_workspace, static_directory=static_directory,
        svg_files=tuple(Path(path) for path in value["svg_files"]),
        binding_manifest=binding_manifest, interactive=value["interactive"],
        source_diff_reference=value["source_diff_reference"],
        view_keys=tuple(value["view_keys"]), revision=value["revision"],
        source_files=tuple(value["source_files"]),
    )


def _failure_to_dict(failure: C4RenderFailure | None) -> dict[str, str] | None:
    return asdict(failure) if failure else None


def _scheduled_from_row(row: dict[str, object]) -> C4ScheduledRender:
    failure = C4RenderFailure(**row["failure"]) if row.get("failure") else None
    return C4ScheduledRender(
        operation_id=row["operation_id"], render_identity=row["render_identity"],
        status=row["status"], owner=row["owner"], snapshot_id=row["snapshot_id"],
        attempts=row["attempts"], recovery_attempts=row["recovery_attempts"],
        created_at=row["created_at"], updated_at=row["updated_at"], failure=failure,
        artifact=_artifact_from_dict(row.get("artifact")),
    )


def _lease_is_live(lease: object) -> bool:
    if not isinstance(lease, dict):
        return False
    expires = lease.get("expires_at")
    pid = lease.get("pid")
    if not isinstance(expires, (int, float)) or expires <= time.time() or not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True
