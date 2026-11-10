"""Pinned and confined Structurizr source materialization."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.workspace import (
    ArchitectureArtifactRef,
    C4SourceError,
    ProjectContext,
    materialize_c4_source_closure,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_VERSIONED_WORKSPACE = (
    _REPOSITORY_ROOT
    / "architecture"
    / "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
)


def test_materializes_only_pinned_closure_with_stable_provenance(
    tmp_path: Path,
) -> None:
    project, contract_ref, source_refs = _repository_with_workspace(tmp_path)

    # Neither an unreferenced file nor later working-tree bytes can enter the
    # isolated renderer input.
    root = project.editable_architecture_root
    root.joinpath("workspace.dsl").write_text("uncommitted replacement\n", encoding="utf-8")
    root.joinpath("unreferenced.dsl").write_text("workspace {}\n", encoding="utf-8")

    first = materialize_c4_source_closure(
        project, contract_ref, source_refs, tmp_path / "input-one"
    )
    second = materialize_c4_source_closure(
        project,
        contract_ref,
        tuple(reversed(source_refs)),
        tmp_path / "input-two",
    )

    assert first.digest == second.digest
    assert first.source == Path("workspace.dsl")
    assert first.destination_repository_role == "target"
    assert first.code_directory == Path(".")
    assert first.design_owner_directory == Path(".")
    assert {item.path.as_posix() for item in first.files} == {
        "workspace.contract.json",
        "workspace.dsl",
        "model.dsl",
        "views.dsl",
    }
    assert {item.owner for item in first.files} == {"task_034_007_002"}
    assert {item.revision for item in first.files} == {contract_ref.revision}
    assert first.input_directory.joinpath("workspace.dsl").read_text(encoding="utf-8").startswith(
        'workspace "Cascade"'
    )
    assert first.contract.root == first.input_directory
    assert not first.input_directory.joinpath("unreferenced.dsl").exists()


def test_rejects_traversal_and_include_cycles_before_materializing(
    tmp_path: Path,
) -> None:
    project, contract_ref, source_refs = _repository_with_workspace(
        tmp_path, workspace_include='!include "../outside.dsl"\n'
    )
    with pytest.raises(C4SourceError, match="escapes"):
        materialize_c4_source_closure(
            project, contract_ref, source_refs, tmp_path / "traversal-input"
        )
    assert not tmp_path.joinpath("traversal-input").exists()

    cycle_root = tmp_path / "cycle"
    project, contract_ref, source_refs = _repository_with_workspace(
        cycle_root, model_suffix='\n!include "workspace.dsl"\n'
    )
    with pytest.raises(C4SourceError, match="include cycle"):
        materialize_c4_source_closure(
            project, contract_ref, source_refs, cycle_root / "cycle-input"
        )


def test_rejects_pinned_symlinks_even_when_the_target_is_readable(
    tmp_path: Path,
) -> None:
    project, contract_ref, source_refs = _repository_with_workspace(tmp_path)
    root = project.editable_architecture_root
    model = root / "model.dsl"
    model.unlink()
    os.symlink("../../README.md", model)
    _git(project.target.root, "add", "-A")
    _git(project.target.root, "commit", "-m", "replace model with escaping symlink")
    revision = _git(project.target.root, "rev-parse", "HEAD")
    contract_ref = replace(contract_ref, revision=revision)
    source_refs = tuple(replace(reference, revision=revision) for reference in source_refs)

    with pytest.raises(C4SourceError, match="not a symlink"):
        materialize_c4_source_closure(
            project, contract_ref, source_refs, tmp_path / "symlink-input"
        )


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ('theme "https://example.test/theme.json"', "remote C4 references"),
        ('!plugin "unsafe.jar"', "executable or inherited"),
        ('!script "unsafe.groovy"', "executable or inherited"),
        ('!export "custom-command"', "executable or inherited"),
        ('workspace extends "base.dsl"', "executable or inherited"),
    ],
)
def test_rejects_remote_and_executable_extensions(
    tmp_path: Path, line: str, message: str
) -> None:
    project, contract_ref, source_refs = _repository_with_workspace(
        tmp_path, model_suffix=f"\n{line}\n"
    )

    with pytest.raises(C4SourceError, match=message):
        materialize_c4_source_closure(
            project, contract_ref, source_refs, tmp_path / "unsafe-input"
        )


def test_requires_every_declared_file_to_have_one_matching_pin_and_owner(
    tmp_path: Path,
) -> None:
    project, contract_ref, source_refs = _repository_with_workspace(tmp_path)

    with pytest.raises(C4SourceError, match="missing="):
        materialize_c4_source_closure(
            project, contract_ref, source_refs[:-1], tmp_path / "missing-input"
        )

    wrong_owner = tuple(
        replace(reference, owning_work="another-feature")
        if reference.repository_path.name == "model.dsl"
        else reference
        for reference in source_refs
    )
    with pytest.raises(C4SourceError, match="owner mismatch"):
        materialize_c4_source_closure(
            project, contract_ref, wrong_owner, tmp_path / "owner-input"
        )


def _repository_with_workspace(
    tmp_path: Path,
    *,
    workspace_include: str | None = None,
    model_suffix: str = "",
) -> tuple[ProjectContext, ArchitectureArtifactRef, tuple[ArchitectureArtifactRef, ...]]:
    repository = tmp_path / "repository"
    repository.mkdir(parents=True)
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test User")
    repository.joinpath("README.md").write_text("repository\n", encoding="utf-8")

    target_key = _VERSIONED_WORKSPACE.name
    architecture = repository / "architecture"
    shutil.copytree(_VERSIONED_WORKSPACE, architecture / target_key)
    shutil.copy2(_REPOSITORY_ROOT / "architecture" / "design-mappings.json", architecture)
    if workspace_include is not None:
        architecture.joinpath(target_key, "workspace.dsl").write_text(
            workspace_include, encoding="utf-8"
        )
    if model_suffix:
        model = architecture / target_key / "model.dsl"
        model.write_text(model.read_text(encoding="utf-8") + model_suffix, encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "add C4 workspace")

    project = ProjectContext.colocated(repository)
    revision = _git(repository, "rev-parse", "HEAD")
    root = Path("architecture") / target_key

    def reference(name: str) -> ArchitectureArtifactRef:
        return ArchitectureArtifactRef(
            target_repository_key=target_key,
            code_directory=Path("."),
            design_owner_directory=Path("."),
            owning_work="task_034_007_002",
            destination_repository_key=target_key,
            destination_repository_role="target",
            repository_path=root / name,
            revision=revision,
        )

    return (
        project,
        reference("workspace.contract.json"),
        (reference("workspace.dsl"), reference("model.dsl"), reference("views.dsl")),
    )


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
