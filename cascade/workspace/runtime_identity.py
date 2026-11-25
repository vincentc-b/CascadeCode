"""Reviewed deployment authority and independently checked worker evidence."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

from cascade.workspace.errors import WorkspaceError
from cascade.workspace.source_fingerprint import source_fingerprint

ENV_RUNTIME_AUTHORITY = "CASCADE_RUNTIME_AUTHORITY"
_SCHEMA_VERSION = 2
_RECEIPT_VERSION = 1
_REVISION_LENGTH = 40

# Resolve these lazy recovery/delivery entry points before measuring startup.
REQUIRED_RUNTIME_CALLABLES: dict[str, tuple[str, ...]] = {
    "cascade.feature.repair": ("feature_repair",),
    "cascade.feature.recovery": ("recover_task",),
    "cascade.feature.audit_recovery": ("retry_owned_publication",),
    "cascade.task_rollup": ("retry_pending_task_merges",),
    "cascade.watchdog.incident_postcheck": ("reconcile_parent_lifecycle_incident",),
    "cascade.watchdog.capabilities": ("default_capability_registry",),
}


class RuntimeAuthority(TypedDict):
    version: int
    manifest_id: str
    manifest_signature: str
    deployment_receipt_id: str
    accepted_review_url: str
    authorized_actor: str
    environment: str
    reviewed_repository: str
    reviewed_revision: str
    integrated_repository: str
    integrated_revision: str
    installed_source_root: str
    installed_source_sha256: str


class LoadedModule(TypedDict):
    origin: str
    sha256: str
    callables: list[str]


class LoadedRuntimeIdentity(TypedDict):
    verified: bool
    reason: str | None
    authority_manifest_id: str | None
    deployment_receipt_id: str | None
    accepted_review_url: str | None
    authorized_actor: str | None
    environment: str | None
    reviewed_revision: str | None
    integrated_revision: str | None
    reviewed_repository: str | None
    integrated_repository: str | None
    installed_source_root: str
    installed_source_sha256: str
    workspace_root: str
    python_executable: str
    worker_pid: int
    process_start_id: str
    capability_generation: str
    loaded_modules: dict[str, LoadedModule]
    started_at: str
    host_verified_at: NotRequired[str]
    host_boot_id: NotRequired[str]
    host_process_start_id: NotRequired[str]


class RuntimeVerificationResult(TypedDict):
    state: Literal["current", "pending", "refused"]
    reason: str | None
    identity: LoadedRuntimeIdentity | None


def installed_source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def create_runtime_authority(
    reviewed_source: Path,
    *,
    integrated_source: Path,
    deployment_receipt: Path,
    authority_key: Path,
    output: Path,
) -> RuntimeAuthority:
    """Bind a signed external deployment receipt to inspected local evidence."""

    key = _read_authority_key(authority_key)
    receipt = _load_signed_deployment_receipt(deployment_receipt, key)
    reviewed_repository = Path(reviewed_source).resolve()
    integrated_repository = Path(integrated_source).resolve()
    if reviewed_repository != Path(str(receipt["reviewed_repository"])).resolve():
        raise WorkspaceError("deployment receipt names a different reviewed repository")
    if integrated_repository != Path(str(receipt["integrated_repository"])).resolve():
        raise WorkspaceError("deployment receipt names a different integrated repository")

    reviewed = str(receipt["reviewed_revision"])
    integrated = str(receipt["integrated_revision"])
    _require_clean_exact_checkout(reviewed_repository, reviewed, "reviewed")
    _require_clean_exact_checkout(integrated_repository, integrated, "integrated")
    _require_commit(integrated_repository, reviewed, "accepted review revision")
    if not _is_ancestor(integrated_repository, reviewed, integrated):
        raise WorkspaceError("accepted review revision is not integrated into the guarded target")

    reviewed_package = reviewed_repository / "cascade"
    if not reviewed_package.is_dir():
        raise WorkspaceError(f"reviewed checkout has no Cascade package: {reviewed_package}")
    installed_root = installed_source_root()
    reviewed_fingerprint = source_fingerprint(reviewed_package)
    installed_fingerprint = source_fingerprint(installed_root)
    if reviewed_fingerprint != installed_fingerprint:
        raise WorkspaceError("installed Cascade source does not match accepted review source")
    if installed_fingerprint != receipt["installed_source_sha256"]:
        raise WorkspaceError("installed Cascade source does not match installation receipt")

    body: dict[str, object] = {
        "version": _SCHEMA_VERSION,
        "deployment_receipt_id": receipt["receipt_id"],
        "accepted_review_url": receipt["accepted_review_url"],
        "authorized_actor": receipt["authorized_actor"],
        "environment": receipt["environment"],
        "reviewed_repository": str(reviewed_repository),
        "reviewed_revision": reviewed,
        "integrated_repository": str(integrated_repository),
        "integrated_revision": integrated,
        "installed_source_root": str(installed_root),
        "installed_source_sha256": installed_fingerprint,
    }
    body["manifest_id"] = _manifest_id(body)
    body["manifest_signature"] = _signature(body, key)
    authority = _parse_authority(body)
    output_path = Path(output).resolve()
    if output_path.is_relative_to(reviewed_repository) or output_path.is_relative_to(integrated_repository):
        raise WorkspaceError("runtime authority output must be outside source checkouts")
    _atomic_write_json(output_path, authority)
    return authority


def load_runtime_authority(path: Path, *, authority_key: Path) -> RuntimeAuthority:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"runtime authority manifest is unavailable: {exc}") from exc
    authority = _parse_authority(raw)
    validate_runtime_authority(authority, authority_key=authority_key)
    return authority


def authority_from_environment() -> RuntimeAuthority | None:
    """Read the launcher's already-authenticated immutable snapshot."""

    raw = os.environ.get(ENV_RUNTIME_AUTHORITY)
    if raw is None:
        return None
    try:
        return _parse_authority(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise WorkspaceError("launcher runtime authority is invalid JSON") from exc


def encode_runtime_authority(authority: RuntimeAuthority) -> str:
    return json.dumps(authority, sort_keys=True, separators=(",", ":"))


def validate_runtime_authority(authority: RuntimeAuthority, *, authority_key: Path) -> None:
    """Authenticate and reject moved, dirty, stale, or conflicting evidence."""

    key = _read_authority_key(authority_key)
    signature = authority["manifest_signature"]
    signed = dict(authority)
    signed.pop("manifest_signature")
    if not hmac.compare_digest(signature, _signature(signed, key)):
        raise WorkspaceError("runtime authority signature is invalid")
    reviewed = Path(authority["reviewed_repository"])
    integrated = Path(authority["integrated_repository"])
    _require_clean_exact_checkout(reviewed, authority["reviewed_revision"], "reviewed")
    _require_clean_exact_checkout(integrated, authority["integrated_revision"], "integrated")
    _require_commit(integrated, authority["reviewed_revision"], "accepted review revision")
    if not _is_ancestor(integrated, authority["reviewed_revision"], authority["integrated_revision"]):
        raise WorkspaceError("accepted review is no longer in the integrated target")
    installed_root = installed_source_root()
    if installed_root != Path(authority["installed_source_root"]):
        raise WorkspaceError("runtime authority names a different installed source root")
    measured = source_fingerprint(installed_root)
    if measured != authority["installed_source_sha256"]:
        raise WorkspaceError("installed Cascade source changed after bootstrap")
    if source_fingerprint(reviewed / "cascade") != measured:
        raise WorkspaceError("accepted review source no longer matches installed source")


def loaded_runtime_identity(
    authority: RuntimeAuthority | None,
    *,
    workspace_root: Path,
    capability_generation: str,
    started_at: str,
) -> LoadedRuntimeIdentity:
    """Report actual imported modules; only the launcher marks them verified."""

    pid = os.getpid()
    root = installed_source_root()
    result: LoadedRuntimeIdentity = {
        "verified": False,
        "reason": "host_verification_pending" if authority else "runtime_authority_missing",
        "authority_manifest_id": authority["manifest_id"] if authority else None,
        "deployment_receipt_id": authority["deployment_receipt_id"] if authority else None,
        "accepted_review_url": authority["accepted_review_url"] if authority else None,
        "authorized_actor": authority["authorized_actor"] if authority else None,
        "environment": authority["environment"] if authority else None,
        "reviewed_revision": authority["reviewed_revision"] if authority else None,
        "integrated_revision": authority["integrated_revision"] if authority else None,
        "reviewed_repository": authority["reviewed_repository"] if authority else None,
        "integrated_repository": authority["integrated_repository"] if authority else None,
        "installed_source_root": str(root),
        "installed_source_sha256": source_fingerprint(root),
        "workspace_root": str(Path(workspace_root).resolve()),
        "python_executable": str(Path(sys.executable).resolve()),
        "worker_pid": pid,
        "process_start_id": _process_start_id(pid),
        "capability_generation": capability_generation,
        "loaded_modules": _loaded_module_closure(root),
        "started_at": started_at,
    }
    return result


def validate_loaded_runtime_identity(
    identity: object,
    *,
    authority: RuntimeAuthority | None,
    worker_pid: int,
    expected_workspace_root: Path,
    expected_capability_generation: str,
    observed_at: str,
) -> LoadedRuntimeIdentity:
    """Independently inspect the live child and bind its imported-source report."""

    required = {
        "verified", "reason", "authority_manifest_id", "deployment_receipt_id",
        "accepted_review_url", "authorized_actor", "environment",
        "reviewed_revision", "integrated_revision", "reviewed_repository",
        "integrated_repository", "installed_source_root",
        "installed_source_sha256", "workspace_root", "python_executable", "worker_pid",
        "process_start_id", "capability_generation", "loaded_modules", "started_at",
    }
    if not isinstance(identity, dict) or not required.issubset(identity):
        raise WorkspaceError("worker readiness omitted loaded runtime identity")
    if identity.get("verified") is not False:
        raise WorkspaceError("worker attempted to self-assert verified runtime evidence")
    if identity.get("worker_pid") != worker_pid:
        raise WorkspaceError("worker readiness PID does not match spawned process")
    process = _inspect_process(worker_pid)
    if identity.get("process_start_id") != process["start_id"]:
        raise WorkspaceError("worker process-start identity is stale or conflicting")
    if identity.get("python_executable") != process["executable"]:
        raise WorkspaceError("worker executable does not match host process evidence")
    if identity.get("workspace_root") != str(Path(expected_workspace_root).resolve()):
        raise WorkspaceError("worker readiness names a different workspace root")
    if identity.get("capability_generation") != expected_capability_generation:
        raise WorkspaceError("worker capability generation conflicts with launcher evidence")

    root = installed_source_root()
    if identity.get("installed_source_root") != str(root):
        raise WorkspaceError("worker imported Cascade from an unexpected root")
    if process["import_root"] != str(root.parent):
        raise WorkspaceError("worker process selected an unexpected import root")
    measured = source_fingerprint(root)
    if identity.get("installed_source_sha256") != measured:
        raise WorkspaceError("worker source changed during startup")
    _verify_loaded_module_closure(identity.get("loaded_modules"), root)

    result = dict(identity)
    if authority is None:
        if identity.get("reason") != "runtime_authority_missing":
            raise WorkspaceError("worker reported conflicting missing-authority evidence")
    else:
        expected = {
            "authority_manifest_id": authority["manifest_id"],
            "deployment_receipt_id": authority["deployment_receipt_id"],
            "accepted_review_url": authority["accepted_review_url"],
            "authorized_actor": authority["authorized_actor"],
            "environment": authority["environment"],
            "reviewed_revision": authority["reviewed_revision"],
            "integrated_revision": authority["integrated_revision"],
            "reviewed_repository": authority["reviewed_repository"],
            "integrated_repository": authority["integrated_repository"],
            "installed_source_root": authority["installed_source_root"],
            "installed_source_sha256": authority["installed_source_sha256"],
        }
        if any(identity.get(key) != value for key, value in expected.items()):
            raise WorkspaceError("worker loaded runtime does not match deployment authority")
        result["verified"] = True
        result["reason"] = None
    result["host_verified_at"] = observed_at
    result["host_boot_id"] = process["boot_id"]
    result["host_process_start_id"] = process["start_id"]
    return result  # type: ignore[return-value]


def verify_loaded_runtime_identity(
    identity: object,
    *,
    authority: RuntimeAuthority | None,
    worker_pid: int,
    expected_workspace_root: Path,
    expected_capability_generation: str,
    observed_at: str,
) -> RuntimeVerificationResult:
    """Return a typed host verdict without turning refusal into success state."""

    try:
        checked = validate_loaded_runtime_identity(
            identity,
            authority=authority,
            worker_pid=worker_pid,
            expected_workspace_root=expected_workspace_root,
            expected_capability_generation=expected_capability_generation,
            observed_at=observed_at,
        )
    except WorkspaceError as exc:
        return {"state": "refused", "reason": str(exc), "identity": None}
    if authority is None:
        return {
            "state": "pending",
            "reason": "authorized deployment receipt and trust key are required",
            "identity": checked,
        }
    return {"state": "current", "reason": None, "identity": checked}


def verify_current_loaded_runtime_identity(
    identity: object,
    *,
    expected_workspace_root: Path,
    expected_capability_generation: str,
) -> RuntimeVerificationResult:
    """Reinspect a launcher's verified receipt before an obligation closes.

    The launcher is the only component that can turn the worker's startup
    report into verified evidence.  A later postcheck still has to prove that
    the named process and source lineage remain current; a persisted status
    payload alone is not sufficient after a crash, restart, or checkout edit.
    """

    if not isinstance(identity, dict):
        return {
            "state": "pending",
            "reason": "loaded runtime evidence is unavailable",
            "identity": None,
        }
    try:
        if identity.get("verified") is not True or identity.get("reason") is not None:
            raise WorkspaceError("loaded runtime evidence is not host verified")
        required_authority = (
            "authority_manifest_id",
            "deployment_receipt_id",
            "accepted_review_url",
            "authorized_actor",
            "environment",
            "reviewed_repository",
            "reviewed_revision",
            "integrated_repository",
            "integrated_revision",
        )
        if any(not isinstance(identity.get(name), str) or not identity[name] for name in required_authority):
            raise WorkspaceError("loaded runtime deployment authority is incomplete")
        if identity.get("workspace_root") != str(Path(expected_workspace_root).resolve()):
            raise WorkspaceError("loaded runtime names a different workspace root")
        if identity.get("capability_generation") != expected_capability_generation:
            raise WorkspaceError("loaded runtime capability generation is stale")

        pid = identity.get("worker_pid")
        if type(pid) is not int or pid <= 0:
            raise WorkspaceError("loaded runtime worker PID is invalid")
        process = _inspect_process(pid)
        process_start = identity.get("process_start_id")
        if (
            process_start != process["start_id"]
            or identity.get("host_process_start_id") != process["start_id"]
            or identity.get("host_boot_id") != process["boot_id"]
        ):
            raise WorkspaceError("loaded runtime process-start identity is stale")
        if identity.get("python_executable") != process["executable"]:
            raise WorkspaceError("loaded runtime executable no longer matches the process")

        installed_root_value = identity.get("installed_source_root")
        if not isinstance(installed_root_value, str):
            raise WorkspaceError("loaded runtime installed source root is invalid")
        installed_root = Path(installed_root_value).resolve()
        if process["import_root"] != str(installed_root.parent):
            raise WorkspaceError("loaded runtime process selected a different import root")
        installed_digest = source_fingerprint(installed_root)
        if identity.get("installed_source_sha256") != installed_digest:
            raise WorkspaceError("loaded runtime installed source changed after startup")
        _verify_loaded_module_closure(identity.get("loaded_modules"), installed_root)

        reviewed = Path(str(identity["reviewed_repository"])).resolve()
        integrated = Path(str(identity["integrated_repository"])).resolve()
        reviewed_revision = str(identity["reviewed_revision"])
        integrated_revision = str(identity["integrated_revision"])
        _require_clean_exact_checkout(reviewed, reviewed_revision, "reviewed")
        _require_clean_exact_checkout(integrated, integrated_revision, "integrated")
        _require_commit(integrated, reviewed_revision, "accepted review revision")
        if not _is_ancestor(integrated, reviewed_revision, integrated_revision):
            raise WorkspaceError("accepted review is no longer in the integrated target")
        if source_fingerprint(reviewed / "cascade") != installed_digest:
            raise WorkspaceError("loaded runtime no longer matches accepted review source")
    except (OSError, WorkspaceError) as exc:
        return {"state": "refused", "reason": str(exc), "identity": None}
    return {
        "state": "current",
        "reason": None,
        "identity": identity,  # type: ignore[typeddict-item]
    }


def _loaded_module_closure(root: Path) -> dict[str, LoadedModule]:
    rows: dict[str, LoadedModule] = {}
    for module_name, callable_names in REQUIRED_RUNTIME_CALLABLES.items():
        module = importlib.import_module(module_name)
        missing = [name for name in callable_names if not callable(getattr(module, name, None))]
        if missing:
            raise WorkspaceError(f"runtime module {module_name} lacks callable targets: {', '.join(missing)}")
        origin = Path(str(getattr(module, "__file__", ""))).resolve()
        if not origin.is_relative_to(root) or origin.suffix != ".py":
            raise WorkspaceError(f"runtime module {module_name} loaded from unknown origin")
        rows[module_name] = {
            "origin": str(origin),
            "sha256": hashlib.sha256(origin.read_bytes()).hexdigest(),
            "callables": list(callable_names),
        }
    return rows


def _verify_loaded_module_closure(value: object, root: Path) -> None:
    if not isinstance(value, dict) or set(value) != set(REQUIRED_RUNTIME_CALLABLES):
        raise WorkspaceError("worker loaded-module closure is incomplete or mixed")
    for module_name, expected_callables in REQUIRED_RUNTIME_CALLABLES.items():
        row = value.get(module_name)
        if not isinstance(row, dict) or set(row) != {"origin", "sha256", "callables"}:
            raise WorkspaceError(f"worker module evidence is invalid: {module_name}")
        origin_value = row.get("origin")
        if not isinstance(origin_value, str):
            raise WorkspaceError(f"worker module origin is invalid: {module_name}")
        origin = Path(origin_value).resolve()
        expected = (root / Path(*module_name.split(".")[1:])).with_suffix(".py")
        if origin != expected or not origin.is_relative_to(root):
            raise WorkspaceError(f"worker module loaded from wrong root: {module_name}")
        try:
            digest = hashlib.sha256(origin.read_bytes()).hexdigest()
        except OSError as exc:
            raise WorkspaceError(f"worker module origin is unavailable: {module_name}") from exc
        if row.get("sha256") != digest:
            raise WorkspaceError(f"worker module changed during startup: {module_name}")
        if row.get("callables") != list(expected_callables):
            raise WorkspaceError(f"worker callable closure conflicts: {module_name}")


def _inspect_process(pid: int) -> dict[str, str]:
    boot_id, start_id = _read_process_start(pid)
    try:
        executable = str(Path(f"/proc/{pid}/exe").resolve())
        environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError as exc:
        raise WorkspaceError("host process identity is unavailable") from exc
    pythonpath = next((item.split(b"=", 1)[1] for item in environ if item.startswith(b"PYTHONPATH=")), b"").decode("utf-8")
    import_root = pythonpath.split(os.pathsep, 1)[0]
    if not import_root:
        raise WorkspaceError("host process import-root evidence is unavailable")
    return {
        "boot_id": boot_id,
        "start_id": start_id,
        "executable": executable,
        "import_root": str(Path(import_root).resolve()),
    }


def _process_start_id(pid: int) -> str:
    return _read_process_start(pid)[1]


def _read_process_start(pid: int) -> tuple[str, str]:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = stat.rfind(")")
        start_ticks = stat[close + 2 :].split()[19]
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except (OSError, IndexError) as exc:
        raise WorkspaceError("host process-start identity is unavailable") from exc
    return boot_id, f"linux:{boot_id}:{pid}:{start_ticks}"


def _load_signed_deployment_receipt(path: Path, key: bytes) -> dict[str, object]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"authorized deployment receipt is unavailable: {exc}") from exc
    fields = {
        "version", "receipt_id", "signature", "accepted_review_url", "authorized_actor",
        "environment", "reviewed_repository", "reviewed_revision", "integrated_repository",
        "integrated_revision", "installed_source_sha256",
    }
    if not isinstance(value, dict) or set(value) != fields or value.get("version") != _RECEIPT_VERSION:
        raise WorkspaceError("authorized deployment receipt has an invalid shape")
    for name in fields - {"version"}:
        if not isinstance(value.get(name), str) or not value[name]:
            raise WorkspaceError(f"authorized deployment receipt {name} is invalid")
    _require_revision(value["reviewed_revision"], "reviewed revision")
    _require_revision(value["integrated_revision"], "integrated revision")
    unsigned = dict(value)
    signature = unsigned.pop("signature")
    receipt_id = unsigned.pop("receipt_id")
    if receipt_id != _manifest_id(unsigned):
        raise WorkspaceError("authorized deployment receipt digest is invalid")
    if not hmac.compare_digest(signature, _signature({**unsigned, "receipt_id": receipt_id}, key)):
        raise WorkspaceError("authorized deployment receipt signature is invalid")
    return value


