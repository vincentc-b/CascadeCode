"""Bounded, offline Structurizr rendering for validated C4 source closures."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from cascade.workspace.c4_bindings import (
    C4BindingError,
    validate_hit_target_manifest,
    verify_and_sanitize_hit_targets,
)
from cascade.workspace.c4_closure import C4SourceClosure


STRUCTURIZR_IMAGE_DIGEST = (
    "sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c"
)
STRUCTURIZR_IMAGE = f"structurizr/structurizr@{STRUCTURIZR_IMAGE_DIGEST}"
_WORKSPACE_JS = re.compile(r"const jsonAsString = '([A-Za-z0-9+/=]+)';\s*")
_VIEW_COLLECTIONS = (
    "customViews",
    "systemLandscapeViews",
    "systemContextViews",
    "containerViews",
    "componentViews",
    "dynamicViews",
    "deploymentViews",
    "filteredViews",
    "imageViews",
)
_BINDING_ADAPTER = Path(__file__).with_name("RendererBindingAdapter.java")
_BINDING_ADAPTER_SCRIPT = r"""
set -eu
mkdir -p /tmp/cascade-binding-lib /tmp/cascade-binding-classes
unzip -q /usr/local/structurizr.war \
  'WEB-INF/lib/gson-*.jar' \
  'WEB-INF/lib/playwright-*.jar' \
  'WEB-INF/lib/driver-*.jar' \
  -d /tmp/cascade-binding-lib
javac -cp '/tmp/cascade-binding-lib/WEB-INF/lib/*' \
  -d /tmp/cascade-binding-classes /adapter/RendererBindingAdapter.java
java -cp '/tmp/cascade-binding-classes:/tmp/cascade-binding-lib/WEB-INF/lib/*' \
  RendererBindingAdapter "$@"
