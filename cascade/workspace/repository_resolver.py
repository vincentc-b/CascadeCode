"""Validate and prepare configured tracking-repository checkouts."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

from cascade.workspace.errors import WorkspaceError
from cascade.workspace.project_config import TrackingRepositoryReference
from cascade.workspace.types import RepositoryContext


_SCP_REMOTE = re.compile(
    r"^(?:(?P<user>[^/@:\s]+)@)?(?P<host>[^/:\s]+):(?P<path>[^\s]+)$"
)
_AUTH_FAILURE_MARKERS = (
    "authentication failed",
    "could not read username",
    "permission denied",
    "publickey",
    "repository not found",
    "access denied",
)


def prepare_tracking_repository(
    reference: TrackingRepositoryReference,
    managed_data_root: Path,
) -> RepositoryContext:
    """Return a validated local checkout, cloning a remote only when absent.

    Remote repositories live below the caller's existing managed-data root.  An
    existing checkout is never fetched or otherwise changed: it is accepted
    only when it is complete and its ``origin`` identifies the requested
    repository.
    """

    if reference.kind == "local":
        path = reference.local_path
        if path is None:
            raise WorkspaceError("tracking_repository local reference is invalid")
        checkout = path.resolve(strict=False)
        _validate_checkout(checkout, label=str(checkout))
        return RepositoryContext(root=checkout, display_identity=str(checkout))

    remote = reference.remote_url
    if reference.kind != "remote" or remote is None:
        raise WorkspaceError("tracking_repository reference kind is unsupported")

    identity = _credential_stripped_identity(remote)
    checkout = _remote_checkout_path(identity, managed_data_root)
    if checkout.exists():
        if not checkout.is_dir():
            raise WorkspaceError(
                f"managed tracking checkout path is not a directory for {identity}; "
                f"move or remove {checkout} and retry"
            )
        _validate_checkout(checkout, label=identity, managed=True)
        _validate_origin(checkout, identity)
        return RepositoryContext(root=checkout, display_identity=identity)

    checkout.parent.mkdir(parents=True, exist_ok=True)
    result = _git_clone(remote, checkout)
    if result.returncode != 0:
        detail = f"{result.stderr}\n{result.stdout}".lower()
        if any(marker in detail for marker in _AUTH_FAILURE_MARKERS):
            raise WorkspaceError(
                f"authentication failed while cloning tracking repository {identity}; "
                "verify the configured Git credentials or SSH access and retry"
            )
        raise WorkspaceError(
            f"failed to clone tracking repository {identity}; verify that the remote is "
            "reachable and cloneable, then retry"
        )

    # Git normally removes a failed clone, but only validation establishes the
    # prepared-result boundary (including for unusual helpers or filesystems).
    _validate_checkout(checkout, label=identity, managed=True)
    _validate_origin(checkout, identity)
    return RepositoryContext(root=checkout, display_identity=identity)


def _validate_checkout(path: Path, *, label: str, managed: bool = False) -> None:
    if not path.exists():
        raise WorkspaceError(f"tracking repository path does not exist: {label}")
    if not path.is_dir():
        raise WorkspaceError(f"tracking repository path is not a directory: {label}")

    inside = _git(path, "rev-parse", "--is-inside-work-tree")
    top = _git(path, "rev-parse", "--show-toplevel")
    if inside.returncode != 0 or inside.stdout.strip() != "true" or top.returncode != 0:
        qualifier = "managed tracking checkout" if managed else "tracking repository path"
        recovery = f"; move or remove {path} and retry" if managed else ""
        raise WorkspaceError(
            f"{qualifier} is not a usable Git checkout: {label}{recovery}"
        )
    try:
        actual_root = Path(top.stdout.strip()).resolve(strict=True)
        expected_root = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceError(f"tracking repository checkout cannot be resolved: {label}") from exc
    if actual_root != expected_root:
        raise WorkspaceError(
            f"tracking repository path must name the Git checkout root: {label}"
        )


def _validate_origin(checkout: Path, identity: str) -> None:
    origin = _git(checkout, "config", "--get", "remote.origin.url")
    if origin.returncode != 0 or not origin.stdout.strip():
        raise WorkspaceError(
            f"managed tracking checkout for {identity} is incomplete (origin is missing); "
            f"move or remove {checkout} and retry"
        )
    try:
        origin_identity = _credential_stripped_identity(origin.stdout.strip())
    except WorkspaceError:
        origin_identity = ""
    if origin_identity != identity:
        raise WorkspaceError(
            f"managed tracking checkout origin does not match {identity}; "
            f"move or remove {checkout} and retry"
        )


def _remote_checkout_path(identity: str, managed_data_root: Path) -> Path:
    parsed = urlsplit(identity)
    name = Path(parsed.path.rstrip("/")).name.removesuffix(".git") or "repository"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "repository"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return (
        Path(managed_data_root).resolve(strict=False)
        / "tracking-repositories"
        / f"{slug[:40]}-{digest}"
    )


def _credential_stripped_identity(remote: str) -> str:
    """Return a stable, redacted identity without provider-specific guessing."""

    scp = _SCP_REMOTE.fullmatch(remote)
    if scp and "://" not in remote:
        host = scp.group("host").lower()
        path = "/" + scp.group("path").lstrip("/").rstrip("/")
        if not host or path == "/":
            raise WorkspaceError("tracking_repository remote identity is invalid")
        return urlunsplit(("ssh", host, path, "", ""))

    try:
        parsed = urlsplit(remote)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise WorkspaceError("tracking_repository remote identity is invalid") from exc
    if not parsed.scheme or not host or not parsed.path or parsed.path == "/":
        raise WorkspaceError("tracking_repository remote identity is invalid")
    hostname = host.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    normalized = SplitResult(
        parsed.scheme.lower(), netloc, parsed.path.rstrip("/"), "", ""
    )
    return urlunsplit(normalized)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git_clone(remote: str, checkout: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", "clone", "--", remote, str(checkout)],
        cwd=checkout.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
