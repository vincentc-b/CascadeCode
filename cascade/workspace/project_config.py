"""Project-level configuration shared by repository-role initialization.

This module deliberately only parses repository references.  Validating or
preparing the referenced checkout belongs to the repository resolver.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml

from cascade.workspace.errors import WorkspaceError


RepositoryReferenceKind = Literal["local", "remote"]

_CONFIG_NAMES = ("cascade.toml", "cascade.yaml", "cascade.yml")
_REMOTE_SCHEMES = frozenset({"git", "http", "https", "ssh"})
_SCP_REMOTE = re.compile(
    r"^(?:(?P<user>[^/@:\s]+)@)?(?P<host>[^/:\s]+):(?P<path>[^\s]+)$"
)


@dataclass(frozen=True)
class TrackingRepositoryReference:
    """A normalized tracking-repository reference from project config.

    Local values are absolute paths anchored to the configuration directory.
    Remote values retain the Git reference for a later resolver; they are never
    written back to configuration or included in parser diagnostics.
    """

    kind: RepositoryReferenceKind
    value: Path | str = field(repr=False)

    @property
    def local_path(self) -> Path | None:
        if self.kind == "local" and isinstance(self.value, Path):
            return self.value
        return None

    @property
    def remote_url(self) -> str | None:
        if self.kind == "remote" and isinstance(self.value, str):
            return self.value
        return None


def find_project_config(root: Path) -> Path:
    """Return the project config path, including the default for a new project.

    A project must not contain multiple supported config files because choosing
    one implicitly would make repository selection depend on precedence.
    """

    project_root = Path(root).resolve()
    found = [
        project_root / name
        for name in _CONFIG_NAMES
        if (project_root / name).is_file()
    ]
    if len(found) > 1:
        names = ", ".join(path.name for path in found)
        raise WorkspaceError(
            f"multiple Cascade project configuration files found ({names}); keep exactly one"
        )
    return found[0] if found else project_root / "cascade.toml"


def read_tracking_repository(
    config_path: Path,
) -> TrackingRepositoryReference | None:
    """Parse the optional top-level ``tracking_repository`` setting.

    TOML and YAML use the same scalar-string contract.  Missing files and an
    omitted key both select the backward-compatible colocated repository mode.
    """

    path = Path(config_path).resolve()
    if not path.exists():
        return None
    data = _load_project_config(path)
    if "tracking_repository" not in data:
        return None
    return parse_tracking_repository_reference(data["tracking_repository"], path)


def parse_tracking_repository_reference(
    value: object,
    config_path: Path,
) -> TrackingRepositoryReference:
    """Normalize a tracking reference without accessing the repository."""

    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError(
            "tracking_repository must be a non-blank local path or Git remote string"
        )

    reference = value.strip()
    try:
        parsed = urlsplit(reference)
        hostname = parsed.hostname
    except ValueError as exc:
        raise WorkspaceError(
            "tracking_repository is not a valid local path or Git remote"
        ) from exc
    if parsed.scheme:
        # A single-letter prefix is a Windows drive, not a URL scheme.  It is
        # accepted as a path on platforms where pathlib recognizes it.
        if (
            len(parsed.scheme) == 1
            and len(reference) >= 3
            and reference[1:3] in {":/", ":\\"}
        ):
            return _local_reference(reference, config_path)
        if parsed.scheme not in _REMOTE_SCHEMES:
            raise WorkspaceError(
                "tracking_repository uses an unsupported URL scheme; use a local path "
                "or a git, http, https, or ssh Git remote"
            )
        if not hostname or not parsed.path or parsed.path == "/":
            raise WorkspaceError(
                "tracking_repository remote is incomplete; provide a host and repository path"
            )
        if parsed.query or parsed.fragment:
            raise WorkspaceError(
                "tracking_repository remote must not contain a query string or fragment"
            )
        return TrackingRepositoryReference(kind="remote", value=reference)

    scp_match = _SCP_REMOTE.fullmatch(reference)
    if scp_match and (
        scp_match.group("user")
        or "/" in scp_match.group("path")
        or "." in scp_match.group("host")
    ):
        return TrackingRepositoryReference(kind="remote", value=reference)

    return _local_reference(reference, config_path)


def _local_reference(reference: str, config_path: Path) -> TrackingRepositoryReference:
    raw_path = Path(reference).expanduser()
    if not raw_path.is_absolute():
        raw_path = Path(config_path).resolve().parent / raw_path
    return TrackingRepositoryReference(kind="local", value=raw_path.resolve(strict=False))


def _load_project_config(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix == ".toml":
        try:
            with path.open("rb") as handle:
                loaded = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise WorkspaceError(f"invalid {path.name}: {exc}") from exc
    elif suffix in {".yaml", ".yml"}:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise WorkspaceError(f"invalid {path.name} project configuration") from exc
        if loaded is None:
            loaded = {}
    else:
        raise WorkspaceError(
            "unsupported project configuration format; use cascade.toml, "
            "cascade.yaml, or cascade.yml"
        )

    if not isinstance(loaded, dict):
        raise WorkspaceError(f"{path.name} project configuration root must be a mapping")
    return loaded
