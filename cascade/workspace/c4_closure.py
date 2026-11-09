"""Pinned, confined materialization for repository-owned C4 source."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Literal, Sequence

from cascade.workspace.architecture import ArchitectureArtifactRef
from cascade.workspace.c4_source import C4SourceError, C4WorkspaceContract, validate_c4_workspace
from cascade.workspace.types import ProjectContext, RepositoryContext

_INCLUDE = re.compile(r"^\s*!include\s+(.+?)\s*$", re.IGNORECASE)
_FORBIDDEN_DIRECTIVE = re.compile(
    r"^\s*(?:!(?:plugin|script|components|extend|export)\b|"
    r"workspace\s+extends\b|(?:export|exporter)\b)",
    re.IGNORECASE,
)
_REMOTE_RESOURCE = re.compile(
    r"^\s*(?:!include|themes?|assets?|icon|logo|image|plantuml|mermaid|kroki)\b.*"
    r"(?:[a-z][a-z0-9+.-]*:|//)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class C4SourceFile:
    """One regular file read from a pinned architecture revision."""

    path: Path
    repository_path: Path
    owner: str
    revision: str
    sha256: str


@dataclass(frozen=True)
class C4SourceClosure:
    """An immutable description of an isolated renderer input tree."""

    target_repository_key: str
    destination_repository_key: str
    destination_repository_role: Literal["target", "tracking"]
    code_directory: Path
    design_owner_directory: Path
    revision: str
    architecture_root: Path
    source: Path
    files: tuple[C4SourceFile, ...]
    digest: str
    input_directory: Path
    contract: C4WorkspaceContract


def materialize_c4_source_closure(
    project: ProjectContext,
    contract_reference: ArchitectureArtifactRef,
    source_references: Sequence[ArchitectureArtifactRef],
    destination: Path | str,
) -> C4SourceClosure:
    """Validate and copy an explicitly pinned C4 include closure.

    Every input is read from Git at the contract reference's revision.  The
    checkout is used only to locate the object database, so later working-tree
    edits and symlinks cannot change the renderer input.
    """

    destination_path = Path(destination).resolve()
    if destination_path.exists():
        raise C4SourceError(f"C4 input destination already exists: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    architecture_root = contract_reference.repository_path.parent
    if contract_reference.repository_path.name != "workspace.contract.json":
        raise C4SourceError("C4 contract reference must name workspace.contract.json")
    _require_architecture_root(contract_reference, architecture_root)

    references = (contract_reference, *tuple(source_references))
    _require_common_pin(contract_reference, references)
    by_repository_path: dict[Path, ArchitectureArtifactRef] = {}
    pinned_text: dict[Path, str] = {}
    pinned_bytes: dict[Path, bytes] = {}
    for reference in references:
        if reference.repository_path in by_repository_path:
            raise C4SourceError(
                f"duplicate pinned C4 artifact reference: {reference.repository_path}"
            )
        _require_architecture_root(reference, architecture_root)
        by_repository_path[reference.repository_path] = reference
        content = _read_regular_blob(project, reference)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise C4SourceError(
                f"C4 source is not UTF-8: {reference.repository_path}"
            ) from exc
        pinned_bytes[reference.repository_path] = content
        pinned_text[reference.repository_path] = text

    contract_payload = _contract_payload(pinned_text[contract_reference.repository_path])
    declared = _declared_sources(contract_payload)
    expected_paths = {
        architecture_root / relative for relative in declared
    }
    supplied_paths = set(by_repository_path) - {contract_reference.repository_path}
    if supplied_paths != expected_paths:
        missing = sorted(path.as_posix() for path in expected_paths - supplied_paths)
        extra = sorted(path.as_posix() for path in supplied_paths - expected_paths)
        raise C4SourceError(
            "pinned C4 references do not match the declared source closure; "
            f"missing={missing}, extra={extra}"
        )

    for relative, owner in declared.items():
        reference = by_repository_path[architecture_root / relative]
        if reference.owning_work != owner:
            raise C4SourceError(
                f"C4 owner mismatch for {relative.as_posix()}: "
                f"contract={owner!r}, reference={reference.owning_work!r}"
            )
    workspace_owner = contract_payload["workspace"]["owner"]
    if contract_reference.owning_work != workspace_owner:
        raise C4SourceError(
            "C4 contract owner does not match the pinned artifact reference"
        )

    source = _contract_source(contract_payload)
    include_graph = _validate_include_closure(
        architecture_root,
        source,
        expected_paths,
        pinned_text,
    )
    reachable = set(include_graph)
    if reachable != expected_paths:
        missing = sorted(path.as_posix() for path in expected_paths - reachable)
        raise C4SourceError(f"declared C4 fragments are not reachable: {missing}")

    entries = tuple(
        C4SourceFile(
            path=path.relative_to(architecture_root),
            repository_path=path,
            owner=(
                contract_reference.owning_work
                if path == contract_reference.repository_path
                else declared[path.relative_to(architecture_root)]
            ),
            revision=contract_reference.revision,
            sha256=hashlib.sha256(pinned_bytes[path]).hexdigest(),
        )
        for path in sorted(
            (contract_reference.repository_path, *expected_paths),
            key=lambda item: item.as_posix(),
        )
    )
    digest = _closure_digest(contract_reference, architecture_root, entries)

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination_path.name}.", dir=destination_path.parent)
    )
    try:
        for entry in entries:
            output = temporary / entry.path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(pinned_bytes[entry.repository_path])
        validated = validate_c4_workspace(temporary)
        os.replace(temporary, destination_path)
        validated = replace(validated, root=destination_path)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return C4SourceClosure(
        target_repository_key=contract_reference.target_repository_key,
        destination_repository_key=contract_reference.destination_repository_key,
        destination_repository_role=contract_reference.destination_repository_role,
        code_directory=contract_reference.code_directory,
        design_owner_directory=contract_reference.design_owner_directory,
        revision=contract_reference.revision,
        architecture_root=architecture_root,
        source=source,
        files=entries,
        digest=digest,
        input_directory=destination_path,
        contract=validated,
    )


def _require_common_pin(
    contract: ArchitectureArtifactRef,
    references: Sequence[ArchitectureArtifactRef],
) -> None:
    expected = (
        contract.target_repository_key,
        contract.destination_repository_key,
        contract.destination_repository_role,
        contract.revision,
        contract.code_directory,
        contract.design_owner_directory,
    )
    for reference in references:
        actual = (
            reference.target_repository_key,
            reference.destination_repository_key,
            reference.destination_repository_role,
            reference.revision,
            reference.code_directory,
            reference.design_owner_directory,
        )
        if actual != expected:
            raise C4SourceError(
                "C4 artifact references must share one revision, repository, and design owner"
            )


def _require_architecture_root(
    reference: ArchitectureArtifactRef, architecture_root: Path
) -> None:
    expected = Path("architecture") / reference.target_repository_key
    if architecture_root != expected:
        raise C4SourceError(
            "C4 artifacts must be confined to the selected target documentation tree"
        )
    try:
        reference.repository_path.relative_to(architecture_root)
    except ValueError as exc:
        raise C4SourceError("C4 artifact reference escapes its architecture root") from exc


def _repository(project: ProjectContext, reference: ArchitectureArtifactRef) -> RepositoryContext:
    repository = (
        project.target
        if reference.destination_repository_role == "target"
        else project.tracking
    )
    expected_key = (
        project.target_repository_key
        if reference.destination_repository_role == "target"
        else repository.repository_key
    )
    if reference.target_repository_key != project.target_repository_key:
        raise C4SourceError("C4 artifact reference belongs to another target")
    if reference.destination_repository_key != expected_key:
        raise C4SourceError("C4 artifact destination repository has changed")
    return repository


def _read_regular_blob(
    project: ProjectContext, reference: ArchitectureArtifactRef
) -> bytes:
    repository = _repository(project, reference)
    path = reference.repository_path.as_posix()
    tree = subprocess.run(
        ["git", "ls-tree", "-z", reference.revision, "--", path],
        cwd=repository.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if tree.returncode != 0 or not tree.stdout:
        raise C4SourceError(f"cannot read pinned C4 artifact {path} at {reference.revision}")
    header, separator, returned_path = tree.stdout.partition(b"\t")
    fields = header.split()
    if separator != b"\t" or returned_path.rstrip(b"\0").decode() != path or len(fields) != 3:
        raise C4SourceError(f"ambiguous pinned C4 artifact tree entry: {path}")
    mode, kind, _ = fields
    if mode != b"100644" or kind != b"blob":
        raise C4SourceError(
            f"pinned C4 artifact must be a non-executable regular file, not a symlink: {path}"
        )
    blob = subprocess.run(
        ["git", "show", f"{reference.revision}:{path}"],
        cwd=repository.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if blob.returncode != 0:
        raise C4SourceError(f"cannot read pinned C4 artifact {path} at {reference.revision}")
    return blob.stdout


def _contract_payload(text: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise C4SourceError("invalid pinned C4 workspace contract") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("workspace"), dict):
        raise C4SourceError("invalid pinned C4 workspace contract")
    return payload


def _contract_source(payload: dict) -> Path:
    raw = payload["workspace"].get("source")
    return _local_dsl_path(raw, "workspace.source")


def _declared_sources(payload: dict) -> dict[Path, str]:
    workspace = payload["workspace"]
    owner = workspace.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        raise C4SourceError("workspace.owner must be a nonempty string")
    rows = payload.get("fragments")
    if not isinstance(rows, list):
        raise C4SourceError("fragments must be a list")
    declared = {_contract_source(payload): owner}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise C4SourceError(f"fragments[{index}] must be an object")
        path = _local_dsl_path(row.get("path"), f"fragments[{index}].path")
        fragment_owner = row.get("owner")
        if not isinstance(fragment_owner, str) or not fragment_owner.strip():
            raise C4SourceError(f"fragments[{index}].owner must be a nonempty string")
        if path in declared:
            raise C4SourceError(f"duplicate C4 source path: {path.as_posix()}")
        declared[path] = fragment_owner
    return declared


def _local_dsl_path(raw: object, field: str) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise C4SourceError(f"{field} must be a normalized local .dsl path")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise C4SourceError(f"{field} escapes the C4 architecture root")
    if candidate.suffix.lower() != ".dsl":
        raise C4SourceError(f"{field} must name a local .dsl file")
    return Path(*candidate.parts)


def _validate_include_closure(
    architecture_root: Path,
    source: Path,
    expected_paths: set[Path],
    pinned_text: dict[Path, str],
) -> dict[Path, tuple[Path, ...]]:
    graph: dict[Path, tuple[Path, ...]] = {}
    active: list[Path] = []

    def visit(repository_path: Path) -> None:
        if repository_path in active:
            cycle = active[active.index(repository_path) :] + [repository_path]
            raise C4SourceError(
                "C4 include cycle is forbidden: "
                + " -> ".join(path.relative_to(architecture_root).as_posix() for path in cycle)
            )
        if repository_path in graph:
            return
        if repository_path not in expected_paths:
            raise C4SourceError(
                f"C4 include is not an explicitly pinned artifact: {repository_path}"
            )
        active.append(repository_path)
        includes: list[Path] = []
        for line_number, line in enumerate(pinned_text[repository_path].splitlines(), 1):
            if _FORBIDDEN_DIRECTIVE.match(line):
                raise C4SourceError(
                    f"executable or inherited C4 extension is forbidden at "
                    f"{repository_path}:{line_number}"
                )
            if _REMOTE_RESOURCE.match(line):
                raise C4SourceError(
                    f"remote C4 references are forbidden at {repository_path}:{line_number}"
                )
            match = _INCLUDE.match(line)
            if not match:
                continue
            raw = match.group(1).strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
                raw = raw[1:-1]
            relative_parent = repository_path.relative_to(architecture_root).parent
            target = architecture_root / _normalized_include_path(
                relative_parent, raw, repository_path, line_number
            )
            includes.append(target)
            visit(target)
        active.pop()
        graph[repository_path] = tuple(includes)

    visit(architecture_root / source)
    return graph


def _normalized_include_path(
    parent: Path, raw: str, source: Path, line_number: int
) -> Path:
    if not raw or "\\" in raw:
        raise C4SourceError(f"!include must name a local .dsl file at {source}:{line_number}")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or candidate.suffix.lower() != ".dsl":
        raise C4SourceError(f"!include must name a local .dsl file at {source}:{line_number}")
    normalized: list[str] = []
    for part in (*PurePosixPath(parent.as_posix()).parts, *candidate.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            if not normalized:
                raise C4SourceError(
                    f"C4 include escapes its architecture root at {source}:{line_number}"
                )
            normalized.pop()
        else:
            normalized.append(part)
    if not normalized:
        raise C4SourceError(
            f"C4 include escapes its architecture root at {source}:{line_number}"
        )
    return Path(*normalized)


def _closure_digest(
    contract: ArchitectureArtifactRef,
    architecture_root: Path,
    entries: tuple[C4SourceFile, ...],
) -> str:
    manifest = {
        "version": 1,
        "target_repository_key": contract.target_repository_key,
        "destination_repository_key": contract.destination_repository_key,
        "destination_repository_role": contract.destination_repository_role,
        "code_directory": contract.code_directory.as_posix(),
        "design_owner_directory": contract.design_owner_directory.as_posix(),
        "revision": contract.revision,
        "architecture_root": architecture_root.as_posix(),
        "files": [
            {
                "path": entry.path.as_posix(),
                "repository_path": entry.repository_path.as_posix(),
                "owner": entry.owner,
                "revision": entry.revision,
                "sha256": entry.sha256,
            }
            for entry in entries
        ],
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