def _parse_authority(value: object) -> RuntimeAuthority:
    fields = set(RuntimeAuthority.__required_keys__)
    if not isinstance(value, dict) or set(value) != fields:
        raise WorkspaceError("runtime authority manifest has an invalid shape")
    if value.get("version") != _SCHEMA_VERSION:
        raise WorkspaceError("runtime authority manifest version is unsupported")
    for name in fields - {"version"}:
        if not isinstance(value.get(name), str) or not value[name]:
            raise WorkspaceError(f"runtime authority {name} is invalid")
    _require_revision(value["reviewed_revision"], "reviewed revision")
    _require_revision(value["integrated_revision"], "integrated revision")
    body = dict(value)
    body.pop("manifest_signature")
    manifest_id = body.pop("manifest_id")
    if manifest_id != _manifest_id(body):
        raise WorkspaceError("runtime authority manifest digest is invalid")
    return value  # type: ignore[return-value]


def _read_authority_key(path: Path) -> bytes:
    try:
        key = Path(path).read_bytes()
    except OSError as exc:
        raise WorkspaceError("authorized deployment key is unavailable; obtain it from the installation authority") from exc
    if len(key) < 32:
        raise WorkspaceError("authorized deployment key must contain at least 32 bytes")
    return key


def _require_clean_exact_checkout(repository: Path, revision: str, label: str) -> None:
    head = _git_text(repository, "rev-parse", "HEAD^{commit}")
    if head != revision:
        raise WorkspaceError(f"{label} checkout is stale: {head or 'unavailable'} != {revision}")
    if _git_text(repository, "status", "--porcelain", "--untracked-files=normal"):
        raise WorkspaceError(f"{label} checkout is dirty; runtime evidence refused")