"""
_ARTIFACT_VERSION = 3

RenderStatus = Literal[
    "first", "running", "empty", "ready", "binding_error", "render_error", "cancelled"
]
FailureCode = Literal[
    "image_unavailable",
    "validation_failed",
    "export_failed",
    "invalid_artifact",
    "binding_failed",
    "timeout",
    "internal_error",
]


@dataclass(frozen=True)
class C4RenderSettings:
    """Artifact-affecting settings and hard execution bounds."""

    # A full interactive render performs validation, semantic/static export,
    # and one trusted binding export per view.  The pinned runtime can exceed
    # 90 seconds on a cold or contended host even for two views, so retain a
    # hard bound with enough room for the supported production pipeline.
    timeout_seconds: float = 180.0
    memory: str = "1536m"
    cpus: str = "2"
    pids_limit: int = 256
    tmpfs_size: str = "512m"

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("render timeout must be positive")
        if self.pids_limit <= 0:
            raise ValueError("render pids_limit must be positive")
        for name in ("memory", "cpus", "tmpfs_size"):
            if not getattr(self, name) or any(
                character.isspace() for character in getattr(self, name)
            ):
                raise ValueError(f"render {name} must be a nonempty token")

    def cache_payload(self) -> dict[str, object]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "memory": self.memory,
            "cpus": self.cpus,
            "pids_limit": self.pids_limit,
            "tmpfs_size": self.tmpfs_size,
        }


@dataclass(frozen=True)
class C4RenderFailure:
    code: FailureCode
    stage: str
    message: str


@dataclass(frozen=True)
class C4RenderArtifact:
    """Consumer-facing state and immutable paths for one render operation."""

    status: RenderStatus
    closure_digest: str
    image_digest: str = STRUCTURIZR_IMAGE_DIGEST
    cache_key: str | None = None
    cache_hit: bool = False
    artifact_directory: Path | None = None
    semantic_workspace: Path | None = None
    semantic_workspace_sha256: str | None = None
    embedded_workspace: Path | None = None
    static_directory: Path | None = None
    svg_files: tuple[Path, ...] = ()
    binding_manifest: Path | None = None
    interactive: bool = False
    source_diff_reference: str | None = None
    view_keys: tuple[str, ...] = ()
    revision: str | None = None
    source_files: tuple[str, ...] = ()
    failure: C4RenderFailure | None = None

    @classmethod
    def first(cls, closure_digest: str = "") -> C4RenderArtifact:
        return cls(status="first", closure_digest=closure_digest)


class C4RenderOperation:
    """A cancellable background artifact operation."""

    def __init__(
        self,
        renderer: C4ArtifactRenderer,
        closure: C4SourceClosure,
        settings: C4RenderSettings,
    ) -> None:
        self._renderer = renderer
        self._closure = closure
        self._settings = settings
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._result = replace(C4RenderArtifact.first(closure.digest), status="running")
        self._thread = threading.Thread(
            target=self._work,
            name=f"c4-render-{closure.digest[:12]}",
            daemon=True,
        )
        self._thread.start()

    def snapshot(self) -> C4RenderArtifact:
        with self._lock:
            return self._result

    def cancel(self) -> bool:
        if self._done.is_set():
            return False
        self._cancel.set()
        return True

    def wait(self, timeout: float | None = None) -> C4RenderArtifact:
        if not self._done.wait(timeout):
            raise TimeoutError("C4 render operation is still running")
        return self.snapshot()

    def _work(self) -> None:
        try:
            result = self._renderer._render(self._closure, self._settings, self._cancel)
        except Exception as exc:  # Keep background failures structured for consumers.
            result = C4RenderArtifact(
                status="render_error",
                closure_digest=self._closure.digest,
                revision=self._closure.revision,
                source_files=tuple(
                    item.path.as_posix() for item in self._closure.files
                ),
                source_diff_reference=_source_diff_reference(self._closure),
                failure=C4RenderFailure("internal_error", "renderer", str(exc)),
            )
        with self._lock:
            self._result = result
        self._done.set()


class C4ArtifactRenderer:
    """Render and atomically cache artifacts from an already-confined closure."""

    def __init__(self, cache_directory: Path | str, *, runtime: str = "docker") -> None:
        self.cache_directory = Path(cache_directory).resolve()
        self.runtime = runtime

    def submit(
        self,
        closure: C4SourceClosure,
        settings: C4RenderSettings | None = None,
    ) -> C4RenderOperation:
        if not closure.input_directory.is_dir():
            raise ValueError("C4 source closure input directory does not exist")
        return C4RenderOperation(self, closure, settings or C4RenderSettings())

    def _render(
        self,
        closure: C4SourceClosure,
        settings: C4RenderSettings,
        cancelled: threading.Event,
    ) -> C4RenderArtifact:
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        snapshot = Path(
            tempfile.mkdtemp(prefix=".c4-source.", dir=self.cache_directory)
        )
        try:
            try:
                _snapshot_verified_closure(closure, snapshot)
            except (OSError, ValueError) as exc:
                return _failed(
                    closure,
                    _cache_key(closure.digest, settings),
                    "invalid_artifact",
                    "source",
                    f"C4 source closure no longer matches its provenance: {exc}",
                )
            return self._render_verified(
                replace(closure, input_directory=snapshot), settings, cancelled
            )
        finally:
            shutil.rmtree(snapshot, ignore_errors=True)

    def _render_verified(
        self,
        closure: C4SourceClosure,
        settings: C4RenderSettings,
        cancelled: threading.Event,
    ) -> C4RenderArtifact:
        cache_key = _cache_key(closure.digest, settings)
        destination = self.cache_directory / cache_key
        if destination.is_dir():
            return _load_artifact(destination, closure, cache_key, cache_hit=True)
        if cancelled.is_set():
            return _cancelled(closure, cache_key)

        temporary = Path(
            tempfile.mkdtemp(prefix=f".{cache_key}.", dir=self.cache_directory)
        )
        try:
            output = temporary / "output"
            output.mkdir()
            for name in (
                "json",
                "static",
                "svg",
                "raw-bindings",
                "raw-bound-svg",
                "bound-svg",
            ):
                (output / name).mkdir()
            if os.getuid() == 0:
                for directory in (output, *(output.iterdir())):
                    directory.chmod(0o777)
            deadline = time.monotonic() + settings.timeout_seconds
            inspected = _run_process(
                [self.runtime, "image", "inspect", STRUCTURIZR_IMAGE],
                deadline,
                cancelled,
            )
            if inspected.kind:
                return _process_failure(closure, cache_key, "image", inspected)
            try:
                image = json.loads(inspected.stdout)[0]
                if STRUCTURIZR_IMAGE not in image["RepoDigests"]:
                    raise ValueError("immutable digest is absent from local image metadata")
            except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                return _failed(
                    closure,
                    cache_key,
                    "image_unavailable",
                    "image",
                    f"pinned Structurizr image cannot be verified: {exc}",
                )

            source = f"/workspace/{closure.source.as_posix()}"
            stages = (
                ("validation", ["validate", "-workspace", source]),
                (
                    "json_export",
                    [
                        "export",
                        "-workspace",
                        source,
                        "-format",
                        "json",
                        "-output",
                        "/output/json",
                    ],
                ),
                (
                    "static_export",
                    [
                        "export",
                        "-workspace",
                        source,
                        "-format",
                        "static",
                        "-output",
                        "/output/static",
                    ],
                ),
                (
                    "svg_export",
                    [
                        "export",
                        "-workspace",
                        source,
                        "-format",
                        "svg",
                        "-output",
                        "/output/svg",
                    ],
                ),
            )
            for stage, arguments in stages:
                result = _run_process(
                    self._container_command(closure, output, settings, arguments),
                    deadline,
                    cancelled,
                )
                if result.kind:
                    return _process_failure(closure, cache_key, stage, result)

            try:
                view_keys = _validate_outputs(output)
                embedded = _embedded_workspace(output / "static" / "workspace.js")
                (output / "embedded-workspace.json").write_text(
                    json.dumps(embedded, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )
            except (OSError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
                return _failed(
                    closure,
                    cache_key,
                    "invalid_artifact",
                    "publish",
                    f"Structurizr produced invalid artifacts: {exc}",
                )

            source_diff_reference = _source_diff_reference(closure)
            binding_views: list[dict[str, object]] = []
            for index, view_key in enumerate(view_keys):
                raw_bindings = output / "raw-bindings" / f"view-{index}.json"
                raw_svg = output / "raw-bound-svg" / f"view-{index}.svg"
                bound_svg = output / "bound-svg" / f"view-{index}.svg"
                result = _run_process(
                    self._binding_command(
                        closure,
                        output,
                        settings,
                        view_key=view_key,
                        bindings=raw_bindings,
                        svg=raw_svg,
                    ),
                    deadline,
                    cancelled,
                )
                if result.kind:
                    return _process_failure(
                        closure, cache_key, f"binding:{view_key}", result
                    )
                try:
                    targets = verify_and_sanitize_hit_targets(
                        workspace=embedded,
                        view_key=view_key,
                        raw_bindings=raw_bindings,
                        raw_svg=raw_svg,
                        sanitized_svg=bound_svg,
                        expected_semantic_ids=closure.contract.semantic_ids,
                    )
                except (C4BindingError, OSError, ET.ParseError) as exc:
                    return _binding_failed(closure, cache_key, view_key, str(exc))
                binding_views.append(
                    {
                        "view_key": view_key,
                        "svg": bound_svg.relative_to(output).as_posix(),
                        "targets": [target.as_dict() for target in targets],
                    }
                )

            hit_target_manifest = {
                "version": 1,
                "interactive": True,
                "source_diff_reference": source_diff_reference,
                "views": binding_views,
            }
            (output / "hit-targets.json").write_text(
                json.dumps(hit_target_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            for transient in ("raw-bindings", "raw-bound-svg", "svg"):
                shutil.rmtree(output / transient)
            try:
                status: RenderStatus = "ready" if view_keys else "empty"
                artifact_sha256 = _directory_hashes(output)
                manifest = {
                    "version": _ARTIFACT_VERSION,
                    "status": status,
                    "cache_key": cache_key,
                    "closure_digest": closure.digest,
                    "image": STRUCTURIZR_IMAGE,
                    "image_digest": STRUCTURIZR_IMAGE_DIGEST,
                    "settings": settings.cache_payload(),
                    "revision": closure.revision,
                    "source": closure.source.as_posix(),
                    "source_provenance": _source_provenance(closure),
                    "source_files": [
                        {
                            "path": item.path.as_posix(),
                            "owner": item.owner,
                            "revision": item.revision,
                            "sha256": item.sha256,
                        }
                        for item in closure.files
                    ],
                    "view_keys": list(view_keys),
                    "binding_manifest": "hit-targets.json",
                    "interactive": True,
                    "source_diff_reference": source_diff_reference,
                    "svg_files": [
                        row["svg"] for row in binding_views
                    ],
                    "artifact_sha256": artifact_sha256,
                }
                (temporary / "manifest.json").write_text(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except (OSError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
                return _failed(
                    closure,
                    cache_key,
                    "invalid_artifact",
                    "publish",
                    f"Structurizr produced invalid artifacts: {exc}",
                )

            published = True
            try:
                os.rename(temporary, destination)
            except FileExistsError:
                published = False
            return _load_artifact(
                destination, closure, cache_key, cache_hit=not published
            )
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)

    def _binding_command(
        self,
        closure: C4SourceClosure,
        output: Path,
        settings: C4RenderSettings,
        *,
        view_key: str,
        bindings: Path,
        svg: Path,
    ) -> list[str]:
        if not _BINDING_ADAPTER.is_file():
            raise ValueError("approved renderer binding adapter is missing")
        command = self._container_command(closure, output, settings, [])
        image_index = command.index(STRUCTURIZR_IMAGE)
        command[image_index:image_index] = [
            "-v",
            f"{_BINDING_ADAPTER.resolve()}:/adapter/RendererBindingAdapter.java:ro",
            "--entrypoint",
            "/bin/sh",
        ]
        command.extend(
            [
                "-c",
                _BINDING_ADAPTER_SCRIPT,
                "cascade-binding-adapter",
                "/output/static",
                f"/output/{bindings.relative_to(output).as_posix()}",
                f"/output/{svg.relative_to(output).as_posix()}",
                view_key,
            ]
        )
        return command

    def _container_command(
        self,
        closure: C4SourceClosure,
        output: Path,
        settings: C4RenderSettings,
        arguments: list[str],
    ) -> list[str]:
        return [
            self.runtime,
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={settings.pids_limit}",
            f"--memory={settings.memory}",
            f"--cpus={settings.cpus}",
            "--tmpfs",
            f"/tmp:rw,nosuid,nodev,size={settings.tmpfs_size}",
            "--user",
            _container_identity(),
            "-e",
            "HOME=/tmp",
            "-e",
            "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
            "-e",
            "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1",
            "-v",
            f"{closure.input_directory.resolve()}:/workspace:ro",
            "-v",
            f"{output.resolve()}:/output:rw",
            STRUCTURIZR_IMAGE,
            *arguments,
        ]


@dataclass(frozen=True)
class _ProcessResult:
    kind: Literal["", "cancelled", "timeout", "failed"]
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _run_process(
    command: list[str], deadline: float, cancelled: threading.Event
) -> _ProcessResult:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return _ProcessResult("timeout", -1)
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file:
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file:
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    start_new_session=True,
                )
            except OSError as exc:
                return _ProcessResult("failed", -1, stderr=str(exc))
            while process.poll() is None:
                wait = min(0.1, max(0.0, deadline - time.monotonic()))
                if cancelled.wait(wait):
                    _stop_process(process)
                    return _ProcessResult("cancelled", process.returncode or -1)
                if time.monotonic() >= deadline:
                    _stop_process(process)
                    return _ProcessResult("timeout", process.returncode or -1)
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read()
            stderr = stderr_file.read()
            return _ProcessResult(
                "" if process.returncode == 0 else "failed",
                process.returncode,
                stdout[-8192:],
                stderr[-8192:],
            )


def _stop_process(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def _container_identity() -> str:
    """Return an explicit non-root identity even for root-run host services."""
    if os.getuid() == 0:
        return "65532:65532"
    return f"{os.getuid()}:{os.getgid()}"


def _process_failure(
    closure: C4SourceClosure,
    cache_key: str,
    stage: str,
    process: _ProcessResult,
) -> C4RenderArtifact:
    if process.kind == "cancelled":
        return _cancelled(closure, cache_key)
    if process.kind == "timeout":
        return _failed(
            closure, cache_key, "timeout", stage, "Structurizr render exceeded its deadline"
        )
    detail = (process.stderr or process.stdout).strip()
    message = f"Structurizr {stage} exited {process.returncode}"
    if detail:
        message = f"{message}: {detail}"
    if stage.startswith("binding:"):
        return _binding_failed(closure, cache_key, stage.split(":", 1)[1], message)
    code: FailureCode = (
        "image_unavailable"
        if stage == "image"
        else "validation_failed"
        if stage == "validation"
        else "export_failed"
    )
    return _failed(closure, cache_key, code, stage, message)


def _failed(
    closure: C4SourceClosure,
    cache_key: str,
    code: FailureCode,
    stage: str,
    message: str,
) -> C4RenderArtifact:
    return C4RenderArtifact(
        status="render_error",
        closure_digest=closure.digest,
        cache_key=cache_key,
        revision=closure.revision,
        source_files=tuple(item.path.as_posix() for item in closure.files),
        source_diff_reference=_source_diff_reference(closure),
        failure=C4RenderFailure(code, stage, message),
    )


def _binding_failed(
    closure: C4SourceClosure,
    cache_key: str,
    view_key: str,
    message: str,
) -> C4RenderArtifact:
    return C4RenderArtifact(
        status="binding_error",
        closure_digest=closure.digest,
        cache_key=cache_key,
        revision=closure.revision,
        source_files=tuple(item.path.as_posix() for item in closure.files),
        interactive=False,
        source_diff_reference=_source_diff_reference(closure),
        failure=C4RenderFailure("binding_failed", f"binding:{view_key}", message),
    )


def _cancelled(closure: C4SourceClosure, cache_key: str) -> C4RenderArtifact:
    return C4RenderArtifact(
        status="cancelled",
        closure_digest=closure.digest,
        cache_key=cache_key,
        revision=closure.revision,
        source_files=tuple(item.path.as_posix() for item in closure.files),
        source_diff_reference=_source_diff_reference(closure),
    )


def _source_diff_reference(closure: C4SourceClosure) -> str:
    paths = ",".join(
        (closure.architecture_root / item.path).as_posix() for item in closure.files
    )
    return f"revision:{closure.revision};paths:{paths}"


def _source_provenance(closure: C4SourceClosure) -> dict[str, object]:
    return {
        "target_repository_key": closure.target_repository_key,
        "destination_repository_key": closure.destination_repository_key,
        "destination_repository_role": closure.destination_repository_role,
        "architecture_root": closure.architecture_root.as_posix(),
        "source": closure.source.as_posix(),
        "revision": closure.revision,
        "closure_digest": closure.digest,
    }


def _snapshot_verified_closure(closure: C4SourceClosure, snapshot: Path) -> None:
    """Copy only hash-verified closure bytes into the renderer's private input."""

    computed_digest = closure.computed_digest()
    if computed_digest != closure.digest:
        raise ValueError(
            "closure provenance digest changed; "
            f"expected={closure.digest}, actual={computed_digest}"
        )
    expected: dict[Path, str] = {}
    for item in closure.files:
        path = item.path
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise ValueError(f"invalid closure path {path.as_posix()!r}")
        if path in expected:
            raise ValueError(f"duplicate closure path {path.as_posix()!r}")
        expected[path] = item.sha256
    if closure.source not in expected:
        raise ValueError("workspace source is absent from the closure")

    actual: set[Path] = set()
    for path in closure.input_directory.rglob("*"):
        relative = path.relative_to(closure.input_directory)
        if path.is_symlink():
            raise ValueError(f"source closure contains symlink {relative.as_posix()!r}")
        if path.is_file():
            actual.add(relative)
        elif not path.is_dir():
            raise ValueError(f"source closure contains special file {relative.as_posix()!r}")
    missing = sorted(path.as_posix() for path in set(expected) - actual)
    extra = sorted(path.as_posix() for path in actual - set(expected))
    if missing or extra:
        raise ValueError(f"source file inventory changed; missing={missing}, extra={extra}")

    snapshot.chmod(0o755)
    for relative, expected_hash in expected.items():
        source = closure.input_directory / relative
        descriptor = os.open(
            source,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb") as source_file:
            if not stat.S_ISREG(os.fstat(source_file.fileno()).st_mode):
                raise ValueError(
                    f"source closure contains non-regular file {relative.as_posix()!r}"
                )
            content = source_file.read()
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(
                f"source file {relative.as_posix()!r} digest changed; "
                f"expected={expected_hash}, actual={actual_hash}"
            )
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.parent.chmod(0o755)
        destination.write_bytes(content)
        destination.chmod(0o444)


def _directory_hashes(directory: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            raise ValueError(f"artifact contains symlink {relative!r}")
        if path.is_file():
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif not path.is_dir():
            raise ValueError(f"artifact contains special file {relative!r}")
    return hashes


def _cache_key(closure_digest: str, settings: C4RenderSettings) -> str:
    encoded = json.dumps(
        {
            "artifact_version": _ARTIFACT_VERSION,
            "closure_digest": closure_digest,
            "image_digest": STRUCTURIZR_IMAGE_DIGEST,
            "settings": settings.cache_payload(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _embedded_workspace(path: Path) -> dict[str, object]:
    match = _WORKSPACE_JS.fullmatch(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("unexpected static workspace.js wrapper")
    decoded = base64.b64decode(match.group(1), validate=True)
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("embedded workspace is not an object")
    return payload


def _view_keys(workspace: dict[str, object]) -> tuple[str, ...]:
    views = workspace.get("views")
    if not isinstance(views, dict):
        raise ValueError("workspace JSON has no views object")
    keys: list[str] = []
    for collection_name in _VIEW_COLLECTIONS:
        collection = views.get(collection_name, [])
        if not isinstance(collection, list):
            raise ValueError(f"workspace view collection {collection_name} is invalid")
        for view in collection:
            if not isinstance(view, dict) or not isinstance(view.get("key"), str):
                raise ValueError(f"workspace view in {collection_name} has no key")
            keys.append(view["key"])
    if len(keys) != len(set(keys)):
        raise ValueError("workspace JSON contains duplicate view keys")
    return tuple(sorted(keys))


def _validate_outputs(
    output: Path, *, require_stock_svg: bool = True
) -> tuple[str, ...]:
    semantic = json.loads((output / "json" / "workspace.json").read_text(encoding="utf-8"))
    embedded = _embedded_workspace(output / "static" / "workspace.js")
    semantic_keys = _view_keys(semantic)
    if semantic_keys != _view_keys(embedded):
        raise ValueError("semantic and static exports disagree on view inventory")
    if require_stock_svg:
        svg_files = sorted((output / "svg").glob("*.svg"))
        for svg in svg_files:
            root = ET.parse(svg).getroot()
            if root.tag.rsplit("}", 1)[-1] != "svg":
                raise ValueError(f"export is not SVG: {svg.name}")
        if semantic_keys and not svg_files:
            raise ValueError("no SVG files were exported for nonempty views")
    if not (output / "static" / "index.html").is_file():
        raise ValueError("static export has no index.html")
    return semantic_keys


def _load_artifact(
    directory: Path,
    closure: C4SourceClosure,
    cache_key: str,
    *,
    cache_hit: bool,
) -> C4RenderArtifact:
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if (
            manifest["version"] != _ARTIFACT_VERSION
            or manifest["cache_key"] != cache_key
            or manifest["closure_digest"] != closure.digest
            or manifest["image_digest"] != STRUCTURIZR_IMAGE_DIGEST
            or manifest["image"] != STRUCTURIZR_IMAGE
            or _cache_key(
                closure.digest, C4RenderSettings(**manifest["settings"])
            )
            != cache_key
            or manifest["revision"] != closure.revision
            or manifest["source"] != closure.source.as_posix()
            or manifest["source_provenance"] != _source_provenance(closure)
        ):
            raise ValueError("cache manifest provenance does not match request")
        expected_sources = [
            {
                "path": item.path.as_posix(),
                "owner": item.owner,
                "revision": item.revision,
                "sha256": item.sha256,
            }
            for item in closure.files
        ]
        if manifest["source_files"] != expected_sources:
            raise ValueError("cache manifest source provenance does not match request")
        output = directory / "output"
        if manifest["artifact_sha256"] != _directory_hashes(output):
            raise ValueError("cache artifact bytes do not match their manifest")
        view_keys = _validate_outputs(output, require_stock_svg=False)
        if list(view_keys) != manifest["view_keys"]:
            raise ValueError("cache manifest view inventory is invalid")
        status = manifest["status"]
        if status not in ("ready", "empty"):
            raise ValueError("cache manifest status is invalid")
        source_diff_reference = _source_diff_reference(closure)
        if (
            manifest["binding_manifest"] != "hit-targets.json"
            or manifest["interactive"] is not True
            or manifest["source_diff_reference"] != source_diff_reference
        ):
            raise ValueError("cache manifest binding contract is invalid")
        binding_manifest = output / manifest["binding_manifest"]
        binding_payload = json.loads(binding_manifest.read_text(encoding="utf-8"))
        if (
            not isinstance(binding_payload, dict)
            or binding_payload.get("source_diff_reference") != source_diff_reference
        ):
            raise ValueError("hit-target source diff reference is stale")
        embedded = json.loads(
            (output / "embedded-workspace.json").read_text(encoding="utf-8")
        )
        if not isinstance(embedded, dict):
            raise ValueError("embedded workspace cache is invalid")
        if embedded != _embedded_workspace(output / "static" / "workspace.js"):
            raise ValueError("embedded workspace cache is stale")
        svg_files = validate_hit_target_manifest(
            workspace=embedded,
            manifest=binding_payload,
            artifact_root=output,
            expected_view_keys=view_keys,
            expected_semantic_ids=closure.contract.semantic_ids,
        )
        if [path.relative_to(output).as_posix() for path in svg_files] != manifest[
            "svg_files"
        ]:
            raise ValueError("cache manifest bound SVG inventory is invalid")
    except (
        C4BindingError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        ET.ParseError,
    ) as exc:
        return _failed(
            closure,
            cache_key,
            "invalid_artifact",
            "cache",
            f"cached Structurizr artifact is invalid: {exc}",
        )
    return C4RenderArtifact(
        status=status,
        closure_digest=closure.digest,
        cache_key=cache_key,
        cache_hit=cache_hit,
        artifact_directory=directory,
        semantic_workspace=output / "json" / "workspace.json",
        semantic_workspace_sha256=manifest["artifact_sha256"]["json/workspace.json"],
        embedded_workspace=output / "embedded-workspace.json",
        static_directory=output / "static",
        svg_files=svg_files,
        binding_manifest=binding_manifest,
        interactive=True,
        source_diff_reference=source_diff_reference,
        view_keys=view_keys,
        revision=closure.revision,
        source_files=tuple(item["path"] for item in manifest["source_files"]),
    )