def _require_revision(value: str, label: str) -> str:
    revision = str(value).lower()
    if len(revision) != _REVISION_LENGTH or any(c not in "0123456789abcdef" for c in revision):
        raise WorkspaceError(f"{label} must be a full Git commit SHA")
    return revision


def _require_commit(repository: Path, revision: str, label: str) -> None:
    result = subprocess.run(["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=repository, capture_output=True, check=False)
    if result.returncode != 0:
        raise WorkspaceError(f"{label} is unknown in the integrated repository")


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=repository, capture_output=True, check=False).returncode == 0


def _git_text(repository: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repository, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise WorkspaceError(f"source is not an inspectable Git checkout: {repository}")
    return result.stdout.strip()


def _manifest_id(body: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _signature(body: dict[str, object], key: bytes) -> str:
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def _atomic_write_json(path: Path, value: object) -> None:
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


__all__ = [
    "ENV_RUNTIME_AUTHORITY", "LoadedRuntimeIdentity", "RuntimeAuthority",
    "authority_from_environment", "create_runtime_authority", "encode_runtime_authority",
    "installed_source_root", "load_runtime_authority", "loaded_runtime_identity",
    "validate_loaded_runtime_identity", "validate_runtime_authority",
    "verify_current_loaded_runtime_identity", "verify_loaded_runtime_identity",
]
